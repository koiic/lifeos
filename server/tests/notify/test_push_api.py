"""T14: the push endpoints of spec 9.2 — the VAPID key, saving and removing a subscription, and
the test push (ONB-3, 10.7 `test`) — against a fake push service."""

import base64
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import DBAPIError

from app.notify.schemas import SubscriptionIn
from app.notify.service import NotifyService
from app.platform.crypto import Vapid, aad, decrypt, load_keyring, unwrap_dek, vapid_public_key
from app.platform.db import create_engine
from tests.auth.conftest import DOMAIN, AuthEnv
from tests.notify.fake_push import FakePushService, Subscriber, fake_push_service

KEY = "/push/vapid-public-key"
SUBSCRIPTIONS = "/push/subscriptions"
TEST = "/push/test"


@pytest.fixture
def push() -> Iterator[FakePushService]:
    with fake_push_service() as service:
        yield service


async def zee(env: AuthEnv, email: str = f"zee{DOMAIN}") -> uuid.UUID:
    """Register a user with a passkey; the client then holds her session."""
    token = await env.invite(email)
    response = env.register(token, email=email)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["user_id"])


def subscribe(
    env: AuthEnv, push: FakePushService, path: str = "/s/phone", label: str = "iPhone"
) -> Subscriber:
    subscriber = Subscriber.new()
    response = env.post(
        SUBSCRIPTIONS, subscriber.subscription(push.url(path)) | {"device_label": label}
    )
    assert response.status_code == 201, response.text
    return subscriber


# ---------- signed in only (plan 4.6) ----------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", KEY, None),
        ("post", SUBSCRIPTIONS, {"endpoint": "https://fcm.googleapis.com/x", "keys": {}}),
        ("delete", SUBSCRIPTIONS, None),
        ("post", TEST, None),
    ],
)
def test_signed_out_gets_401(env: AuthEnv, method: str, path: str, body: object) -> None:
    if method == "get":
        response = env.get(path)
    elif method == "delete":
        response = env.client.request(
            "DELETE",
            f"/api/v1{path}",
            json={"endpoint": "https://fcm.googleapis.com/x"},
            headers={"Origin": "https://app.test", "X-LifeOS-Client": "web"},
        )
    else:
        response = env.post(path, body)
    assert response.status_code == 401


# ---------- the VAPID key ----------


async def test_the_vapid_public_key_is_the_servers(env: AuthEnv) -> None:
    await zee(env)
    response = env.get(KEY)
    assert response.status_code == 200
    vapid: Vapid = env.app.state.vapid
    assert response.json() == {"public_key": vapid.public_key}
    assert vapid_public_key(vapid.private_key) == vapid.public_key
    raw = base64.urlsafe_b64decode(vapid.public_key + "=" * (-len(vapid.public_key) % 4))
    assert len(raw) == 65


# ---------- subscriptions ----------


@pytest.mark.req("ONB-3")
async def test_a_subscription_is_saved_for_her_and_this_session(
    env: AuthEnv, push: FakePushService
) -> None:
    user_id = await zee(env)
    subscriber = subscribe(env, push)
    row = await env.db.fetchrow(
        "SELECT * FROM push_subscriptions WHERE endpoint = $1", push.url("/s/phone")
    )
    assert row is not None
    assert row["user_id"] == user_id
    assert row["session_id"] is not None
    assert (row["p256dh"], row["auth"], row["device_label"]) == (
        subscriber.p256dh,
        subscriber.auth_secret,
        "iPhone",
    )
    assert row["disabled_at"] is None


