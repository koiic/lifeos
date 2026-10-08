"""auth: HTTP layer: request and response handling only (plan 4.2).

Endpoints of spec 9.2 (auth rows built in T06 and T07) and `require_session`, the dependency
every signed-in endpoint uses. The session cookie is `lo_session` (9.1): HttpOnly, Secure,
SameSite=Lax, Path=/. Sign-in attempts are rate-limited per account and IP (AUTH-7, in the
service); signed-in endpoints are limited to 300 requests/min per session (9.1).
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
    PasswordRegistered,
    PasswordRegistration,
    PasswordSignIn,
    Recovered,
    RecoverySignIn,
    Registered,
    Registration,
    RegistrationVerify,
    SignedIn,
    SignInOptions,
    SignInVerify,
    TotpConfirm,
    TotpConfirmed,
    WebAuthnOptions,
)
from app.auth.service import (
    AuthError,
    AuthService,
    NewSession,
    NotSignedIn,
    SessionContext,
)
from app.platform.client_ip import client_ip_hash
from app.platform.clock import utc_now

__all__ = ["SessionContext", "require_session", "router"]

COOKIE = "lo_session"
UNAUTHORISED: dict[int | str, dict[str, Any]] = {
    401: {"description": "Not signed in, or the session has ended."}
}
LOCKED: dict[int | str, dict[str, Any]] = {
    429: {"description": "Too many failed sign-ins (AUTH-7); see Retry-After."}
}
SIGN_IN_ERRORS = UNAUTHORISED | LOCKED
# 9.1: "all others 300 requests/min per session" (CR-016: counted in Postgres, shared by workers).


def no_store(response: Response) -> None:
    """Auth responses carry recovery codes and session cookies: never cached (AUTH-4)."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(no_store)])


def get_service(request: Request) -> AuthService:
    service: AuthService = request.app.state.auth
    return service


Service = Annotated[AuthService, Depends(get_service)]
Now = Annotated[datetime, Depends(utc_now)]
IpHash = Annotated[bytes, Depends(client_ip_hash)]


@contextmanager
def problems() -> Iterator[None]:
    try:
        yield
    except AuthError as error:
        headers = None if error.retry_after is None else {"Retry-After": str(error.retry_after)}
        raise HTTPException(error.status, error.detail, headers=headers) from None


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


async def end_previous_session(
    request: Request, service: AuthService, now: datetime, ip_hash: bytes
) -> None:
    """A new sign-in on this browser ends the session its cookie still names (12.3)."""
    token = request.cookies.get(COOKIE)
    if token:
        await service.sign_out(token, now, ip_hash)


async def _session(
    request: Request,
    response: Response,
    service: AuthService,
    now: datetime,
    *,
    inactive: bool,
    count: bool,
) -> SessionContext:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(NotSignedIn.status, NotSignedIn.detail)
    with problems():
        context, refreshed = await service.authenticate(
            token, now, allow_inactive=inactive, count_request=count
        )
    if refreshed is not None:
        set_session_cookie(response, refreshed)
    return context


async def require_session(
    request: Request, response: Response, service: Service, now: Now
) -> SessionContext:
    """The signed-in user's session, or 401 (403 before a password account is activated,
    CR-014). Slides the session's expiry (AUTH-5) and limits it to 300 requests/min (9.1)."""
    return await _session(request, response, service, now, inactive=False, count=True)


async def require_any_session(
    request: Request, response: Response, service: Service, now: Now
) -> SessionContext:
    """A session, activated or not: only for `/auth/totp/confirm` (CR-014)."""
    return await _session(request, response, service, now, inactive=True, count=False)


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
    body: RegistrationVerify,
    request: Request,
    response: Response,
    service: Service,
    now: Now,
    ip_hash: IpHash,
) -> Registered:
    data = Registration(token=body.token, name=body.name, email=body.email)
    with problems():
        registered, session = await service.register(data, body.credential, now, ip_hash)
    await end_previous_session(request, service, now, ip_hash)
    set_session_cookie(response, session)
    return registered


