"""T03: the database matches the spec's DDL (spec 7 intro, 7.2, 7.5).

The expected tables and columns are parsed from docs/spec.md itself, so the test cannot drift from
the specification.
"""

import re
from pathlib import Path

import asyncpg
import pytest

pytestmark = pytest.mark.integration

SPEC = Path(__file__).resolve().parents[3] / "docs" / "spec.md"
CONSTRAINT_WORDS = {"CHECK", "UNIQUE", "PRIMARY", "CONSTRAINT", "FOREIGN"}


def split_top_level(body: str) -> list[str]:
    """Split a CREATE TABLE body on commas outside parentheses and quoted literals."""
    items, depth, current, quoted = [], 0, [], False
    for char in body:
        if char == "'":
            quoted = not quoted
        elif char == "(" and not quoted:
            depth += 1
        elif char == ")" and not quoted:
            depth -= 1
        if char == "," and depth == 0 and not quoted:
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return [item.strip() for item in items if item.strip()]


def spec_tables() -> dict[str, set[str]]:
    text = SPEC.read_text()
    section = text[text.index("### 7.2 Schema (DDL)") : text.index("Optimistic concurrency uses")]
    sql_blocks = re.findall(r"```sql\n(.*?)```", section, re.S)
    sql = "\n".join(re.sub(r"--[^\n]*", "", block) for block in sql_blocks)
    tables: dict[str, set[str]] = {}
    for name, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", sql, re.S):
        columns = set()
        for item in split_top_level(body):
            first = item.split()[0]
            if first.upper() not in CONSTRAINT_WORDS:
                columns.add(first)
        tables[name] = columns
    return tables


SPEC_TABLES = spec_tables()
# Tables added by approved change requests whose spec re-sync is pending. Once the spec carries a
# table, the test below fails until it is removed from here.
PENDING_CR_TABLES = {
    "session_request_counts": {"session_id", "window_start", "count"},  # CR-016
}
EXPECTED_TABLES = SPEC_TABLES | PENDING_CR_TABLES


def test_pending_cr_tables_are_not_yet_in_the_spec() -> None:
    assert not set(PENDING_CR_TABLES) & set(SPEC_TABLES)


def test_the_spec_defines_28_tables() -> None:
    assert len(SPEC_TABLES) == 28


async def test_the_database_has_exactly_the_spec_tables(db: asyncpg.Connection) -> None:
    rows = await db.fetch(
        "SELECT table_name FROM information_schema.tables"
        " WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        " AND table_name <> 'alembic_version'"
    )
    assert {row["table_name"] for row in rows} == set(EXPECTED_TABLES)


@pytest.mark.parametrize("table", sorted(EXPECTED_TABLES))
async def test_each_table_has_exactly_the_spec_columns(db: asyncpg.Connection, table: str) -> None:
    rows = await db.fetch(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = $1",
        table,
    )
    assert {row["column_name"] for row in rows} == EXPECTED_TABLES[table]


async def test_citext_is_installed(db: asyncpg.Connection) -> None:
    assert await db.fetchval("SELECT count(*) FROM pg_extension WHERE extname = 'citext'") == 1


async def test_every_updated_at_column_is_trigger_maintained(db: asyncpg.Connection) -> None:
    tables = await db.fetch(
        "SELECT table_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND column_name = 'updated_at'"
    )
    triggered = await db.fetch(
        "SELECT event_object_table FROM information_schema.triggers"
        " WHERE trigger_name = 'set_updated_at'"
    )
    expected = {row["table_name"] for row in tables}
    assert expected
    assert expected == {row["event_object_table"] for row in triggered}


async def test_updated_at_changes_on_update(db: asyncpg.Connection) -> None:
    from tests.db.conftest import create_user

    user = await create_user(db, "a@example.test")
    await db.execute("UPDATE users SET updated_at = now() - interval '1 day' WHERE id = $1", user)
    before = await db.fetchval("SELECT updated_at FROM users WHERE id = $1", user)
    await db.execute("UPDATE users SET display_name = 'B' WHERE id = $1", user)
    after = await db.fetchval("SELECT updated_at FROM users WHERE id = $1", user)
    assert after > before


def normalised(sql: str) -> str:
    return " ".join(re.sub(r"--[^\n]*", "", sql).split())


def test_the_migration_ddl_is_the_spec_ddl_verbatim() -> None:
    import importlib.util

    path = SPEC.parents[1] / "server/migrations/versions/0001_schema_roles_rls.py"
    spec_obj = importlib.util.spec_from_file_location("migration_0001", path)
    assert spec_obj is not None
    assert spec_obj.loader is not None
    migration = importlib.util.module_from_spec(spec_obj)
    spec_obj.loader.exec_module(migration)
    text = SPEC.read_text()
    section = text[text.index("### 7.2 Schema (DDL)") : text.index("Optimistic concurrency uses")]
    spec_sql = "\n".join(re.findall(r"```sql\n(.*?)```", section, re.S))
    assert normalised(migration.SCHEMA) == normalised(spec_sql)
