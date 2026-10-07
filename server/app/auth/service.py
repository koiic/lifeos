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
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from typing import Any

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
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from webauthn.registration.verify_registration_response import VerifiedRegistration

from app.auth import repo
from app.auth.schemas import Registered, Registration, SignedIn
from app.platform.crypto import Keyring, generate_data_key, wrap_dek
from app.platform.db import Database, Transaction, system_transaction, user_transaction
from app.platform.ids import new_id

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


class AuthError(Exception):
    status = 400
    detail = "The request could not be completed."


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


@dataclass(frozen=True)
class SessionContext:
    user_id: uuid.UUID
    session_id: uuid.UUID


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
        _dummy_hash()  # computed now, so the first recovery attempt is not slower than the rest

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
        self, data: Registration, credential: dict[str, Any], now: datetime
    ) -> tuple[Registered, NewSession]:
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
        kek_version, dek_wrapped = wrap_dek(self._keyring, generate_data_key(), user_id)
        codes = [_new_code() for _ in range(RECOVERY_CODES)]
        hashes = await asyncio.to_thread(lambda: [CODE_HASHER.hash(_normal_code(c)) for c in codes])
        async with user_transaction(self._db, user_id) as tx:
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
            await self._store_passkey(tx, user_id, verified, credential, now)
            await repo.insert_recovery_codes(tx, user_id, hashes)
            session = await self._start_session(tx, user_id, now)
        return Registered(user_id=user_id, display_name=data.name, recovery_codes=codes), session

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
        self, credential: dict[str, Any], now: datetime
    ) -> tuple[SignedIn, NewSession]:
        challenge = _client_challenge(credential)
        credential_id = _raw_id(credential)
        if challenge is None or credential_id is None:
            raise SignInFailed
        async with system_transaction(self._db) as tx:
            spent = await repo.consume_challenge(tx, "signin", challenge, now)
        if spent is None:
            raise SignInFailed
        async with system_transaction(self._db) as tx:
            stored = await repo.find_credential(tx, credential_id)
        if stored is None or _user_handle(credential) != stored.user_id.bytes:
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
            # Conditional on the stored count, so concurrent sign-ins cannot move it backwards.
            if not await repo.record_credential_use(
                tx, credential_id, verified.new_sign_count, verified.credential_backed_up, now
            ):
                raise SignInFailed
            session = await self._start_session(tx, stored.user_id, now)
        return SignedIn(user_id=stored.user_id, display_name=name), session

    async def recover(self, email: str, code: str, now: datetime) -> dict[str, Any]:
        """Spend a recovery code; returns creation options for a new passkey. No session is
        issued until that passkey is verified (CR-013: "forces new passkey setup")."""
        typed = _normal_code(code)
        async with system_transaction(self._db) as tx:
            user_id = await repo.find_user_id_by_email(tx, email)
        # An unknown email runs the same queries for a random id (RLS returns no rows) and the
        # same hash checks, so failures cost the same whether or not the account exists.
        known = user_id is not None
        subject = user_id or uuid.uuid4()
        # Read, then hash with no connection held (argon2 is slow by design), then spend the code
        # with a conditional update, so concurrent attempts cannot both use it.
        async with user_transaction(self._db, subject) as tx:
            active = await repo.active_display_name(tx, subject) is not None
            codes = await repo.unused_recovery_codes(tx, subject)
        code_id = await asyncio.to_thread(_matching_code, codes if active else [], typed)
        if not known or code_id is None:
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
        self, credential: dict[str, Any], now: datetime
    ) -> tuple[SignedIn, NewSession]:
        """Finish a recovery sign-in: verify the new passkey for the user the recovery
        challenge names, store it and only then start a session (CR-013)."""
        challenge = _client_challenge(credential)
        if challenge is None:
            raise RegistrationFailed
        async with system_transaction(self._db) as tx:
            spent = await repo.consume_challenge(tx, "add_passkey", challenge, now)
        if spent is None or spent.user_id is None:
            raise RegistrationFailed
        verified = self._verify_new_passkey(credential, challenge)
        async with user_transaction(self._db, spent.user_id) as tx:
            account = await repo.account(tx, spent.user_id)
            if account is None:
                raise RegistrationFailed
            await self._store_passkey(tx, spent.user_id, verified, credential, now)
            session = await self._start_session(tx, spent.user_id, now)
        return SignedIn(user_id=spent.user_id, display_name=account.display_name), session

    # ----- sessions -----

    async def _start_session(
        self, tx: Transaction, user_id: uuid.UUID, now: datetime
    ) -> NewSession:
        token, raw = _new_token()
        await repo.insert_session(
            tx,
            session_id=new_id(),
            user_id=user_id,
            token_hash=_sha256(raw),
            now=now,
            expires_at=now + SESSION_IDLE,
        )
        return NewSession(token, int(SESSION_IDLE.total_seconds()))

    async def _find_session(self, token: str) -> repo.SessionRef | None:
        raw = _decode_token(token)
        if raw is None:
            return None
        async with system_transaction(self._db) as tx:
            return await repo.find_session(tx, _sha256(raw))

    async def authenticate(
        self, token: str, now: datetime
    ) -> tuple[SessionContext, NewSession | None]:
        """The session's user, and a refreshed cookie when the expiry slid."""
        ref = await self._find_session(token)
        if ref is None or ref.revoked or ref.expires_at <= now:
            raise NotSignedIn
        refreshed = None
        async with user_transaction(self._db, ref.user_id) as tx:
            times = await repo.session_times(tx, ref.id)
            if times is None or await repo.active_display_name(tx, ref.user_id) is None:
                raise NotSignedIn
            if now - times.last_seen_at >= SLIDE_EVERY:
                expires_at = min(now + SESSION_IDLE, times.created_at + SESSION_ABSOLUTE)
                await repo.slide_session(tx, ref.id, now, expires_at)
                refreshed = NewSession(token, int((expires_at - now).total_seconds()))
        return SessionContext(ref.user_id, ref.id), refreshed

    async def sign_out(self, token: str, now: datetime) -> None:
        ref = await self._find_session(token)
        if ref is None:
            return
        async with user_transaction(self._db, ref.user_id) as tx:
            await repo.revoke_session(tx, ref.id, now)
