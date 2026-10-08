"""T08: recent authentication (spec 9.2 note, 12.3; CR-017: `sessions.reauth_at`, per session).

Recovery-code regeneration is the sensitive action used to observe it here.
"""

import uuid
from datetime import timedelta

import pyotp
import pytest

from tests.auth.authenticator import b64url
from tests.auth.conftest import DOMAIN, PASSWORD, AuthEnv

pytestmark = [pytest.mark.integration, pytest.mark.req("AUTH-6")]  # unlock purpose

FIVE_MIN = timedelta(minutes=5)


async def passkey_user(env: AuthEnv) -> uuid.UUID:
    response = env.register(await env.invite())
    assert response.status_code == 201
    return uuid.UUID(response.json()["user_id"])


def sensitive(env: AuthEnv) -> int:
    status: int = env.post("/auth/recovery-codes", {}).status_code
    return status


def reauth_passkey(env: AuthEnv, purpose: str = "reauth", **get: object) -> int:
    options = env.post("/auth/reauth/options", {"purpose": purpose})
    assert options.status_code == 200, options.text
    credential = env.authenticator.get(options.json(), **get)
    status: int = env.post("/auth/reauth/verify", {"credential": credential}).status_code
    return status


async def test_a_fresh_sign_in_is_recent_auth(env: AuthEnv) -> None:
    await passkey_user(env)
    env.clock.advance(minutes=4, seconds=59)
    assert sensitive(env) == 200


async def test_after_five_minutes_sensitive_actions_need_reauth(env: AuthEnv) -> None:
    await passkey_user(env)
    env.clock.advance(minutes=5)
    response = env.post("/auth/recovery-codes", {})
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "Confirm it's you to continue."


async def test_a_passkey_reauth_restores_it_for_five_minutes(env: AuthEnv) -> None:
    await passkey_user(env)
    env.clock.advance(minutes=30)
    assert reauth_passkey(env) == 204
    env.clock.advance(minutes=4, seconds=59)
    assert sensitive(env) == 200
    env.clock.advance(seconds=1)
    assert sensitive(env) == 403


async def test_reauth_options_require_user_verification_and_list_her_passkeys(
    env: AuthEnv,
) -> None:
    await passkey_user(env)
    options = env.post("/auth/reauth/options", {"purpose": "reauth"}).json()
    assert options["userVerification"] == "required"
    expected = b64url(env.authenticator.passkeys[0].credential_id)
    assert [c["id"] for c in options["allowCredentials"]] == [expected]
    stored = await env.db.fetchrow(
        "SELECT purpose, user_id, expires_at FROM auth_challenges WHERE purpose = 'reauth'"
    )
    assert stored is not None
    assert stored["user_id"] == await env.db.fetchval(
        "SELECT id FROM users WHERE email = $1", f"zee{DOMAIN}"
    )
    assert stored["expires_at"] == env.clock.now + FIVE_MIN


async def test_unlock_purpose_also_counts(env: AuthEnv) -> None:
    await passkey_user(env)
    env.clock.advance(minutes=30)
    assert reauth_passkey(env, purpose="unlock") == 204
    assert sensitive(env) == 200


async def test_recent_auth_is_per_session(env: AuthEnv) -> None:
    await passkey_user(env)
    first = env.session_token()
    env.client.cookies.clear()
    env.clock.advance(minutes=30)
    assert env.signin().status_code == 200  # a fresh session elsewhere
    env.use_session(first)
    assert sensitive(env) == 403


async def test_another_users_passkey_cannot_reauth_this_session(env: AuthEnv) -> None:
    await passkey_user(env)
    mine = env.session_token()
    env.client.cookies.clear()
    assert env.register(await env.invite(), name="O", email=f"other{DOMAIN}").status_code == 201
    env.use_session(mine)
    env.clock.advance(minutes=30)
    theirs = env.authenticator.passkeys[1]
    assert reauth_passkey(env, passkey=theirs) == 401
    assert sensitive(env) == 403


async def test_a_reauth_challenge_is_single_use_and_five_minutes(env: AuthEnv) -> None:
    await passkey_user(env)
    env.clock.advance(minutes=30)
    options = env.post("/auth/reauth/options", {"purpose": "reauth"}).json()
    credential = env.authenticator.get(options)
    assert env.post("/auth/reauth/verify", {"credential": credential}).status_code == 204
    assert env.post("/auth/reauth/verify", {"credential": credential}).status_code == 401
    late = env.post("/auth/reauth/options", {"purpose": "reauth"}).json()
    env.clock.advance(minutes=5, seconds=1)
    assert (
        env.post("/auth/reauth/verify", {"credential": env.authenticator.get(late)}).status_code
        == 401
    )


async def test_a_sign_in_challenge_cannot_reauth(env: AuthEnv) -> None:
    await passkey_user(env)
    env.clock.advance(minutes=30)
    options = env.post("/auth/signin/options", {}).json()
    response = env.post("/auth/reauth/verify", {"credential": env.authenticator.get(options)})
    assert response.status_code == 401
    assert sensitive(env) == 403


async def test_user_verification_is_required(env: AuthEnv) -> None:
    await passkey_user(env)
    env.clock.advance(minutes=30)
    env.authenticator.user_verification = False
    assert reauth_passkey(env) == 401


