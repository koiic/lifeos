"""auth: Service layer: rules and transactions (plan 4.2).

Invites, passkey registration and sign-in (spec 9.2, 12.3), sessions (AUTH-5) and recovery codes
(AUTH-4). Every method takes `now`; the API passes its clock.

- Challenges: 32 random bytes, stored for 5 minutes, used once. Each is consumed in its own
  committed transaction before the response is verified, so a failed attempt still spends it.
- Registration: the new account's id is the registration challenge's id, so the WebAuthn user
  handle and the account id are the same UUID v7.
- Sessions: the cookie holds 32 random bytes (base64url); only their SHA-256 is stored. Use slides
  the expiry to now + 30 days (at most once an hour), never past created + 180 days.
- Recovery codes: 10 codes of 12 base32 characters, stored argon2id. Every recovery attempt runs
  the same number of hash checks, so failures look alike whatever the reason. A code gives no
  session: it gives an `add_passkey` challenge, and the session starts once the new passkey is
  verified (CR-013).
"""

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import math
import re
import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from typing import Any

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    CredentialDeviceType,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from webauthn.registration.verify_registration_response import VerifiedRegistration

from app.auth import repo
from app.auth.schemas import (
    PasswordRegistered,
    PasswordRegistration,
    Registered,
    Registration,
    SignedIn,
)
from app.health.service import seed_symptoms
from app.notify.service import stop_session_notifications
from app.platform.crypto import (
    DataKey,
    Keyring,
    aad,
    decrypt,
    encrypt,
    generate_data_key,
    unwrap_dek,
    wrap_dek,
)
from app.platform.db import Database, Transaction, system_transaction, user_transaction
from app.platform.ids import new_id
from app.platform.outbox import publish

RP_NAME = "Life OS"
INVITE_TTL = timedelta(days=7)  # AUTH-1
INVITE_TOKEN_BYTES = 32  # 7.2 invites.token_hash: "sha256 of a 32-byte random token"
CHALLENGE_TTL = timedelta(minutes=5)
CHALLENGE_BYTES = 32
# Spec 12.3: ES256 and RS256 only (py_webauthn also accepts EdDSA by default).
ALGORITHMS = [
    COSEAlgorithmIdentifier.ECDSA_SHA_256,
    COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
]

TOKEN_BYTES = 32
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")  # base64url of 32 bytes, unpadded
SESSION_IDLE = timedelta(days=30)
SESSION_ABSOLUTE = timedelta(days=180)
SLIDE_EVERY = timedelta(hours=1)

RECOVERY_CODES = 10
CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"  # RFC 4648 base32 (no 0, 1, 8 or 9)
CODE_LENGTH = 12
# Recovery codes carry 60 random bits, so a lighter argon2id than passwords (12.3) suffices.
CODE_HASHER = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)
TRANSPORTS_MAX = 8

# 12.3: Argon2id, memory 64 MiB, iterations 3, parallelism 4.
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)
TOTP_ISSUER = "Life OS"
TOTP_CODE = re.compile(r"\d{6}")

# AUTH-7: 5 failed sign-ins per 15 min per account and per IP, then a 15-min lockout.
FAILURE_LIMIT = 5
FAILURE_WINDOW = timedelta(minutes=15)
# Attempts that guess something; registrations and sign-outs are logged but never counted.
COUNTED_KINDS = ("signin_passkey", "signin_password", "recovery", "totp")
# Verifications in flight per API process: bounds Argon2id CPU and the connections that attempts
# hold (each holds its gate transaction while it verifies).
CONCURRENT_ATTEMPTS = 4
FAILURES_READ = 1000  # newest failures read per lockout check (more is an attack in progress)

# 12.3 / 9.2 note: "recent auth" = a passkey or password verification within 5 minutes (CR-017).
RECENT_AUTH = timedelta(minutes=5)
PIN_TRIES = 5  # 9.2 app-lock unlock: "5 tries then full sign-in required"
RECOVERY_INVITE_TTL = timedelta(hours=24)  # AUTH-8
SECURITY_NOTICE = "auth.security_notice"  # outbox topic; notify delivers 10.7 "Account notice"

# 9.1: all other endpoints, 300 requests/min per session (shared by the workers, CR-016).
SESSION_LIMIT = 300
SESSION_WINDOW = timedelta(minutes=1)


class AuthError(Exception):
    status = 400
    detail = "The request could not be completed."
    retry_after: int | None = None  # sent as Retry-After with a 429


class InviteInvalid(AuthError):
    status = 403
    detail = "The invite is not valid."


class EmailInUse(AuthError):
    status = 409
    detail = "This email address already has an account."


class RegistrationFailed(AuthError):
    status = 400
    detail = "The passkey could not be registered."


class SignInFailed(AuthError):
    status = 401
    detail = "Sign-in failed."


class NotSignedIn(AuthError):
    status = 401
    detail = "Sign in to continue."


class NotActivated(AuthError):
    """CR-014: a password account before its TOTP is confirmed."""

    status = 403
    detail = "Confirm your authenticator app to finish setting up."


class AlreadyConfirmed(AuthError):
    status = 409
    detail = "The authenticator app is already confirmed."


class Locked(AuthError):
    """AUTH-7 lockout (or another attempt for the same account or IP in progress);
    `retry_after` seconds until it ends."""

    status = 429
    detail = "Too many failed sign-ins. Try again later."

    def __init__(self, retry_after: int) -> None:
        super().__init__()
        self.retry_after = retry_after


class ReauthRequired(AuthError):
    """12.3: a sensitive action without a passkey or password verification in 5 minutes."""

    status = 403
    detail = "Confirm it's you to continue."


class LastSignInMethod(AuthError):
    status = 409
    detail = "This is your last way to sign in."


class NotFound(AuthError):
    status = 404
    detail = "Not found."


class AdminWritesUnavailable(AuthError):
    """No `database_admin_write_url` configured (CR-022)."""

    status = 503
    detail = "Admin changes are not available."


class NoPin(AuthError):
    status = 409
    detail = "No app-lock PIN is set."


class PinFailed(AuthError):
    status = 401
    detail = "Wrong PIN."


class PinLockedOut(AuthError):
    """AUTH-6 / 9.2: the fifth wrong PIN ends the session ("full sign-in required")."""

    status = 401
    detail = "Too many wrong PINs. Sign in again."


