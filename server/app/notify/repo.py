"""notify: SQL for push subscriptions and reminders (spec 7.2). Called inside a user
transaction, so RLS limits every statement to that user's rows."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.platform.db import Transaction

# SQLSTATE 42501 (insufficient_privilege): the row-level security policy refused the statement.
RLS_REFUSED = "42501"


@dataclass(frozen=True)
class SubscriptionRow:
    id: uuid.UUID
    endpoint: str
    p256dh: str
    auth: str


async def upsert_subscription(
    tx: Transaction,
    *,
    subscription_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    endpoint: str,
    p256dh: str,
    auth: str,
    device_label: str | None,
    now: datetime,
) -> bool:
    """Save the subscription, or refresh it (new keys, this session, turned back on) when the
    browser sends the same endpoint again (10.5: re-registered on every app start). False when
    the endpoint is another account's row: RLS hides it, so the update is refused."""
    try:
        async with tx.begin_nested():
            await _upsert(
                tx,
                {
                    "id": subscription_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "endpoint": endpoint,
                    "p256dh": p256dh,
                    "auth": auth,
                    "label": device_label,
                    "now": now,
                },
            )
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == RLS_REFUSED:
            return False
        raise  # anything else is a fault, not "another account's endpoint"
    return True


async def _upsert(tx: Transaction, values: dict[str, object]) -> None:
    await tx.execute(
        text(
            "INSERT INTO push_subscriptions"
            " (id, user_id, session_id, endpoint, p256dh, auth, device_label, created_at)"
            " VALUES (:id, :user_id, :session_id, :endpoint, :p256dh, :auth, :label, :now)"
            " ON CONFLICT (endpoint) DO UPDATE SET"
            " session_id = EXCLUDED.session_id, p256dh = EXCLUDED.p256dh,"
            " auth = EXCLUDED.auth,"
            # 10.5: the service worker resubscribes without a label; keep the saved one.
            " device_label = COALESCE(EXCLUDED.device_label, push_subscriptions.device_label),"
            " failure_count = 0, disabled_at = NULL"
        ),
        values,
    )


async def delete_subscription(tx: Transaction, endpoint: str) -> bool:
    result = await tx.execute(
        text("DELETE FROM push_subscriptions WHERE endpoint = :endpoint"), {"endpoint": endpoint}
    )
    return bool(result.rowcount)


async def active_subscriptions(tx: Transaction) -> list[SubscriptionRow]:
    rows = await tx.execute(
        text(
            "SELECT id, endpoint, p256dh, auth FROM push_subscriptions"
            " WHERE disabled_at IS NULL ORDER BY created_at"
        )
    )
    return [SubscriptionRow(r.id, r.endpoint, r.p256dh, r.auth) for r in rows]


async def mark_delivered(tx: Transaction, subscription_id: uuid.UUID, now: datetime) -> None:
    await tx.execute(
        text(
            "UPDATE push_subscriptions SET last_success_at = :now, failure_count = 0 WHERE id = :id"
        ),
        {"id": subscription_id, "now": now},
    )


async def mark_failed(tx: Transaction, subscription_id: uuid.UUID) -> None:
    await tx.execute(
        text(
            "UPDATE push_subscriptions SET failure_count = LEAST(failure_count + 1, 32767)"
            " WHERE id = :id"
        ),
        {"id": subscription_id},
    )


async def disable(tx: Transaction, subscription_id: uuid.UUID, now: datetime) -> None:
    await tx.execute(
        text("UPDATE push_subscriptions SET disabled_at = :now WHERE id = :id"),
        {"id": subscription_id, "now": now},
    )


async def disable_for_session(tx: Transaction, session_id: uuid.UUID, now: datetime) -> None:
    await tx.execute(
        text(
            "UPDATE push_subscriptions SET disabled_at = :now"
            " WHERE session_id = :session_id AND disabled_at IS NULL"
        ),
        {"session_id": session_id, "now": now},
    )


async def discreet_notifications(tx: Transaction) -> bool:
    """`user_settings.discreet_notifications` (7.2, SET-5): the same direct read the dispatcher
    makes (10.3); the settings module (T09) owns the writes."""
    value = await tx.scalar(text("SELECT discreet_notifications FROM user_settings"))
    return bool(value)


@dataclass(frozen=True)
class UserKey:
    dek_wrapped: bytes
    kek_version: int


async def user_key(tx: Transaction, user_id: uuid.UUID) -> UserKey:
    """Her wrapped DEK, to encrypt a reminder's payload: the columns of `users` the dispatcher
    reads too (10.3)."""
    row = (
        await tx.execute(
            text("SELECT dek_wrapped, kek_version FROM users WHERE id = :id"), {"id": user_id}
        )
    ).one()
    return UserKey(row.dek_wrapped, row.kek_version)


async def insert_reminder(
    tx: Transaction,
    *,
    reminder_id: uuid.UUID,
    user_id: uuid.UUID,
    kind: str,
    fire_at: datetime,
    dedupe_key: str,
    payload_enc: bytes,
) -> None:
    """A reminder being sent now (`sending`, first attempt), as the dispatcher marks it (10.3)."""
    await tx.execute(
        text(
            "INSERT INTO reminders"
            " (id, user_id, kind, fire_at, status, attempts, dedupe_key, payload_enc)"
            " VALUES (:id, :user_id, :kind, :fire_at, 'sending', 1, :dedupe_key, :payload)"
        ),
        {
            "id": reminder_id,
            "user_id": user_id,
            "kind": kind,
            "fire_at": fire_at,
            "dedupe_key": dedupe_key,
            "payload": payload_enc,
        },
    )


async def finish_reminder(
    tx: Transaction, reminder_id: uuid.UUID, *, sent_at: datetime | None
) -> None:
    """`sent` with `sent_at` when any device accepted it; otherwise `failed`."""
    await tx.execute(
        text(
            "UPDATE reminders SET status = :status, sent_at = :sent_at, updated_at = now()"
            " WHERE id = :id"
        ),
        {"id": reminder_id, "status": "sent" if sent_at else "failed", "sent_at": sent_at},
    )
