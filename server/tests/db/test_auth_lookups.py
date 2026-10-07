"""T03: sign-in lookups before the user is known (spec 7.1 as amended by CR-003)."""

import uuid
from datetime import UTC, datetime

import asyncpg
import pytest

from tests.db.conftest import as_role, create_user

pytestmark = pytest.mark.integration

EXPIRES = datetime(2026, 11, 5, tzinfo=UTC)


async def seed(db: asyncpg.Connection) -> tuple[uuid.UUID, bytes, bytes, uuid.UUID]:
    user = await create_user(db, "Zee@Example.test")
    credential = b"credential-" + uuid.uuid4().bytes
    await db.execute(
        "INSERT INTO webauthn_credentials (id, user_id, credential_id, public_key, sign_count)"
        " VALUES ($1, $2, $3, $4, 7)",
        uuid.uuid4(),
        user,
        credential,
        b"public-key",
    )
    token_hash = uuid.uuid4().bytes
    session = uuid.uuid4()
    await db.execute(
        "INSERT INTO sessions (id, user_id, token_hash, expires_at) VALUES ($1, $2, $3, $4)",
        session,
        user,
        token_hash,
        EXPIRES,
    )
    return user, credential, token_hash, session


async def test_lookups_work_for_lifeos_app_before_the_user_is_known(
    db: asyncpg.Connection,
) -> None:
    user, credential, token_hash, session = await seed(db)
    await as_role(db, "lifeos_app")
    # Under RLS with no user set, the tables themselves show nothing...
    assert await db.fetchval("SELECT count(*) FROM sessions") == 0
    # ...but the lookup functions return exactly what authentication needs.
    found = await db.fetch("SELECT * FROM auth_find_credential($1)", credential)
    assert [dict(r) for r in found] == [
        {"user_id": user, "public_key": b"public-key", "sign_count": 7}
    ]
    found = await db.fetch("SELECT * FROM auth_find_session($1)", token_hash)
    assert [dict(r) for r in found] == [
        {"session_id": session, "user_id": user, "expires_at": EXPIRES, "revoked": False}
    ]
    found = await db.fetch("SELECT * FROM auth_find_user_by_email($1)", "zee@example.TEST")
    assert [dict(r) for r in found] == [{"user_id": user}]


async def test_lookups_return_nothing_for_unknown_keys(db: asyncpg.Connection) -> None:
    await seed(db)
    await as_role(db, "lifeos_app")
    assert await db.fetch("SELECT * FROM auth_find_credential($1)", b"nope") == []
    assert await db.fetch("SELECT * FROM auth_find_session($1)", b"nope") == []
    assert await db.fetch("SELECT * FROM auth_find_user_by_email($1)", "nobody@x.test") == []


async def test_revoked_sessions_are_reported_as_revoked(db: asyncpg.Connection) -> None:
    _, _, token_hash, session = await seed(db)
    await db.execute("UPDATE sessions SET revoked_at = now() WHERE id = $1", session)
    await as_role(db, "lifeos_app")
    [row] = await db.fetch("SELECT revoked FROM auth_find_session($1)", token_hash)
    assert row["revoked"] is True


@pytest.mark.parametrize(
    "role", ["lifeos_admin_ro", "lifeos_jobs", "lifeos_dispatcher", "lifeos_backup"]
)
@pytest.mark.parametrize(
    "call",
    [
        "SELECT * FROM auth_find_credential('x'::bytea)",
        "SELECT * FROM auth_find_session('x'::bytea)",
        "SELECT * FROM auth_find_user_by_email('x')",
    ],
)
async def test_only_lifeos_app_may_execute_the_lookups(
    db: asyncpg.Connection, role: str, call: str
) -> None:
    await as_role(db, role)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        async with db.transaction():
            await db.fetch(call)


async def test_lookups_are_security_definer_with_a_fixed_search_path(
    db: asyncpg.Connection,
) -> None:
    rows = await db.fetch(
        "SELECT proname, prosecdef, proconfig FROM pg_proc WHERE proname LIKE 'auth\\_find\\_%'"
    )
    assert {row["proname"] for row in rows} == {
        "auth_find_credential",
        "auth_find_session",
        "auth_find_user_by_email",
    }
    for row in rows:
        assert row["prosecdef"], row["proname"]
        assert row["proconfig"] == ["search_path=public, pg_temp"], row["proname"]
