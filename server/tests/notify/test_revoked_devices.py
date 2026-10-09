"""CR-027 B1 (spec 12.1 "Lost or stolen phone … remote session revocation"): when a device's
session ends — she signs out, revokes it from another device (AUTH-5), or the app lock's five
wrong PINs end it — that device's push subscription is turned off, so a lost phone stops showing
reminders on its lock screen. Her other devices keep theirs; signing in again re-registers and
turns it back on (10.5)."""

import pytest

from tests.auth.conftest import AuthEnv
from tests.notify.fake_push import FakePushService, Subscriber, fake_push_service
from tests.notify.test_push_api import SUBSCRIPTIONS, subscribe, zee


@pytest.fixture
def push():  # type: ignore[no-untyped-def]
    with fake_push_service() as service:
        yield service


async def disabled(env: AuthEnv, push: FakePushService, path: str) -> bool:
    value = await env.db.fetchval(
        "SELECT disabled_at FROM push_subscriptions WHERE endpoint = $1", push.url(path)
    )
    return value is not None


async def phone_and_laptop(env: AuthEnv, push: FakePushService) -> tuple[str, str]:
    """Her phone (registered) and her laptop (signed in later), each with its subscription."""
    await zee(env)
    subscribe(env, push, "/s/phone")
    phone = env.session_token()
    env.client.cookies.clear()
    assert env.signin().status_code == 200
    subscribe(env, push, "/s/laptop", "Mac")
    return phone, env.session_token()


@pytest.mark.req("AUTH-5")
async def test_signing_out_turns_off_this_devices_notifications(
    env: AuthEnv, push: FakePushService
) -> None:
    phone, _laptop = await phone_and_laptop(env, push)
    env.use_session(phone)
    assert env.post("/auth/signout").status_code == 204
    assert await disabled(env, push, "/s/phone")
    assert not await disabled(env, push, "/s/laptop")


@pytest.mark.req("AUTH-5")
async def test_revoking_a_lost_phone_turns_off_its_notifications(
    env: AuthEnv, push: FakePushService
) -> None:
    await phone_and_laptop(env, push)  # now on the laptop
    [phone] = [i for i in env.get("/auth/sessions").json()["items"] if not i["current"]]
    assert env.delete(f"/auth/sessions/{phone['id']}").status_code == 204
    assert await disabled(env, push, "/s/phone")
    assert not await disabled(env, push, "/s/laptop")
    assert env.post("/push/test").json() == {"delivered": 1}
    assert push.to("/s/phone") == []


@pytest.mark.req("AUTH-6")
async def test_five_wrong_pins_turn_off_this_devices_notifications(
    env: AuthEnv, push: FakePushService
) -> None:
    _phone, _laptop = await phone_and_laptop(env, push)  # now on the laptop
    assert env.put("/auth/app-lock", {"pin": "482913", "timeout_s": 300}).status_code == 204
    for _ in range(4):
        assert env.post("/auth/app-lock/unlock", {"pin": "000000"}).status_code == 401
    assert not await disabled(env, push, "/s/laptop")  # still her device after four
    assert env.post("/auth/app-lock/unlock", {"pin": "000000"}).status_code == 401
    assert env.whoami().status_code == 401  # the fifth ended the session
    assert await disabled(env, push, "/s/laptop")
    assert not await disabled(env, push, "/s/phone")


async def test_signing_in_again_turns_them_back_on(env: AuthEnv, push: FakePushService) -> None:
    phone, _laptop = await phone_and_laptop(env, push)
    env.use_session(phone)
    env.post("/auth/signout")
    env.client.cookies.clear()
    assert env.signin().status_code == 200
    # 10.5: on start the app saves its subscription again.
    again = Subscriber.new()
    response = env.post(SUBSCRIPTIONS, again.subscription(push.url("/s/phone")))
    assert response.status_code == 201
    assert not await disabled(env, push, "/s/phone")
    # It now belongs to the new session, so ending that one turns it off again.
    current = await env.db.fetchval(
        "SELECT session_id FROM push_subscriptions WHERE endpoint = $1", push.url("/s/phone")
    )
    [item] = [i for i in env.get("/auth/sessions").json()["items"] if i["current"]]
    assert str(current) == item["id"]
    assert env.post("/auth/signout").status_code == 204
    assert await disabled(env, push, "/s/phone")


@pytest.mark.req("AUTH-8")
async def test_a_recovery_invite_leaves_them_on_for_the_security_notice(
    env: AuthEnv, push: FakePushService
) -> None:
    """CR-028: after recovery the account notice goes to her devices first; the T30 dispatcher
    then turns them off. Until T30, recovery itself must not turn them off."""
    _phone, _laptop = await phone_and_laptop(env, push)
    user_id = await env.db.fetchval("SELECT user_id FROM push_subscriptions LIMIT 1")
    env.client.cookies.clear()
    env.use_session(await env.admin_token())
    assert env.post(f"/admin/users/{user_id}/recovery-invite", {}).status_code == 201
    assert not await disabled(env, push, "/s/phone")
    assert not await disabled(env, push, "/s/laptop")
