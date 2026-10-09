"""T14: sending one push (spec 10.4) to a fake push service: the message, encrypted to the
browser; TTL, Urgency and Topic per kind; the VAPID signature; discreet mode; the outcome the
dispatcher acts on (10.3: 404/410 disable the subscription; 429/5xx retry)."""

import base64
import hashlib
import json
import logging
import socket
from urllib.parse import urlsplit

import pytest
import structlog

from app.notify.sender import (
    Action,
    Outcome,
    PushMessage,
    Subscription,
    discreet,
    send,
    topic_for,
    ttl_for,
    urgency_for,
)
from app.platform.crypto import Vapid, generate_vapid_keys
from tests.notify.fake_push import FakePushService, Subscriber, fake_push_service

KEYS = generate_vapid_keys()
VAPID = Vapid(KEYS.public_key, KEYS.private_key, "mailto:admin@example.test")

DOSE = PushMessage(
    reminder_id="0192f2aa-0000-7000-8000-000000000001",
    kind="medication",
    title="Vitamin D",
    body="1 tablet — tap when taken",
    url="/meds/doses/0192f2aa",
    tag="dose:0192f2aa",
    actions=(Action("taken", "Taken"), Action("snooze", "In 15 min")),
    badge_count=2,
)


def b64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@pytest.fixture
def push() -> FakePushService:
    with fake_push_service() as service:
        yield service  # type: ignore[misc]


async def deliver(push: FakePushService, message: PushMessage, path: str = "/s/1") -> Subscriber:
    subscriber = Subscriber.new()
    outcome = await send(
        Subscription(push.url(path), subscriber.p256dh, subscriber.auth_secret), message, VAPID
    )
    assert outcome is Outcome.DELIVERED
    return subscriber


@pytest.mark.parametrize(
    ("kind", "ttl", "urgency"),
    [
        ("medication", 21_600, "high"),
        ("appointment", 21_600, "high"),
        ("checkin", 86_400, "normal"),
        ("period_due", 86_400, "normal"),
        ("late_period", 86_400, "normal"),
        ("task", 86_400, "normal"),
        ("test", 86_400, "normal"),
        ("account", 86_400, "normal"),
    ],
)
def test_ttl_and_urgency_per_kind(kind: str, ttl: int, urgency: str) -> None:
    """10.4: TTL 21,600 s and Urgency high for medication and appointment; 86,400 s and normal
    otherwise."""
    assert ttl_for(kind) == ttl  # type: ignore[arg-type]
    assert urgency_for(kind) == urgency  # type: ignore[arg-type]


def test_topic_is_a_hash_of_the_tag() -> None:
    """10.4: a newer message with the same tag replaces an undelivered older one. RFC 8030: at
    most 32 characters of the URL-safe base64 alphabet."""
    topic = topic_for("dose:0192f2aa")
    assert topic == topic_for("dose:0192f2aa")
    assert topic != topic_for("dose:0192f2bb")
    assert len(topic) <= 32
    assert set(topic) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert (
        topic == base64.urlsafe_b64encode(hashlib.sha256(b"dose:0192f2aa").digest()).decode()[:32]
    )


async def test_the_push_carries_the_headers_of_10_4(push: FakePushService) -> None:
    await deliver(push, DOSE)
    [request] = push.received
    assert request.headers["ttl"] == "21600"
    assert request.headers["urgency"] == "high"
    assert request.headers["topic"] == topic_for(DOSE.tag)
    assert request.headers["content-encoding"] == "aes128gcm"


async def test_the_payload_is_the_10_4_message_encrypted_to_the_browser(
    push: FakePushService,
) -> None:
    subscriber = await deliver(push, DOSE)
    [request] = push.received
    assert b"Vitamin D" not in request.body  # the push service cannot read it
    assert subscriber.decrypt(request.body) == {
        "reminder_id": "0192f2aa-0000-7000-8000-000000000001",
        "kind": "medication",
        "title": "Vitamin D",
        "body": "1 tablet — tap when taken",
        "url": "/meds/doses/0192f2aa",
        "tag": "dose:0192f2aa",
        "actions": [
            {"action": "taken", "title": "Taken"},
            {"action": "snooze", "title": "In 15 min"},
        ],
        "badge_count": 2,
    }


async def test_the_push_is_signed_with_vapid(push: FakePushService) -> None:
    """RFC 8292: `vapid t=<JWT>, k=<public key>`; the JWT names the push service's origin and the
    admin subject."""
    await deliver(push, DOSE)
    [request] = push.received
    scheme, _, params = request.headers["authorization"].partition(" ")
    assert scheme == "vapid"
    fields = dict(part.strip().split("=", 1) for part in params.split(","))
    assert fields["k"] == KEYS.public_key
    claims = json.loads(b64(fields["t"].split(".")[1]))
    endpoint = urlsplit(push.url("/s/1"))
    assert claims["aud"] == f"{endpoint.scheme}://{endpoint.netloc}"
    assert claims["sub"] == "mailto:admin@example.test"


