"""Test-only: end the recent authentication (CR-017) of a user's sessions in the e2e database.

Signing in counts as recent authentication for 5 minutes, so a journey could only reach "Confirm
it's you" by waiting. `uv run python -m tests.e2e.expire_recent_auth <email>` clears
`sessions.reauth_at` for that user instead. Local `_e2e` database only.
"""

import asyncio
import sys

import asyncpg

from app.platform.config import load_settings
from tests.e2e.guard import e2e_database


async def main(email: str) -> int:
    settings = load_settings()
    if settings.env != "local":
        raise SystemExit("tests.e2e.expire_recent_auth runs only with ENV=local")
    dsn = settings.database_url.get_secret_value().replace("+asyncpg", "")
    e2e_database(dsn)
    connection = await asyncpg.connect(dsn)
    try:
        result: str = await connection.execute(
            "UPDATE sessions SET reauth_at = NULL"
            " WHERE user_id = (SELECT id FROM users WHERE email = $1)",
            email,
        )
    finally:
        await connection.close()
    return int(result.split()[-1])


if __name__ == "__main__":
    if asyncio.run(main(sys.argv[1])) == 0:
        raise SystemExit("no sessions for that email")
