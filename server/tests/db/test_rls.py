"""T03: generated RLS test — every user table isolates users (spec 7.1 as amended by CR-003).

The table list comes from the database catalog; every user-owned table must appear in
tests/db/fixtures.py, so a new table without RLS or without coverage fails here.
"""

import uuid

import asyncpg
import pytest

from tests.db.conftest import as_role, create_user
from tests.db.fixtures import SYSTEM_TABLES, USER_OWNED, WITH_PARENT

pytestmark = pytest.mark.integration


async def catalog_tables(db: asyncpg.Connection) -> dict[str, tuple[bool, bool]]:
    """table → (row security enabled, forced) for every table in public."""
    rows = await db.fetch(
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'alembic_version'"
    )
    return {row["relname"]: (row["relrowsecurity"], row["relforcerowsecurity"]) for row in rows}


async def test_every_table_is_either_user_owned_or_a_known_system_table(
    db: asyncpg.Connection,
) -> None:
    tables = await catalog_tables(db)
    assert set(tables) == set(USER_OWNED) | SYSTEM_TABLES | {"users"}


async def test_user_owned_tables_have_rls_enabled_and_forced(db: asyncpg.Connection) -> None:
    tables = await catalog_tables(db)
    not_forced = [t for t in [*USER_OWNED, "users"] if tables[t] != (True, True)]
    assert not_forced == []


async def test_only_the_system_tables_lack_rls(db: asyncpg.Connection) -> None:
    tables = await catalog_tables(db)
    assert {t for t, (enabled, _) in tables.items() if not enabled} == SYSTEM_TABLES


async def test_every_user_owned_table_has_a_user_id_column(db: asyncpg.Connection) -> None:
    rows = await db.fetch(
        "SELECT table_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND column_name = 'user_id'"
    )
    with_user_id = {row["table_name"] for row in rows}
    assert set(USER_OWNED) <= with_user_id
    # System tables may carry a nullable user_id (auth_events, auth_challenges) but are not RLS'd.
    assert with_user_id - set(USER_OWNED) <= SYSTEM_TABLES


async def two_users_with_rows(db: asyncpg.Connection, table: str) -> tuple[uuid.UUID, uuid.UUID]:
    alice = await create_user(db, f"alice-{uuid.uuid4()}@example.test")
    bob = await create_user(db, f"bob-{uuid.uuid4()}@example.test")
    if table in USER_OWNED:
        await USER_OWNED[table](db, alice)
        await USER_OWNED[table](db, bob)
    return alice, bob


def key_column(table: str) -> str:
    return "id" if table == "users" else "user_id"


@pytest.mark.parametrize("table", sorted([*USER_OWNED, "users"]))
async def test_lifeos_app_sees_and_changes_only_its_own_rows(
    db: asyncpg.Connection, table: str
) -> None:
    alice, bob = await two_users_with_rows(db, table)
    key = key_column(table)
    await as_role(db, "lifeos_app", alice)

    owners = {row[0] for row in await db.fetch(f"SELECT {key} FROM {table}")}  # noqa: S608
    assert owners == {alice}
    assert await db.fetchval(f"SELECT count(*) FROM {table} WHERE {key} = $1", bob) == 0  # noqa: S608
    updated = await db.execute(f"UPDATE {table} SET {key} = {key} WHERE {key} = $1", bob)  # noqa: S608
    assert updated == "UPDATE 0"
    deleted = await db.execute(f"DELETE FROM {table} WHERE {key} = $1", bob)  # noqa: S608
    assert deleted == "DELETE 0"


@pytest.mark.parametrize("table", sorted(USER_OWNED))
async def test_lifeos_app_cannot_insert_rows_for_another_user(
    db: asyncpg.Connection, table: str
) -> None:
    alice, bob = await two_users_with_rows(db, table)
    parent = None
    if table in WITH_PARENT:
        parent = await WITH_PARENT[table][0](db, bob)  # as superuser: the parent is not the test
    await as_role(db, "lifeos_app", alice)

    async def insert_for_bob() -> None:
        async with db.transaction():
            if parent is not None:
                await WITH_PARENT[table][1](db, bob, parent)
            else:
                await USER_OWNED[table](db, bob)

    expected = f'row-level security policy for table "{table}"'
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match=expected):
        await insert_for_bob()


