"""Outbox relay (spec 6.2, 8.5, 10.1).

Modules write `outbox_events` in the same transaction as their change and `subscribe` jobs to
topics. `outbox.relay` runs every minute and whenever an event is written (the `outbox_queue_relay`
trigger queues it), reads unprocessed events of subscribed topics as `lifeos_jobs`, queues each
subscribed job for the event's user, then marks the events processed. Jobs are queued (and committed
on Procrastinate's own connection) before the events are marked, so delivery is at-least-once;
jobs are idempotent and the per-user queueing lock drops duplicates still waiting. Events of topics
this worker does not know stay unprocessed for a worker that does (e.g. during a deploy).
"""

import uuid

import procrastinate
import structlog
from sqlalchemy import text

from app.platform.jobs import Runtime, defer_for_user

RELAY_TASK = "outbox.relay"
BATCH = 500

log = structlog.get_logger()

_subscriptions: dict[str, list[str]] = {}


def subscribe(topic: str, task_name: str) -> None:
    tasks = _subscriptions.setdefault(topic, [])
    if task_name not in tasks:
        tasks.append(task_name)


async def relay_outbox(runtime: Runtime, app: procrastinate.App) -> int:
    """Relay one batch of unprocessed events; returns how many were processed."""
    topics = sorted(topic for topic, tasks in _subscriptions.items() if tasks)
    async with runtime.jobs_engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, topic, user_id FROM outbox_events"
                    " WHERE processed_at IS NULL AND topic = ANY(:topics)"
                    " ORDER BY id LIMIT :batch FOR UPDATE SKIP LOCKED"
                ),
                {"topics": topics, "batch": BATCH},
            )
        ).all()
        for row in rows:
            for task_name in _subscriptions[row.topic]:
                await defer_for_user(app, task_name, uuid.UUID(str(row.user_id)))
        if rows:
            await conn.execute(
                text("UPDATE outbox_events SET processed_at = now() WHERE id = ANY(:ids)"),
                {"ids": [row.id for row in rows]},
            )
        waiting = (
            await conn.execute(
                text(
                    "SELECT topic, count(*) AS events FROM outbox_events"
                    " WHERE processed_at IS NULL AND NOT (topic = ANY(:topics)) GROUP BY topic"
                ),
                {"topics": topics},
            )
        ).all()
    for topic, events in waiting:
        log.warning("outbox.unknown_topic", topic=topic, events=events)
    if rows:
        log.info("outbox.relayed", count=len(rows))
    return len(rows)


async def relay_all(runtime: Runtime, app: procrastinate.App) -> int:
    """Relay batches until the backlog is empty; returns how many events were processed."""
    total = 0
    while (processed := await relay_outbox(runtime, app)) > 0:
        total += processed
        if processed < BATCH:
            break
    return total


def register(app: procrastinate.App, runtime: Runtime) -> None:
    """Register `outbox.relay`: queued by the trigger, and periodic every minute."""

    @app.periodic(cron="* * * * *", periodic_id=RELAY_TASK)
    @app.task(name=RELAY_TASK, queueing_lock=RELAY_TASK)
    async def relay(timestamp: int | None = None) -> None:
        await relay_all(runtime, app)
