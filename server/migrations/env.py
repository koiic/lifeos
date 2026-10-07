"""Alembic environment (async, asyncpg). Table metadata is attached from T03."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.platform.config import ConfigError, load_settings
from app.platform.db import async_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def database_url() -> str:
    """Migrations run as lifeos_owner (spec 7.3, CR-003): the `database_owner_url` secret file
    outside local; locally DATABASE_OWNER_URL or the local database URL."""
    owner_url = load_settings().database_owner_url
    if owner_url is None:
        raise ConfigError("secret file database_owner_url is required to run migrations")
    return async_url(owner_url.get_secret_value())


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Every object (alembic_version included) is created and owned by lifeos_owner (spec 7.3,
    # CR-003), also when connected as a superuser locally or in CI.
    connection.exec_driver_sql("SET ROLE lifeos_owner")
    # SET ROLE is session-level; commit the implicit transaction it opened so Alembic manages
    # (and commits) its own migration transaction instead of treating it as the caller's.
    connection.commit()
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
