"""T05: jobs for the same user are serialised (spec 8.5 "Procrastinate `queueing_lock`")."""

import json
import uuid

import pytest

from app.platform.jobs import defer_for_user
from tests.jobs.conftest import JobEnv, jobs_named

pytestmark = pytest.mark.integration


@pytest.fixture
def tasks(env: JobEnv) -> list[str]:
    names = ["tests.first", "tests.second"]
    for name in names:

        async def noop(user_id: str) -> None:
            return None

        env.app.task(name=name)(noop)
    return names


async def test_deferred_jobs_carry_the_user_lock_and_queueing_lock(
    env: JobEnv, tasks: list[str]
) -> None:
    user = uuid.uuid4()
    await defer_for_user(env.app, tasks[0], user)
    [job] = await jobs_named(env.superuser, tasks[0])
    assert job["lock"] == f"user:{user}"
    assert job["queueing_lock"] == f"{tasks[0]}:{user}"
    assert json.loads(job["args"]) == {"user_id": str(user)}


async def test_the_same_job_for_the_same_user_is_queued_once(env: JobEnv, tasks: list[str]) -> None:
    user, other = uuid.uuid4(), uuid.uuid4()
    assert await defer_for_user(env.app, tasks[0], user) is True
    assert await defer_for_user(env.app, tasks[0], user) is False
    assert await defer_for_user(env.app, tasks[0], user) is False
    await defer_for_user(env.app, tasks[0], other)
    await defer_for_user(env.app, tasks[1], user)
    assert len(await jobs_named(env.superuser, tasks[0])) == 2
    assert len(await jobs_named(env.superuser, tasks[1])) == 1


async def test_a_users_next_job_waits_while_another_of_theirs_runs(
    env: JobEnv, tasks: list[str]
) -> None:
    user, other = uuid.uuid4(), uuid.uuid4()
    await defer_for_user(env.app, tasks[0], user)
    await defer_for_user(env.app, tasks[1], user)
    await defer_for_user(env.app, tasks[1], other)
    manager = env.app.job_manager
    worker_id = await manager.register_worker()

    first = await manager.fetch_job(queues=None, worker_id=worker_id)
    assert first is not None
    assert first.lock == f"user:{user}"
    # The user's second job is not handed out while the first is running; the other user's is.
    second = await manager.fetch_job(queues=None, worker_id=worker_id)
    assert second is not None
    assert second.lock == f"user:{other}"
    assert await manager.fetch_job(queues=None, worker_id=worker_id) is None