async def test_saving_the_same_endpoint_again_updates_it_and_turns_it_back_on(
    env: AuthEnv, push: FakePushService
) -> None:
    """10.5: the app re-registers its subscription on every start; that must not duplicate it."""
    await zee(env)
    subscribe(env, push)
    await env.db.execute(
        "UPDATE push_subscriptions SET disabled_at = now(), failure_count = 3 WHERE endpoint = $1",
        push.url("/s/phone"),
    )
    newer = subscribe(env, push)
    rows = await env.db.fetch(
        "SELECT * FROM push_subscriptions WHERE endpoint = $1", push.url("/s/phone")
    )
    assert len(rows) == 1
    assert rows[0]["p256dh"] == newer.p256dh
    assert rows[0]["disabled_at"] is None
    assert rows[0]["failure_count"] == 0


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/x",  # not https
        "https://evil.example/collect",  # not a push service
        "https://fcm.googleapis.com.evil.example/x",  # look-alike host
        "https://169.254.169.254/latest",  # an internal address
        "ftp://fcm.googleapis.com/x",
        "not a url",
    ],
)
async def test_only_push_service_endpoints_are_accepted(env: AuthEnv, endpoint: str) -> None:
    """The server will POST to the endpoint: only known push services, over https (no requests
    to arbitrary or internal addresses)."""
    await zee(env)
    subscriber = Subscriber.new()
    response = env.post(SUBSCRIPTIONS, subscriber.subscription(endpoint))
    assert response.status_code == 422


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/QGx",
        "https://wns2-db5p.notify.windows.com/w/?token=abc",
    ],
)
async def test_the_browsers_push_services_are_accepted(env: AuthEnv, endpoint: str) -> None:
    await zee(env)
    response = env.post(SUBSCRIPTIONS, Subscriber.new().subscription(endpoint))
    assert response.status_code == 201, response.text


async def test_malformed_keys_are_refused(env: AuthEnv) -> None:
    await zee(env)
    response = env.post(
        SUBSCRIPTIONS,
        {"endpoint": "https://fcm.googleapis.com/x", "keys": {"p256dh": "short", "auth": "x"}},
    )
    assert response.status_code == 422


async def test_a_subscription_is_removed_by_its_endpoint(
    env: AuthEnv, push: FakePushService
) -> None:
    await zee(env)
    subscribe(env, push)
    response = env.client.request(
        "DELETE",
        f"/api/v1{SUBSCRIPTIONS}",
        json={"endpoint": push.url("/s/phone")},
        headers={"Origin": "https://app.test", "X-LifeOS-Client": "web"},
    )
    assert response.status_code == 204
    assert (
        await env.db.fetchval(
            "SELECT count(*) FROM push_subscriptions WHERE endpoint = $1", push.url("/s/phone")
        )
        == 0
    )


# ---------- the test push (ONB-3, 10.7) ----------


@pytest.mark.req("ONB-3")
async def test_the_test_push_reaches_every_device_with_the_10_7_copy(
    env: AuthEnv, push: FakePushService
) -> None:
    await zee(env)
    phone = subscribe(env, push, "/s/phone")
    laptop = subscribe(env, push, "/s/laptop", "Mac")
    response = env.post(TEST)
    assert response.status_code == 200, response.text
    assert response.json() == {"delivered": 2}
    for path, subscriber in (("/s/phone", phone), ("/s/laptop", laptop)):
        [request] = push.to(path)
        message = subscriber.decrypt(request.body)
        assert message["kind"] == "test"
        assert message["title"] == "Notifications are on"
        assert message["body"] == "You'll get reminders here"
        assert message["url"] == "/today"
        assert request.headers["ttl"] == "86400"
        assert request.headers["urgency"] == "normal"
    row = await env.db.fetchrow(
        "SELECT last_success_at, failure_count FROM push_subscriptions WHERE endpoint = $1",
        push.url("/s/phone"),
    )
    assert row is not None
    assert row["last_success_at"] is not None
    assert row["failure_count"] == 0


@pytest.mark.req("ONB-3")
async def test_discreet_notifications_hide_the_test_copy(
    env: AuthEnv, push: FakePushService
) -> None:
    user_id = await zee(env)
    await env.db.execute(
        "UPDATE user_settings SET discreet_notifications = true WHERE user_id = $1", user_id
    )
    phone = subscribe(env, push)
    assert env.post(TEST).json() == {"delivered": 1}
    message = phone.decrypt(push.to("/s/phone")[0].body)
    assert (message["title"], message["body"]) == ("Life OS", "You have a reminder")


