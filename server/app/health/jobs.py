"""health: Procrastinate jobs (spec 8.5, 10.1)."""

import uuid

import procrastinate

from app.health.service import DailyLogService
from app.platform import outbox
from app.platform.crypto import Keyring
from app.platform.jobs import Runtime

REBUILD_TASK = "health.rebuild_cycles"
NIGHTLY_TASK = "health.nightly_predict"


def register(
    app: procrastinate.App,
    runtime: Runtime,
    keyring: Keyring,
) -> None:
    """Register health jobs: rebuild_cycles and nightly_predict (spec 8.5, 10.1)."""
    outbox.subscribe("daily_log.flow_changed", REBUILD_TASK)
    outbox.subscribe("health_profile.changed", REBUILD_TASK)

    service = DailyLogService(runtime.app_engine, keyring)

    @app.task(name=REBUILD_TASK)
    async def rebuild_cycles(user_id: str) -> None:
        await service.rebuild_for_user(uuid.UUID(user_id))

    @app.periodic(cron="5 3 * * *", periodic_id=NIGHTLY_TASK)
    @app.task(name=NIGHTLY_TASK, queueing_lock=NIGHTLY_TASK)
    async def nightly_predict(timestamp: int | None = None) -> None:
        await service.nightly_predict_all_users(app, runtime.jobs_engine)
