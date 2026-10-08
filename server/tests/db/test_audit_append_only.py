"""T07: CR-010 — `audit_log` and `auth_events` are append-only for the API; retention by jobs."""

import uuid

import asyncpg
import pytest

from tests.db.conftest import as_role, create_user

pytestmark = pytest.mark.integration


async def denied(db: asyncpg.Connection, query: str, *args: object) -> bool:
    try:
        async with db.transaction():
            await db.execute(query, *args)
    except asyncpg.InsufficientPrivilegeError:
        return True
    return False


async def test_the_api_can_append_and_read_auth_events(db: asyncpg.Connection) -> None:
    user = await create_user(db, f"ev-{uuid.uuid4()}@example.test")
    await as_role(db, "lifeos_app")
    await db.execute(
        "INSERT INTO auth_events (user_id, kind, success) VALUES ($1, 'signin_passkey', true)",
        user,
    )
    assert await db.fetchval("SELECT count(*) FROM auth_events WHERE user_id = $1", user) == 1


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE auth_events SET success = true",
        "DELETE FROM auth_events",
        "TRUNCATE auth_events",
        "UPDATE audit_log SET action = 'x'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ],
)
async def test_the_api_cannot_rewrite_or_erase_the_trail(
    db: asyncpg.Connection, query: str
) -> None:
    await as_role(db, "lifeos_app")
    assert await denied(db, query)


async def test_the_api_can_append_to_and_read_the_audit_log(db: asyncpg.Connection) -> None:
    await as_role(db, "lifeos_app")
    action = f"test.append-{uuid.uuid4()}"
    await db.execute("INSERT INTO audit_log (actor_role, action) VALUES ('user', $1)", action)
    assert await db.fetchval("SELECT count(*) FROM audit_log WHERE action = $1", action) == 1


async def test_jobs_can_delete_old_auth_events_only(db: asyncpg.Connection) -> None:
    ids = []
    for days in (400, 1):
        ids.append(
            await db.fetchval(
                "INSERT INTO auth_events (kind, success, at)"
                " VALUES ('signin_passkey', false, now() - make_interval(days => $1)) RETURNING id",
                days,
            )
        )
    old, recent = ids
    await as_role(db, "lifeos_jobs")
    # The retention query (10.1, T43) filters on `at` only, the column lifeos_jobs may read.
    await db.execute("DELETE FROM auth_events WHERE at < now() - interval '1 year'")
    assert await denied(db, "UPDATE auth_events SET success = true")
    assert await denied(db, "DELETE FROM audit_log")
    await db.execute("RESET ROLE")
    left = await db.fetch("SELECT id FROM auth_events WHERE id = ANY($1)", [old, recent])
    assert [row["id"] for row in left] == [recent]


async def test_the_lockout_reads_are_indexed(db: asyncpg.Connection) -> None:
    """T07: partial indexes for failures by IP and by account, and TOTP successes by account."""
    rows = await db.fetch("SELECT indexdef FROM pg_indexes WHERE tablename = 'auth_events'")
    definitions = " ".join(row["indexdef"] for row in rows)
    assert "(ip_hash, at) WHERE (NOT success)" in definitions
    assert "(user_id, at) WHERE (NOT success)" in definitions
    assert "(user_id, at) WHERE (success AND (kind = ANY" in definitions
