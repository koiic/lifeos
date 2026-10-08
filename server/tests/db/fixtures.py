"""One minimal valid row per user-owned table, for the generated RLS test.

Every user-owned table in the schema must have an entry; the completeness test fails otherwise, so a
new table cannot ship without being covered by the isolation test.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

import asyncpg

ENC = b"\x01" + b"\x00" * 12 + b"ciphertext" + b"\x00" * 16
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)

RowFactory = Callable[[asyncpg.Connection, uuid.UUID], Awaitable[None]]


def _id() -> uuid.UUID:
    return uuid.uuid4()


async def _medication(conn: asyncpg.Connection, user: uuid.UUID) -> uuid.UUID:
    med = _id()
    await conn.execute(
        "INSERT INTO medications (id, user_id, start_date, timezone, payload_enc)"
        " VALUES ($1, $2, $3, 'Europe/London', $4)",
        med,
        user,
        date(2026, 10, 1),
        ENC,
    )
    return med


async def _session(conn: asyncpg.Connection, user: uuid.UUID) -> uuid.UUID:
    session = _id()
    await conn.execute(
        "INSERT INTO sessions (id, user_id, token_hash, expires_at) VALUES ($1, $2, $3, $4)",
        session,
        user,
        _id().bytes,
        NOW,
    )
    return session


def sql(statement: str, *extra: object, with_id: bool = True) -> RowFactory:
    """A factory inserting one row. With `with_id`, `$1` is a new id and `$2` the user; without
    (tables keyed by the user), `$1` is the user. `extra` values follow."""

    async def insert(conn: asyncpg.Connection, user: uuid.UUID) -> None:
        leading = (_id(), user) if with_id else (user,)
        await conn.execute(statement, *leading, *extra)

    return insert


async def _medication_dose(conn: asyncpg.Connection, user: uuid.UUID) -> None:
    med = await _medication(conn, user)
    await conn.execute(
        "INSERT INTO medication_doses (id, user_id, medication_id, scheduled_at)"
        " VALUES ($1, $2, $3, $4)",
        _id(),
        user,
        med,
        NOW,
    )


async def _session_row(conn: asyncpg.Connection, user: uuid.UUID) -> None:
    await _session(conn, user)


async def _medication_row(conn: asyncpg.Connection, user: uuid.UUID) -> None:
    await _medication(conn, user)


async def _webauthn_credential(conn: asyncpg.Connection, user: uuid.UUID) -> None:
    await conn.execute(
        "INSERT INTO webauthn_credentials (id, user_id, credential_id, public_key)"
        " VALUES ($1, $2, $3, $4)",
        _id(),
        user,
        b"credential-" + _id().bytes,
        b"public-key",
    )


async def _push_subscription(conn: asyncpg.Connection, user: uuid.UUID) -> None:
    await conn.execute(
        "INSERT INTO push_subscriptions (id, user_id, endpoint, p256dh, auth)"
        " VALUES ($1, $2, $3, 'key', 'auth')",
        _id(),
        user,
        f"https://push.example/{_id()}",
    )


async def _idempotency_key(conn: asyncpg.Connection, user: uuid.UUID) -> None:
    await conn.execute(
        "INSERT INTO idempotency_keys (key, user_id, method, path, request_hash,"
        " response_status, response_body_enc) VALUES ($1, $2, 'POST', '/x', $3, 200, $4)",
        _id(),
        user,
        b"hash",
        ENC,
    )


# Tables whose primary key is user_id (one row per user) take only the user.
USER_OWNED: dict[str, RowFactory] = {
    "user_settings": sql("INSERT INTO user_settings (user_id) VALUES ($1)", with_id=False),
    "webauthn_credentials": _webauthn_credential,
    "password_credentials": sql(
        "INSERT INTO password_credentials (user_id, password_hash) VALUES ($1, 'argon2id$x')",
        with_id=False,
    ),
    "recovery_codes": sql(
        "INSERT INTO recovery_codes (id, user_id, code_hash) VALUES ($1, $2, 'argon2id$y')"
    ),
    "sessions": _session_row,
    "people": sql("INSERT INTO people (id, user_id, payload_enc) VALUES ($1, $2, $3)", ENC),
    "events": sql(
        "INSERT INTO events (id, user_id, starts_at, ends_at, timezone, reminder_rules,"
        " payload_enc) VALUES ($1, $2, $3, $3, 'Europe/London', '[]', $4)",
        NOW,
        ENC,
    ),
    "tasks": sql(
        "INSERT INTO tasks (id, user_id, timezone, payload_enc)"
        " VALUES ($1, $2, 'Europe/London', $3)",
        ENC,
    ),
    "notes": sql("INSERT INTO notes (id, user_id, payload_enc) VALUES ($1, $2, $3)", ENC),
    "health_profile": sql(
        "INSERT INTO health_profile (user_id, payload_enc) VALUES ($1, $2)", ENC, with_id=False
    ),
    "symptoms": sql(
        "INSERT INTO symptoms (id, user_id, category, payload_enc) VALUES ($1, $2, 'pain', $3)",
        ENC,
    ),
    "daily_logs": sql(
        "INSERT INTO daily_logs (id, user_id, date, payload_enc, client_updated_at)"
        " VALUES ($1, $2, $3, $4, $5)",
        date(2026, 10, 6),
        ENC,
        NOW,
    ),
    "cycles": sql("INSERT INTO cycles (id, user_id, seq, payload_enc) VALUES ($1, $2, 1, $3)", ENC),
    "cycle_predictions": sql(
        "INSERT INTO cycle_predictions (id, user_id, algorithm_version, payload_enc)"
        " VALUES ($1, $2, 'calendar-1.0', $3)",
        ENC,
    ),
    "medications": _medication_row,
    "medication_doses": _medication_dose,
    "reminders": sql(
        "INSERT INTO reminders (id, user_id, kind, fire_at, dedupe_key, payload_enc)"
        " VALUES ($1, $2, 'checkin', $3, 'checkin:2026-10-06', $4)",
        NOW,
        ENC,
    ),
    "push_subscriptions": _push_subscription,
    "imports": sql(
        "INSERT INTO imports (id, user_id, source, status) VALUES ($1, $2, 'csv', 'uploaded')"
    ),
    "exports": sql("INSERT INTO exports (id, user_id, status) VALUES ($1, $2, 'queued')"),
    "outbox_events": sql(
        "INSERT INTO outbox_events (user_id, topic, body) VALUES ($1, 'settings.changed', '{}')",
        with_id=False,
    ),
    "idempotency_keys": _idempotency_key,
}


async def _dose_for(conn: asyncpg.Connection, user: uuid.UUID, medication: uuid.UUID) -> None:
    await conn.execute(
        "INSERT INTO medication_doses (id, user_id, medication_id, scheduled_at)"
        " VALUES ($1, $2, $3, $4)",
        _id(),
        user,
        medication,
        NOW,
    )


# Tables whose row needs a parent row: (create the parent, insert only the target row). The
# cross-user insert test creates the parent as superuser, so the RLS error comes from the target.
WITH_PARENT = {"medication_doses": (_medication, _dose_for)}

SYSTEM_TABLES = {
    "invites",
    "auth_challenges",
    "auth_events",
    "audit_log",
    "pending_deletions",
    "session_request_counts",  # CR-016
}