@router.post("/signin/options")
async def signin_options(_body: SignInOptions, service: Service, now: Now) -> WebAuthnOptions:
    return WebAuthnOptions(**await service.signin_options(now))


@router.post("/signin/verify", responses=SIGN_IN_ERRORS)
async def sign_in(
    body: SignInVerify,
    request: Request,
    response: Response,
    service: Service,
    now: Now,
    ip_hash: IpHash,
) -> SignedIn:
    with problems():
        signed_in, session = await service.sign_in(body.credential, now, ip_hash)
    await end_previous_session(request, service, now, ip_hash)
    set_session_cookie(response, session)
    return signed_in


@router.post("/signin/recovery", responses=SIGN_IN_ERRORS)
async def recovery_sign_in(
    body: RecoverySignIn, service: Service, now: Now, ip_hash: IpHash
) -> Recovered:
    """Spends the code and returns passkey creation options; no session until the new passkey
    is verified at /auth/passkeys/verify (CR-013)."""
    with problems():
        options = await service.recover(body.email, body.code, now, ip_hash)
    return Recovered(options=WebAuthnOptions(**options))


@router.post(
    "/passkeys/verify",
    status_code=status.HTTP_201_CREATED,
    responses={400: {"description": "The passkey could not be verified."}},
)
async def add_passkey(
    body: PasskeyVerify,
    request: Request,
    response: Response,
    service: Service,
    now: Now,
    ip_hash: IpHash,
) -> SignedIn:
    """Add a passkey. T06 builds the recovery path (the challenge from /auth/signin/recovery
    names the account, CR-013); T08 adds the signed-in path."""
    with problems():
        signed_in, session = await service.add_recovery_passkey(body.credential, now, ip_hash)
    await end_previous_session(request, service, now, ip_hash)
    set_session_cookie(response, session)
    return signed_in


@router.post("/signout", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(request: Request, service: Service, now: Now, ip_hash: IpHash) -> Response:
    token = request.cookies.get(COOKIE)
    if token:
        await service.sign_out(token, now, ip_hash)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    no_store(response)
    clear_session_cookie(response)
    return response


# ---------- password + TOTP fallback (AUTH-3, CR-014) ----------


@router.post(
    "/register/password",
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "The invite is not valid."},
        409: {"description": "The email address already has an account."},
    },
)
async def register_password(
    body: PasswordRegistration,
    request: Request,
    response: Response,
    service: Service,
    now: Now,
    ip_hash: IpHash,
) -> PasswordRegistered:
    """Creates the account, inactive until `/auth/totp/confirm`; its session can only confirm."""
    with problems():
        registered, session = await service.register_password(body, now, ip_hash)
    await end_previous_session(request, service, now, ip_hash)
    set_session_cookie(response, session)
    return registered


@router.post(
    "/totp/confirm",
    responses=SIGN_IN_ERRORS
    | {409: {"description": "The authenticator app is already confirmed."}},
)
async def confirm_totp(
    body: TotpConfirm,
    session: Annotated[SessionContext, Depends(require_any_session)],
    service: Service,
    now: Now,
    ip_hash: IpHash,
) -> TotpConfirmed:
    """Activates the account; returns the recovery codes once."""
    with problems():
        codes = await service.confirm_totp(session, body.code, now, ip_hash)
    return TotpConfirmed(recovery_codes=codes)


@router.post("/signin/password", responses=SIGN_IN_ERRORS)
async def sign_in_password(
    body: PasswordSignIn,
    request: Request,
    response: Response,
    service: Service,
    now: Now,
    ip_hash: IpHash,
) -> SignedIn:
    with problems():
        signed_in, session = await service.sign_in_password(
            body.email, body.password, body.totp, now, ip_hash
        )
    await end_previous_session(request, service, now, ip_hash)
    set_session_cookie(response, session)
    return signed_in
