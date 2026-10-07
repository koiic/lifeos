"""auth: Repository layer: SQL only (plan 4.2).

Pre-auth lookups go through the CR-003 SECURITY DEFINER functions; everything else runs in a
`user_transaction` (RLS) or touches the system tables `invites` and `auth_challenges`.
"""

import uuid
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


# ---------- invites and challenges (system tables) ----------


async def find_valid_invite(tx: Transaction, token_hash: bytes, now: datetime) -> Invite | None:
    row = (
        await tx.execute(
            text(
                "SELECT id, email::text AS email FROM invites WHERE token_hash = :hash"
                " AND used_at IS NULL AND revoked_at IS NULL AND expires_at > :now"
            ),
            {"hash": token_hash, "now": now},
        )
    ).one_or_none()
    return Invite(row.id, row.email) if row else None


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
) -> None:
    await tx.execute(
        text(
            "INSERT INTO invites (id, token_hash, email, created_by, expires_at, created_at)"
            " VALUES (:id, :hash, :email, :created_by, :expires_at, :now)"
        ),
        {
            "id": invite_id,
            "hash": token_hash,
            "email": email,
            "created_by": created_by,
            "expires_at": expires_at,
            "now": now,
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
    tx: Transaction, purpose: str, challenge: bytes, now: datetime
) -> Challenge | None:
    """Use a live challenge once; None when unknown, used, expired or for another purpose."""
    row = (
        await tx.execute(
            text(
                "UPDATE auth_challenges SET used_at = :now"
                " WHERE challenge = :challenge AND purpose = :purpose"
                " AND used_at IS NULL AND expires_at > :now RETURNING id, invite_id, user_id"
            ),
            {"challenge": challenge, "purpose": purpose, "now": now},
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
) -> None:
    await tx.execute(
        text(
            "INSERT INTO sessions (id, user_id, token_hash, created_at, last_seen_at, expires_at)"
            " VALUES (:id, :user_id, :hash, :now, :now, :expires_at)"
        ),
        {
            "id": session_id,
            "user_id": user_id,
            "hash": token_hash,
            "now": now,
            "expires_at": expires_at,
        },
    )


async def session_times(tx: Transaction, session_id: uuid.UUID) -> SessionTimes | None:
    row = (
        await tx.execute(
            text("SELECT created_at, last_seen_at, expires_at FROM sessions WHERE id = :id"),
            {"id": session_id},
        )
    ).one_or_none()
    return SessionTimes(row.created_at, row.last_seen_at, row.expires_at) if row else None


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
