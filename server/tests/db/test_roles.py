"""T03: database roles get exactly their grants (spec 7.3 as amended by CR-003)."""

import uuid

import asyncpg
import pytest

from tests.db.conftest import as_role, create_user
from tests.db.fixtures import SYSTEM_TABLES, USER_OWNED

pytestmark = pytest.mark.integration

ADMIN_READABLE = {"sessions", "invites", "auth_events", "audit_log"}
ALL_TABLES = {*USER_OWNED, *SYSTEM_TABLES, "users"}


async def denied(db: asyncpg.Connection, query: str, *args: object) -> bool:
    try:
        async with db.transaction():
            await db.fetch(query, *args)
    except asyncpg.InsufficientPrivilegeError:
        return True
    return False


async def seeded(db: asyncpg.Connection) -> tuple[uuid.UUID, uuid.UUID]:
    """Two users with a row in every user-owned table."""
    alice = await create_user(db, f"alice-{uuid.uuid4()}@example.test")
    bob = await create_user(db, f"bob-{uuid.uuid4()}@example.test")
    for factory in USER_OWNED.values():
        await factory(db, alice)
        await factory(db, bob)
    return alice, bob


# ---------- lifeos_admin_ro ----------


@pytest.mark.parametrize("table", sorted(ALL_TABLES - ADMIN_READABLE - {"users"}))
async def test_admin_is_denied_every_other_table(db: asyncpg.Connection, table: str) -> None:
    await as_role(db, "lifeos_admin_ro")
    assert await denied(db, f"SELECT 1 FROM {table} LIMIT 1")  # noqa: S608


@pytest.mark.parametrize("column", ["dek_wrapped", "timezone", "deletion_requested_at", "*"])
async def test_admin_is_denied_other_user_columns(db: asyncpg.Connection, column: str) -> None:
    await as_role(db, "lifeos_admin_ro")
    assert await denied(db, f"SELECT {column} FROM users")  # noqa: S608


async def test_admin_reads_its_user_columns_and_tables_across_users(
    db: asyncpg.Connection,
) -> None:
    await seeded(db)
    await as_role(db, "lifeos_admin_ro")
    users = await db.fetch("SELECT id, email, display_name, role, created_at FROM users")
    assert len(users) >= 2
    sessions = "SELECT id, user_id, created_at, last_seen_at, expires_at, revoked_at FROM sessions"
    assert len(await db.fetch(sessions)) >= 2
    await db.fetch("SELECT id, email, created_by, expires_at, used_at, revoked_at FROM invites")
    for table in ("auth_events", "audit_log"):
        await db.fetch(f"SELECT * FROM {table}")  # noqa: S608


async def test_admin_cannot_write(db: asyncpg.Connection) -> None:
    await as_role(db, "lifeos_admin_ro")
    assert await denied(db, "UPDATE users SET display_name = 'x'")
    assert await denied(db, "DELETE FROM sessions")


# ---------- lifeos_jobs ----------


async def test_jobs_find_work_across_users(db: asyncpg.Connection) -> None:
    await seeded(db)
    await as_role(db, "lifeos_jobs")
    assert await db.fetchval("SELECT count(*) FROM outbox_events WHERE processed_at IS NULL") >= 2
    assert await db.fetchval("SELECT count(*) FROM (SELECT id, timezone FROM users) u") >= 2
    reminders = "SELECT id, user_id, status, fire_at FROM reminders"
    assert len(await db.fetch(reminders)) >= 2
    doses = "SELECT id, user_id, status, scheduled_at FROM medication_doses"
    assert len(await db.fetch(doses)) >= 2
    await db.fetch("SELECT * FROM pending_deletions")
    updated = await db.execute("UPDATE outbox_events SET processed_at = now()")
    assert updated != "UPDATE 0"


@pytest.mark.parametrize(
    "query",
    [
        "SELECT payload_enc FROM reminders",
        "SELECT email FROM users",
        "SELECT * FROM daily_logs",
        "SELECT * FROM medications",
        "UPDATE outbox_events SET topic = 'x'",
        "DELETE FROM outbox_events",
        "UPDATE reminders SET status = 'sent'",
    ],
)
async def test_jobs_are_denied_everything_else(db: asyncpg.Connection, query: str) -> None:
    await as_role(db, "lifeos_jobs")
    assert await denied(db, query)


# ---------- lifeos_dispatcher ----------


