"""auth: HTTP layer: request and response handling only (plan 4.2).

Endpoints of spec 9.2 (auth rows built in T06 and T07) and `require_session`, the dependency
every signed-in endpoint uses. The session cookie is `lo_session` (9.1): HttpOnly, Secure,
SameSite=Lax, Path=/. Sign-in attempts are rate-limited per account and IP (AUTH-7, in the
service); signed-in endpoints are limited to 300 requests/min per session (9.1).
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from http.cookies import SimpleCookie
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.device import device_label
from app.auth.schemas import (
    AppLockSettings,
    InviteCheck,
    InviteStatus,
    PasskeyList,
    PasskeyOut,
    PasskeyVerify,
    PasswordRegistered,
    PasswordRegistration,
    PasswordSignIn,
    PinUnlock,
    ReauthOptionsRequest,
    ReauthVerify,
    Recovered,
    RecoverOptions,
    RecoverVerify,
    RecoveryCodes,
    RecoverySignIn,
    Registered,
    Registration,
    RegistrationVerify,
    SessionList,
    SessionOut,
    SignedIn,
    SignInOptions,
    SignInVerify,
    TotpConfirm,
    TotpConfirmed,
    WebAuthnOptions,
)
from app.auth.service import (
    AccountService,
    AuthError,
    AuthService,
    ClientInfo,
    NewSession,
    NotSignedIn,
    PinLockedOut,
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


def client_info(request: Request) -> ClientInfo:
    """The client IP's HMAC and a device label from the user agent (for sessions and events)."""
    return ClientInfo(
        ip_hash=client_ip_hash(request),
        device_label=device_label(request.headers.get("user-agent")),
    )


Client = Annotated[ClientInfo, Depends(client_info)]


def get_account(request: Request) -> AccountService:
    account: AccountService = request.app.state.account
    return account


Account = Annotated[AccountService, Depends(get_account)]


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
    client: Client,
) -> Registered:
    data = Registration(token=body.token, name=body.name, email=body.email)
    with problems():
        registered, session = await service.register(data, body.credential, now, client)
    await end_previous_session(request, service, now, client.ip_hash)
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
    client: Client,
) -> SignedIn:
    with problems():
        signed_in, session = await service.sign_in(body.credential, now, client)
    await end_previous_session(request, service, now, client.ip_hash)
    set_session_cookie(response, session)
    return signed_in


@router.post("/signin/recovery", responses=SIGN_IN_ERRORS)
async def recovery_sign_in(
    body: RecoverySignIn, service: Service, now: Now, client: Client
) -> Recovered:
    """Spends the code and returns passkey creation options; no session until the new passkey
    is verified at /auth/passkeys/verify (CR-013)."""
    with problems():
        options = await service.recover(body.email, body.code, now, client)
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
    account: Account,
    now: Now,
    client: Client,
) -> SignedIn:
    """Add a passkey. Signed in: to this account, for a challenge from `/auth/passkeys/options`
    (no new session). Not signed in: the recovery-code path (CR-013) — the challenge from
    `/auth/signin/recovery` names the account, and the session starts here."""
    current = await _optional_session(request, response, service, now)
    if current is not None:
        with problems():
            return await account.add_passkey(current, body.credential, now, client)
    with problems():
        signed_in, session = await service.add_recovery_passkey(body.credential, now, client)
    await end_previous_session(request, service, now, client.ip_hash)
    set_session_cookie(response, session)
    return signed_in


