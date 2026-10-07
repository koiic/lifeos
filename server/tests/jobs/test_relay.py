"""T05: outbox event → relay → job runs with app.user_id set (spec 6.2, 7.3, 8.5, 10.1)."""

import io
import json
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text

from app.platform import outbox
from app.platform.db import user_transaction
from app.platform.jobs import Runtime
from app.platform.logging import configure_logging
from tests.jobs.conftest import JobEnv, create_user, jobs_named, write_event

pytestmark = pytest.mark.integration

TOPIC = "test.changed"
TASK = "tests.record_user"


@pytest.fixture
def seen(env: JobEnv, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Register a test task subscribed to TOPIC that records what it sees as lifeos_app."""
    records: list[dict[str, object]] = []

    @env.app.task(name=TASK)
    async def record_user(user_id: str) -> None:
        async with user_transaction(env.runtime.app_engine, uuid.UUID(user_id)) as conn:
            setting = (await conn.execute(text("SELECT current_setting('app.user_id')"))).scalar()
            role = (await conn.execute(text("SELECT current_user"))).scalar()
            owners = (await conn.execute(text("SELECT DISTINCT user_id FROM outbox_events"))).all()
            records.append({"user_id": user_id, "setting": setting, "role": role, "owners": owners})

    monkeypatch.setattr(outbox, "_subscriptions", {})  # restored after the test
    outbox.subscribe(TOPIC, TASK)
    return records


async def run_worker(env: JobEnv) -> None:
    # concurrency=1: the worker stops once the queue is empty, so jobs queued by a running relay
    # must be fetched by the same single loop (higher concurrency could stop early and flake).
    await env.app.run_worker_async(wait=False, install_signal_handlers=False, concurrency=1)


async def test_event_relay_job_runs_as_the_user(env: JobEnv, seen: list[dict[str, object]]) -> None:
    alice = await create_user(env.superuser)
    bob = await create_user(env.superuser)
    await write_event(env.superuser, alice, TOPIC)
    await write_event(env.superuser, bob, "other.topic.nobody.handles")

    await run_worker(env)

    assert len(seen) == 1
    record = seen[0]
    assert record["user_id"] == str(alice)
    assert record["setting"] == str(alice)
    assert record["role"] == "lifeos_app"
    # Under RLS the job sees only Alice's outbox rows, never Bob's.
    assert record["owners"] == [(alice,)]
    unprocessed = await env.superuser.fetch(
        "SELECT topic FROM outbox_events WHERE processed_at IS NULL"
    )
    assert [row["topic"] for row in unprocessed] == ["other.topic.nobody.handles"]
    [job] = await jobs_named(env.superuser, TASK)
    assert job["status"] == "succeeded"
    assert json.loads(job["args"]) == {"user_id": str(alice)}


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    configure_logging(stream)
    yield stream
    configure_logging()  # back to stdout for later tests


async def test_unknown_topics_wait_for_a_worker_that_knows_them(
    env: JobEnv, seen: list[dict[str, object]], log_stream: io.StringIO
) -> None:
    alice = await create_user(env.superuser)
    await write_event(env.superuser, alice, "nobody.listens")
    await write_event(env.superuser, alice, TOPIC)

    await run_worker(env)

    # The known event is relayed; the unknown one stays for a newer worker (deploy skew).
    remaining = await env.superuser.fetch(
        "SELECT topic FROM outbox_events WHERE processed_at IS NULL"
    )
    assert [row["topic"] for row in remaining] == ["nobody.listens"]
    assert len(seen) == 1
    lines = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    warnings = [line for line in lines if line["event"] == "outbox.unknown_topic"]
    assert warnings
    assert {(w["topic"], w["events"]) for w in warnings} == {("nobody.listens", 1)}
    assert str(alice) not in log_stream.getvalue()
    jobs = await env.superuser.fetch(
        "SELECT task_name FROM jobs.procrastinate_jobs WHERE task_name <> 'outbox.relay'"
    )
    assert [row["task_name"] for row in jobs] == [TASK]


async def test_relay_marks_events_processed_only_after_queueing(
    env: JobEnv, seen: list[dict[str, object]]
) -> None:
    alice = await create_user(env.superuser)
    for _ in range(3):
        await write_event(env.superuser, alice, TOPIC)

    relayed = await outbox.relay_outbox(env.runtime, env.app)

    assert relayed == 3
    # Three events for the same user and task: one job (per-user queueing lock).
    assert len(await jobs_named(env.superuser, TASK)) == 1
    assert (
        await env.superuser.fetchval(
            "SELECT count(*) FROM outbox_events WHERE processed_at IS NOT NULL"
        )
        == 3
    )
    assert await outbox.relay_outbox(env.runtime, env.app) == 0


async def test_the_relay_reads_across_users_as_lifeos_jobs(env: JobEnv) -> None:
    async with env.runtime.jobs_engine.connect() as conn:
        role = (await conn.execute(text("SELECT current_user"))).scalar()
    assert role == "lifeos_jobs"


async def test_a_backlog_larger_than_a_batch_is_drained_in_one_run(
    env: JobEnv, seen: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(outbox, "BATCH", 2)
    users = [await create_user(env.superuser) for _ in range(5)]
    for user in users:
        await write_event(env.superuser, user, TOPIC)

    assert await outbox.relay_all(env.runtime, env.app) == 5

    assert (
        await env.superuser.fetchval(
            "SELECT count(*) FROM outbox_events WHERE processed_at IS NULL"
        )
        == 0
    )
    assert len(await jobs_named(env.superuser, TASK)) == 5


async def test_a_failed_queue_leaves_the_whole_batch_unprocessed(
    env: JobEnv, seen: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    users = [await create_user(env.superuser) for _ in range(3)]
    for user in users:
        await write_event(env.superuser, user, TOPIC)
    calls = 0
    real_defer = outbox.defer_for_user

    async def flaky_defer(app: object, task_name: str, user_id: uuid.UUID) -> bool:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("queue unavailable")
        return await real_defer(app, task_name, user_id)  # type: ignore[arg-type]

    monkeypatch.setattr(outbox, "defer_for_user", flaky_defer)
    with pytest.raises(RuntimeError):
        await outbox.relay_outbox(env.runtime, env.app)
    # Nothing is marked processed (at-least-once): the next run relays all three again.
    assert (
        await env.superuser.fetchval(
            "SELECT count(*) FROM outbox_events WHERE processed_at IS NULL"
        )
        == 3
    )
    monkeypatch.setattr(outbox, "defer_for_user", real_defer)
    assert await outbox.relay_outbox(env.runtime, env.app) == 3
    assert len(await jobs_named(env.superuser, TASK)) == 3


async def test_the_relay_only_works_through_the_lifeos_jobs_engine(
    env: JobEnv, seen: list[dict[str, object]]
) -> None:
    alice = await create_user(env.superuser)
    await write_event(env.superuser, alice, TOPIC)
    # The same relay on a lifeos_app engine (no app.user_id) sees no events at all under RLS...
    wrong = Runtime(app_engine=env.runtime.app_engine, jobs_engine=env.runtime.app_engine)
    assert await outbox.relay_outbox(wrong, env.app) == 0
    # ...and on the real runtime it relays, reading as lifeos_jobs.
    assert await outbox.relay_outbox(env.runtime, env.app) == 1
