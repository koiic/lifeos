"""Job tests for health rebuild and nightly predict (spec 8.5, 10.1, CYC-1, CYC-7)."""

import json

import pytest

from app.platform import outbox
from tests.jobs.conftest import JobEnv, create_user, jobs_named, write_event

pytestmark = pytest.mark.integration

REBUILD_TASK = "health.rebuild_cycles"
NIGHTLY_TASK = "health.nightly_predict"


async def run_worker(env: JobEnv) -> None:
    await env.app.run_worker_async(wait=False, install_signal_handlers=False, concurrency=1)


@pytest.mark.req("CYC-1", "CYC-7")
async def test_flow_changed_outbox_event_relays_to_rebuild_cycles(env: JobEnv) -> None:
    """Spec 8.5, 10.1: Outbox event daily_log.flow_changed relays to health.rebuild_cycles."""
    alice = await create_user(env.superuser)
    await write_event(env.superuser, alice, "daily_log.flow_changed")

    # Run outbox relay
    processed = await outbox.relay_outbox(env.runtime, env.app)
    assert processed >= 1

    # Verify health.rebuild_cycles was queued for Alice
    jobs = await jobs_named(env.superuser, REBUILD_TASK)
    assert len(jobs) == 1
    assert json.loads(jobs[0]["args"]) == {"user_id": str(alice)}
    assert jobs[0]["lock"] == f"user:{alice}"
    assert jobs[0]["queueing_lock"] == f"{REBUILD_TASK}:{alice}"


@pytest.mark.req("CYC-1")
async def test_health_profile_changed_outbox_event_relays_to_rebuild_cycles(env: JobEnv) -> None:
    """Spec 8.5, 10.1: Outbox event health_profile.changed relays to health.rebuild_cycles."""
    bob = await create_user(env.superuser)
    await write_event(env.superuser, bob, "health_profile.changed")

    processed = await outbox.relay_outbox(env.runtime, env.app)
    assert processed >= 1

    jobs = await jobs_named(env.superuser, REBUILD_TASK)
    assert len(jobs) == 1
    assert json.loads(jobs[0]["args"]) == {"user_id": str(bob)}


@pytest.mark.req("CYC-1", "CYC-7")
def test_nightly_predict_periodic_job_registration(env: JobEnv) -> None:
    """Spec 8.5, 10.1, CYC-1, CYC-7: health.nightly_predict daily cron at 03:05 UTC."""
    periodic = env.app.periodic_registry.periodic_tasks
    matching = [t for k, t in periodic.items() if k[0] == NIGHTLY_TASK]
    assert len(matching) == 1
    task = matching[0]
    assert task.cron == "5 3 * * *"
    assert task.task.queueing_lock == NIGHTLY_TASK
