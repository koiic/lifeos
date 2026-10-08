"""auth: Repository layer: SQL only (plan 4.2).

Pre-auth lookups go through the CR-003 SECURITY DEFINER functions; everything else runs in a
`user_transaction` (RLS) or touches the system tables `invites` and `auth_challenges`.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.platform.db import Transaction
from app.platform.ids import new_id


class EmailTaken(Exception):
    """users.email is unique."""


class CredentialTaken(Exception):
    """webauthn_credentials.credential_id is unique."""


@dataclass(frozen=True)
class Invite:
    id: uuid.UUID
    email: str | None
    recover_user_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Challenge:
    id: uuid.UUID
    invite_id: uuid.UUID | None
    user_id: uuid.UUID | None


@dataclass(frozen=True)
class StoredCredential:
    user_id: uuid.UUID
    public_key: bytes
    sign_count: int


@dataclass(frozen=True)
class SessionRef:
    id: uuid.UUID
    user_id: uuid.UUID
    expires_at: datetime
    revoked: bool


@dataclass(frozen=True)
class SessionTimes:
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    reauth_at: datetime | None


# ---------- invites and challenges (system tables) ----------


_INVITE = (
    "SELECT id, email::text AS email, recover_user_id FROM invites"
    " WHERE token_hash = :hash AND used_at IS NULL AND revoked_at IS NULL AND expires_at > :now"
)
REGISTRATION_INVITE = _INVITE + " AND recover_user_id IS NULL"
RECOVERY_INVITE = _INVITE + " AND recover_user_id IS NOT NULL"


async def find_valid_invite(
    tx: Transaction, token_hash: bytes, now: datetime, *, recovery: bool = False
) -> Invite | None:
    """A live invite of the requested kind: registration (`recover_user_id` null) or recovery
    (CR-018); a token of the other kind is not found."""
    query = RECOVERY_INVITE if recovery else REGISTRATION_INVITE
    row = (await tx.execute(text(query), {"hash": token_hash, "now": now})).one_or_none()
    return Invite(row.id, row.email, row.recover_user_id) if row else None


async def use_invite(
    tx: Transaction, invite_id: uuid.UUID, user_id: uuid.UUID, now: datetime
) -> bool:
    """Mark the invite used; False when it was used, revoked or expired meanwhile."""
    row = (
        await tx.execute(
            text(
                "UPDATE invites SET used_at = :now, used_by = :user_id WHERE id = :id"
                " AND used_at IS NULL AND revoked_at IS NULL AND expires_at > :now RETURNING id"
            ),
            {"id": invite_id, "user_id": user_id, "now": now},
        )
    ).one_or_none()
    return row is not None


async def insert_invite(
    tx: Transaction,
    *,
    invite_id: uuid.UUID,
    token_hash: bytes,
    email: str | None,
    created_by: uuid.UUID,
    expires_at: datetime,
    now: datetime,
    recover_user_id: uuid.UUID | None = None,
) -> None:
    await tx.execute(
        text(
            "INSERT INTO invites"
            " (id, token_hash, email, created_by, expires_at, created_at, recover_user_id)"
            " VALUES (:id, :hash, :email, :created_by, :expires_at, :now, :recover)"
        ),
        {
            "id": invite_id,
            "hash": token_hash,
            "email": email,
            "created_by": created_by,
            "expires_at": expires_at,
            "now": now,
            "recover": recover_user_id,
        },
    )


# Spent and expired challenges are kept a day (enough to investigate), then deleted as new ones
# are issued, so the unauthenticated options endpoints cannot grow the table without bound.
CHALLENGE_RETENTION = timedelta(days=1)


async def insert_challenge(
    tx: Transaction,
    *,
    challenge_id: uuid.UUID,
    purpose: str,
    challenge: bytes,
    now: datetime,
    expires_at: datetime,
    invite_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    await tx.execute(
        text("DELETE FROM auth_challenges WHERE expires_at < :cutoff"),
        {"cutoff": now - CHALLENGE_RETENTION},
    )
    await tx.execute(
        text(
            "INSERT INTO auth_challenges (id, purpose, challenge, invite_id, user_id, expires_at)"
            " VALUES (:id, :purpose, :challenge, :invite_id, :user_id, :expires_at)"
        ),
        {
            "id": challenge_id,
            "purpose": purpose,
            "challenge": challenge,
            "invite_id": invite_id,
            "user_id": user_id,
            "expires_at": expires_at,
        },
    )


async def consume_challenge(
    tx: Transaction, purpose: str | tuple[str, ...], challenge: bytes, now: datetime
) -> Challenge | None:
    """Use a live challenge once; None when unknown, used, expired or for another purpose."""
    purposes = [purpose] if isinstance(purpose, str) else list(purpose)
    row = (
        await tx.execute(
            text(
                "UPDATE auth_challenges SET used_at = :now"
                " WHERE challenge = :challenge AND purpose = ANY(:purposes)"
                " AND used_at IS NULL AND expires_at > :now RETURNING id, invite_id, user_id"
            ),
            {"challenge": challenge, "purposes": purposes, "now": now},
        )
    ).one_or_none()
    return Challenge(row.id, row.invite_id, row.user_id) if row else None


# ---------- pre-auth lookups (CR-003 functions) ----------


async def find_user_id_by_email(tx: Transaction, email: str) -> uuid.UUID | None:
    row = (
        await tx.execute(
            text("SELECT user_id FROM auth_find_user_by_email(:email)"), {"email": email}
        )
    ).one_or_none()
    return row.user_id if row else None


async def find_credential(tx: Transaction, credential_id: bytes) -> StoredCredential | None:
    row = (
        await tx.execute(
            text("SELECT user_id, public_key, sign_count FROM auth_find_credential(:id)"),
            {"id": credential_id},
        )
    ).one_or_none()
    return StoredCredential(row.user_id, row.public_key, row.sign_count) if row else None


async def find_session(tx: Transaction, token_hash: bytes) -> SessionRef | None:
    row = (
        await tx.execute(
            text("SELECT session_id, user_id, expires_at, revoked FROM auth_find_session(:hash)"),
            {"hash": token_hash},
        )
    ).one_or_none()
    return SessionRef(row.session_id, row.user_id, row.expires_at, row.revoked) if row else None


# ---------- the user's own rows (user_transaction) ----------


async def insert_user(
    tx: Transaction,
    *,
    user_id: uuid.UUID,
    email: str,
    display_name: str,
    dek_wrapped: bytes,
    kek_version: int,
) -> None:
    try:
        async with tx.begin_nested():
            await tx.execute(
                text(
                    "INSERT INTO users (id, email, display_name, dek_wrapped, kek_version)"
                    " VALUES (:id, :email, :name, :dek, :kek)"
                ),
                {
                    "id": user_id,
                    "email": email,
                    "name": display_name,
                    "dek": dek_wrapped,
                    "kek": kek_version,
                },
            )
    except IntegrityError:
        raise EmailTaken from None
    await tx.execute(text("INSERT INTO user_settings (user_id) VALUES (:id)"), {"id": user_id})


@dataclass(frozen=True)
class Account:
    email: str
    display_name: str


async def account(tx: Transaction, user_id: uuid.UUID) -> Account | None:
    """The active (not deleted) account's email and display name."""
    row = (
        await tx.execute(
            text(
                "SELECT email::text AS email, display_name FROM users"
                " WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": user_id},
        )
    ).one_or_none()
    return Account(row.email, row.display_name) if row else None