class TooManyRequests(AuthError):
    """9.1: more than 300 requests in a minute on one session."""

    status = 429
    detail = "Too many requests. Try again shortly."

    def __init__(self, retry_after: int) -> None:
        super().__init__()
        self.retry_after = retry_after


@dataclass
class Attempt:
    """One sign-in attempt: its gate transaction (holding the advisory locks, and where its auth
    event is written) and what it has learnt so far."""

    gate: Transaction
    ip_hash: bytes
    now: datetime
    user_id: uuid.UUID | None = None
    locked_for: int | None = None  # seconds, the longest lockout `_guard` found


@dataclass(frozen=True)
class ClientInfo:
    """Who is asking: the client IP's HMAC and a device label from the user agent."""

    ip_hash: bytes
    device_label: str


@dataclass(frozen=True)
class SessionContext:
    user_id: uuid.UUID
    session_id: uuid.UUID
    created_at: datetime | None = None
    reauth_at: datetime | None = None


@dataclass(frozen=True)
class NewSession:
    """A session to put in the cookie: the token and the cookie's max age in seconds."""

    token: str
    max_age: int


# ---------- helpers ----------


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _client_challenge(credential: dict[str, Any]) -> bytes | None:
    """The challenge the authenticator signed, read from clientDataJSON (verified later)."""
    try:
        client_data = json.loads(base64url_to_bytes(credential["response"]["clientDataJSON"]))
        return base64url_to_bytes(client_data["challenge"])
    except (KeyError, TypeError, ValueError, AttributeError, binascii.Error):
        return None


def _raw_id(credential: dict[str, Any]) -> bytes | None:
    try:
        return base64url_to_bytes(credential["rawId"])
    except (KeyError, TypeError, ValueError, AttributeError, binascii.Error):
        return None


def _user_handle(credential: dict[str, Any]) -> bytes | None:
    try:
        return base64url_to_bytes(credential["response"]["userHandle"])
    except (KeyError, TypeError, ValueError, AttributeError, binascii.Error):
        return None


def _transports(credential: dict[str, Any]) -> list[str]:
    response = credential.get("response")
    values = response.get("transports") if isinstance(response, dict) else None
    if not isinstance(values, list):
        return []
    return [v for v in values if isinstance(v, str) and len(v) <= 32][:TRANSPORTS_MAX]


def _decode_token(value: str) -> bytes | None:
    if TOKEN.fullmatch(value) is None:
        return None
    return base64.urlsafe_b64decode(value + "=")


def _new_token() -> tuple[str, bytes]:
    raw = secrets.token_bytes(TOKEN_BYTES)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode(), raw


def _normal_code(code: str) -> str:
    return re.sub(r"[\s-]", "", code).upper()


def _new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


@cache
def _dummy_hash() -> str:
    return CODE_HASHER.hash(_new_code())


@cache
def _dummy_password_hash() -> str:
    return PASSWORD_HASHER.hash(secrets.token_urlsafe(16))


def _password_matches(password_hash: str | None, password: str) -> bool:
    """Always one Argon2id verification, against a dummy hash when there is no account."""
    try:
        matched = PASSWORD_HASHER.verify(password_hash or _dummy_password_hash(), password)
    except (VerificationError, InvalidHashError):
        return False
    return matched and password_hash is not None


def _totp_step(secret: str, code: str, now: datetime) -> int | None:
    """The time step `code` belongs to, within ±1 step of now (12.3), or None."""
    code = re.sub(r"\s", "", code)
    if TOTP_CODE.fullmatch(code) is None:
        return None
    totp = pyotp.TOTP(secret)
    current = totp.timecode(now)
    matched = None
    for step in (current - 1, current, current + 1):
        if hmac.compare_digest(totp.generate_otp(step), code) and matched is None:
            matched = step
    return matched


def _totp_secret_aad(user_id: uuid.UUID) -> bytes:
    # password_credentials is keyed by user_id, so the row id is the user id.
    return aad("password_credentials", "totp_secret_enc", user_id, user_id)


def _locked_until(failures: list[datetime]) -> datetime | None:
    """AUTH-7: a failure that makes FAILURE_LIMIT inside FAILURE_WINDOW (counting itself) locks
    for FAILURE_WINDOW from that failure; returns when the latest such lock ends."""
    times = sorted(failures)
    until = None
    first = 0
    for last, at in enumerate(times):
        while times[first] <= at - FAILURE_WINDOW:
            first += 1
        if last - first + 1 >= FAILURE_LIMIT:
            until = at + FAILURE_WINDOW
    return until


def _seconds(delta: timedelta) -> int:
    return max(1, math.ceil(delta.total_seconds()))


def _matching_code(codes: list[tuple[uuid.UUID, str]], code: str) -> uuid.UUID | None:
    """Check `code` against exactly RECOVERY_CODES hashes (padded with a dummy), never stopping
    early, so the work does not depend on the account, the codes left or the match."""
    candidates: list[tuple[uuid.UUID | None, str]] = list(codes[:RECOVERY_CODES])
    candidates += [(None, _dummy_hash())] * (RECOVERY_CODES - len(candidates))
    found = None
    for code_id, code_hash in candidates:
        try:
            if CODE_HASHER.verify(code_hash, code) and code_id is not None and found is None:
                found = code_id
        except (VerificationError, InvalidHashError):
            pass
    return found


def _options_json(options: Any) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(options_to_json(options))
    return result


# ---------- the service ----------


