"""T06: passkey sign-in with discoverable credentials (spec 9.2, 12.3)."""

import uuid
from datetime import timedelta

import pytest

from tests.auth.conftest import AuthEnv

pytestmark = pytest.mark.integration


@pytest.fixture
async def registered(env: AuthEnv) -> uuid.UUID:
    response = env.register(await env.invite())
    assert response.status_code == 201, response.text
    env.client.cookies.clear()
    return uuid.UUID(response.json()["user_id"])


async def test_options_are_discoverable_and_require_user_verification(env: AuthEnv) -> None:
    response = env.post("/auth/signin/options", {})
    assert response.status_code == 200
    options = response.json()
    assert options["rpId"] == "app.test"
    assert options["userVerification"] == "required"
    assert options.get("allowCredentials", []) == []
    assert options["timeout"] == 300000
    stored = await env.db.fetchrow(
        "SELECT user_id, invite_id, expires_at FROM auth_challenges WHERE purpose = 'signin'"
    )
    assert stored is not None
    assert stored["user_id"] is None
    assert stored["invite_id"] is None
    assert stored["expires_at"] == env.clock.now + timedelta(minutes=5)


async def test_sign_in_sets_the_session_cookie(env: AuthEnv, registered: uuid.UUID) -> None:
    response = env.signin()
    assert response.status_code == 200, response.text
    assert response.json() == {"user_id": str(registered), "display_name": "Zee"}
    assert "lo_session" in response.cookies
    assert env.whoami().json()["user_id"] == str(registered)


async def test_sign_in_records_the_sign_count_and_last_use(
    env: AuthEnv, registered: uuid.UUID
) -> None:
    env.signin(sign_count=7)
    row = await env.db.fetchrow(
        "SELECT sign_count, last_used_at FROM webauthn_credentials WHERE user_id = $1", registered
    )
    assert row is not None
    assert row["sign_count"] == 7
    assert row["last_used_at"] == env.clock.now


async def test_a_sign_count_regression_is_rejected(env: AuthEnv, registered: uuid.UUID) -> None:
    assert env.signin(sign_count=7).status_code == 200
    env.client.cookies.clear()
    assert env.signin(sign_count=7).status_code == 401
    assert env.signin(sign_count=3).status_code == 401
    assert env.whoami().status_code == 401


async def test_a_zero_sign_count_is_not_checked(env: AuthEnv, registered: uuid.UUID) -> None:
    """Synced passkeys always report 0 (spec 12.3: "checked when non-zero")."""
    assert env.signin(sign_count=0).status_code == 200
    assert env.signin(sign_count=0).status_code == 200


async def test_an_unknown_credential_is_rejected(env: AuthEnv, registered: uuid.UUID) -> None:
    await env.db.execute("DELETE FROM webauthn_credentials WHERE user_id = $1", registered)
    response = env.signin()
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert "lo_session" not in response.cookies


async def test_a_challenge_is_single_use(env: AuthEnv, registered: uuid.UUID) -> None:
    options = env.post("/auth/signin/options", {}).json()
    credential = env.authenticator.get(options)
    assert env.post("/auth/signin/verify", {"credential": credential}).status_code == 200
    env.client.cookies.clear()
    replay = env.post("/auth/signin/verify", {"credential": credential})
    assert replay.status_code == 401
    assert env.whoami().status_code == 401


async def test_a_challenge_expires_after_five_minutes(env: AuthEnv, registered: uuid.UUID) -> None:
    options = env.post("/auth/signin/options", {}).json()
    env.clock.advance(minutes=5, seconds=1)
    response = env.post("/auth/signin/verify", {"credential": env.authenticator.get(options)})
    assert response.status_code == 401


async def test_a_challenge_works_until_five_minutes(env: AuthEnv, registered: uuid.UUID) -> None:
    options = env.post("/auth/signin/options", {}).json()
    env.clock.advance(minutes=4, seconds=59)
    response = env.post("/auth/signin/verify", {"credential": env.authenticator.get(options)})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "get", [{"origin": "https://evil.test"}, {"rp_id": "evil.test"}], ids=["origin", "rp-id"]
)
async def test_wrong_origin_or_rp_id_is_rejected(
    env: AuthEnv, registered: uuid.UUID, get: dict[str, str]
) -> None:
    assert env.signin(**get).status_code == 401
    assert env.whoami().status_code == 401


async def test_an_unissued_challenge_is_rejected(env: AuthEnv, registered: uuid.UUID) -> None:
    response = env.post(
        "/auth/signin/verify",
        {"credential": env.authenticator.get({"challenge": "AAAAAAAAAAAAAAAAAAAAAA"})},
    )
    assert response.status_code == 401


async def test_a_registration_challenge_cannot_sign_in(env: AuthEnv, registered: uuid.UUID) -> None:
    token = await env.invite()
    options = env.post(
        "/auth/register/options", {"token": token, "name": "Z", "email": "z2@auth.test"}
    ).json()
    response = env.post("/auth/signin/verify", {"credential": env.authenticator.get(options)})
    assert response.status_code == 401


async def test_user_verification_is_required(env: AuthEnv, registered: uuid.UUID) -> None:
    env.authenticator.user_verification = False
    assert env.signin().status_code == 401


async def test_the_user_handle_must_match_the_credential_owner(
    env: AuthEnv, registered: uuid.UUID
) -> None:
    assert env.signin(user_handle=uuid.uuid4().bytes).status_code == 401
    assert env.signin(user_handle=b"").status_code == 401


async def test_a_forged_signature_is_rejected(env: AuthEnv, registered: uuid.UUID) -> None:
    options = env.post("/auth/signin/options", {}).json()
    credential = env.authenticator.get(options)
    credential["response"]["signature"] = credential["response"]["signature"][:-4] + "AAAA"
    assert env.post("/auth/signin/verify", {"credential": credential}).status_code == 401


async def test_a_deleted_account_cannot_sign_in(env: AuthEnv, registered: uuid.UUID) -> None:
    await env.db.execute("UPDATE users SET deleted_at = now() WHERE id = $1", registered)
    assert env.signin().status_code == 401


async def test_malformed_credentials_are_401_not_500(env: AuthEnv, registered: uuid.UUID) -> None:
    for credential in ({}, {"id": "x"}, {"response": "x"}, "x"):
        response = env.post("/auth/signin/verify", {"credential": credential})
        assert response.status_code in {401, 422}, credential


async def test_expired_challenges_are_purged_after_a_day(env: AuthEnv) -> None:
    """New challenges delete ones expired over a day ago (the table cannot grow without bound)."""
    old, recent = b"o" * 32, b"r" * 32
    for challenge, expired in ((old, timedelta(days=1, seconds=1)), (recent, timedelta(hours=23))):
        await env.db.execute(
            "INSERT INTO auth_challenges (id, purpose, challenge, expires_at)"
            " VALUES ($1, 'signin', $2, $3)",
            uuid.uuid4(),
            challenge,
            env.clock.now - expired,
        )
    env.post("/auth/signin/options", {})
    left = {
        r["challenge"]
        for r in await env.db.fetch(
            "SELECT challenge FROM auth_challenges WHERE challenge = ANY($1)", [old, recent]
        )
    }
    assert left == {recent}