async def active_display_name(tx: Transaction, user_id: uuid.UUID) -> str | None:
    """The user's display name, or None when the account does not exist or is deleted."""
    row = (
        await tx.execute(
            text("SELECT display_name FROM users WHERE id = :id AND deleted_at IS NULL"),
            {"id": user_id},
        )
    ).one_or_none()
    return row.display_name if row else None


async def insert_credential(
    tx: Transaction,
    *,
    user_id: uuid.UUID,
    credential_id: bytes,
    public_key: bytes,
    sign_count: int,
    transports: list[str],
    aaguid: uuid.UUID | None,
    backup_eligible: bool,
    backed_up: bool,
    now: datetime,
) -> None:
    try:
        async with tx.begin_nested():
            await tx.execute(
                text(
                    "INSERT INTO webauthn_credentials (id, user_id, credential_id, public_key,"
                    " sign_count, transports, aaguid, backup_eligible, backed_up, created_at)"
                    " VALUES (:id, :user_id, :credential_id, :public_key, :sign_count,"
                    " :transports, :aaguid, :be, :bs, :now)"
                ),
                {
                    "id": new_id(),
                    "user_id": user_id,
                    "credential_id": credential_id,
                    "public_key": public_key,
                    "sign_count": sign_count,
                    "transports": transports,
                    "aaguid": aaguid,
                    "be": backup_eligible,
                    "bs": backed_up,
                    "now": now,
                },
            )
    except IntegrityError:
        raise CredentialTaken from None


