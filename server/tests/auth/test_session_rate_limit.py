"""T07: spec 9.1 "all others 300 requests/min per session → 429 with `Retry-After`"."""

import pytest

from tests.auth.conftest import DOMAIN, ORIGIN, RP_ID, AuthEnv, whoami_router

pytestmark = pytest.mark.integration

LIMIT = 300


@pytest.fixture
async def token(env: AuthEnv) -> str:
    assert env.register(await env.invite()).status_code == 201
    return env.session_token()


async def test_300_requests_a_minute_then_429(env: AuthEnv, token: str) -> None:
    for _ in range(LIMIT):
        assert env.whoami().status_code == 200
    refused = env.whoami()
    assert refused.status_code == 429
    assert refused.headers["content-type"] == "application/problem+json"
    assert refused.headers["retry-after"] == "60"


async def test_retry_after_counts_down_and_the_window_resets(env: AuthEnv, token: str) -> None:
    for _ in range(LIMIT):
        env.whoami()
    env.clock.advance(seconds=45)
    assert env.whoami().headers["retry-after"] == "15"
    env.clock.advance(seconds=15)
    assert env.whoami().status_code == 200


async def test_other_sessions_are_not_limited(env: AuthEnv, token: str) -> None:
    for _ in range(LIMIT + 1):
        env.whoami()
    env.client.cookies.clear()  # a new sign-in on the same browser would end the first session
    assert env.register(await env.invite(), email=f"other{DOMAIN}", name="O").status_code == 201
    assert env.whoami().status_code == 200
    env.use_session(token)
    assert env.whoami().status_code == 429  # the first session is still limited


async def test_the_count_is_kept_in_postgres_for_every_worker(env: AuthEnv, token: str) -> None:
    """CR-016: shared by the API workers, so it lives in session_request_counts."""
    for _ in range(3):
        env.whoami()
    row = await env.db.fetchrow("SELECT window_start, count FROM session_request_counts")
    assert row is not None
    assert (row["window_start"], row["count"]) == (env.clock.now, 3)


async def test_requests_from_another_api_process_count_too(env: AuthEnv, token: str) -> None:
    """A second app (as a second worker would be) shares the same count."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.platform.clock import utc_now

    for _ in range(LIMIT - 1):
        env.whoami()
    other = create_app(env.app.state.settings)
    other.include_router(whoami_router())
    other.dependency_overrides[utc_now] = env.clock
    with TestClient(other, base_url=ORIGIN) as second:
        second.cookies.set("lo_session", token, domain=RP_ID)
        assert second.get("/api/v1/_test/whoami").status_code == 200
        assert second.get("/api/v1/_test/whoami").status_code == 429


async def test_an_over_limit_session_cannot_fall_through_to_recovery(
    env: AuthEnv, token: str
) -> None:
    """Over the 9.1 limit, `/auth/passkeys/verify` refuses (429); it does not treat the request as
    cookie-less and mint a new session from this session's pending challenge."""
    options = env.post("/auth/passkeys/options", {}).json()
    for _ in range(LIMIT):
        env.whoami()
    credential = env.authenticator.create(options)
    response = env.post("/auth/passkeys/verify", {"credential": credential})
    assert response.status_code == 429
    assert env.session_token() == token
    count = "SELECT count(*) FROM sessions WHERE revoked_at IS NULL"
    assert await env.db.fetchval(count) == 1