async def test_a_gone_subscription_is_turned_off_and_skipped_after(
    env: AuthEnv, push: FakePushService
) -> None:
    """10.3: 404/410 from the push service disables that subscription."""
    await zee(env)
    subscribe(env, push, "/s/old")
    subscribe(env, push, "/s/phone")
    push.statuses["/s/old"] = 410
    assert env.post(TEST).json() == {"delivered": 1}
    disabled = await env.db.fetchval(
        "SELECT disabled_at FROM push_subscriptions WHERE endpoint = $1", push.url("/s/old")
    )
    assert disabled is not None
    assert env.post(TEST).json() == {"delivered": 1}
    assert len(push.to("/s/old")) == 1  # not tried again


async def test_a_failing_push_service_counts_a_failure(env: AuthEnv, push: FakePushService) -> None:
    await zee(env)
    subscribe(env, push)
    push.statuses["/s/phone"] = 503
    assert env.post(TEST).json() == {"delivered": 0}
    row = await env.db.fetchrow(
        "SELECT failure_count, disabled_at FROM push_subscriptions WHERE endpoint = $1",
        push.url("/s/phone"),
    )
    assert row is not None
    assert row["failure_count"] == 1
    assert row["disabled_at"] is None


async def test_without_a_device_the_test_push_says_so(env: AuthEnv) -> None:
    await zee(env)
    response = env.post(TEST)
    assert response.status_code == 409
    assert response.json()["detail"] == "No device is set up for notifications."


# ---------- other users (plan 4.6) ----------


async def test_another_user_cannot_reach_or_remove_her_subscription(
    env: AuthEnv, push: FakePushService
) -> None:
    await zee(env)
    subscribe(env, push, "/s/zee")
    env.client.cookies.clear()
    await zee(env, f"other{DOMAIN}")
    subscribe(env, push, "/s/other")
    assert env.post(TEST).json() == {"delivered": 1}
    assert push.to("/s/zee") == []
    response = env.client.request(
        "DELETE",
        f"/api/v1{SUBSCRIPTIONS}",
        json={"endpoint": push.url("/s/zee")},
        headers={"Origin": "https://app.test", "X-LifeOS-Client": "web"},
    )
    assert response.status_code == 404
    assert (
        await env.db.fetchval(
            "SELECT count(*) FROM push_subscriptions WHERE endpoint = $1", push.url("/s/zee")
        )
        == 1
    )


async def test_an_endpoint_of_another_account_is_refused_and_left_alone(
    env: AuthEnv, push: FakePushService
) -> None:
    """The same browser endpoint cannot be taken over by a second account (RLS hides the row)."""
    first = await zee(env)
    subscribe(env, push, "/s/shared")
    env.client.cookies.clear()
    await zee(env, f"other{DOMAIN}")
    response = env.post(SUBSCRIPTIONS, Subscriber.new().subscription(push.url("/s/shared")))
    assert response.status_code == 409
    owner = await env.db.fetchval(
        "SELECT user_id FROM push_subscriptions WHERE endpoint = $1", push.url("/s/shared")
    )
    assert owner == first


# ---------- 9.4 strings ----------


async def test_the_device_label_is_cleaned(env: AuthEnv, push: FakePushService) -> None:
    """9.4: trimmed, control and format characters stripped, Unicode NFC."""
    await zee(env)
    subscribe(env, push, label="  Zee\u0007's\u200b phone e\u0301 ")
    label = await env.db.fetchval(
        "SELECT device_label FROM push_subscriptions WHERE endpoint = $1", push.url("/s/phone")
    )
    assert label == "Zee's phone \u00e9"


async def test_a_resubscribe_without_a_label_keeps_the_label(
    env: AuthEnv, push: FakePushService
) -> None:
    """The service worker's pushsubscriptionchange (10.5) sends no label; keep the one saved."""
    await zee(env)
    subscribe(env, push, label="iPhone")
    response = env.post(SUBSCRIPTIONS, Subscriber.new().subscription(push.url("/s/phone")))
    assert response.status_code == 201
    label = await env.db.fetchval(
        "SELECT device_label FROM push_subscriptions WHERE endpoint = $1", push.url("/s/phone")
    )
    assert label == "iPhone"


# ---------- the test push is a reminder (spec 10 intro, 10.2 `test`) ----------


