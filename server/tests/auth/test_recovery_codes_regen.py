"""T08: `POST /auth/recovery-codes` "Regenerate codes" — "Requires recent auth (< 5 min)";
AUTH-4 "regenerating invalidates old codes"."""

import pytest

from tests.auth.conftest import DOMAIN, AuthEnv

pytestmark = pytest.mark.integration


async def test_regenerating_returns_ten_new_codes_and_retires_the_old(env: AuthEnv) -> None:
    old = env.register(await env.invite()).json()["recovery_codes"]
    response = env.post("/auth/recovery-codes", {})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    new = response.json()["recovery_codes"]
    assert len(set(new)) == 10
    assert not set(new) & set(old)
    env.client.cookies.clear()
    email = f"zee{DOMAIN}"
    assert env.post("/auth/signin/recovery", {"email": email, "code": old[0]}).status_code == 401
    assert env.post("/auth/signin/recovery", {"email": email, "code": new[0]}).status_code == 200


async def test_regenerating_needs_recent_auth(env: AuthEnv) -> None:
    old = env.register(await env.invite()).json()["recovery_codes"]
    env.clock.advance(minutes=5)
    assert env.post("/auth/recovery-codes", {}).status_code == 403
    env.client.cookies.clear()
    email = f"zee{DOMAIN}"
    assert env.post("/auth/signin/recovery", {"email": email, "code": old[0]}).status_code == 200


async def test_regenerating_needs_a_session(env: AuthEnv) -> None:
    assert env.post("/auth/recovery-codes", {}).status_code == 401
