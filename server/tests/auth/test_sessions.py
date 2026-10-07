"""T06: session cookies (AUTH-5; spec 9.1, 12.3)."""

import base64
import hashlib
import uuid
from http.cookies import SimpleCookie

import httpx
import pytest

from tests.auth.conftest import AuthEnv

pytestmark = pytest.mark.integration

THIRTY_DAYS = 30 * 24 * 3600


def set_cookie(response_headers: list[str]) -> SimpleCookie:
    [header] = [h for h in response_headers if h.startswith("lo_session=")]
    cookie: SimpleCookie = SimpleCookie()
    cookie.load(header)
    return cookie


@pytest.fixture
async def user(env: AuthEnv) -> uuid.UUID:
    response = env.register(await env.invite())
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["user_id"])


def assert_session_cookie(env: AuthEnv, response: httpx.Response) -> None:
    """9.1: lo_session; HttpOnly; Secure; SameSite=Lax; Path=/; 30-day max age; host-only."""
    flags = env.set_cookie_flags(response)
    assert set(flags) == {"httponly", "secure", "samesite", "path", "max-age"}
    assert flags["samesite"] == "Lax"
    assert flags["path"] == "/"
    assert flags["max-age"] == str(THIRTY_DAYS)
    morsel = set_cookie(response.headers.get_list("set-cookie"))["lo_session"]
    assert len(base64.urlsafe_b64decode(morsel.value + "=")) == 32
    assert response.headers["cache-control"] == "no-store"


async def test_cookie_flags_on_registration(env: AuthEnv) -> None:
    response = env.register(await env.invite())
    assert_session_cookie(env, response)
    assert env.whoami().json()["user_id"] == response.json()["user_id"]


async def test_cookie_flags_on_sign_in(env: AuthEnv, user: uuid.UUID) -> None:
    env.client.cookies.clear()
    assert_session_cookie(env, env.signin())


async def test_cookie_flags_on_recovery(env: AuthEnv) -> None:
    code = env.register(await env.invite()).json()["recovery_codes"][0]
    env.client.cookies.clear()
    recovered = env.post("/auth/signin/recovery", {"email": "zee@auth.test", "code": code})
    assert recovered.headers["cache-control"] == "no-store"
    credential = env.authenticator.create(recovered.json()["options"])
    assert_session_cookie(env, env.post("/auth/passkeys/verify", {"credential": credential}))


@pytest.mark.parametrize("how", ["signin", "register"])
async def test_a_new_sign_in_ends_the_session_the_browser_held(
    env: AuthEnv, user: uuid.UUID, how: str
) -> None:
    old = env.session_token()
    if how == "signin":
        assert env.signin().status_code == 200
    else:
        other = env.register(await env.invite(), name="Other", email="other@auth.test")
        assert other.status_code == 201
    new = env.session_token()
    assert new != old
    env.use_session(old)
    assert env.whoami().status_code == 401
    env.use_session(new)
    assert env.whoami().status_code == 200


async def test_only_the_sha256_of_the_token_is_stored(env: AuthEnv, user: uuid.UUID) -> None:
    token = env.session_token()
    row = await env.db.fetchrow(
        "SELECT token_hash, expires_at FROM sessions WHERE user_id = $1", user
    )
    assert row is not None
    assert row["token_hash"] == hashlib.sha256(base64.urlsafe_b64decode(token + "==")).digest()
    assert (row["expires_at"] - env.clock.now).total_seconds() == THIRTY_DAYS


async def test_no_cookie_is_401(env: AuthEnv) -> None:
    response = env.whoami()
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"


@pytest.mark.parametrize("value", ["garbage", "", "A" * 43, "!!!", "A" * 400])
async def test_unknown_or_malformed_tokens_are_401(env: AuthEnv, value: str) -> None:
    env.use_session(value)
    assert env.whoami().status_code == 401


async def test_idle_sessions_expire_after_30_days(env: AuthEnv, user: uuid.UUID) -> None:
    env.clock.advance(days=30, seconds=-1)
    assert env.whoami().status_code == 200  # still inside the window: this use slides it
    env.clock.advance(days=30, seconds=1)
    assert env.whoami().status_code == 401


async def test_an_unused_session_expires_after_exactly_30_days(
    env: AuthEnv, user: uuid.UUID
) -> None:
    env.clock.advance(days=30)
    assert env.whoami().status_code == 401


