"""Job tests run real workers against the real database, so data is committed and cleaned up."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg
import procrastinate
import pytest

from app.platform.config import Settings
from app.platform.jobs import Runtime, create_runtime
from app.worker import create_job_app

pytestmark = pytest.mark.integration


@dataclass
class JobEnv:
    settings: Settings
    runtime: Runtime
    app: procrastinate.App
    superuser: asyncpg.Connection


async def clean(conn: asyncpg.Connection) -> None:
    await conn.execute("TRUNCATE jobs.procrastinate_jobs, jobs.procrastinate_workers CASCADE")
    await conn.execute("TRUNCATE outbox_events")
    await conn.execute("DELETE FROM users WHERE email LIKE '%@jobs.test'")


@pytest.fixture
async def env(migrated: str) -> AsyncIterator[JobEnv]:
    settings = Settings(
        env="local",
        app_origin="https://app.test",
        database_url=migrated,
        database_jobs_url=migrated,
    )
    superuser = await asyncpg.connect(migrated)
    await clean(superuser)
    runtime = create_runtime(settings)
    app = create_job_app(settings, runtime)
    async with app.open_async():
        yield JobEnv(settings, runtime, app, superuser)
    await runtime.dispose()
    await clean(superuser)
    await superuser.close()


async def create_user(conn: asyncpg.Connection) -> uuid.UUID:
    user_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO users (id, email, display_name, dek_wrapped) VALUES ($1, $2, 'T', $3)",
        user_id,
        f"{user_id}@jobs.test",
        b"k",
    )
    return user_id


async def write_event(conn: asyncpg.Connection, user_id: uuid.UUID, topic: str) -> None:
    """Write an outbox event the way the app does: as lifeos_app, for its own user, committed."""
    async with conn.transaction():
        await conn.execute("SET LOCAL ROLE lifeos_app")
        await conn.execute("SELECT set_config('app.user_id', $1, true)", str(user_id))
        await conn.execute(
            "INSERT INTO outbox_events (user_id, topic, body) VALUES ($1, $2, '{}')",
            user_id,
            topic,
        )


async def jobs_named(conn: asyncpg.Connection, task_name: str) -> list[asyncpg.Record]:
    return await conn.fetch(
        "SELECT id, status, lock, queueing_lock, args FROM jobs.procrastinate_jobs"
        " WHERE task_name = $1 ORDER BY id",
        task_name,
    )
