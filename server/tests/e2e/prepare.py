"""Test-only: a fresh e2e database for the Playwright journeys (plan 6.1 `make verify-e2e`).

`uv run python -m tests.e2e.prepare <base_dsn> <e2e_dsn>` drops and recreates the e2e database
on the local PostgreSQL (fake data only), applies the roles and migrations, and seeds the admin
user that test invites name as their creator. Refuses anything but a local `_e2e` database on
the same local server as the base connection (tests/e2e/guard.py).
"""

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg

from tests.e2e.guard import e2e_database, same_server

SERVER = Path(__file__).resolve().parents[2]


def plain(dsn: str) -> str:
    return dsn.replace("+asyncpg", "")


async def recreate(base_dsn: str, name: str) -> None:
    connection = await asyncpg.connect(plain(base_dsn))
    try:
        # `name` passed the guard: lowercase letters, digits and underscores only.
        await connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await connection.execute(f'CREATE DATABASE "{name}"')
    finally:
        await connection.close()


async def seed_admin(e2e_dsn: str) -> None:
    connection = await asyncpg.connect(plain(e2e_dsn))
    try:
        await connection.execute(
            "INSERT INTO users (id, email, display_name, role, dek_wrapped)"
            " VALUES ($1, 'admin@example.test', 'Ibrahim', 'admin', $2)",
            uuid.uuid4(),
            b"e2e-admin-has-no-data",
        )
    finally:
        await connection.close()


def main(base_dsn: str, e2e_dsn: str) -> None:
    name = e2e_database(e2e_dsn)
    same_server(base_dsn, e2e_dsn)
    asyncio.run(recreate(base_dsn, name))
    # Fixed programs; the only argument is the DSN the guard accepted above.
    subprocess.run(  # noqa: S603
        [sys.executable, "migrations/apply_roles.py", plain(e2e_dsn)], cwd=SERVER, check=True
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVER,
        check=True,
        env={**os.environ, "ENV": "local", "DATABASE_URL": e2e_dsn},
    )
    asyncio.run(seed_admin(e2e_dsn))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
