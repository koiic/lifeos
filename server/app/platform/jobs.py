"""Job queue primitives (spec 6.2 "job registration", 7.3, 8.5, 10.1).

- `Runtime`: the worker's engines — `lifeos_app` for per-user work, `lifeos_jobs` for finding work
  across users.
- `new_job_app`: a Procrastinate app whose connections run as `lifeos_jobs` with
  `search_path = jobs, public` (its tables live in schema `jobs`).
- `defer_for_user`: queue a job for one user, serialised per user (lock `user:<id>`) and never
  queued twice while waiting (queueing lock `<task>:<id>`).
- Jobs use `app.platform.db.user_transaction`: a `lifeos_app` transaction with `app.user_id` set,
  which every job opens before touching user tables (spec 7.3).
"""

import uuid
from dataclasses import dataclass

import procrastinate
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy.ext.asyncio import AsyncEngine

from app.platform.config import ConfigError, Settings
from app.platform.db import APP_ROLE, JOBS_ROLE, create_engine

# pg_temp last: temporary tables can never shadow the queue tables.
JOBS_SEARCH_PATH = "jobs,public,pg_temp"
PRUNE_TASK = "jobs.prune_finished"
FINISHED_JOB_RETENTION_HOURS = 7 * 24


@dataclass(frozen=True)
class Runtime:
    app_engine: AsyncEngine
    jobs_engine: AsyncEngine

    async def dispose(self) -> None:
        await self.app_engine.dispose()
        await self.jobs_engine.dispose()


def _jobs_url(settings: Settings) -> str:
    if settings.database_jobs_url is None:
        raise ConfigError("secret file database_jobs_url is required to run the worker")
    return settings.database_jobs_url.get_secret_value()


def create_runtime(settings: Settings) -> Runtime:
    return Runtime(
        app_engine=create_engine(settings.database_url.get_secret_value(), APP_ROLE),
        jobs_engine=create_engine(_jobs_url(settings), JOBS_ROLE),
    )


def new_job_app(settings: Settings) -> procrastinate.App:
    connector = procrastinate.PsycopgConnector(
        conninfo=_jobs_url(settings).replace("+asyncpg", ""),
        kwargs={"options": f"-c search_path={JOBS_SEARCH_PATH} -c role={JOBS_ROLE}"},
    )
    return procrastinate.App(connector=connector)


async def defer_for_user(app: procrastinate.App, task_name: str, user_id: uuid.UUID) -> bool:
    """Queue `task_name(user_id=…)`; returns False when the same job is already waiting."""
    try:
        await app.configure_task(
            task_name, lock=f"user:{user_id}", queueing_lock=f"{task_name}:{user_id}"
        ).defer_async(user_id=str(user_id))
    except AlreadyEnqueued:
        return False
    return True


def register_maintenance(app: procrastinate.App) -> None:
    """Delete finished jobs after 7 days, daily (data minimisation, spec 12.6): job history would
    otherwise keep a per-user timeline of activity forever."""

    @app.periodic(cron="20 4 * * *", periodic_id=PRUNE_TASK)
    @app.task(name=PRUNE_TASK, queueing_lock=PRUNE_TASK)
    async def prune_finished(timestamp: int | None = None) -> None:
        await prune_finished_jobs(app)


async def prune_finished_jobs(app: procrastinate.App) -> None:
    await app.job_manager.delete_old_jobs(
        nb_hours=FINISHED_JOB_RETENTION_HOURS,
        include_failed=True,
        include_cancelled=True,
        include_aborted=True,
    )
