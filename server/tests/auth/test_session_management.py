"""T08: list and revoke sessions in Settings (AUTH-5; spec 9.2 `GET/DELETE /auth/sessions`)."""

import uuid
from datetime import datetime, timedelta

import pytest

from tests.auth.conftest import DOMAIN, AuthEnv

pytestmark = [pytest.mark.integration, pytest.mark.req("AUTH-5")]

IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)


@pytest.fixture
async def two_sessions(env: AuthEnv) -> tuple[str, str]:
    """Her phone (registration, at `env.start`) and her Mac (a passkey sign-in 10 min later)."""
    env.client.headers["User-Agent"] = IPHONE
    assert env.register(await env.invite()).status_code == 201
    phone = env.session_token()
    env.client.cookies.clear()
    env.clock.advance(minutes=10)
    env.client.headers["User-Agent"] = MAC
    assert env.signin().status_code == 200
    return phone, env.session_token()


async def test_she_sees_her_sessions_with_device_last_seen_and_current(
    env: AuthEnv, two_sessions: tuple[str, str]
) -> None:
    response = env.get("/auth/sessions")
    assert response.status_code == 200
    body = response.json()
    assert body["next_cursor"] is None
    items = body["items"]  # oldest first, as the API returns them
    assert [item["device_label"] for item in items] == ["iPhone Safari", "Mac Safari"]
    assert [item["current"] for item in items] == [False, True]
    assert set(items[0]) == {"id", "device_label", "created_at", "last_seen_at", "current"}
    mac_signed_in = env.clock.now
    phone_registered = mac_signed_in - timedelta(minutes=10)
    assert [datetime.fromisoformat(i["created_at"]) for i in items] == [
        phone_registered,
        mac_signed_in,
    ]
    assert [datetime.fromisoformat(i["last_seen_at"]) for i in items] == [
        phone_registered,
        mac_signed_in,
    ]


@pytest.mark.parametrize("ended", ["revoked_at", "expires_at"], ids=["revoked", "expired"])
async def test_ended_sessions_are_not_listed(
    env: AuthEnv, two_sessions: tuple[str, str], ended: str
) -> None:
    await env.db.execute(
        f"UPDATE sessions SET {ended} = $1 WHERE device_label = 'iPhone Safari'",  # noqa: S608
        env.clock.now,
    )
    labels = [item["device_label"] for item in env.get("/auth/sessions").json()["items"]]
    assert labels == ["Mac Safari"]


async def test_another_users_sessions_are_never_listed(
    env: AuthEnv, two_sessions: tuple[str, str]
) -> None:
    env.client.cookies.clear()
    assert env.register(await env.invite(), name="Other", email=f"other{DOMAIN}").status_code == 201
    assert len(env.get("/auth/sessions").json()["items"]) == 1


async def test_revoking_another_device_signs_it_out(
    env: AuthEnv, two_sessions: tuple[str, str]
) -> None:
    phone, mac = two_sessions
    [phone_item] = [i for i in env.get("/auth/sessions").json()["items"] if not i["current"]]
    response = env.delete(f"/auth/sessions/{phone_item['id']}")
    assert response.status_code == 204
    assert not [h for h in response.headers.get_list("set-cookie") if h.startswith("lo_session")]
    assert env.whoami().status_code == 200  # this device is still signed in
    env.use_session(phone)
    assert env.whoami().status_code == 401
    env.use_session(mac)
    assert [i["current"] for i in env.get("/auth/sessions").json()["items"]] == [True]


async def test_revoking_the_current_session_clears_the_cookie(
    env: AuthEnv, two_sessions: tuple[str, str]
) -> None:
    [current] = [i for i in env.get("/auth/sessions").json()["items"] if i["current"]]
    response = env.delete(f"/auth/sessions/{current['id']}")
    assert response.status_code == 204
    assert env.set_cookie_flags(response)["max-age"] == "0"
    assert env.whoami().status_code == 401


async def test_revoking_is_logged(env: AuthEnv, two_sessions: tuple[str, str]) -> None:
    await env.db.execute("DELETE FROM auth_events")
    [phone_item] = [i for i in env.get("/auth/sessions").json()["items"] if not i["current"]]
    env.delete(f"/auth/sessions/{phone_item['id']}")
    row = await env.db.fetchrow("SELECT kind, success FROM auth_events")
    assert row is not None
    assert (row["kind"], row["success"]) == ("revoke", True)


async def test_another_users_session_cannot_be_revoked(
    env: AuthEnv, two_sessions: tuple[str, str]
) -> None:
    phone, _mac = two_sessions
    theirs = await env.db.fetchval("SELECT id FROM sessions WHERE device_label = 'iPhone Safari'")
    env.client.cookies.clear()
    assert env.register(await env.invite(), name="Other", email=f"other{DOMAIN}").status_code == 201
    response = env.delete(f"/auth/sessions/{theirs}")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "Not found."  # the endpoint refused, not a missing route
    assert await env.db.fetchval("SELECT revoked_at FROM sessions WHERE id = $1", theirs) is None
    env.use_session(phone)
    assert env.whoami().status_code == 200


async def test_an_unknown_id_is_not_found(env: AuthEnv, two_sessions: tuple[str, str]) -> None:
    response = env.delete(f"/auth/sessions/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not found."


async def test_a_malformed_id_is_a_validation_error(
    env: AuthEnv, two_sessions: tuple[str, str]
) -> None:
    assert env.delete("/auth/sessions/nope").status_code == 422


async def test_listing_and_revoking_need_a_session(env: AuthEnv) -> None:
    assert env.get("/auth/sessions").status_code == 401
    assert env.delete(f"/auth/sessions/{uuid.uuid4()}").status_code == 401