async def test_dispatcher_reads_and_updates_its_tables_across_users(
    db: asyncpg.Connection,
) -> None:
    await seeded(db)
    await as_role(db, "lifeos_dispatcher")
    assert len(await db.fetch("SELECT * FROM reminders")) >= 2
    assert len(await db.fetch("SELECT * FROM push_subscriptions")) >= 2
    assert len(await db.fetch("SELECT user_id, quiet_start FROM user_settings")) >= 2
    assert len(await db.fetch("SELECT id, timezone, dek_wrapped FROM users")) >= 2
    await db.execute("UPDATE reminders SET status = 'sending', attempts = attempts + 1")
    await db.execute("UPDATE push_subscriptions SET failure_count = failure_count + 1")


@pytest.mark.parametrize(
    "query",
    [
        "SELECT email FROM users",
        "SELECT * FROM daily_logs",
        "SELECT * FROM sessions",
        "UPDATE reminders SET payload_enc = ''",
        "DELETE FROM reminders",
        "UPDATE user_settings SET theme = 'dark'",
    ],
)
async def test_dispatcher_is_denied_everything_else(db: asyncpg.Connection, query: str) -> None:
    await as_role(db, "lifeos_dispatcher")
    assert await denied(db, query)


# ---------- lifeos_backup and role attributes ----------


async def test_roles_exist_without_login_or_bypass(db: asyncpg.Connection) -> None:
    rows = await db.fetch(
        "SELECT rolname, rolcanlogin, rolbypassrls, rolsuper FROM pg_roles"
        " WHERE rolname LIKE 'lifeos\\_%'"
    )
    roles = {row["rolname"]: row for row in rows}
    expected = {
        "lifeos_app",
        "lifeos_admin_ro",
        "lifeos_jobs",
        "lifeos_dispatcher",
        "lifeos_backup",
    }
    assert expected <= set(roles)
    for name in expected:
        assert not roles[name]["rolbypassrls"], name
        assert not roles[name]["rolsuper"], name


async def test_backup_role_has_pg_read_all_data(db: asyncpg.Connection) -> None:
    assert await db.fetchval("SELECT pg_has_role('lifeos_backup', 'pg_read_all_data', 'member')")


# ---------- ownership and schema privileges ----------


async def test_schema_objects_are_owned_by_lifeos_owner(db: asyncpg.Connection) -> None:
    owners = await db.fetch(
        "SELECT c.relname, pg_get_userbyid(c.relowner) AS owner FROM pg_class c"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'public' AND c.relkind IN ('r', 'S', 'i')"
    )
    assert owners
    assert {row["owner"] for row in owners} == {"lifeos_owner"}
    functions = await db.fetch(
        "SELECT proname, pg_get_userbyid(proowner) AS owner FROM pg_proc"
        " WHERE proname LIKE 'auth\\_find\\_%' OR proname = 'set_updated_at'"
    )
    assert len(functions) == 4
    assert {row["owner"] for row in functions} == {"lifeos_owner"}


async def test_lifeos_owner_bypasses_rls_but_is_not_superuser(db: asyncpg.Connection) -> None:
    row = await db.fetchrow(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'lifeos_owner'"
    )
    assert row is not None
    assert row["rolsuper"] is False
    assert row["rolbypassrls"] is True


@pytest.mark.parametrize(
    "role", ["lifeos_app", "lifeos_admin_ro", "lifeos_jobs", "lifeos_dispatcher", "lifeos_backup"]
)
async def test_only_the_owner_can_create_in_schema_public(
    db: asyncpg.Connection, role: str
) -> None:
    assert not await db.fetchval("SELECT has_schema_privilege($1, 'public', 'CREATE')", role)
    assert not await db.fetchval("SELECT has_schema_privilege('public', 'public', 'CREATE')")


async def test_dispatcher_cannot_read_the_pin_hash_or_consent(db: asyncpg.Connection) -> None:
    await as_role(db, "lifeos_dispatcher")
    for column in ("app_lock_pin_hash", "health_consent_at", "*"):
        assert await denied(db, f"SELECT {column} FROM user_settings")  # noqa: S608
    await db.fetch(
        "SELECT user_id, quiet_start, quiet_end, notif_prefs, discreet_notifications,"
        " checkin_time FROM user_settings"
    )


@pytest.mark.parametrize("table", ["sessions", "invites"])
async def test_admin_cannot_read_token_hashes(db: asyncpg.Connection, table: str) -> None:
    await as_role(db, "lifeos_admin_ro")
    assert await denied(db, f"SELECT token_hash FROM {table}")  # noqa: S608


