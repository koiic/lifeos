"""T06: registration by invite only (AUTH-1; spec 9.2 `POST /auth/invites/verify`)."""

import base64
import hashlib
from datetime import timedelta

import pytest

from tests.auth.conftest import DOMAIN, AuthEnv

pytestmark = pytest.mark.integration

INVALID = {"valid": False}


async def test_a_valid_invite_is_reported_with_its_email(env: AuthEnv) -> None:
    token = await env.invite(f"zee{DOMAIN}")
    response = env.post("/auth/invites/verify", {"token": token})
    assert response.status_code == 200
    assert response.json() == {"valid": True, "email": f"zee{DOMAIN}"}
    assert response.headers["cache-control"] == "no-store"


async def test_an_invite_without_email_omits_it(env: AuthEnv) -> None:
    """9.2: `{valid, email?}`."""
    token = await env.invite()
    assert env.post("/auth/invites/verify", {"token": token}).json() == {"valid": True}


@pytest.mark.parametrize(
    "state",
    [{"used": True}, {"revoked": True}, {"expires_in": timedelta(seconds=-1)}],
    ids=["used", "revoked", "expired"],
)
async def test_used_revoked_and_expired_invites_are_invalid(
    env: AuthEnv, state: dict[str, object]
) -> None:
    token = await env.invite(f"zee{DOMAIN}", **state)  # type: ignore[arg-type]
    assert env.post("/auth/invites/verify", {"token": token}).json() == INVALID


async def test_an_unknown_token_is_invalid(env: AuthEnv) -> None:
    assert env.post("/auth/invites/verify", {"token": "nope"}).json() == INVALID


async def test_invites_last_exactly_seven_days(env: AuthEnv) -> None:
    token = await env.invite()
    row = await env.invite_row(token)
    assert row["expires_at"] == env.clock.now + timedelta(days=7)
    env.clock.advance(days=7, seconds=-1)
    assert env.post("/auth/invites/verify", {"token": token}).json()["valid"] is True
    env.clock.advance(seconds=1)
    assert env.post("/auth/invites/verify", {"token": token}).json() == INVALID


async def test_tokens_are_32_random_bytes_stored_only_as_sha256(env: AuthEnv) -> None:
    token = await env.invite()
    assert len(base64.urlsafe_b64decode(token + "=")) == 32
    row = await env.invite_row(token)
    assert row["token_hash"] == hashlib.sha256(token.encode()).digest()
    assert token.encode() not in row["token_hash"]
    assert row["created_by"] == env.admin_id
    assert row["used_at"] is None
    assert await env.invite() != token


async def test_the_plaintext_token_is_never_a_lookup_key(env: AuthEnv) -> None:
    token = await env.invite()
    await env.db.execute(
        "UPDATE invites SET token_hash = $1 WHERE token_hash = $2",
        token.encode(),
        hashlib.sha256(token.encode()).digest(),
    )
    assert env.post("/auth/invites/verify", {"token": token}).json() == INVALID


@pytest.mark.parametrize("token", ["nope", ""])
async def test_registration_without_a_valid_token_is_403(env: AuthEnv, token: str) -> None:
    response = env.post(
        "/auth/register/options", {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"}
    )
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"


@pytest.mark.parametrize(
    "state",
    [{"used": True}, {"revoked": True}, {"expires_in": timedelta(seconds=-1)}],
    ids=["used", "revoked", "expired"],
)
async def test_registration_with_a_spent_token_is_403(
    env: AuthEnv, state: dict[str, object]
) -> None:
    token = await env.invite(**state)  # type: ignore[arg-type]
    response = env.post(
        "/auth/register/options", {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"}
    )
    assert response.status_code == 403
