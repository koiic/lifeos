"""Database test fixtures: roles bootstrapped, schema migrated to head, each test rolled back.

Tests connect as the database superuser and switch role with `SET LOCAL ROLE`; RLS and grants apply
to the current role, exactly as they do for the app's login roles.
"""

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest

pytestmark = pytest.mark.integration


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