async def record_credential_use(
    tx: Transaction, credential_id: bytes, sign_count: int, backed_up: bool, now: datetime
) -> bool:
    """Store the new sign count; False when the stored count is already as high (12.3: checked
    when non-zero), e.g. a concurrent sign-in with the same counter."""
    row = (
        await tx.execute(
            text(
                "UPDATE webauthn_credentials SET sign_count = :sign_count, backed_up = :bs,"
                " last_used_at = :now WHERE credential_id = :id"
                " AND (sign_count < :sign_count OR (sign_count = 0 AND :sign_count = 0))"
                " RETURNING id"
            ),
            {"id": credential_id, "sign_count": sign_count, "bs": backed_up, "now": now},
        )
    ).one_or_none()
    return row is not None


async def insert_recovery_codes(tx: Transaction, user_id: uuid.UUID, hashes: list[str]) -> None:
    await tx.execute(
        text("INSERT INTO recovery_codes (id, user_id, code_hash) VALUES (:id, :user_id, :hash)"),
        [{"id": new_id(), "user_id": user_id, "hash": h} for h in hashes],
    )


async def unused_recovery_codes(tx: Transaction, user_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
    rows = await tx.execute(
        text(
            "SELECT id, code_hash FROM recovery_codes WHERE user_id = :user_id"
            " AND used_at IS NULL ORDER BY id"
        ),
        {"user_id": user_id},
    )
    return [(row.id, row.code_hash) for row in rows]


async def use_recovery_code(tx: Transaction, code_id: uuid.UUID, now: datetime) -> bool:
    """Spend the code; False when a concurrent attempt spent it first."""
    row = (
        await tx.execute(
            text(
                "UPDATE recovery_codes SET used_at = :now WHERE id = :id AND used_at IS NULL"
                " RETURNING id"
            ),
            {"id": code_id, "now": now},
        )
    ).one_or_none()
    return row is not None


async def insert_session(
    tx: Transaction,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    token_hash: bytes,
    now: datetime,
    expires_at: datetime,
    ip_hash: bytes,
    device_label: str,
) -> None:
    """A new session; signing in is a fresh verification, so `reauth_at` starts now (CR-017)."""
    await tx.execute(
        text(
            "INSERT INTO sessions (id, user_id, token_hash, created_at, last_seen_at, expires_at,"
            " ip_hash, device_label, reauth_at)"
            " VALUES (:id, :user_id, :hash, :now, :now, :expires_at, :ip_hash, :device, :now)"
        ),
        {
            "id": session_id,
            "user_id": user_id,
            "hash": token_hash,
            "now": now,
            "expires_at": expires_at,
            "ip_hash": ip_hash,
            "device": device_label,
        },
    )


async def session_times(tx: Transaction, session_id: uuid.UUID) -> SessionTimes | None:
    row = (
        await tx.execute(
            text(
                "SELECT created_at, last_seen_at, expires_at, reauth_at FROM sessions"
                " WHERE id = :id"
            ),
            {"id": session_id},
        )
    ).one_or_none()
    if row is None:
        return None
    return SessionTimes(row.created_at, row.last_seen_at, row.expires_at, row.reauth_at)


async def slide_session(
    tx: Transaction, session_id: uuid.UUID, now: datetime, expires_at: datetime
) -> None:
    await tx.execute(
        text("UPDATE sessions SET last_seen_at = :now, expires_at = :expires_at WHERE id = :id"),
        {"id": session_id, "now": now, "expires_at": expires_at},
    )


async def revoke_session(tx: Transaction, session_id: uuid.UUID, now: datetime) -> None:
    await tx.execute(
        text("UPDATE sessions SET revoked_at = :now WHERE id = :id AND revoked_at IS NULL"),
        {"id": session_id, "now": now},
    )


# ---------- password + TOTP (user_transaction) ----------


@dataclass(frozen=True)
class PasswordCredentials:
    password_hash: str
    totp_secret_enc: bytes | None
    totp_enabled: bool


@dataclass(frozen=True)
class UserKey:
    dek_wrapped: bytes
    kek_version: int


async def insert_password_credentials(
    tx: Transaction,
    user_id: uuid.UUID,
    password_hash: str,
    totp_secret_enc: bytes,
) -> None:
    await tx.execute(
        text(
            "INSERT INTO password_credentials (user_id, password_hash, totp_secret_enc)"
            " VALUES (:user_id, :hash, :secret)"
        ),
        {"user_id": user_id, "hash": password_hash, "secret": totp_secret_enc},
    )


async def password_credentials(tx: Transaction, user_id: uuid.UUID) -> PasswordCredentials | None:
    row = (
        await tx.execute(
            text(
                "SELECT password_hash, totp_secret_enc, totp_enabled FROM password_credentials"
                " WHERE user_id = :user_id"
            ),
            {"user_id": user_id},
        )
    ).one_or_none()
    if row is None:
        return None
    return PasswordCredentials(row.password_hash, row.totp_secret_enc, row.totp_enabled)


async def enable_totp(tx: Transaction, user_id: uuid.UUID) -> bool:
    """Confirm TOTP; False when it already was."""
    row = (
        await tx.execute(
            text(
                "UPDATE password_credentials SET totp_enabled = true"
                " WHERE user_id = :user_id AND NOT totp_enabled RETURNING user_id"
            ),
            {"user_id": user_id},
        )
    ).one_or_none()
    return row is not None


async def user_key(tx: Transaction, user_id: uuid.UUID) -> UserKey | None:
    row = (
        await tx.execute(
            text("SELECT dek_wrapped, kek_version FROM users WHERE id = :id"), {"id": user_id}
        )
    ).one_or_none()
    return UserKey(row.dek_wrapped, row.kek_version) if row else None


async def is_activated(tx: Transaction, user_id: uuid.UUID) -> bool:
    """CR-014: an account is active once it has a passkey or a confirmed TOTP."""
    active: bool = (
        await tx.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM webauthn_credentials WHERE user_id = :id)"
                " OR EXISTS (SELECT 1 FROM password_credentials"
                " WHERE user_id = :id AND totp_enabled)"
            ),
            {"id": user_id},
        )
    ).scalar_one()
    return active