def test_discreet_mode_hides_what_the_reminder_is_about() -> None:
    """10.4, 10.7: title "Life OS", body "You have a reminder", no actions; the rest is kept so
    the tap still opens the right screen."""
    hidden = discreet(DOSE)
    assert hidden.title == "Life OS"
    assert hidden.body == "You have a reminder"
    assert hidden.actions == ()
    assert (hidden.url, hidden.tag, hidden.kind, hidden.reminder_id) == (
        DOSE.url,
        DOSE.tag,
        DOSE.kind,
        DOSE.reminder_id,
    )


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (201, Outcome.DELIVERED),
        (202, Outcome.DELIVERED),
        (404, Outcome.GONE),
        (410, Outcome.GONE),
        (429, Outcome.RETRY),
        (500, Outcome.RETRY),
        (503, Outcome.RETRY),
        (400, Outcome.REJECTED),
        (413, Outcome.REJECTED),
    ],
)
async def test_the_push_service_answer_becomes_an_outcome(
    push: FakePushService, status: int, outcome: Outcome
) -> None:
    """10.3: 404/410 → the subscription is gone (disable it); 429/5xx → retry later."""
    push.statuses["/s/x"] = status
    subscriber = Subscriber.new()
    result = await send(
        Subscription(push.url("/s/x"), subscriber.p256dh, subscriber.auth_secret), DOSE, VAPID
    )
    assert result is outcome


def closed_port() -> int:
    """A port nothing listens on: the OS hands out a free one, which is then closed again."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


async def test_an_unreachable_push_service_is_retried() -> None:
    subscriber = Subscriber.new()
    result = await send(
        Subscription(
            f"http://127.0.0.1:{closed_port()}/s/1", subscriber.p256dh, subscriber.auth_secret
        ),
        DOSE,
        VAPID,
    )
    assert result is Outcome.RETRY


async def test_nothing_of_the_message_is_logged(
    push: FakePushService, caplog: pytest.LogCaptureFixture
) -> None:
    """12.5: push payloads are never logged."""
    caplog.set_level(logging.DEBUG)
    with structlog.testing.capture_logs() as events:
        await deliver(push, DOSE)
        push.statuses["/s/gone"] = 410
        subscriber = Subscriber.new()
        await send(
            Subscription(push.url("/s/gone"), subscriber.p256dh, subscriber.auth_secret),
            DOSE,
            VAPID,
        )
    text = caplog.text + json.dumps(events, default=str)
    for secret in ("Vitamin D", "1 tablet", "/meds/doses", subscriber.auth_secret):
        assert secret not in text


async def test_any_other_failure_rejects_that_subscription_only(
    push: FakePushService,
) -> None:
    """10.3: one bad row (here keys that are not a point on the curve) must not stop a batch;
    only the error's type is logged, never its message."""
    not_a_point = base64.urlsafe_b64encode(b"\x04" + b"\x00" * 64).rstrip(b"=").decode()
    subscriber = Subscriber.new()
    with structlog.testing.capture_logs() as events:
        result = await send(
            Subscription(push.url("/s/bad"), not_a_point, subscriber.auth_secret), DOSE, VAPID
        )
    assert result is Outcome.REJECTED
    assert push.to("/s/bad") == []
    [event] = [e for e in events if e["event"] == "push.sent"]
    assert event["error"] == "ValueError"
    assert set(event) <= {"event", "log_level", "kind", "outcome", "status", "error"}


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_a_redirect_is_never_followed(push: FakePushService, status: int) -> None:
    """CR-027: a redirect would resend the encrypted message and the VAPID header to an address
    the endpoint allowlist never checked (an internal one, say). It is not followed."""
    push.statuses["/s/moved"] = status
    push.redirects["/s/moved"] = push.url("/internal")
    subscriber = Subscriber.new()
    result = await send(
        Subscription(push.url("/s/moved"), subscriber.p256dh, subscriber.auth_secret), DOSE, VAPID
    )
    assert result is Outcome.REJECTED
    assert len(push.to("/s/moved")) == 1
    assert push.to("/internal") == []


async def test_an_answer_that_is_not_a_response_is_not_counted_delivered(
    push: FakePushService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed: only a push service's 201/202 is delivery."""

    async def not_a_response(**_: object) -> str:
        return "curl ..."

    monkeypatch.setattr("app.notify.sender.webpush_async", not_a_response)
    subscriber = Subscriber.new()
    result = await send(
        Subscription(push.url("/s/1"), subscriber.p256dh, subscriber.auth_secret), DOSE, VAPID
    )
    assert result is Outcome.REJECTED
