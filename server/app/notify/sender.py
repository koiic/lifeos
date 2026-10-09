"""notify: one Web Push (spec 10.4), sent with pywebpush and VAPID.

The message is end-to-end encrypted to the browser (aes128gcm); the push service sees only the
headers. `send` returns what the dispatcher (10.3) acts on and never logs the message (12.5).
"""

import base64
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any, Literal

import aiohttp
import structlog
from pywebpush import WebPushException, webpush_async

from app.platform.crypto import Vapid

log = structlog.get_logger()

# `reminders.kind` (7.2).
Kind = Literal["checkin", "period_due", "late_period", "medication", "appointment", "task", "test"]

# 10.4: medication and appointment reminders matter within hours; the rest within a day.
TIMELY: frozenset[str] = frozenset({"medication", "appointment"})
SEND_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class Action:
    action: str
    title: str


@dataclass(frozen=True)
class PushMessage:
    """The 10.4 payload."""

    reminder_id: str | None
    kind: Kind
    title: str
    body: str
    url: str
    tag: str
    actions: tuple[Action, ...] = ()
    badge_count: int | None = None

    def payload(self) -> dict[str, object]:
        data = asdict(self)
        data["actions"] = [asdict(action) for action in self.actions]
        return data


@dataclass(frozen=True)
class Subscription:
    endpoint: str
    p256dh: str
    auth: str


class Outcome(Enum):
    DELIVERED = "delivered"  # the push service accepted it (201/202)
    GONE = "gone"  # 404/410: the browser dropped the subscription; disable it (10.3)
    RETRY = "retry"  # 429, 5xx or unreachable: try again later (10.3)
    REJECTED = "rejected"  # any other answer: this message will not go


def ttl_for(kind: Kind) -> int:
    return 21_600 if kind in TIMELY else 86_400


def urgency_for(kind: Kind) -> str:
    return "high" if kind in TIMELY else "normal"


def topic_for(tag: str) -> str:
    """RFC 8030 Topic: at most 32 URL-safe base64 characters; a newer message with the same tag
    replaces an undelivered older one (10.4)."""
    return base64.urlsafe_b64encode(hashlib.sha256(tag.encode()).digest()).decode()[:32]


def discreet(message: PushMessage) -> PushMessage:
    """10.4, 10.7: nothing on the lock screen says what the reminder is about."""
    return replace(message, title="Life OS", body="You have a reminder", actions=())


def _outcome(status: int) -> Outcome:
    if status in (201, 202):
        return Outcome.DELIVERED
    if status in (404, 410):
        return Outcome.GONE
    if status == 429 or status >= 500:
        return Outcome.RETRY
    return Outcome.REJECTED


class _NoRedirects:
    """The session pywebpush posts through. aiohttp follows up to 10 redirects by default, which
    would resend the encrypted message and the VAPID header to an address the endpoint allowlist
    never checked (CR-027); here a redirect is just an answer (`rejected`)."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    def post(self, url: str, **kwargs: Any) -> Any:
        return self._session.post(url, allow_redirects=False, **kwargs)


async def send(subscription: Subscription, message: PushMessage, vapid: Vapid) -> Outcome:
    """Send one message to one subscription. Logs the kind and outcome only."""
    try:
        async with aiohttp.ClientSession() as session:
            response = await _post(subscription, message, vapid, _NoRedirects(session))
            # Fail closed: only a push service's answer can count as delivered.
            status = response.status if isinstance(response, aiohttp.ClientResponse) else -1
    except WebPushException as error:
        status = error.response.status if error.response is not None else 0
    except (aiohttp.ClientError, TimeoutError, OSError):
        status = 0
    except Exception as error:  # one bad row must not stop the others (10.3)
        # Keys that are not a key, an endpoint the HTTP client refuses: never sendable as is.
        # Only the type is logged: messages can quote the subscription.
        log.warning(
            "push.sent",
            kind=message.kind,
            outcome=Outcome.REJECTED.value,
            status=None,
            error=type(error).__name__,
        )
        return Outcome.REJECTED
    outcome = Outcome.RETRY if status == 0 else _outcome(status)
    log.info("push.sent", kind=message.kind, outcome=outcome.value, status=status)
    return outcome


async def _post(
    subscription: Subscription, message: PushMessage, vapid: Vapid, session: _NoRedirects
) -> Any:
    return await webpush_async(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        },
        data=json.dumps(message.payload(), ensure_ascii=False),
        vapid_private_key=vapid.private_key,
        vapid_claims={"sub": vapid.subject},
        ttl=ttl_for(message.kind),
        headers={"Urgency": urgency_for(message.kind), "Topic": topic_for(message.tag)},
        timeout=SEND_TIMEOUT_S,
        aiohttp_session=session,
    )
