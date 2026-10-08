"""T05: the relay is a periodic task every minute; the worker entrypoint builds the app (10.1)."""

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import asyncpg
import pytest

from tests.jobs.conftest import JobEnv
from tests.kek import TEST_IP_KEY, TEST_KEK

pytestmark = pytest.mark.integration

SERVER = Path(__file__).resolve().parents[2]


def test_outbox_relay_runs_every_minute(env: JobEnv) -> None:
    periodic = env.app.periodic_registry.periodic_tasks
    [task] = [t for k, t in periodic.items() if k[0] == "outbox.relay"]
    assert task.cron == "* * * * *"
    assert task.task.queueing_lock == "outbox.relay"


def test_the_worker_entrypoint_exposes_a_configured_app() -> None:
    script = "from app.worker import app; names = sorted(app.tasks); print(','.join(names))"
    run = subprocess.run(
        [sys.executable, "-c", script],
        cwd=SERVER,
        env={**os.environ, "ENV": "local"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert "outbox.relay" in run.stdout.split(",")


async def test_jobs_schema_is_owned_by_lifeos_owner_and_usable(env: JobEnv) -> None:
    db = env.superuser
    owners = await db.fetch(
        "SELECT c.relname, pg_get_userbyid(c.relowner) AS owner FROM pg_class c"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'jobs' AND c.relkind = 'r'"
    )
    assert {row["relname"] for row in owners} >= {
        "procrastinate_jobs",
        "procrastinate_events",
        "procrastinate_workers",
        "procrastinate_periodic_defers",
    }
    assert {row["owner"] for row in owners} == {"lifeos_owner"}
    public = await db.fetchval(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'public' AND c.relname LIKE 'procrastinate%'"
    )
    assert public == 0


DEFER = (
    "SELECT jobs.procrastinate_defer_jobs_v1(ARRAY[ROW('default', 'tests.x', 0, NULL, NULL,"
    " '{}'::jsonb, NULL)::jobs.procrastinate_job_to_defer_v1])"
)


async def as_role_denied(env: JobEnv, role: str, statement: str) -> bool:
    async with env.superuser.transaction():
        await env.superuser.execute(f"SET LOCAL ROLE {role}")
        await env.superuser.execute("SET LOCAL search_path TO jobs, public, pg_temp")
        try:
            async with env.superuser.transaction():
                await env.superuser.execute(statement)
        except asyncpg.InsufficientPrivilegeError:
            return True
    return False


async def test_the_worker_role_has_full_use_of_the_queue(env: JobEnv) -> None:
    for statement in (
        "SELECT * FROM procrastinate_jobs LIMIT 1",
        "SELECT procrastinate_register_worker_v1()",
        DEFER,
        "DELETE FROM procrastinate_jobs WHERE task_name = 'tests.x'",
    ):
        assert not await as_role_denied(env, "lifeos_jobs", statement), statement


async def test_the_api_role_can_only_queue_jobs(env: JobEnv) -> None:
    assert not await as_role_denied(env, "lifeos_app", DEFER)
    for statement in (
        "SELECT task_name, args, lock FROM procrastinate_jobs",
        "UPDATE procrastinate_jobs SET status = 'succeeded'",
        "DELETE FROM procrastinate_jobs",
        "SELECT procrastinate_register_worker_v1()",
        "SELECT * FROM procrastinate_fetch_job_v2(NULL, 1)",
        "SELECT * FROM procrastinate_events",
    ):
        assert await as_role_denied(env, "lifeos_app", statement), statement


async def test_admin_sees_only_aggregate_queue_health(env: JobEnv) -> None:
    async with env.superuser.transaction():
        await env.superuser.execute("SET LOCAL search_path TO jobs, public, pg_temp")
        await env.superuser.execute(DEFER)
    async with env.superuser.transaction():
        await env.superuser.execute("SET LOCAL ROLE lifeos_admin_ro")
        rows = await env.superuser.fetch(
            "SELECT status, jobs, oldest_deferred_at FROM jobs.queue_stats"
        )
    assert {row["status"] for row in rows} >= {"todo"}
    for table in ("procrastinate_jobs", "procrastinate_events", "procrastinate_workers"):
        assert await as_role_denied(env, "lifeos_admin_ro", f"SELECT * FROM jobs.{table}")  # noqa: S608


@pytest.mark.parametrize("role", ["lifeos_dispatcher", "lifeos_backup"])
async def test_other_roles_cannot_use_the_queue(env: JobEnv, role: str) -> None:
    async with env.superuser.transaction():
        await env.superuser.execute(f"SET LOCAL ROLE {role}")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with env.superuser.transaction():
                await env.superuser.execute(
                    "INSERT INTO jobs.procrastinate_jobs (queue_name, task_name) VALUES ('q', 't')"
                )


def test_the_vendored_procrastinate_schema_matches_the_installed_version() -> None:
    """Migration 0002 runs a frozen copy of Procrastinate's schema. An upgrade of the package must
    come with a new migration (its schema deltas) and a new vendored file; this test says so."""
    import procrastinate
    from procrastinate.schema import SchemaManager

    vendored = SERVER / "migrations" / "procrastinate_3_10_0_schema.sql"
    assert procrastinate.__version__ == "3.10.0"
    assert vendored.read_text() == SchemaManager.get_schema()


async def test_the_queue_connection_runs_as_lifeos_jobs_in_schema_jobs(env: JobEnv) -> None:
    row = await env.app.connector.execute_query_one_async(
        "SELECT current_user AS role, current_setting('search_path') AS path"
    )
    assert row["role"] == "lifeos_jobs"
    assert [part.strip() for part in row["path"].split(",")] == ["jobs", "public", "pg_temp"]


def test_finished_jobs_are_pruned_daily(env: JobEnv) -> None:
    periodic = env.app.periodic_registry.periodic_tasks
    [task] = [t for k, t in periodic.items() if k[0] == "jobs.prune_finished"]
    assert task.cron == "20 4 * * *"


async def test_pruning_deletes_finished_jobs_older_than_seven_days(env: JobEnv) -> None:
    from app.platform.jobs import prune_finished_jobs

    db = env.superuser
    await db.execute("SET search_path TO jobs, public, pg_temp")
    ids = {}
    for name, status, age in (
        ("old_done", "succeeded", timedelta(days=8)),
        ("old_failed", "failed", timedelta(days=8)),
        ("recent_done", "succeeded", timedelta(days=1)),
        ("old_waiting", "todo", timedelta(days=8)),
    ):
        job_id = await db.fetchval(
            "INSERT INTO procrastinate_jobs (queue_name, task_name, status)"
            " VALUES ('default', $1, $2::procrastinate_job_status) RETURNING id",
            name,
            status,
        )
        await db.execute(
            "UPDATE procrastinate_events SET at = now() - $2::interval WHERE job_id = $1",
            job_id,
            age,
        )
        if status != "todo":
            await db.execute(
                "INSERT INTO procrastinate_events (job_id, type, at)"
                " VALUES ($1, $2::procrastinate_job_event_type, now() - $3::interval)",
                job_id,
                status,
                age,
            )
        ids[name] = job_id
    await db.execute("SET search_path TO public")

    await prune_finished_jobs(env.app)

    left = {
        row["task_name"] for row in await db.fetch("SELECT task_name FROM jobs.procrastinate_jobs")
    }
    assert left == {"recent_done", "old_waiting"}


async def test_outside_local_the_api_refuses_a_login_that_is_not_lifeos_app(migrated: str) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.platform.config import ConfigError, Settings

    settings = Settings(
        env="production",
        app_origin="https://a.example",
        database_url=migrated,
        lifeos_kek=TEST_KEK,
        ip_hmac_key=TEST_IP_KEY,
    )
    with pytest.raises(ConfigError, match="lifeos_app"), TestClient(create_app(settings)):
        pass
