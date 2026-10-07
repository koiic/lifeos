"""Database engines (SQLAlchemy 2.0 async, asyncpg).

Each engine runs as one database role, set at connect (`role` startup setting). In production the
login role already is that role; locally and in CI (a superuser login) it makes connections behave
like production, so development runs under RLS too.

Services open transactions with `user_transaction` (RLS scoped to one user, spec 7.3) or
`system_transaction` (no user: system tables and the CR-003 lookup functions only) and pass the
`Transaction` to their repository; only repositories run SQL.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.platform.config import ConfigError

APP_ROLE = "lifeos_app"
JOBS_ROLE = "lifeos_jobs"

# Names for services, which never import SQLAlchemy themselves (plan 4.2).
type Database = AsyncEngine
type Transaction = AsyncConnection


def async_url(database_url: str) -> str:
    return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


def create_engine(database_url: str, role: str = APP_ROLE) -> AsyncEngine:
    return create_async_engine(
        async_url(database_url),
        pool_pre_ping=True,
        connect_args={"server_settings": {"role": role}},
    )


async def verify_role(engine: AsyncEngine, role: str) -> None:
    """Outside local, the login itself must be `role` (no SET ROLE on top of a stronger login,
    which `SET ROLE NONE` could undo). Raises ConfigError otherwise."""
    async with engine.connect() as connection:
        session_user, current_user = (
            await connection.execute(text("SELECT session_user, current_user"))
        ).one()
    if session_user != role or current_user != role:
        raise ConfigError(f"the database login must be {role}")


async def ping(engine: AsyncEngine) -> None:
    """Raise if the database cannot answer a trivial query."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


@asynccontextmanager
async def user_transaction(engine: AsyncEngine, user_id: uuid.UUID) -> AsyncIterator[Transaction]:
    """A transaction as `lifeos_app` with `app.user_id` set (RLS limits it to that user)."""
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user_id)}
        )
        yield conn


@asynccontextmanager
async def system_transaction(engine: AsyncEngine) -> AsyncIterator[Transaction]:
    """A transaction with no user: RLS hides every user row (spec 7.3, CR-003)."""
    async with engine.begin() as conn:
        yield conn