async def test_lifeos_app_cannot_create_another_user(db: asyncpg.Connection) -> None:
    alice = await create_user(db, "alice@example.test")
    await as_role(db, "lifeos_app", alice)
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
        async with db.transaction():
            await create_user(db, "mallory@example.test")


@pytest.mark.parametrize("setting", [None, ""], ids=["never-set", "empty"])
@pytest.mark.parametrize("table", sorted([*USER_OWNED, "users"]))
async def test_nothing_is_visible_without_a_user(
    db: asyncpg.Connection, table: str, setting: str | None
) -> None:
    await two_users_with_rows(db, table)
    # never-set: app.user_id was never set in this session, so current_setting returns NULL.
    assert await db.fetchval("SELECT current_setting('app.user_id', true)") is None
    await as_role(db, "lifeos_app", setting)
    assert await db.fetchval(f"SELECT count(*) FROM {table}") == 0  # noqa: S608


@pytest.mark.parametrize("table", sorted([*USER_OWNED, "users"]))
async def test_lifeos_app_cannot_move_its_rows_to_another_user(
    db: asyncpg.Connection, table: str
) -> None:
    alice, bob = await two_users_with_rows(db, table)
    key = key_column(table)
    await as_role(db, "lifeos_app", alice)
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
        async with db.transaction():
            await db.execute(f"UPDATE {table} SET {key} = $1 WHERE {key} = $2", bob, alice)  # noqa: S608


@pytest.mark.parametrize("table", sorted(USER_OWNED))
async def test_lifeos_app_has_full_crud_on_its_own_rows(db: asyncpg.Connection, table: str) -> None:
    alice = await create_user(db, f"alice-{uuid.uuid4()}@example.test")
    await as_role(db, "lifeos_app", alice)
    await USER_OWNED[table](db, alice)
    assert await db.fetchval(f"SELECT count(*) FROM {table}") >= 1  # noqa: S608
    updated = await db.execute(f"UPDATE {table} SET user_id = user_id WHERE user_id = $1", alice)  # noqa: S608
    assert updated != "UPDATE 0"
    deleted = await db.execute(f"DELETE FROM {table} WHERE user_id = $1", alice)  # noqa: S608
    assert deleted != "DELETE 0"


async def test_lifeos_app_can_create_and_manage_its_own_user(db: asyncpg.Connection) -> None:
    user_id = uuid.uuid4()
    await as_role(db, "lifeos_app", user_id)
    await db.execute(
        "INSERT INTO users (id, email, display_name, dek_wrapped) VALUES ($1, 'z@x.test', 'Z', $2)",
        user_id,
        b"k",
    )
    assert await db.execute("UPDATE users SET display_name = 'Zee' WHERE id = $1", user_id) == (
        "UPDATE 1"
    )


async def test_lifeos_app_has_crud_on_the_system_tables(db: asyncpg.Connection) -> None:
    admin = await create_user(db, "admin@example.test")
    await as_role(db, "lifeos_app")
    invite = uuid.uuid4()
    await db.execute(
        "INSERT INTO invites (id, token_hash, created_by, expires_at)"
        " VALUES ($1, $2, $3, now() + interval '7 days')",
        invite,
        b"hash",
        admin,
    )
    await db.execute(
        "INSERT INTO auth_challenges (id, purpose, challenge, invite_id, expires_at)"
        " VALUES ($1, 'register', $2, $3, now())",
        uuid.uuid4(),
        b"c",
        invite,
    )
    await db.execute("INSERT INTO auth_events (kind, success) VALUES ('register', true)")
    await db.execute("INSERT INTO audit_log (actor_role, action) VALUES ('admin', 'admin.x')")
    await db.execute(
        "INSERT INTO pending_deletions (user_id, delete_after) VALUES ($1, now())", admin
    )
    for table in sorted(SYSTEM_TABLES):
        assert await db.fetchval(f"SELECT count(*) FROM {table}") >= 1  # noqa: S608
    assert await db.execute("UPDATE invites SET revoked_at = now() WHERE id = $1", invite) == (
        "UPDATE 1"
    )
    assert await db.execute("DELETE FROM auth_challenges WHERE invite_id = $1", invite) == (
        "DELETE 1"
    )