async def _optional_session(
    request: Request, response: Response, service: AuthService, now: datetime
) -> SessionContext | None:
    """The signed-in session if the cookie names a usable one (counted against the 9.1 limit and
    slid like any signed-in request), else None."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        context, refreshed = await service.authenticate(token, now, count_request=True)
    except NotSignedIn:
        return None  # no usable session: the cookie-less recovery-code path
    except AuthError as error:  # over the 9.1 limit, or not activated: refused, never bypassed
        headers = None if error.retry_after is None else {"Retry-After": str(error.retry_after)}
        raise HTTPException(error.status, error.detail, headers=headers) from None
    if refreshed is not None:
        set_session_cookie(response, refreshed)
    return context


@router.post("/signout", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(request: Request, service: Service, now: Now, client: Client) -> Response:
    token = request.cookies.get(COOKIE)
    if token:
        await service.sign_out(token, now, client.ip_hash)
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
    client: Client,
) -> PasswordRegistered:
    """Creates the account, inactive until `/auth/totp/confirm`; its session can only confirm."""
    with problems():
        registered, session = await service.register_password(body, now, client)
    await end_previous_session(request, service, now, client.ip_hash)
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
    client: Client,
) -> TotpConfirmed:
    """Activates the account; returns the recovery codes once."""
    with problems():
        codes = await service.confirm_totp(session, body.code, now, client)
    return TotpConfirmed(recovery_codes=codes)


@router.post("/signin/password", responses=SIGN_IN_ERRORS)
async def sign_in_password(
    body: PasswordSignIn,
    request: Request,
    response: Response,
    service: Service,
    now: Now,
    client: Client,
) -> SignedIn:
    with problems():
        signed_in, session = await service.sign_in_password(
            body.email, body.password, body.totp, now, client
        )
    await end_previous_session(request, service, now, client.ip_hash)
    set_session_cookie(response, session)
    return signed_in


# ---------- T08: sessions, passkeys, re-auth, recovery codes, app lock, recovery ----------

SignedInSession = Annotated[SessionContext, Depends(require_session)]
# Every signed-in endpoint: no session (401), an inactive account (403, CR-014), the 9.1 limit.
SIGNED_IN: dict[int | str, dict[str, Any]] = {
    401: {"description": "Not signed in, or the session has ended."},
    403: {"description": "Account not activated (CR-014)."},
    429: {"description": "More than 300 requests in a minute on this session (9.1)."},
}
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Not found."}}
REAUTH: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "Recent authentication required (POST /auth/reauth/verify), or account "
        "not activated."
    }
}


@router.get("/sessions", responses=SIGNED_IN)
async def list_sessions(session: SignedInSession, account: Account, now: Now) -> SessionList:
    items = await account.sessions(session, now)
    return SessionList(
        items=[
            SessionOut(
                id=item.id,
                device_label=item.device_label,
                created_at=item.created_at,
                last_seen_at=item.last_seen_at,
                current=current,
            )
            for item, current in items
        ]
    )


@router.delete(
    "/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND
)
async def revoke_session(
    session_id: uuid.UUID, session: SignedInSession, account: Account, now: Now, client: Client
) -> Response:
    with problems():
        await account.revoke_session(session, session_id, now, client)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    no_store(response)
    if session_id == session.session_id:
        clear_session_cookie(response)
    return response


@router.get("/passkeys", responses=SIGNED_IN)
async def list_passkeys(session: SignedInSession, account: Account) -> PasskeyList:
    items = await account.passkeys(session)
    return PasskeyList(
        items=[
            PasskeyOut(
                id=p.id,
                nickname=p.nickname,
                created_at=p.created_at,
                last_used_at=p.last_used_at,
                backed_up=p.backed_up,
            )
            for p in items
        ]
    )


@router.post("/passkeys/options", responses=SIGNED_IN | REAUTH)
async def add_passkey_options(
    _body: SignInOptions, session: SignedInSession, account: Account, now: Now
) -> WebAuthnOptions:
    with problems():
        return WebAuthnOptions(**await account.add_passkey_options(session, now))


@router.delete(
    "/passkeys/{passkey_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=SIGNED_IN | NOT_FOUND | REAUTH | {409: {"description": "Her last way to sign in."}},
)
async def remove_passkey(
    passkey_id: uuid.UUID, session: SignedInSession, account: Account, now: Now
) -> Response:
    with problems():
        await account.remove_passkey(session, passkey_id, now)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    no_store(response)
    return response


@router.post("/reauth/options", responses=SIGNED_IN)
async def reauth_options(
    body: ReauthOptionsRequest, session: SignedInSession, account: Account, now: Now
) -> WebAuthnOptions:
    return WebAuthnOptions(**await account.reauth_options(session, body.purpose, now))


@router.post(
    "/reauth/verify", status_code=status.HTTP_204_NO_CONTENT, responses=SIGNED_IN | SIGN_IN_ERRORS
)
async def reauth_verify(
    body: ReauthVerify, session: SignedInSession, account: Account, now: Now, client: Client
) -> Response:
    """Recent auth for this session (CR-017): a passkey, or password and TOTP."""
    with problems():
        if body.credential is not None:
            await account.reauth_passkey(session, body.credential, now, client)
        else:
            await account.reauth_password(
                session, body.password or "", body.totp or "", now, client
            )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    no_store(response)
    return response


@router.post("/recovery-codes", responses=SIGNED_IN | REAUTH)
async def regenerate_recovery_codes(
    session: SignedInSession, account: Account, now: Now
) -> RecoveryCodes:
    with problems():
        return RecoveryCodes(recovery_codes=await account.regenerate_recovery_codes(session, now))


@router.put("/app-lock", status_code=status.HTTP_204_NO_CONTENT, responses=SIGNED_IN | REAUTH)
async def set_app_lock(
    body: AppLockSettings, session: SignedInSession, account: Account, now: Now
) -> Response:
    """Set or clear the PIN (needs recent auth, CR-020) and/or the lock timeout."""
    with problems():
        await account.set_app_lock(
            session,
            now,
            pin=body.pin,
            change_pin="pin" in body.model_fields_set,
            timeout_s=body.timeout_s,
        )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    no_store(response)
    return response


@router.post(
    "/app-lock/unlock",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=SIGNED_IN | {409: {"description": "No PIN is set."}},
)
async def unlock_app(
    body: PinUnlock, session: SignedInSession, account: Account, now: Now, client: Client
) -> Response:
    """AUTH-6: unlock with the PIN; the fifth wrong PIN ends the session (cookie cleared)."""
    try:
        await account.unlock_with_pin(session, body.pin, now, client)
    except PinLockedOut as error:
        cleared = Response()
        clear_session_cookie(cleared)
        headers = {"set-cookie": cleared.headers["set-cookie"]}
        raise HTTPException(error.status, error.detail, headers=headers) from None
    except AuthError as error:
        raise HTTPException(error.status, error.detail) from None
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    no_store(response)
    return response


RECOVER_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "The passkey could not be verified."},
    403: {"description": "The invite is not valid."},
    **LOCKED,
}


@router.post("/recover/options", responses={403: {"description": "The invite is not valid."}})
async def recover_options(body: RecoverOptions, account: Account, now: Now) -> WebAuthnOptions:
    """AUTH-8: start registering a new passkey on her account from a recovery invite."""
    with problems():
        return WebAuthnOptions(**await account.recover_options(body.token, now))


@router.post(
    "/recover/verify",
    status_code=status.HTTP_201_CREATED,
    responses=RECOVER_ERRORS,
)
async def recover_verify(
    body: RecoverVerify,
    request: Request,
    response: Response,
    service: Service,
    account: Account,
    now: Now,
    client: Client,
) -> Registered:
    """AUTH-8: the new passkey is stored, fresh recovery codes are returned once (the old ones
    stop working) and she is signed in."""
    with problems():
        registered, session = await account.recover(body.token, body.credential, now, client)
    await end_previous_session(request, service, now, client.ip_hash)
    set_session_cookie(response, session)
    return registered