async def test_a_password_account_reauths_with_password_and_totp(env: AuthEnv) -> None:
    totp = env.password_account(env.register_password(await env.invite()))
    assert env.post("/auth/totp/confirm", {"code": env.code(totp)}).status_code == 200
    env.clock.advance(minutes=30)
    assert sensitive(env) == 403
    wrong = env.post(
        "/auth/reauth/verify", {"password": "not the password!", "totp": env.code(totp)}
    )
    assert wrong.status_code == 401
    good = env.post("/auth/reauth/verify", {"password": PASSWORD, "totp": env.code(totp)})
    assert good.status_code == 204
    assert sensitive(env) == 200


async def test_reauth_needs_a_session(env: AuthEnv) -> None:
    assert env.post("/auth/reauth/options", {"purpose": "reauth"}).status_code == 401
    assert (
        env.post("/auth/reauth/verify", {"password": "x" * 12, "totp": "123456"}).status_code == 401
    )


@pytest.mark.parametrize(
    "body",
    [{}, {"purpose": "signin"}, {"purpose": "add_passkey"}],
    ids=["missing", "signin", "add_passkey"],
)
async def test_only_reauth_and_unlock_purposes(env: AuthEnv, body: dict[str, str]) -> None:
    await passkey_user(env)
    assert env.post("/auth/reauth/options", body).status_code == 422


async def test_failed_reauth_counts_toward_the_lockout(env: AuthEnv) -> None:
    """AUTH-7: a re-authentication is a verification like a sign-in."""
    await passkey_user(env)
    env.clock.advance(minutes=30)
    for _ in range(5):
        assert reauth_passkey(env, user_handle=uuid.uuid4().bytes) == 401
    assert reauth_passkey(env) == 429


async def test_a_challenge_issued_to_another_session_cannot_reauth_this_one(env: AuthEnv) -> None:
    """The reauth challenge is bound to the account that asked for it."""
    await passkey_user(env)
    mine = env.session_token()
    env.client.cookies.clear()
    assert env.register(await env.invite(), name="O", email=f"other{DOMAIN}").status_code == 201
    env.clock.advance(minutes=30)  # her own sign-in is no longer recent
    theirs = env.post("/auth/reauth/options", {"purpose": "reauth"}).json()
    env.use_session(mine)
    own_passkey = env.authenticator.passkeys[0]
    credential = env.authenticator.get(theirs, passkey=own_passkey)
    assert env.post("/auth/reauth/verify", {"credential": credential}).status_code == 401
    assert sensitive(env) == 403


async def confirmed_password_user(env: AuthEnv) -> pyotp.TOTP:
    totp = env.password_account(env.register_password(await env.invite()))
    assert env.post("/auth/totp/confirm", {"code": env.code(totp)}).status_code == 200
    env.clock.advance(minutes=30)
    return totp


async def test_a_right_password_with_a_wrong_code_does_not_reauth(env: AuthEnv) -> None:
    totp = await confirmed_password_user(env)
    body = {"password": PASSWORD, "totp": env.wrong_code(totp)}
    assert env.post("/auth/reauth/verify", body).status_code == 401
    assert sensitive(env) == 403


async def test_a_used_code_does_not_reauth_again(env: AuthEnv) -> None:
    totp = await confirmed_password_user(env)
    code = env.code(totp)
    assert env.post("/auth/reauth/verify", {"password": PASSWORD, "totp": code}).status_code == 204
    env.clock.advance(minutes=6)
    # A new step's code works; the used one would not (12.3, replay).
    assert env.post("/auth/reauth/verify", {"password": PASSWORD, "totp": code}).status_code == 401


async def test_an_unconfirmed_password_account_cannot_reauth(env: AuthEnv) -> None:
    totp = env.password_account(env.register_password(await env.invite()))
    env.clock.advance(minutes=30)
    response = env.post("/auth/reauth/verify", {"password": PASSWORD, "totp": env.code(totp)})
    assert response.status_code == 403  # the inactive session is refused (CR-014)


async def test_a_passkey_account_cannot_reauth_with_a_password(env: AuthEnv) -> None:
    await passkey_user(env)
    env.clock.advance(minutes=30)
    body = {"password": PASSWORD, "totp": "123456"}
    assert env.post("/auth/reauth/verify", body).status_code == 401
    assert sensitive(env) == 403


async def test_a_pin_unlock_is_not_recent_auth(env: AuthEnv) -> None:
    """12.3 / CR-017: only a passkey or password verification counts; a PIN is weaker."""
    await passkey_user(env)
    assert env.put("/auth/app-lock", {"pin": "482915"}).status_code == 204
    env.clock.advance(minutes=30)
    assert env.post("/auth/app-lock/unlock", {"pin": "482915"}).status_code == 204
    assert sensitive(env) == 403


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"password": "a long password!", "totp": "123456", "credential": {"id": "x"}},
        {"password": "a long password!"},
        {"totp": "123456"},
    ],
    ids=["empty", "both", "password-only", "totp-only"],
)
async def test_malformed_reauth_bodies(env: AuthEnv, body: dict[str, object]) -> None:
    await passkey_user(env)
    response = env.post("/auth/reauth/verify", body)
    assert response.status_code == 422
    assert "a long password!" not in response.text


async def test_wrong_password_reauths_lock_the_account(env: AuthEnv) -> None:
    totp = await confirmed_password_user(env)
    for n in range(5):
        env.ip = f"198.51.100.{n}"
        body = {"password": "not the password!", "totp": env.code(totp)}
        assert env.post("/auth/reauth/verify", body).status_code == 401
    env.ip = "198.51.100.99"
    good = {"password": PASSWORD, "totp": env.code(totp)}
    assert env.post("/auth/reauth/verify", good).status_code == 429