async def reminder_payload(env: AuthEnv, user_id: uuid.UUID, row_id: uuid.UUID, blob: bytes):  # type: ignore[no-untyped-def]
    keyring = load_keyring(env.app.state.settings)
    user = await env.db.fetchrow(
        "SELECT dek_wrapped, kek_version FROM users WHERE id = $1", user_id
    )
    assert user is not None
    dek = unwrap_dek(keyring, user["kek_version"], user["dek_wrapped"], user_id)
    return json.loads(decrypt(dek, blob, aad("reminders", "payload_enc", row_id, user_id)))


@pytest.mark.req("ONB-3")
async def test_the_test_push_is_a_reminders_row_sent_now(
    env: AuthEnv, push: FakePushService
) -> None:
    user_id = await zee(env)
    phone = subscribe(env, push)
    assert env.post(TEST).json() == {"delivered": 1}
    [row] = await env.db.fetch("SELECT * FROM reminders WHERE user_id = $1", user_id)
    assert row["kind"] == "test"
    assert row["status"] == "sent"
    assert row["attempts"] == 1
    assert row["fire_at"] == row["sent_at"] == env.clock.now  # fire time: now (10.2)
    assert b"Notifications are on" not in row["payload_enc"]  # encrypted (7.1)
    payload = await reminder_payload(env, user_id, row["id"], row["payload_enc"])
    assert payload["title"] == "Notifications are on"
    assert payload["body"] == "You'll get reminders here"
    assert payload["url"] == "/today"
    assert payload["actions"] == []
    message = phone.decrypt(push.to("/s/phone")[0].body)
    assert message["reminder_id"] == str(row["id"])


async def test_a_test_push_that_reaches_no_device_is_marked_failed(
    env: AuthEnv, push: FakePushService
) -> None:
    user_id = await zee(env)
    subscribe(env, push)
    push.statuses["/s/phone"] = 503
    assert env.post(TEST).json() == {"delivered": 0}
    row = await env.db.fetchrow("SELECT status, sent_at FROM reminders WHERE user_id = $1", user_id)
    assert row is not None
    assert (row["status"], row["sent_at"]) == ("failed", None)


async def test_each_test_push_is_its_own_reminder(env: AuthEnv, push: FakePushService) -> None:
    user_id = await zee(env)
    subscribe(env, push)
    env.post(TEST)
    env.post(TEST)
    count = await env.db.fetchval("SELECT count(*) FROM reminders WHERE user_id = $1", user_id)
    assert count == 2


# ---------- faults are not "another account" ----------


@asynccontextmanager
async def service(env: AuthEnv, *, local: bool) -> AsyncIterator[NotifyService]:
    """A NotifyService on this test's event loop (the app's engine belongs to the TestClient)."""
    settings = env.app.state.settings
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        yield NotifyService(engine, env.app.state.vapid, load_keyring(settings), local=local)
    finally:
        await engine.dispose()


async def test_a_database_fault_is_not_reported_as_another_account(
    env: AuthEnv, push: FakePushService
) -> None:
    """Only the RLS refusal means "another account's endpoint" (409); a missing session (FK)
    is a fault and is raised."""
    user_id = await zee(env)
    data = SubscriptionIn.model_validate(Subscriber.new().subscription(push.url("/s/phone")))
    async with service(env, local=True) as notify:
        with pytest.raises(DBAPIError):
            await notify.save_subscription(user_id, uuid.uuid4(), data, datetime.now(UTC))


async def test_a_stored_endpoint_no_longer_allowed_is_turned_off_not_called(
    env: AuthEnv, push: FakePushService
) -> None:
    """The allowlist is checked again before every send, not only when saving."""
    user_id = await zee(env)
    subscribe(env, push, "/s/phone")
    # The fake push service (127.0.0.1) is not a push service outside local.
    async with service(env, local=False) as strict:
        assert await strict.send_test(user_id, datetime.now(UTC)) == 0
    assert push.to("/s/phone") == []
    disabled = await env.db.fetchval(
        "SELECT disabled_at FROM push_subscriptions WHERE endpoint = $1", push.url("/s/phone")
    )
    assert disabled is not None
