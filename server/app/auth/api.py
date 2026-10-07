"""auth: HTTP layer: request and response handling only (plan 4.2).

Endpoints of spec 9.2 (auth rows built in T06) and `require_session`, the dependency every
signed-in endpoint uses. The session cookie is `lo_session` (9.1): HttpOnly, Secure, SameSite=Lax,
Path=/.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from http.cookies import SimpleCookie
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.schemas import (
    InviteCheck,
    InviteStatus,
    PasskeyVerify,
    Recovered,
    RecoverySignIn,
    Registered,
    Registration,
    RegistrationVerify,
    SignedIn,
    SignInOptions,
    SignInVerify,
    WebAuthnOptions,
)
from app.auth.service import AuthError, AuthService, NewSession, NotSignedIn, SessionContext
from app.platform.clock import utc_now

__all__ = ["SessionContext", "require_session", "router"]

COOKIE = "lo_session"
UNAUTHORISED: dict[int | str, dict[str, Any]] = {
    401: {"description": "Not signed in, or the session has ended."}
}


def no_store(response: Response) -> None:
    """Auth responses carry recovery codes and session cookies: never cached (AUTH-4)."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(no_store)])


def get_service(request: Request) -> AuthService:
    service: AuthService = request.app.state.auth
    return service


Service = Annotated[AuthService, Depends(get_service)]
Now = Annotated[datetime, Depends(utc_now)]


@contextmanager
def problems() -> Iterator[None]:
    try:
        yield
    except AuthError as error:
        raise HTTPException(error.status, error.detail) from None


def _cookie_header(value: str, max_age: int) -> str:
    cookie: SimpleCookie = SimpleCookie()
    cookie[COOKIE] = value
    morsel = cookie[COOKIE]
    morsel["max-age"] = max_age
    morsel["path"] = "/"
    morsel["secure"] = True
    morsel["httponly"] = True
    morsel["samesite"] = "Lax"
    return morsel.OutputString()


def set_session_cookie(response: Response, session: NewSession) -> None:
    response.headers.append("set-cookie", _cookie_header(session.token, session.max_age))


def clear_session_cookie(response: Response) -> None:
    response.headers.append("set-cookie", _cookie_header("", 0))


async def end_previous_session(request: Request, service: AuthService, now: datetime) -> None:
    """A new sign-in on this browser ends the session its cookie still names (12.3)."""
    token = request.cookies.get(COOKIE)
    if token:
        await service.sign_out(token, now)


async def require_session(
    request: Request, response: Response, service: Service, now: Now
) -> SessionContext:
    """The signed-in user's session, or 401. Slides the session's expiry (AUTH-5)."""
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(NotSignedIn.status, NotSignedIn.detail)
    with problems():
        context, refreshed = await service.authenticate(token, now)
    if refreshed is not None:
        set_session_cookie(response, refreshed)
    return context


@router.post("/invites/verify", response_model_exclude_none=True)
async def verify_invite(body: InviteCheck, service: Service, now: Now) -> InviteStatus:
    invite = await service.check_invite(body.token, now)
    return InviteStatus(valid=invite is not None, email=invite.email if invite else None)


@router.post(
    "/register/options",
    responses={
        403: {"description": "The invite is not valid."},
        409: {"description": "The email address already has an account."},
    },
)
async def registration_options(body: Registration, service: Service, now: Now) -> WebAuthnOptions:
    with problems():
        return WebAuthnOptions(**await service.registration_options(body, now))


@router.post(
    "/register/verify",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "The passkey could not be verified."},
        403: {"description": "The invite is not valid."},
        409: {"description": "The email address already has an account."},
    },
)
async def register(
    body: RegistrationVerify, request: Request, response: Response, service: Service, now: Now
) -> Registered:
    data = Registration(token=body.token, name=body.name, email=body.email)
    with problems():
        registered, session = await service.register(data, body.credential, now)
    await end_previous_session(request, service, now)
    set_session_cookie(response, session)
    return registered


@router.post("/signin/options")
async def signin_options(_body: SignInOptions, service: Service, now: Now) -> WebAuthnOptions:
    return WebAuthnOptions(**await service.signin_options(now))


@router.post("/signin/verify", responses=UNAUTHORISED)
async def sign_in(
    body: SignInVerify, request: Request, response: Response, service: Service, now: Now
) -> SignedIn:
    with problems():
        signed_in, session = await service.sign_in(body.credential, now)
    await end_previous_session(request, service, now)
    set_session_cookie(response, session)
    return signed_in


@router.post("/signin/recovery", responses=UNAUTHORISED)
async def recovery_sign_in(body: RecoverySignIn, service: Service, now: Now) -> Recovered:
    """Spends the code and returns passkey creation options; no session until the new passkey
    is verified at /auth/passkeys/verify (CR-013)."""
    with problems():
        options = await service.recover(body.email, body.code, now)
    return Recovered(options=WebAuthnOptions(**options))


@router.post(
    "/passkeys/verify",
    status_code=status.HTTP_201_CREATED,
    responses={400: {"description": "The passkey could not be verified."}},
)
async def add_passkey(
    body: PasskeyVerify, request: Request, response: Response, service: Service, now: Now
) -> SignedIn:
    """Add a passkey. T06 builds the recovery path (the challenge from /auth/signin/recovery
    names the account, CR-013); T08 adds the signed-in path."""
    with problems():
        signed_in, session = await service.add_recovery_passkey(body.credential, now)
    await end_previous_session(request, service, now)
    set_session_cookie(response, session)
    return signed_in


@router.post("/signout", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(request: Request, service: Service, now: Now) -> Response:
    token = request.cookies.get(COOKIE)
    if token:
        await service.sign_out(token, now)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    no_store(response)
    clear_session_cookie(response)
    return response
