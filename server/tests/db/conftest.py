"""Database test fixtures: roles bootstrapped, schema migrated to head, each test rolled back.

Tests connect as the database superuser and switch role with `SET LOCAL ROLE`; RLS and grants apply
to the current role, exactly as they do for the app's login roles.
"""

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

SERVER = Path(__file__).resolve().parents[2]
APPLY_ROLES = SERVER / "migrations" / "apply_roles.py"

pytestmark = pytest.mark.integration


def plain_dsn(database_url: str) -> str:
    return database_url.replace("+asyncpg", "")


@pytest.fixture(scope="session")
def migrated(database_url: str) -> str:
    """Apply roles.sql and `alembic upgrade head` once per session (in a subprocess: env.py runs
    its own event loop)."""
    run = subprocess.run(
        [sys.executable, str(APPLY_ROLES), plain_dsn(database_url)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVER,
        env={**os.environ, "ENV": "local", "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgrade.returncode == 0, upgrade.stderr
    return plain_dsn(database_url)


@pytest.fixture
async def db(migrated: str) -> AsyncIterator[asyncpg.Connection]:
    """A superuser connection inside a transaction that is always rolled back."""
    conn = await asyncpg.connect(migrated)
    tx = conn.transaction()
    await tx.start()
    try:
        yield conn
    finally:
        await tx.rollback()
        await conn.close()


async def as_role(
    conn: asyncpg.Connection, role: str, user_id: uuid.UUID | str | None = None
) -> None:
    """Switch the current transaction to `role`, optionally with `app.user_id` set."""
    await conn.execute(f"SET LOCAL ROLE {role}")
    if user_id is not None:
        await conn.execute("SELECT set_config('app.user_id', $1, true)", str(user_id))


async def reset_role(conn: asyncpg.Connection) -> None:
    await conn.execute("RESET ROLE")
    await conn.execute("SELECT set_config('app.user_id', '', true)")


async def create_user(conn: asyncpg.Connection, email: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO users (id, email, display_name, dek_wrapped) VALUES ($1, $2, 'Test', $3)",
        user_id,
        email,
        b"\x01wrapped",
    )
    return user_id
