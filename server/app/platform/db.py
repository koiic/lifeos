"""Database engines (SQLAlchemy 2.0 async, asyncpg).

Each engine runs as one database role, set at connect (`role` startup setting). In production the
login role already is that role; locally and in CI (a superuser login) it makes connections behave
like production, so development runs under RLS too.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.platform.config import ConfigError

APP_ROLE = "lifeos_app"
JOBS_ROLE = "lifeos_jobs"


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
