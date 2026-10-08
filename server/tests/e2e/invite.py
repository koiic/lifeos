"""Test-only: create a registration invite in the e2e database and print its token.

The Playwright journeys (web/tests/journeys) call `uv run python -m tests.e2e.invite [email]`
with the e2e stack's environment (ENV=local). The invite is made through `AuthService`, as the
admin console will (T44), by the admin user `scripts/e2e_stack.sh` seeds. Never used outside
ENV=local.
"""

import asyncio
import sys

import asyncpg

from app.auth.service import AuthService
from app.platform.clock import utc_now
from app.platform.config import load_settings
from app.platform.crypto import load_keyring
from app.platform.db import create_engine
from tests.e2e.guard import e2e_database


async def main(email: str | None) -> str:
    settings = load_settings()
    if settings.env != "local":
        raise SystemExit("tests.e2e.invite runs only with ENV=local")
    dsn = settings.database_url.get_secret_value().replace("+asyncpg", "")
    e2e_database(dsn)  # a local `_e2e` database only, whatever the environment says
    connection = await asyncpg.connect(dsn)
    try:
        admin_id = await connection.fetchval("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    finally:
        await connection.close()
    if admin_id is None:
        raise SystemExit("no admin user: run scripts/e2e_stack.sh first")
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        service = AuthService(
            engine, load_keyring(settings), settings.webauthn_rp_id, settings.app_origin
        )
        return await service.create_invite(admin_id, email, utc_now())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    print(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None)))