# ---------- auth events (system table, append-only for the API: CR-010) ----------


async def insert_auth_event(
    tx: Transaction,
    *,
    user_id: uuid.UUID | None,
    kind: str,
    success: bool,
    ip_hash: bytes,
    now: datetime,
) -> None:
    await tx.execute(
        text(
            "INSERT INTO auth_events (user_id, kind, success, ip_hash, at)"
            " VALUES (:user_id, :kind, :success, :ip_hash, :now)"
        ),
        {"user_id": user_id, "kind": kind, "success": success, "ip_hash": ip_hash, "now": now},
    )


FAILURES_BY_USER = (
    "SELECT at FROM auth_events WHERE user_id = :value AND NOT success"
    " AND kind = ANY(:kinds) AND at > :since ORDER BY at DESC LIMIT :limit"
)
FAILURES_BY_IP = (
    "SELECT at FROM auth_events WHERE ip_hash = :value AND NOT success"
    " AND kind = ANY(:kinds) AND at > :since ORDER BY at DESC LIMIT :limit"
)


async def recent_failures(
    tx: Transaction,
    *,
    kinds: Sequence[str],
    since: datetime,
    limit: int,
    user_id: uuid.UUID | None = None,
    ip_hash: bytes | None = None,
) -> list[datetime]:
    """The newest failed attempts after `since`, for one account or one IP, newest first."""
    query = FAILURES_BY_USER if user_id is not None else FAILURES_BY_IP
    value = user_id if user_id is not None else ip_hash
    rows = await tx.execute(
        text(query), {"value": value, "kinds": list(kinds), "since": since, "limit": limit}
    )
    return [row.at for row in rows]


async def last_totp_success(tx: Transaction, user_id: uuid.UUID) -> datetime | None:
    """When a TOTP code last succeeded for this account (replay protection, 12.3)."""
    at: datetime | None = (
        await tx.execute(
            text(
                "SELECT max(at) FROM auth_events WHERE user_id = :user_id AND success"
                " AND kind IN ('totp', 'signin_password')"
            ),
            {"user_id": user_id},
        )
    ).scalar_one()
    return at


# ---------- concurrency and per-session counts ----------


async def try_advisory_lock(tx: Transaction, key: str) -> bool:
    """A transaction-scoped Postgres advisory lock on `key` (shared by every API worker);
    False when another transaction holds it."""
    locked: bool = (
        await tx.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )
    ).scalar_one()
    return locked


