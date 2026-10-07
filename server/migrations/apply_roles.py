"""Apply migrations/roles.sql as the database superuser (local, CI, tests).

Usage: python migrations/apply_roles.py [DSN]   (default: DATABASE_URL, then the local database)
Staging and production create roles once, with logins and passwords, in T15.
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

ROLES_SQL = Path(__file__).with_name("roles.sql")
LOCAL_DATABASE_URL = "postgresql://lifeos:lifeos@127.0.0.1:54320/lifeos"


async def apply(dsn: str) -> None:
    conn = await asyncpg.connect(dsn.replace("+asyncpg", ""))
    try:
        await conn.execute(ROLES_SQL.read_text())
    finally:
        await conn.close()


if __name__ == "__main__":
    dsn = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL", LOCAL_DATABASE_URL)
    asyncio.run(apply(dsn))
    print("roles: applied migrations/roles.sql")
