"""Database engine (SQLAlchemy 2.0 async, asyncpg). Sessions and `app.user_id` arrive with T03."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def async_url(database_url: str) -> str:
    return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(async_url(database_url), pool_pre_ping=True)


async def ping(engine: AsyncEngine) -> None:
    """Raise if the database cannot answer a trivial query."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