async def count_session_request(
    tx: Transaction, session_id: uuid.UUID, now: datetime, window_over: datetime
) -> tuple[datetime, int]:
    """Count one request in the session's current window (a new window when the stored one
    started at or before `window_over`); returns the window start and the count so far."""
    row = (
        await tx.execute(
            text(
                "INSERT INTO session_request_counts AS c (session_id, window_start, count)"
                " VALUES (:id, :now, 1)"
                " ON CONFLICT (session_id) DO UPDATE SET"
                " window_start = CASE WHEN c.window_start <= :over THEN :now"
                " ELSE c.window_start END,"
                " count = CASE WHEN c.window_start <= :over THEN 1 ELSE c.count + 1 END"
                " RETURNING window_start, count"
            ),
            {"id": session_id, "now": now, "over": window_over},
        )
    ).one()
    count: int = row._mapping["count"]  # `row.count` is the Row method
    return row.window_start, count


# ---------- session management, passkeys, app lock, recovery (T08) ----------


@dataclass(frozen=True)
class SessionItem:
    id: uuid.UUID
    device_label: str | None
    created_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class PasskeyItem:
    id: uuid.UUID
    credential_id: bytes
    nickname: str
    created_at: datetime
    last_used_at: datetime | None
    backed_up: bool


async def active_sessions(tx: Transaction, user_id: uuid.UUID, now: datetime) -> list[SessionItem]:
    rows = await tx.execute(
        text(
            "SELECT id, device_label, created_at, last_seen_at FROM sessions"
            " WHERE user_id = :user_id AND revoked_at IS NULL AND expires_at > :now"
            " ORDER BY created_at"
        ),
        {"user_id": user_id, "now": now},
    )
    return [SessionItem(r.id, r.device_label, r.created_at, r.last_seen_at) for r in rows]


async def revoke_user_session(
    tx: Transaction, user_id: uuid.UUID, session_id: uuid.UUID, now: datetime
) -> bool:
    """Revoke one of the user's live sessions; False when there is no such session."""
    row = (
        await tx.execute(
            text(
                "UPDATE sessions SET revoked_at = :now WHERE id = :id AND user_id = :user_id"
                " AND revoked_at IS NULL AND expires_at > :now RETURNING id"
            ),
            {"id": session_id, "user_id": user_id, "now": now},
        )
    ).one_or_none()
    return row is not None


async def revoke_all_sessions(tx: Transaction, user_id: uuid.UUID, now: datetime) -> int:
    rows = await tx.execute(
        text(
            "UPDATE sessions SET revoked_at = :now WHERE user_id = :user_id"
            " AND revoked_at IS NULL RETURNING id"
        ),
        {"user_id": user_id, "now": now},
    )
    return len(rows.all())


async def set_reauth(tx: Transaction, session_id: uuid.UUID, now: datetime) -> None:
    await tx.execute(
        text("UPDATE sessions SET reauth_at = :now WHERE id = :id"), {"id": session_id, "now": now}
    )


async def passkeys(tx: Transaction, user_id: uuid.UUID) -> list[PasskeyItem]:
    rows = await tx.execute(
        text(
            "SELECT id, credential_id, nickname, created_at, last_used_at, backed_up"
            " FROM webauthn_credentials WHERE user_id = :user_id ORDER BY created_at, id"
        ),
        {"user_id": user_id},
    )
    return [
        PasskeyItem(r.id, r.credential_id, r.nickname, r.created_at, r.last_used_at, r.backed_up)
        for r in rows
    ]


async def delete_passkey(tx: Transaction, user_id: uuid.UUID, passkey_id: uuid.UUID) -> bool:
    row = (
        await tx.execute(
            text(
                "DELETE FROM webauthn_credentials WHERE id = :id AND user_id = :user_id"
                " RETURNING id"
            ),
            {"id": passkey_id, "user_id": user_id},
        )
    ).one_or_none()
    return row is not None


async def delete_recovery_codes(tx: Transaction, user_id: uuid.UUID) -> None:
    await tx.execute(
        text("DELETE FROM recovery_codes WHERE user_id = :user_id"), {"user_id": user_id}
    )