async def test_use_slides_the_expiry_and_refreshes_the_cookie(
    env: AuthEnv, user: uuid.UUID
) -> None:
    env.clock.advance(days=10)
    response = env.whoami()
    assert response.status_code == 200
    morsel = set_cookie(response.headers.get_list("set-cookie"))["lo_session"]
    assert morsel["max-age"] == str(THIRTY_DAYS)
    row = await env.db.fetchrow(
        "SELECT expires_at, last_seen_at FROM sessions WHERE user_id = $1", user
    )
    assert row is not None
    assert (row["expires_at"] - env.clock.now).total_seconds() == THIRTY_DAYS
    assert row["last_seen_at"] == env.clock.now


async def test_sliding_happens_once_an_hour_has_passed(env: AuthEnv, user: uuid.UUID) -> None:
    env.clock.advance(hours=1)
    response = env.whoami()
    assert env.set_cookie_flags(response)["max-age"] == str(THIRTY_DAYS)
    last_seen = await env.db.fetchval("SELECT last_seen_at FROM sessions WHERE user_id = $1", user)
    assert last_seen == env.clock.now


async def test_sliding_writes_at_most_once_an_hour(env: AuthEnv, user: uuid.UUID) -> None:
    env.clock.advance(minutes=30)
    response = env.whoami()
    assert response.status_code == 200
    assert not [h for h in response.headers.get_list("set-cookie") if h.startswith("lo_session=")]
    row = await env.db.fetchrow(
        "SELECT created_at, last_seen_at FROM sessions WHERE user_id = $1", user
    )
    assert row is not None
    assert row["last_seen_at"] == row["created_at"]


async def test_sessions_end_180_days_after_creation_however_active(
    env: AuthEnv, user: uuid.UUID
) -> None:
    for _ in range(17):
        env.clock.advance(days=10)
        assert env.whoami().status_code == 200
    # Day 170: the expiry is capped at day 180.
    env.clock.advance(days=9, hours=23)
    assert env.whoami().status_code == 200
    env.clock.advance(hours=1)
    assert env.whoami().status_code == 401


async def test_the_cookie_max_age_is_capped_near_the_absolute_limit(
    env: AuthEnv, user: uuid.UUID
) -> None:
    for _ in range(17):
        env.clock.advance(days=10)
        env.whoami()
    env.clock.advance(days=1, hours=1)  # day 171 + 1 hour: 8 days 23 hours left
    response = env.whoami()
    morsel = set_cookie(response.headers.get_list("set-cookie"))["lo_session"]
    assert morsel["max-age"] == str((8 * 24 + 23) * 3600)


async def test_a_revoked_session_is_401(env: AuthEnv, user: uuid.UUID) -> None:
    await env.db.execute("UPDATE sessions SET revoked_at = now() WHERE user_id = $1", user)
    assert env.whoami().status_code == 401


async def test_a_deleted_account_has_no_session(env: AuthEnv, user: uuid.UUID) -> None:
    await env.db.execute("UPDATE users SET deleted_at = now() WHERE id = $1", user)
    assert env.whoami().status_code == 401


async def test_sign_out_revokes_and_clears_the_cookie(env: AuthEnv, user: uuid.UUID) -> None:
    token = env.session_token()
    response = env.post("/auth/signout")
    assert response.status_code == 204
    cleared = set_cookie(response.headers.get_list("set-cookie"))["lo_session"]
    assert cleared.value == ""
    assert cleared["max-age"] == "0"
    assert (
        await env.db.fetchval("SELECT revoked_at FROM sessions WHERE user_id = $1", user)
        == env.clock.now
    )
    env.use_session(token)
    assert env.whoami().status_code == 401


async def test_sign_out_without_a_session_still_clears_the_cookie(env: AuthEnv) -> None:
    env.use_session("garbage")
    response = env.post("/auth/signout")
    assert response.status_code == 204
    assert set_cookie(response.headers.get_list("set-cookie"))["lo_session"].value == ""


async def test_sign_out_ends_only_this_session(env: AuthEnv, user: uuid.UUID) -> None:
    """Other sessions of the same user and of other users stay valid."""
    first = env.session_token()
    env.client.cookies.clear()
    assert env.signin().status_code == 200
    second = env.session_token()
    other = env.register(await env.invite(), name="Other", email="other@auth.test")
    assert other.status_code == 201
    third = env.session_token()

    env.use_session(second)
    assert env.post("/auth/signout").status_code == 204
    for token, status in ((first, 200), (second, 401), (third, 200)):
        env.use_session(token)
        assert env.whoami().status_code == status


async def test_sign_out_needs_csrf_headers(env: AuthEnv, user: uuid.UUID) -> None:
    response = env.client.post("/api/v1/auth/signout")
    assert response.status_code == 403
    assert env.whoami().status_code == 200
