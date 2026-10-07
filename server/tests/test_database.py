"""T01: integration tests run against a real PostgreSQL 16 (plan 4.7, spec 15.1)."""

import asyncpg
import pytest

pytestmark = pytest.mark.integration


async def test_database_is_postgres_16(database_url: str) -> None:
    conn = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        assert conn.get_server_version().major == 16
    finally:
        await conn.close()
