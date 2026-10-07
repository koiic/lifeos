"""T05: writing an outbox event queues the relay in the same transaction (10.1 "on NOTIFY")."""

import asyncpg
import pytest

from tests.jobs.conftest import JobEnv, create_user, jobs_named, write_event

pytestmark = pytest.mark.integration


async def test_an_event_queues_one_relay_job(env: JobEnv) -> None:
    alice = await create_user(env.superuser)
    await write_event(env.superuser, alice, "x.changed")
    [job] = await jobs_named(env.superuser, "outbox.relay")
    assert job["status"] == "todo"
    assert job["queueing_lock"] == "outbox.relay"


async def test_more_events_do_not_queue_more_relays_or_fail(env: JobEnv) -> None:
    alice = await create_user(env.superuser)
    bob = await create_user(env.superuser)
    for user in (alice, bob, alice):
        await write_event(env.superuser, user, "x.changed")
    assert len(await jobs_named(env.superuser, "outbox.relay")) == 1
    assert await env.superuser.fetchval("SELECT count(*) FROM outbox_events") == 3


async def test_a_rolled_back_event_queues_nothing(env: JobEnv) -> None:
    alice = await create_user(env.superuser)
    tx = env.superuser.transaction()
    await tx.start()
    try:
        await env.superuser.execute("SET LOCAL ROLE lifeos_app")
        await env.superuser.execute("SELECT set_config('app.user_id', $1, true)", str(alice))
        await env.superuser.execute(
            "INSERT INTO outbox_events (user_id, topic, body) VALUES ($1, 'x.changed', '{}')",
            alice,
        )
    finally:
        await tx.rollback()
    assert await jobs_named(env.superuser, "outbox.relay") == []


async def test_no_role_can_execute_the_trigger_function_directly(
    env: JobEnv,
) -> None:
    async with env.superuser.transaction():
        await env.superuser.execute("SET LOCAL ROLE lifeos_app")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with env.superuser.transaction():
                await env.superuser.execute("SELECT public.outbox_queue_relay()")


async def test_an_event_during_a_running_relay_queues_a_new_one(env: JobEnv) -> None:
    alice = await create_user(env.superuser)
    await write_event(env.superuser, alice, "x.changed")
    # The queueing lock only covers waiting ('todo') jobs: once the relay is running, a new event
    # must queue the next relay so it is not missed.
    async with env.superuser.transaction():
        # Procrastinate's own triggers use unqualified names: run with its search_path.
        await env.superuser.execute("SET LOCAL search_path TO jobs, public, pg_temp")
        await env.superuser.execute(
            "UPDATE procrastinate_jobs SET status = 'doing' WHERE task_name = 'outbox.relay'"
        )
    await write_event(env.superuser, alice, "x.changed")
    statuses = sorted(job["status"] for job in await jobs_named(env.superuser, "outbox.relay"))
    assert statuses == ["doing", "todo"]