async def pin_hash(tx: Transaction, user_id: uuid.UUID) -> str | None:
    value: str | None = (
        await tx.execute(
            text("SELECT app_lock_pin_hash FROM user_settings WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
    ).scalar_one_or_none()
    return value


async def set_app_lock(
    tx: Transaction,
    user_id: uuid.UUID,
    *,
    pin_hash: str | None,
    change_pin: bool,
    timeout_s: int | None,
) -> None:
    await tx.execute(
        text(
            "UPDATE user_settings SET"
            " app_lock_pin_hash = CASE WHEN :change_pin THEN :pin_hash"
            " ELSE app_lock_pin_hash END,"
            " app_lock_timeout_s = COALESCE(:timeout_s, app_lock_timeout_s)"
            " WHERE user_id = :user_id"
        ),
        {
            "user_id": user_id,
            "pin_hash": pin_hash,
            "change_pin": change_pin,
            "timeout_s": timeout_s,
        },
    )


async def bump_pin_failures(tx: Transaction, session_id: uuid.UUID) -> int:
    """Count one PIN try on this session before checking it (CR-021); returns the count so far.
    Atomic on the row, so concurrent tries each get their own number."""
    count: int = (
        await tx.execute(
            text(
                "UPDATE sessions SET pin_failures = pin_failures + 1 WHERE id = :id"
                " RETURNING pin_failures"
            ),
            {"id": session_id},
        )
    ).scalar_one()
    return count


async def reset_pin_failures(tx: Transaction, session_id: uuid.UUID) -> None:
    await tx.execute(
        text("UPDATE sessions SET pin_failures = 0 WHERE id = :id"), {"id": session_id}
    )


async def spend_pending_challenges(tx: Transaction, user_id: uuid.UUID, now: datetime) -> None:
    """Spend the account's unused passkey-add, re-auth and unlock challenges, so none issued to a
    session can be finished after that session is revoked (recovery-invite challenges, which
    carry their invite, are left alone)."""
    await tx.execute(
        text(
            "UPDATE auth_challenges SET used_at = :now WHERE user_id = :user_id"
            " AND used_at IS NULL AND invite_id IS NULL"
            " AND purpose IN ('add_passkey', 'reauth', 'unlock')"
        ),
        {"user_id": user_id, "now": now},
    )


async def revoke_recovery_invites(tx: Transaction, user_id: uuid.UUID, now: datetime) -> None:
    """Revoke the account's unused recovery invites (only the newest link may work)."""
    await tx.execute(
        text(
            "UPDATE invites SET revoked_at = :now WHERE recover_user_id = :user_id"
            " AND used_at IS NULL AND revoked_at IS NULL"
        ),
        {"user_id": user_id, "now": now},
    )


async def lock_passkeys(tx: Transaction, user_id: uuid.UUID) -> list[uuid.UUID]:
    """Her passkey ids, locked for the rest of the transaction (serialises removals)."""
    rows = await tx.execute(
        text("SELECT id FROM webauthn_credentials WHERE user_id = :user_id FOR UPDATE"),
        {"user_id": user_id},
    )
    return [row.id for row in rows]


async def user_role(tx: Transaction, user_id: uuid.UUID) -> str | None:
    role: str | None = (
        await tx.execute(
            text("SELECT role FROM users WHERE id = :id AND deleted_at IS NULL"), {"id": user_id}
        )
    ).scalar_one_or_none()
    return role


async def insert_audit(
    tx: Transaction,
    *,
    actor_user_id: uuid.UUID,
    actor_role: str,
    action: str,
    target_user_id: uuid.UUID | None,
    ip_hash: bytes,
    now: datetime,
) -> None:
    await tx.execute(
        text(
            "INSERT INTO audit_log (actor_user_id, actor_role, action, target_user_id, at, ip_hash)"
            " VALUES (:actor, :role, :action, :target, :now, :ip_hash)"
        ),
        {
            "actor": actor_user_id,
            "role": actor_role,
            "action": action,
            "target": target_user_id,
            "now": now,
            "ip_hash": ip_hash,
        },
    )


async def hold_live_session(tx: Transaction, session_id: uuid.UUID) -> bool:
    """Share-lock the session row if it is still live, so a revocation cannot commit between this
    check and the rest of the transaction (it waits, then spends what this inserted)."""
    row = (
        await tx.execute(
            text("SELECT 1 FROM sessions WHERE id = :id AND revoked_at IS NULL FOR SHARE"),
            {"id": session_id},
        )
    ).one_or_none()
    return row is not None