ALL = "*"
EXACT_GRANTS: dict[str, dict[str, dict[str, set[str] | str]]] = {
    "lifeos_admin_ro": {
        "users": {"SELECT": {"id", "email", "display_name", "role", "created_at"}},
        "sessions": {"SELECT": "* - token_hash"},
        "invites": {"SELECT": "* - token_hash"},
        "auth_events": {"SELECT": ALL},
        "audit_log": {"SELECT": ALL},
    },
    "lifeos_jobs": {
        "outbox_events": {"SELECT": ALL, "UPDATE": {"processed_at"}},
        "users": {"SELECT": {"id", "timezone"}},
        "reminders": {"SELECT": {"id", "user_id", "status", "fire_at"}},
        "medication_doses": {"SELECT": {"id", "user_id", "status", "scheduled_at"}},
        "pending_deletions": {"SELECT": ALL},
    },
    "lifeos_dispatcher": {
        "reminders": {"SELECT": ALL, "UPDATE": {"status", "attempts", "sent_at", "fire_at"}},
        "push_subscriptions": {
            "SELECT": ALL,
            "UPDATE": {"last_success_at", "failure_count", "disabled_at"},
        },
        "user_settings": {
            "SELECT": {
                "user_id",
                "quiet_start",
                "quiet_end",
                "notif_prefs",
                "discreet_notifications",
                "checkin_time",
            }
        },
        "users": {"SELECT": {"id", "timezone", "dek_wrapped"}},
    },
}


async def columns_of(db: asyncpg.Connection) -> dict[str, set[str]]:
    rows = await db.fetch(
        "SELECT table_name, column_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
    )
    out: dict[str, set[str]] = {}
    for row in rows:
        out.setdefault(row["table_name"], set()).add(row["column_name"])
    return out


def expand(spec: set[str] | str, columns: set[str]) -> set[str]:
    if spec == ALL:
        return set(columns)
    if isinstance(spec, str) and spec.startswith("* - "):
        return columns - {spec[4:]}
    assert isinstance(spec, set)
    return spec


@pytest.mark.parametrize("role", sorted(EXACT_GRANTS))
async def test_role_has_exactly_its_grants(db: asyncpg.Connection, role: str) -> None:
    """Catalog-driven: every table, column and privilege, not a hand-picked deny list."""
    columns = await columns_of(db)
    actual: dict[str, dict[str, set[str]]] = {}
    for table, cols in columns.items():
        for privilege in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
            allowed = {
                col
                for col in cols
                if await db.fetchval(
                    "SELECT has_column_privilege($1, $2, $3, $4)",
                    role,
                    f"public.{table}",
                    col,
                    privilege,
                )
            }
            if allowed:
                actual.setdefault(table, {})[privilege] = allowed
        for privilege in ("DELETE", "TRUNCATE", "TRIGGER"):
            if await db.fetchval(
                "SELECT has_table_privilege($1, $2, $3)", role, f"public.{table}", privilege
            ):
                actual.setdefault(table, {})[privilege] = {ALL}
    expected = {
        table: {privilege: expand(spec, columns[table]) for privilege, spec in grants.items()}
        for table, grants in EXACT_GRANTS[role].items()
    }
    assert actual == expected


async def test_policies_are_exactly_the_expected_set(db: asyncpg.Connection) -> None:
    rows = await db.fetch("SELECT tablename, policyname, roles FROM pg_policies")
    actual = {(row["tablename"], row["policyname"], tuple(row["roles"])) for row in rows}
    expected = {(table, "app_isolation", ("lifeos_app",)) for table in [*USER_OWNED, "users"]}
    expected |= {
        ("users", "admin_read", ("lifeos_admin_ro",)),
        ("sessions", "admin_read", ("lifeos_admin_ro",)),
        ("outbox_events", "jobs_all", ("lifeos_jobs",)),
        ("users", "jobs_read", ("lifeos_jobs",)),
        ("reminders", "jobs_read", ("lifeos_jobs",)),
        ("medication_doses", "jobs_read", ("lifeos_jobs",)),
        ("reminders", "dispatcher_all", ("lifeos_dispatcher",)),
        ("push_subscriptions", "dispatcher_all", ("lifeos_dispatcher",)),
        ("user_settings", "dispatcher_read", ("lifeos_dispatcher",)),
        ("users", "dispatcher_read", ("lifeos_dispatcher",)),
    }
    assert actual == expected


async def test_dispatcher_can_run_the_10_3_claim_query(db: asyncpg.Connection) -> None:
    await seeded(db)
    await db.execute("UPDATE reminders SET fire_at = now() - interval '1 minute'")
    await as_role(db, "lifeos_dispatcher")
    claimed = await db.fetch(
        "SELECT id, user_id FROM reminders"
        " WHERE status IN ('scheduled','snoozed') AND fire_at <= now()"
        " ORDER BY fire_at FOR UPDATE SKIP LOCKED LIMIT 200"
    )
    assert len({row["user_id"] for row in claimed}) >= 2