class AuthService:
    def __init__(self, db: Database, keyring: Keyring, rp_id: str, origin: str) -> None:
        self._db = db
        self._keyring = keyring
        self._rp_id = rp_id
        self._origin = origin
        self._verifying = asyncio.Semaphore(CONCURRENT_ATTEMPTS)
        # Computed now, so the first attempt is not slower than the rest.
        _dummy_hash()
        _dummy_password_hash()

    # ----- attempts: auth events and lockouts (AUTH-7) -----

    async def _log(
        self, kind: str, success: bool, user_id: uuid.UUID | None, ip_hash: bytes, now: datetime
    ) -> None:
        """One auth event per attempt, committed on its own so failures are kept."""
        async with system_transaction(self._db) as tx:
            await repo.insert_auth_event(
                tx, user_id=user_id, kind=kind, success=success, ip_hash=ip_hash, now=now
            )

    @asynccontextmanager
    async def _attempt(self, kind: str, ip_hash: bytes, now: datetime) -> AsyncIterator[Attempt]:
        """Run one attempt inside its gate transaction and log its outcome there: success, or
        failure on any exception (lockouts included; "all attempts logged", AUTH-7). The advisory
        locks `_guard` takes are held until the event is committed, so concurrent attempts for
        the same account or IP cannot all pass the lockout check, and a TOTP success is recorded
        before another attempt can read it."""
        async with self._verifying, system_transaction(self._db) as gate:
            attempt = Attempt(gate=gate, ip_hash=ip_hash, now=now)
            failure: BaseException | None = None
            try:
                yield attempt
            except BaseException as error:  # cancellation too: the attempt still happened
                failure = error
            logged = True
            try:
                async with gate.begin_nested():
                    await repo.insert_auth_event(
                        gate,
                        user_id=attempt.user_id,
                        kind=kind,
                        success=failure is None,
                        ip_hash=ip_hash,
                        now=now,
                    )
            except Exception:
                logged = False
        if not logged:
            # The gate could not take the event: write it on its own (never lose an attempt).
            await asyncio.shield(self._log(kind, failure is None, attempt.user_id, ip_hash, now))
        if failure is not None:
            raise failure

    async def _guard(self, attempt: Attempt, user_id: uuid.UUID | None = None) -> None:
        """AUTH-7 for this IP, or for this account if given: take its advisory lock (another
        attempt in progress → Locked now) and note how long it is locked out, counting this
        attempt (it is logged as a failure). `_refuse_if_locked` then refuses with the longest
        wait, so the IP and the account are both checked first."""
        key = f"auth:user:{user_id}" if user_id is not None else f"auth:ip:{attempt.ip_hash.hex()}"
        if not await repo.try_advisory_lock(attempt.gate, key):
            raise Locked(1)
        # In a savepoint, so a failed read cannot abort the gate before its event is written.
        async with attempt.gate.begin_nested():
            failures = await repo.recent_failures(
                attempt.gate,
                kinds=COUNTED_KINDS,
                since=attempt.now - 2 * FAILURE_WINDOW,
                limit=FAILURES_READ,
                user_id=user_id,
                ip_hash=None if user_id is not None else attempt.ip_hash,
            )
        until = _locked_until(failures)
        if until is not None and until > attempt.now:
            with_this = _locked_until([*failures, attempt.now]) or until
            wait = _seconds(max(until, with_this) - attempt.now)
            attempt.locked_for = max(wait, attempt.locked_for or 0)

    @staticmethod
    def _refuse_if_locked(attempt: Attempt) -> None:
        if attempt.locked_for is not None:
            raise Locked(attempt.locked_for)

    # ----- invites -----

    async def create_invite(self, created_by: uuid.UUID, email: str | None, now: datetime) -> str:
        """A single-use invite valid for 7 days (AUTH-1); returns the token, stores its SHA-256.
        The admin console (T44) calls this."""
        token = base64.urlsafe_b64encode(secrets.token_bytes(INVITE_TOKEN_BYTES)).rstrip(b"=")
        async with system_transaction(self._db) as tx:
            await repo.insert_invite(
                tx,
                invite_id=new_id(),
                token_hash=_sha256(token),
                email=email,
                created_by=created_by,
                expires_at=now + INVITE_TTL,
                now=now,
            )
        return token.decode()

    async def check_invite(self, token: str, now: datetime) -> repo.Invite | None:
        async with system_transaction(self._db) as tx:
            return await repo.find_valid_invite(tx, _sha256(token.encode()), now)

    async def _invite_for(self, tx: Transaction, data: Registration, now: datetime) -> repo.Invite:
        invite = await repo.find_valid_invite(tx, _sha256(data.token.encode()), now)
        if invite is None:
            raise InviteInvalid
        if invite.email is not None and invite.email.casefold() != data.email.casefold():
            raise InviteInvalid
        if await repo.find_user_id_by_email(tx, data.email) is not None:
            raise EmailInUse
        return invite

    # ----- registration -----

    async def registration_options(self, data: Registration, now: datetime) -> dict[str, Any]:
        challenge_id, challenge = new_id(), secrets.token_bytes(CHALLENGE_BYTES)
        async with system_transaction(self._db) as tx:
            invite = await self._invite_for(tx, data, now)
            await repo.insert_challenge(
                tx,
                challenge_id=challenge_id,
                purpose="register",
                challenge=challenge,
                invite_id=invite.id,
                now=now,
                expires_at=now + CHALLENGE_TTL,
            )
        return self._creation_options(challenge_id, data.email, data.name, challenge)

    def _creation_options(
        self, user_id: uuid.UUID, email: str, name: str, challenge: bytes
    ) -> dict[str, Any]:
        """WebAuthn creation options (12.3); the user handle is the account id."""
        options = generate_registration_options(
            rp_id=self._rp_id,
            rp_name=RP_NAME,
            user_name=email,
            user_id=user_id.bytes,
            user_display_name=name,
            challenge=challenge,
            timeout=int(CHALLENGE_TTL.total_seconds() * 1000),
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                require_resident_key=True,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            supported_pub_key_algs=ALGORITHMS,
        )
        return _options_json(options)

    def _verify_new_passkey(
        self, credential: dict[str, Any], challenge: bytes
    ) -> VerifiedRegistration:
        try:
            return verify_registration_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=self._rp_id,
                expected_origin=self._origin,
                require_user_verification=True,
                supported_pub_key_algs=ALGORITHMS,
            )
        except (WebAuthnException, KeyError, TypeError, ValueError):
            raise RegistrationFailed from None

    @staticmethod
    async def _store_passkey(
        tx: Transaction,
        user_id: uuid.UUID,
        verified: VerifiedRegistration,
        credential: dict[str, Any],
        now: datetime,
    ) -> None:
        try:
            await repo.insert_credential(
                tx,
                user_id=user_id,
                credential_id=verified.credential_id,
                public_key=verified.credential_public_key,
                sign_count=verified.sign_count,
                transports=_transports(credential),
                aaguid=uuid.UUID(verified.aaguid),
                backup_eligible=(
                    verified.credential_device_type == CredentialDeviceType.MULTI_DEVICE
                ),
                backed_up=verified.credential_backed_up,
                now=now,
            )
        except repo.CredentialTaken:
            raise RegistrationFailed from None

    async def register(
        self, data: Registration, credential: dict[str, Any], now: datetime, client: ClientInfo
    ) -> tuple[Registered, NewSession]:
        async with self._attempt("register", client.ip_hash, now) as attempt:
            challenge = _client_challenge(credential)
            if challenge is None:
                raise RegistrationFailed
            async with system_transaction(self._db) as tx:
                spent = await repo.consume_challenge(tx, "register", challenge, now)
            if spent is None:
                raise RegistrationFailed
            async with system_transaction(self._db) as tx:
                invite = await self._invite_for(tx, data, now)
            if invite.id != spent.invite_id:
                raise InviteInvalid
            verified = self._verify_new_passkey(credential, challenge)

            user_id = spent.id
            codes, hashes = await _new_recovery_codes()
            async with user_transaction(self._db, user_id) as tx:
                await self._create_account(tx, user_id, data, invite, now)
                await self._store_passkey(tx, user_id, verified, credential, now)
                await repo.insert_recovery_codes(tx, user_id, hashes)
                session = await self._start_session(tx, user_id, now, client)
            attempt.user_id = user_id
        return Registered(user_id=user_id, display_name=data.name, recovery_codes=codes), session

    async def _create_account(
        self,
        tx: Transaction,
        user_id: uuid.UUID,
        data: Registration,
        invite: repo.Invite,
        now: datetime,
    ) -> DataKey:
        """The user, their settings and wrapped DEK, her seeded symptoms, and the invite spent;
        returns the DEK."""
        dek = generate_data_key()
        kek_version, dek_wrapped = wrap_dek(self._keyring, dek, user_id)
        try:
            await repo.insert_user(
                tx,
                user_id=user_id,
                email=data.email,
                display_name=data.name,
                dek_wrapped=dek_wrapped,
                kek_version=kek_version,
            )
        except repo.EmailTaken:
            raise EmailInUse from None
        if not await repo.use_invite(tx, invite.id, user_id, now):
            raise InviteInvalid
        await seed_symptoms(tx, user_id, dek)  # 7.4
        return dek

    async def _dek(self, tx: Transaction, user_id: uuid.UUID) -> DataKey:
        key = await repo.user_key(tx, user_id)
        if key is None:
            raise SignInFailed
        return unwrap_dek(self._keyring, key.kek_version, key.dek_wrapped, user_id)

    # ----- password + TOTP fallback (AUTH-3, CR-014) -----

    async def register_password(
        self, data: PasswordRegistration, now: datetime, client: ClientInfo
    ) -> tuple[PasswordRegistered, NewSession]:
        """Create an inactive account with a password and an unconfirmed TOTP secret; its session
        can only confirm the TOTP (CR-014)."""
        async with self._attempt("register", client.ip_hash, now) as attempt:
            async with system_transaction(self._db) as tx:
                invite = await self._invite_for(tx, data, now)
            user_id = new_id()
            secret = pyotp.random_base32()  # 160 bits
            password_hash = await asyncio.to_thread(PASSWORD_HASHER.hash, data.password)
            async with user_transaction(self._db, user_id) as tx:
                dek = await self._create_account(tx, user_id, data, invite, now)
                await repo.insert_password_credentials(
                    tx,
                    user_id,
                    password_hash,
                    encrypt(dek, secret.encode(), _totp_secret_aad(user_id)),
                )
                session = await self._start_session(tx, user_id, now, client)
            attempt.user_id = user_id
        uri = pyotp.TOTP(secret).provisioning_uri(name=data.email, issuer_name=TOTP_ISSUER)
        return PasswordRegistered(provisioning_uri=uri), session

    async def _check_totp(
        self,
        tx: Transaction,
        user_id: uuid.UUID,
        secret_enc: bytes | None,
        code: str,
        now: datetime,
    ) -> bool:
        """A code within ±1 step that is newer than any code already used (12.3: "codes cannot
        be reused within their window"). The last success's step is not stored, so any step up
        to one after it counts as used."""
        if secret_enc is None:
            return False
        dek = await self._dek(tx, user_id)
        secret = decrypt(dek, secret_enc, _totp_secret_aad(user_id)).decode()
        step = _totp_step(secret, code, now)
        if step is None:
            return False
        last = await repo.last_totp_success(tx, user_id)
        return last is None or step > pyotp.TOTP(secret).timecode(last) + 1

    async def confirm_totp(
        self, session: SessionContext, code: str, now: datetime, client: ClientInfo
    ) -> list[str]:
        """Activate a password account: a valid code turns TOTP on; returns the recovery codes
        once. An already confirmed account gets 409 before any attempt is counted (nothing is
        guessed)."""
        async with user_transaction(self._db, session.user_id) as tx:
            credentials = await repo.password_credentials(tx, session.user_id)
        if credentials is None or credentials.totp_enabled:
            raise AlreadyConfirmed
        async with self._attempt("totp", client.ip_hash, now) as attempt:
            attempt.user_id = session.user_id
            await self._guard(attempt)
            await self._guard(attempt, session.user_id)
            self._refuse_if_locked(attempt)
            async with user_transaction(self._db, session.user_id) as tx:
                credentials = await repo.password_credentials(tx, session.user_id)
                if credentials is None or credentials.totp_enabled:
                    raise AlreadyConfirmed
                if not await self._check_totp(
                    tx, session.user_id, credentials.totp_secret_enc, code, now
                ):
                    raise SignInFailed
            codes, hashes = await _new_recovery_codes()
            async with user_transaction(self._db, session.user_id) as tx:
                if not await repo.enable_totp(tx, session.user_id):
                    raise AlreadyConfirmed
                await repo.insert_recovery_codes(tx, session.user_id, hashes)
        return codes

    async def sign_in_password(
        self, email: str, password: str, code: str, now: datetime, client: ClientInfo
    ) -> tuple[SignedIn, NewSession]:
        async with self._attempt("signin_password", client.ip_hash, now) as attempt:
            await self._guard(attempt)
            async with system_transaction(self._db) as tx:
                user_id = await repo.find_user_id_by_email(tx, email)
            attempt.user_id = user_id
            if user_id is not None:
                await self._guard(attempt, user_id)
            self._refuse_if_locked(attempt)
            # Unknown emails do the same work (one Argon2id check against a dummy hash).
            subject = user_id or uuid.uuid4()
            async with user_transaction(self._db, subject) as tx:
                name = await repo.active_display_name(tx, subject)
                credentials = await repo.password_credentials(tx, subject)
            stored_hash = credentials.password_hash if credentials and name else None
            if not await asyncio.to_thread(_password_matches, stored_hash, password):
                raise SignInFailed
            if user_id is None or name is None or credentials is None:
                raise SignInFailed
            if not credentials.totp_enabled:
                raise SignInFailed
            async with user_transaction(self._db, user_id) as tx:
                if not await self._check_totp(tx, user_id, credentials.totp_secret_enc, code, now):
                    raise SignInFailed
                session = await self._start_session(tx, user_id, now, client)
        return SignedIn(user_id=user_id, display_name=name), session

    # ----- sign-in -----

    async def signin_options(self, now: datetime) -> dict[str, Any]:
        challenge = secrets.token_bytes(CHALLENGE_BYTES)
        async with system_transaction(self._db) as tx:
            await repo.insert_challenge(
                tx,
                challenge_id=new_id(),
                purpose="signin",
                challenge=challenge,
                now=now,
                expires_at=now + CHALLENGE_TTL,
            )
        options = generate_authentication_options(
            rp_id=self._rp_id,
            challenge=challenge,
            timeout=int(CHALLENGE_TTL.total_seconds() * 1000),
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        return _options_json(options)

    async def sign_in(
        self, credential: dict[str, Any], now: datetime, client: ClientInfo
    ) -> tuple[SignedIn, NewSession]:
        """Passkey sign-in. Only the IP lockout applies: a passkey cannot be guessed, and an
        account lockout here would let anyone who knows her email lock her out (T07)."""
        async with self._attempt("signin_passkey", client.ip_hash, now) as attempt:
            await self._guard(attempt)
            self._refuse_if_locked(attempt)
            challenge = _client_challenge(credential)
            credential_id = _raw_id(credential)
            if challenge is None or credential_id is None:
                raise SignInFailed
            async with system_transaction(self._db) as tx:
                spent = await repo.consume_challenge(tx, "signin", challenge, now)
                stored = await repo.find_credential(tx, credential_id)
            if stored is not None:
                attempt.user_id = stored.user_id
            if spent is None or stored is None:
                raise SignInFailed
            if _user_handle(credential) != stored.user_id.bytes:
                raise SignInFailed
            try:
                verified = verify_authentication_response(
                    credential=credential,
                    expected_challenge=challenge,
                    expected_rp_id=self._rp_id,
                    expected_origin=self._origin,
                    credential_public_key=stored.public_key,
                    credential_current_sign_count=stored.sign_count,
                    require_user_verification=True,
                )
            except (WebAuthnException, KeyError, TypeError, ValueError):
                raise SignInFailed from None
            async with user_transaction(self._db, stored.user_id) as tx:
                name = await repo.active_display_name(tx, stored.user_id)
                if name is None:
                    raise SignInFailed
                # Conditional on the stored count, so concurrent sign-ins cannot move it back.
                if not await repo.record_credential_use(
                    tx, credential_id, verified.new_sign_count, verified.credential_backed_up, now
                ):
                    raise SignInFailed
                session = await self._start_session(tx, stored.user_id, now, client)
        return SignedIn(user_id=stored.user_id, display_name=name), session

    async def recover(
        self, email: str, code: str, now: datetime, client: ClientInfo
    ) -> dict[str, Any]:
        """Spend a recovery code; returns creation options for a new passkey. No session is
        issued until that passkey is verified (CR-013: "forces new passkey setup")."""
        async with self._attempt("recovery", client.ip_hash, now) as attempt:
            await self._guard(attempt)
            typed = _normal_code(code)
            async with system_transaction(self._db) as tx:
                user_id = await repo.find_user_id_by_email(tx, email)
            attempt.user_id = user_id
            if user_id is not None:
                await self._guard(attempt, user_id)
            self._refuse_if_locked(attempt)
            # An unknown email runs the same queries for a random id (RLS returns no rows) and
            # the same hash checks, so failures cost the same whether or not the account exists.
            subject = user_id or uuid.uuid4()
            # Read, then hash with no connection held (argon2 is slow by design), then spend the
            # code with a conditional update, so concurrent attempts cannot both use it.
            async with user_transaction(self._db, subject) as tx:
                active = await repo.active_display_name(tx, subject) is not None
                codes = await repo.unused_recovery_codes(tx, subject)
            code_id = await asyncio.to_thread(_matching_code, codes if active else [], typed)
            if user_id is None or code_id is None:
                raise SignInFailed
            async with user_transaction(self._db, subject) as tx:
                account = await repo.account(tx, subject)
                if account is None or not await repo.use_recovery_code(tx, code_id, now):
                    raise SignInFailed
                challenge = secrets.token_bytes(CHALLENGE_BYTES)
                await repo.insert_challenge(
                    tx,
                    challenge_id=new_id(),
                    purpose="add_passkey",
                    challenge=challenge,
                    user_id=subject,
                    now=now,
                    expires_at=now + CHALLENGE_TTL,
                )
        return self._creation_options(subject, account.email, account.display_name, challenge)

    async def add_recovery_passkey(
        self, credential: dict[str, Any], now: datetime, client: ClientInfo
    ) -> tuple[SignedIn, NewSession]:
        """Finish a recovery sign-in: verify the new passkey for the user the recovery
        challenge names, store it and only then start a session (CR-013). Logged as a passkey
        registration."""
        async with self._attempt("register", client.ip_hash, now) as attempt:
            challenge = _client_challenge(credential)
            if challenge is None:
                raise RegistrationFailed
            async with system_transaction(self._db) as tx:
                spent = await repo.consume_challenge(tx, "add_passkey", challenge, now)
            # Recovery-invite challenges (CR-018) carry their invite and finish only at
            # /auth/recover/verify.
            if spent is None or spent.user_id is None or spent.invite_id is not None:
                raise RegistrationFailed
            attempt.user_id = spent.user_id
            verified = self._verify_new_passkey(credential, challenge)
            async with user_transaction(self._db, spent.user_id) as tx:
                account = await repo.account(tx, spent.user_id)
                if account is None:
                    raise RegistrationFailed
                await self._store_passkey(tx, spent.user_id, verified, credential, now)
                session = await self._start_session(tx, spent.user_id, now, client)
        return SignedIn(user_id=spent.user_id, display_name=account.display_name), session

    # ----- sessions -----

    async def _start_session(
        self, tx: Transaction, user_id: uuid.UUID, now: datetime, client: ClientInfo
    ) -> NewSession:
        token, raw = _new_token()
        await repo.insert_session(
            tx,
            session_id=new_id(),
            user_id=user_id,
            token_hash=_sha256(raw),
            now=now,
            expires_at=now + SESSION_IDLE,
            ip_hash=client.ip_hash,
            device_label=client.device_label,
        )
        return NewSession(token, int(SESSION_IDLE.total_seconds()))

    async def _find_session(self, token: str) -> repo.SessionRef | None:
        raw = _decode_token(token)
        if raw is None:
            return None
        async with system_transaction(self._db) as tx:
            return await repo.find_session(tx, _sha256(raw))

    async def authenticate(
        self,
        token: str,
        now: datetime,
        *,
        allow_inactive: bool = False,
        count_request: bool = False,
    ) -> tuple[SessionContext, NewSession | None]:
        """The session's user, and a refreshed cookie when the expiry slid. Sessions of accounts
        not yet activated are refused unless `allow_inactive` (only TOTP confirm, CR-014).
        `count_request` applies the 9.1 limit of 300 requests/min per session (CR-016)."""
        ref = await self._find_session(token)
        if ref is None or ref.revoked or ref.expires_at <= now:
            raise NotSignedIn
        refreshed = None
        async with user_transaction(self._db, ref.user_id) as tx:
            times = await repo.session_times(tx, ref.id)
            if times is None or await repo.active_display_name(tx, ref.user_id) is None:
                raise NotSignedIn
            if not allow_inactive and not await repo.is_activated(tx, ref.user_id):
                raise NotActivated
            if count_request:
                window_start, count = await repo.count_session_request(
                    tx, ref.id, now, now - SESSION_WINDOW
                )
                if count > SESSION_LIMIT:
                    raise TooManyRequests(_seconds(window_start + SESSION_WINDOW - now))
            if now - times.last_seen_at >= SLIDE_EVERY:
                expires_at = min(now + SESSION_IDLE, times.created_at + SESSION_ABSOLUTE)
                await repo.slide_session(tx, ref.id, now, expires_at)
                refreshed = NewSession(token, int((expires_at - now).total_seconds()))
        context = SessionContext(ref.user_id, ref.id, times.created_at, times.reauth_at)
        return context, refreshed

    async def sign_out(self, token: str, now: datetime, ip_hash: bytes) -> None:
        """End the session the token names (logged as `revoke`); nothing to do otherwise."""
        ref = await self._find_session(token)
        if ref is None:
            return
        async with user_transaction(self._db, ref.user_id) as tx:
            await repo.revoke_session(tx, ref.id, now)
            await repo.spend_pending_challenges(tx, ref.user_id, now)
            await stop_session_notifications(tx, ref.id, now)
        await self._log("revoke", True, ref.user_id, ip_hash, now)


async def _new_recovery_codes() -> tuple[list[str], list[str]]:
    """RECOVERY_CODES new codes, shown once, and their Argon2id hashes."""
    codes = [_new_code() for _ in range(RECOVERY_CODES)]
    hashes = await asyncio.to_thread(lambda: [CODE_HASHER.hash(_normal_code(c)) for c in codes])
    return codes, hashes


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class AccountService:
    """T08: session and passkey management, re-authentication, recovery codes, app lock and
    recovery invites. Shares the AuthService's database, keyring and WebAuthn settings."""

    def __init__(self, auth: AuthService, admin_db: Database | None = None) -> None:
        self._auth = auth
        self._db = auth._db
        # lifeos_admin (CR-022): admin endpoints that write use only this connection.
        self._admin_db = admin_db

    # ----- recent auth (CR-017) -----

    @staticmethod
    def require_recent_auth(session: SessionContext, now: datetime) -> None:
        if session.reauth_at is None or now - session.reauth_at >= RECENT_AUTH:
            raise ReauthRequired

    async def reauth_options(
        self, session: SessionContext, purpose: str, now: datetime
    ) -> dict[str, Any]:
        """Request options for her own passkeys (purpose `reauth`, or `unlock` for the app lock,
        11.6); the challenge is bound to her account."""
        challenge = secrets.token_bytes(CHALLENGE_BYTES)
        async with user_transaction(self._db, session.user_id) as tx:
            mine = await repo.passkeys(tx, session.user_id)
            await repo.insert_challenge(
                tx,
                challenge_id=new_id(),
                purpose=purpose,
                challenge=challenge,
                user_id=session.user_id,
                now=now,
                expires_at=now + CHALLENGE_TTL,
            )
        options = generate_authentication_options(
            rp_id=self._auth._rp_id,
            challenge=challenge,
            timeout=int(CHALLENGE_TTL.total_seconds() * 1000),
            allow_credentials=[PublicKeyCredentialDescriptor(id=p.credential_id) for p in mine],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        return _options_json(options)

    async def reauth_passkey(
        self, session: SessionContext, credential: dict[str, Any], now: datetime, client: ClientInfo
    ) -> None:
        auth = self._auth
        async with auth._attempt("signin_passkey", client.ip_hash, now) as attempt:
            attempt.user_id = session.user_id
            await auth._guard(attempt)
            auth._refuse_if_locked(attempt)
            challenge = _client_challenge(credential)
            credential_id = _raw_id(credential)
            if challenge is None or credential_id is None:
                raise SignInFailed
            async with system_transaction(self._db) as tx:
                spent = await repo.consume_challenge(tx, ("reauth", "unlock"), challenge, now)
                stored = await repo.find_credential(tx, credential_id)
            if spent is None or spent.user_id != session.user_id:
                raise SignInFailed
            if stored is None or stored.user_id != session.user_id:
                raise SignInFailed
            if _user_handle(credential) != stored.user_id.bytes:
                raise SignInFailed
            try:
                verified = verify_authentication_response(
                    credential=credential,
                    expected_challenge=challenge,
                    expected_rp_id=auth._rp_id,
                    expected_origin=auth._origin,
                    credential_public_key=stored.public_key,
                    credential_current_sign_count=stored.sign_count,
                    require_user_verification=True,
                )
            except (WebAuthnException, KeyError, TypeError, ValueError):
                raise SignInFailed from None
            async with user_transaction(self._db, session.user_id) as tx:
                if not await repo.record_credential_use(
                    tx, credential_id, verified.new_sign_count, verified.credential_backed_up, now
                ):
                    raise SignInFailed
                await repo.set_reauth(tx, session.session_id, now)
                # A passkey unlock (or any passkey verification) also resets the PIN tries.
                await repo.reset_pin_failures(tx, session.session_id)

    async def reauth_password(
        self, session: SessionContext, password: str, code: str, now: datetime, client: ClientInfo
    ) -> None:
        auth = self._auth
        async with auth._attempt("signin_password", client.ip_hash, now) as attempt:
            attempt.user_id = session.user_id
            await auth._guard(attempt)
            await auth._guard(attempt, session.user_id)
            auth._refuse_if_locked(attempt)
            async with user_transaction(self._db, session.user_id) as tx:
                credentials = await repo.password_credentials(tx, session.user_id)
            stored_hash = credentials.password_hash if credentials else None
            if not await asyncio.to_thread(_password_matches, stored_hash, password):
                raise SignInFailed
            if credentials is None or not credentials.totp_enabled:
                raise SignInFailed
            async with user_transaction(self._db, session.user_id) as tx:
                if not await auth._check_totp(
                    tx, session.user_id, credentials.totp_secret_enc, code, now
                ):
                    raise SignInFailed
                await repo.set_reauth(tx, session.session_id, now)

    # ----- sessions (AUTH-5) -----

    async def sessions(
        self, session: SessionContext, now: datetime
    ) -> list[tuple[repo.SessionItem, bool]]:
        async with user_transaction(self._db, session.user_id) as tx:
            items = await repo.active_sessions(tx, session.user_id, now)
        return [(item, item.id == session.session_id) for item in items]

    async def revoke_session(
        self, session: SessionContext, session_id: uuid.UUID, now: datetime, client: ClientInfo
    ) -> None:
        async with user_transaction(self._db, session.user_id) as tx:
            if not await repo.revoke_user_session(tx, session.user_id, session_id, now):
                raise NotFound
            await repo.spend_pending_challenges(tx, session.user_id, now)
            await stop_session_notifications(tx, session_id, now)
        await self._auth._log("revoke", True, session.user_id, client.ip_hash, now)

    # ----- passkeys -----

    async def passkeys(self, session: SessionContext) -> list[repo.PasskeyItem]:
        async with user_transaction(self._db, session.user_id) as tx:
            return await repo.passkeys(tx, session.user_id)

    async def add_passkey_options(self, session: SessionContext, now: datetime) -> dict[str, Any]:
        self.require_recent_auth(session, now)  # CR-020
        challenge = secrets.token_bytes(CHALLENGE_BYTES)
        async with user_transaction(self._db, session.user_id) as tx:
            if not await repo.hold_live_session(tx, session.session_id):
                raise NotSignedIn
            account = await repo.account(tx, session.user_id)
            mine = await repo.passkeys(tx, session.user_id)
            if account is None:
                raise NotSignedIn
            await repo.insert_challenge(
                tx,
                challenge_id=new_id(),
                purpose="add_passkey",
                challenge=challenge,
                user_id=session.user_id,
                now=now,
                expires_at=now + CHALLENGE_TTL,
            )
        options = self._auth._creation_options(
            session.user_id, account.email, account.display_name, challenge
        )
        options["excludeCredentials"] = [
            {"type": "public-key", "id": _b64url(p.credential_id)} for p in mine
        ]
        return options

    async def add_passkey(
        self, session: SessionContext, credential: dict[str, Any], now: datetime, client: ClientInfo
    ) -> SignedIn:
        """Add a passkey to the signed-in account (no new session). The challenge must be one
        this account asked for, not a recovery invite's (CR-018). Needs recent auth (CR-020)."""
        self.require_recent_auth(session, now)
        auth = self._auth
        async with auth._attempt("register", client.ip_hash, now) as attempt:
            attempt.user_id = session.user_id
            challenge = _client_challenge(credential)
            if challenge is None:
                raise RegistrationFailed
            async with system_transaction(self._db) as tx:
                spent = await repo.consume_challenge(tx, "add_passkey", challenge, now)
            if spent is None or spent.user_id != session.user_id or spent.invite_id is not None:
                raise RegistrationFailed
            verified = auth._verify_new_passkey(credential, challenge)
            async with user_transaction(self._db, session.user_id) as tx:
                account = await repo.account(tx, session.user_id)
                if account is None:
                    raise RegistrationFailed
                await auth._store_passkey(tx, session.user_id, verified, credential, now)
        return SignedIn(user_id=session.user_id, display_name=account.display_name)

    async def remove_passkey(
        self, session: SessionContext, passkey_id: uuid.UUID, now: datetime
    ) -> None:
        """12.3: needs recent auth; refused when it is her last sign-in method (passkeys, or a
        password with confirmed TOTP)."""
        async with user_transaction(self._db, session.user_id) as tx:
            mine = await repo.lock_passkeys(tx, session.user_id)  # serialises removals
            if passkey_id not in mine:
                raise NotFound
            self.require_recent_auth(session, now)
            credentials = await repo.password_credentials(tx, session.user_id)
            methods = len(mine) + (1 if credentials and credentials.totp_enabled else 0)
            if methods <= 1:
                raise LastSignInMethod
            await repo.delete_passkey(tx, session.user_id, passkey_id)

    # ----- recovery codes (AUTH-4) -----

    async def regenerate_recovery_codes(self, session: SessionContext, now: datetime) -> list[str]:
        """Needs recent auth; the old codes stop working ("regenerating invalidates old codes")."""
        self.require_recent_auth(session, now)
        codes, hashes = await _new_recovery_codes()
        async with user_transaction(self._db, session.user_id) as tx:
            await repo.delete_recovery_codes(tx, session.user_id)
            await repo.insert_recovery_codes(tx, session.user_id, hashes)
        return codes

    # ----- app lock (AUTH-6) -----

    async def set_app_lock(
        self,
        session: SessionContext,
        now: datetime,
        *,
        pin: str | None,
        change_pin: bool,
        timeout_s: int | None,
    ) -> None:
        """Changing or clearing the PIN needs recent auth (CR-020); the timeout alone does not."""
        if change_pin:
            self.require_recent_auth(session, now)
        pin_hash = None
        if change_pin and pin is not None:
            pin_hash = await asyncio.to_thread(PASSWORD_HASHER.hash, pin)
        async with user_transaction(self._db, session.user_id) as tx:
            await repo.set_app_lock(
                tx, session.user_id, pin_hash=pin_hash, change_pin=change_pin, timeout_s=timeout_s
            )

    async def unlock_with_pin(
        self, session: SessionContext, pin: str, now: datetime, client: ClientInfo
    ) -> None:
        """Each try is counted on this session before the PIN is checked (CR-021), so concurrent
        tries cannot exceed five; a good PIN resets the count; the fifth wrong one (or any try
        past it) revokes the session."""
        async with user_transaction(self._db, session.user_id) as tx:
            stored = await repo.pin_hash(tx, session.user_id)
        if stored is None:
            raise NoPin
        async with self._auth._attempt("pin_unlock", client.ip_hash, now) as attempt:
            attempt.user_id = session.user_id
            async with user_transaction(self._db, session.user_id) as tx:
                tries = await repo.bump_pin_failures(tx, session.session_id)
            if tries > PIN_TRIES:
                await self._end_session(session, now)
                raise PinLockedOut
            if await asyncio.to_thread(_password_matches, stored, pin):
                async with user_transaction(self._db, session.user_id) as tx:
                    await repo.reset_pin_failures(tx, session.session_id)
                return
            if tries == PIN_TRIES:
                await self._end_session(session, now)
                raise PinLockedOut
            raise PinFailed

    async def _end_session(self, session: SessionContext, now: datetime) -> None:
        async with user_transaction(self._db, session.user_id) as tx:
            await repo.revoke_session(tx, session.session_id, now)
            await repo.spend_pending_challenges(tx, session.user_id, now)
            await stop_session_notifications(tx, session.session_id, now)

    # ----- recovery invites (AUTH-8, CR-018) -----

    async def issue_recovery_invite(
        self, admin: SessionContext, user_id: uuid.UUID, now: datetime, client: ClientInfo
    ) -> tuple[str, datetime]:
        """A single-use 24-hour invite to add a passkey to `user_id`'s account; returns the token
        and its expiry. Needs the admin's recent auth (CR-020). In one transaction as
        `lifeos_admin` (CR-022): her earlier unused recovery invites are revoked, all her
        sessions are revoked and their pending challenges spent, a security notice is queued
        for her devices and the audit log is written."""
        self.require_recent_auth(admin, now)
        if self._admin_db is None:
            raise AdminWritesUnavailable
        token = _b64url(secrets.token_bytes(INVITE_TOKEN_BYTES))
        expires_at = now + RECOVERY_INVITE_TTL
        async with system_transaction(self._admin_db) as tx:
            account = await repo.account(tx, user_id)
            if account is None:
                raise NotFound
            await repo.revoke_recovery_invites(tx, user_id, now)
            await repo.insert_invite(
                tx,
                invite_id=new_id(),
                token_hash=_sha256(token.encode()),
                email=account.email,
                created_by=admin.user_id,
                expires_at=expires_at,
                now=now,
                recover_user_id=user_id,
            )
            await repo.revoke_all_sessions(tx, user_id, now)
            await repo.spend_pending_challenges(tx, user_id, now)
            await publish(tx, user_id, SECURITY_NOTICE, {"event": "recovery_invite"})
            await repo.insert_audit(
                tx,
                actor_user_id=admin.user_id,
                actor_role="admin",
                action="admin.recovery_invite",
                target_user_id=user_id,
                ip_hash=client.ip_hash,
                now=now,
            )
        return token, expires_at

    async def _recovery_invite(self, token: str, now: datetime) -> tuple[repo.Invite, uuid.UUID]:
        """A live recovery invite and the account it recovers; InviteInvalid otherwise."""
        async with system_transaction(self._db) as tx:
            invite = await repo.find_valid_invite(tx, _sha256(token.encode()), now, recovery=True)
        if invite is None or invite.recover_user_id is None:
            raise InviteInvalid
        return invite, invite.recover_user_id

    async def recover_options(self, token: str, now: datetime) -> dict[str, Any]:
        invite, user_id = await self._recovery_invite(token, now)
        challenge = secrets.token_bytes(CHALLENGE_BYTES)
        async with user_transaction(self._db, user_id) as tx:
            account = await repo.account(tx, user_id)
            if account is None:
                raise InviteInvalid
            await repo.insert_challenge(
                tx,
                challenge_id=new_id(),
                purpose="add_passkey",
                challenge=challenge,
                invite_id=invite.id,
                user_id=user_id,
                now=now,
                expires_at=now + CHALLENGE_TTL,
            )
        return self._auth._creation_options(user_id, account.email, account.display_name, challenge)

    async def recover(
        self, token: str, credential: dict[str, Any], now: datetime, client: ClientInfo
    ) -> tuple[Registered, NewSession]:
        """Finish an AUTH-8 recovery: a new passkey on her account, fresh recovery codes (the
        old ones are deleted), the invite spent and a new session."""
        auth = self._auth
        async with auth._attempt("recovery", client.ip_hash, now) as attempt:
            await auth._guard(attempt)
            auth._refuse_if_locked(attempt)
            invite, user_id = await self._recovery_invite(token, now)
            attempt.user_id = user_id
            challenge = _client_challenge(credential)
            if challenge is None:
                raise RegistrationFailed
            async with system_transaction(self._db) as tx:
                spent = await repo.consume_challenge(tx, "add_passkey", challenge, now)
            if spent is None or spent.invite_id != invite.id or spent.user_id != user_id:
                raise InviteInvalid
            verified = auth._verify_new_passkey(credential, challenge)
            codes, hashes = await _new_recovery_codes()
            async with user_transaction(self._db, user_id) as tx:
                account = await repo.account(tx, user_id)
                if account is None or not await repo.use_invite(tx, invite.id, user_id, now):
                    raise InviteInvalid
                await auth._store_passkey(tx, user_id, verified, credential, now)
                await repo.delete_recovery_codes(tx, user_id)
                await repo.insert_recovery_codes(tx, user_id, hashes)
                await repo.revoke_recovery_invites(tx, user_id, now)
                session = await auth._start_session(tx, user_id, now, client)
        registered = Registered(
            user_id=user_id, display_name=account.display_name, recovery_codes=codes
        )
        return registered, session

    async def role(self, session: SessionContext) -> str | None:
        async with user_transaction(self._db, session.user_id) as tx:
            return await repo.user_role(tx, session.user_id)
