"""T08: passkeys in Settings (spec 9.2; CR-019 `GET /auth/passkeys`; 12.3 removing a passkey
needs recent auth; "Not the last sign-in method")."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from tests.auth.conftest import DOMAIN, AuthEnv

pytestmark = pytest.mark.integration


async def signed_in(env: AuthEnv) -> uuid.UUID:
    response = env.register(await env.invite())
    assert response.status_code == 201
    return uuid.UUID(response.json()["user_id"])


def add_passkey(env: AuthEnv) -> int:
    options = env.post("/auth/passkeys/options", {})
    assert options.status_code == 200, options.text
    credential = env.authenticator.create(options.json())
    status: int = env.post("/auth/passkeys/verify", {"credential": credential}).status_code
    return status


async def test_she_lists_her_passkeys_without_key_material(env: AuthEnv) -> None:
    await signed_in(env)
    body = env.get("/auth/passkeys").json()
    assert body["next_cursor"] is None
    [item] = body["items"]
    assert set(item) == {"id", "nickname", "created_at", "last_used_at", "backed_up"}
    assert item["nickname"] == "Passkey"


async def test_adding_a_passkey_while_signed_in(env: AuthEnv) -> None:
    user_id = await signed_in(env)
    token = env.session_token()
    assert add_passkey(env) == 201
    assert len(env.get("/auth/passkeys").json()["items"]) == 2
    assert env.session_token() == token  # same session, no new cookie
    assert env.authenticator.passkeys[-1].user_handle == user_id.bytes
    env.client.cookies.clear()
    assert env.signin().status_code == 200  # the new passkey signs in


async def test_add_options_exclude_her_existing_passkeys(env: AuthEnv) -> None:
    await signed_in(env)
    options = env.post("/auth/passkeys/options", {}).json()
    assert len(options["excludeCredentials"]) == 1
    assert options["authenticatorSelection"]["userVerification"] == "required"


async def test_a_challenge_for_one_user_cannot_add_a_passkey_to_another(env: AuthEnv) -> None:
    await signed_in(env)
    options = env.post("/auth/passkeys/options", {}).json()
    env.client.cookies.clear()
    assert env.register(await env.invite(), name="O", email=f"other{DOMAIN}").status_code == 201
    credential = env.authenticator.create(options)
    response = env.post("/auth/passkeys/verify", {"credential": credential})
    assert response.status_code == 400
    assert len(env.get("/auth/passkeys").json()["items"]) == 1


async def test_removing_a_passkey(env: AuthEnv) -> None:
    await signed_in(env)
    assert add_passkey(env) == 201
    first = env.get("/auth/passkeys").json()["items"][0]["id"]
    assert env.delete(f"/auth/passkeys/{first}").status_code == 204
    ids = [i["id"] for i in env.get("/auth/passkeys").json()["items"]]
    assert first not in ids
    assert len(ids) == 1


async def test_removing_needs_recent_auth(env: AuthEnv) -> None:
    await signed_in(env)
    assert add_passkey(env) == 201
    env.clock.advance(minutes=5)
    first = env.get("/auth/passkeys").json()["items"][0]["id"]
    assert env.delete(f"/auth/passkeys/{first}").status_code == 403
    assert len(env.get("/auth/passkeys").json()["items"]) == 2


async def test_the_last_sign_in_method_cannot_be_removed(env: AuthEnv) -> None:
    await signed_in(env)
    [only] = env.get("/auth/passkeys").json()["items"]
    response = env.delete(f"/auth/passkeys/{only['id']}")
    assert response.status_code == 409
    assert response.json()["detail"] == "This is your last way to sign in."
    assert len(env.get("/auth/passkeys").json()["items"]) == 1


async def test_a_password_account_can_remove_its_only_passkey(env: AuthEnv) -> None:
    """Password + confirmed TOTP is a sign-in method too."""
    totp = env.password_account(env.register_password(await env.invite()))
    assert env.post("/auth/totp/confirm", {"code": env.code(totp)}).status_code == 200
    assert add_passkey(env) == 201
    [passkey] = env.get("/auth/passkeys").json()["items"]
    assert env.delete(f"/auth/passkeys/{passkey['id']}").status_code == 204


async def test_another_users_passkey_is_not_found(env: AuthEnv) -> None:
    await signed_in(env)
    assert add_passkey(env) == 201
    theirs = env.get("/auth/passkeys").json()["items"][0]["id"]
    env.client.cookies.clear()
    assert env.register(await env.invite(), name="O", email=f"other{DOMAIN}").status_code == 201
    assert env.delete(f"/auth/passkeys/{theirs}").status_code == 404
    assert (
        await env.db.fetchval(
            "SELECT count(*) FROM webauthn_credentials WHERE id = $1", uuid.UUID(theirs)
        )
        == 1
    )


async def test_passkey_endpoints_need_a_session(env: AuthEnv) -> None:
    assert env.get("/auth/passkeys").status_code == 401
    assert env.post("/auth/passkeys/options", {}).status_code == 401
    assert env.delete(f"/auth/passkeys/{uuid.uuid4()}").status_code == 401


async def test_last_used_is_shown(env: AuthEnv) -> None:
    await signed_in(env)
    env.client.cookies.clear()
    env.clock.advance(hours=1)
    assert env.signin().status_code == 200
    [item] = env.get("/auth/passkeys").json()["items"]
    assert datetime.fromisoformat(item["last_used_at"]) == env.clock.now


# ---------- review follow-ups ----------


async def test_adding_a_passkey_needs_recent_auth(env: AuthEnv) -> None:
    """CR-020: otherwise a stale stolen session could add its own passkey and re-auth with it."""
    await signed_in(env)
    env.clock.advance(minutes=5)
    assert env.post("/auth/passkeys/options", {}).status_code == 403


async def test_a_challenge_fetched_while_recent_cannot_be_finished_later(env: AuthEnv) -> None:
    await signed_in(env)
    options = env.post("/auth/passkeys/options", {}).json()
    env.clock.advance(minutes=5)  # recent auth has lapsed (the challenge itself has too)
    credential = env.authenticator.create(options)
    response = env.post("/auth/passkeys/verify", {"credential": credential})
    assert response.status_code == 403
    assert len(env.get("/auth/passkeys").json()["items"]) == 1


async def test_another_users_passkey_is_not_found_even_without_recent_auth(env: AuthEnv) -> None:
    await signed_in(env)
    assert add_passkey(env) == 201
    theirs = env.get("/auth/passkeys").json()["items"][0]["id"]
    env.client.cookies.clear()
    assert env.register(await env.invite(), name="O", email=f"other{DOMAIN}").status_code == 201
    env.clock.advance(minutes=10)
    assert env.delete(f"/auth/passkeys/{theirs}").status_code == 404


async def test_an_unconfirmed_password_is_not_a_sign_in_method(env: AuthEnv) -> None:
    """Last-method rule: only a password with confirmed TOTP counts."""
    await signed_in(env)
    await env.db.execute(
        "INSERT INTO password_credentials (user_id, password_hash, totp_enabled)"
        " SELECT id, 'x', false FROM users WHERE email = $1",
        f"zee{DOMAIN}",
    )
    [only] = env.get("/auth/passkeys").json()["items"]
    response = env.delete(f"/auth/passkeys/{only['id']}")
    assert response.status_code == 409
    assert len(env.get("/auth/passkeys").json()["items"]) == 1


async def test_two_removals_at_once_keep_one_passkey(env: AuthEnv) -> None:
    await signed_in(env)
    assert add_passkey(env) == 201
    ids = [item["id"] for item in env.get("/auth/passkeys").json()["items"]]
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(
            pool.map(lambda pid: env.delete(f"/auth/passkeys/{pid}").status_code, ids)
        )
    assert statuses == [204, 409]
    assert len(env.get("/auth/passkeys").json()["items"]) == 1


async def test_revoking_a_session_spends_its_pending_challenges(env: AuthEnv) -> None:
    """A passkey-add challenge from a revoked session cannot be finished without a cookie (which
    would otherwise start a new session through the recovery-code path)."""
    await signed_in(env)
    options = env.post("/auth/passkeys/options", {}).json()
    [current] = [i for i in env.get("/auth/sessions").json()["items"] if i["current"]]
    assert env.delete(f"/auth/sessions/{current['id']}").status_code == 204
    env.client.cookies.clear()
    credential = env.authenticator.create(options)
    assert env.post("/auth/passkeys/verify", {"credential": credential}).status_code == 400
    assert env.whoami().status_code == 401
