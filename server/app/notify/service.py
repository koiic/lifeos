"""notify: push subscriptions and the test push (spec 9.2, 10.4, 10.7, ONB-3)."""

import re
import uuid
from dataclasses import replace
from datetime import datetime
from urllib.parse import urlsplit

from app.notify import repo
from app.notify.schemas import ReminderAction, ReminderPayload, SubscriptionIn
from app.notify.sender import Outcome, PushMessage, Subscription, discreet, send
from app.platform.crypto import Keyring, Vapid, aad, encrypt_payload, unwrap_dek
from app.platform.db import Database, Transaction, user_transaction
from app.platform.ids import new_id

# The push services of the browsers she can use (Safari, Chrome, Firefox, Edge). The server POSTs
# to a subscription's endpoint, so only these hosts, over https, are accepted: a stored endpoint
# can never make the server call an arbitrary or internal address.
PUSH_SERVICE_HOSTS = (
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
    "web.push.apple.com",
)
PUSH_SERVICE_SUFFIXES = (".push.apple.com", ".notify.windows.com")
LOCAL_HOSTS = ("127.0.0.1", "localhost")
# Never in a push service's endpoint, and read differently by different URL parsers: user info,
# backslashes, whitespace and control characters. Refusing them keeps our check and the HTTP
# client agreeing on the host.
# A host label as push services write them: ASCII letters, digits and hyphens only (no percent
# encoding, no other scripts), so no client can decode it into a different host.
LABEL = re.compile(r"[a-z0-9-]+")
AMBIGUOUS = re.compile(r"[@\\\s\x00-\x1f\x7f]")

# 10.7, the `test` row.
TEST_MESSAGE = PushMessage(
    reminder_id=None,
    kind="test",
    title="Notifications are on",
    body="You'll get reminders here",
    url="/today",
    tag="test",
)


class NotifyError(Exception):
    status = 400
    detail = "The request could not be completed."


class EndpointRefused(NotifyError):
    status = 422
    detail = "This is not a push service address."


class EndpointTaken(NotifyError):
    status = 409
    detail = "This device is already set up for another account."


class SubscriptionNotFound(NotifyError):
    status = 404
    detail = "Not found."


class NoDevice(NotifyError):
    status = 409
    detail = "No device is set up for notifications."


def endpoint_allowed(endpoint: str, *, local: bool) -> bool:
    if AMBIGUOUS.search(endpoint):
        return False
    try:
        parts = urlsplit(endpoint)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    if local and host in LOCAL_HOSTS:
        return parts.scheme in ("http", "https")  # the e2e and test fake push services
    # https, the host alone (no port), plain labels (none empty: ".x", "x..y", a trailing dot).
    if parts.scheme != "https" or parts.netloc.lower() != host:
        return False
    if not all(LABEL.fullmatch(label) for label in host.split(".")):
        return False
    return host in PUSH_SERVICE_HOSTS or host.endswith(PUSH_SERVICE_SUFFIXES)


async def stop_session_notifications(tx: Transaction, session_id: uuid.UUID, now: datetime) -> None:
    """CR-027 (12.1, lost phone): a session that ends — signed out, revoked, locked out — takes
    its device's subscription with it, in the caller's transaction. The device turns it back on
    when it saves its subscription after the next sign-in (10.5)."""
    await repo.disable_for_session(tx, session_id, now)


class NotifyService:
    def __init__(self, engine: Database, vapid: Vapid, keyring: Keyring, *, local: bool) -> None:
        self._db = engine
        self._vapid = vapid
        self._keyring = keyring
        self._local = local

    @property
    def vapid_public_key(self) -> str:
        return self._vapid.public_key

    async def save_subscription(
        self, user_id: uuid.UUID, session_id: uuid.UUID, data: SubscriptionIn, now: datetime
    ) -> None:
        if not endpoint_allowed(data.endpoint, local=self._local):
            raise EndpointRefused
        async with user_transaction(self._db, user_id) as tx:
            saved = await repo.upsert_subscription(
                tx,
                subscription_id=new_id(),
                user_id=user_id,
                session_id=session_id,
                endpoint=data.endpoint,
                p256dh=data.keys.p256dh,
                auth=data.keys.auth,
                device_label=data.device_label,
                now=now,
            )
        if not saved:
            raise EndpointTaken

    async def remove_subscription(self, user_id: uuid.UUID, endpoint: str) -> None:
        async with user_transaction(self._db, user_id) as tx:
            if not await repo.delete_subscription(tx, endpoint):
                raise SubscriptionNotFound

    async def send_test(self, user_id: uuid.UUID, now: datetime) -> int:
        """ONB-3: the 10.7 test push to every device she has turned on; returns how many the push
        services accepted. Like every nudge it is a `reminders` row (10 intro, 10.2 `test`, fire
        time now): `sending`, then `sent` or `failed`. Gone subscriptions are turned off (10.3),
        failures counted; retries are the dispatcher's (T30)."""
        reminder_id = new_id()
        async with user_transaction(self._db, user_id) as tx:
            subscriptions = await repo.active_subscriptions(tx)
            if not subscriptions:
                raise NoDevice
            hide = await repo.discreet_notifications(tx)
            key = await repo.user_key(tx, user_id)
            dek = unwrap_dek(self._keyring, key.kek_version, key.dek_wrapped, user_id)
            await repo.insert_reminder(
                tx,
                reminder_id=reminder_id,
                user_id=user_id,
                kind=TEST_MESSAGE.kind,
                fire_at=now,
                dedupe_key=f"test:{reminder_id}",
                payload_enc=encrypt_payload(
                    dek,
                    ReminderPayload(
                        title=TEST_MESSAGE.title,
                        body=TEST_MESSAGE.body,
                        url=TEST_MESSAGE.url,
                        actions=[
                            ReminderAction(action=a.action, title=a.title)
                            for a in TEST_MESSAGE.actions
                        ],
                    ),
                    aad("reminders", "payload_enc", reminder_id, user_id),
                ),
            )
        message = replace(TEST_MESSAGE, reminder_id=str(reminder_id))
        message = discreet(message) if hide else message
        outcomes: list[tuple[repo.SubscriptionRow, Outcome | None]] = []
        for row in subscriptions:
            if not endpoint_allowed(row.endpoint, local=self._local):
                outcomes.append((row, None))  # checked again before every send, never called
                continue
            subscription = Subscription(row.endpoint, row.p256dh, row.auth)
            outcomes.append((row, await send(subscription, message, self._vapid)))
        delivered = sum(outcome is Outcome.DELIVERED for _, outcome in outcomes)
        async with user_transaction(self._db, user_id) as tx:
            for row, outcome in outcomes:
                if outcome is Outcome.DELIVERED:
                    await repo.mark_delivered(tx, row.id, now)
                elif outcome is Outcome.GONE or outcome is None:
                    await repo.disable(tx, row.id, now)
                else:
                    await repo.mark_failed(tx, row.id)
            await repo.finish_reminder(tx, reminder_id, sent_at=now if delivered else None)
        return delivered
