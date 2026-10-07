"""T06: recovery codes (AUTH-4; spec 9.2 `POST /auth/signin/recovery`, CR-013).

A code gives no session: it gives creation options for a new passkey, and the session starts
when that passkey is verified at `POST /auth/passkeys/verify`.
"""

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import asyncpg
import pytest

from app.auth import service
from tests.auth.conftest import DOMAIN, AuthEnv

pytestmark = pytest.mark.integration

EMAIL = f"zee{DOMAIN}"
FAILED = 401


@pytest.fixture
async def codes(env: AuthEnv) -> list[str]:
    response = env.register(await env.invite())
    assert response.status_code == 201, response.text
    env.client.cookies.clear()
    return list(response.json()["recovery_codes"])


async def user_id(env: AuthEnv) -> uuid.UUID:
    found: uuid.UUID = await env.db.fetchval("SELECT id FROM users WHERE email = $1", EMAIL)
    return found


def recover(env: AuthEnv, code: str, email: str = EMAIL) -> Any:
    return env.post("/auth/signin/recovery", {"email": email, "code": code})


def finish(env: AuthEnv, options: dict[str, Any], **create: Any) -> Any:
    credential = env.authenticator.create(options, **create)
    return env.post("/auth/passkeys/verify", {"credential": credential})


async def test_codes_are_12_unambiguous_characters(codes: list[str]) -> None:
    for code in codes:
        assert len(code.replace("-", "")) == 12
        assert set(code.replace("-", "")) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")


async def test_a_code_gives_no_session_only_new_passkey_options(
    env: AuthEnv, codes: list[str]
) -> None:
    response = recover(env, codes[3])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["next"] == "add_passkey"
    options = body["options"]
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert [p["alg"] for p in options["pubKeyCredParams"]] == [-7, -257]
    assert "lo_session" not in response.cookies
    assert env.whoami().status_code == 401
    challenge = await env.db.fetchrow(
        "SELECT user_id, expires_at FROM auth_challenges WHERE purpose = 'add_passkey'"
    )
    assert challenge is not None
    assert challenge["user_id"] == await user_id(env)
    assert challenge["expires_at"] == env.clock.now + timedelta(minutes=5)


async def test_the_new_passkey_starts_the_session(env: AuthEnv, codes: list[str]) -> None:
    options = recover(env, codes[0]).json()["options"]
    response = finish(env, options)
    assert response.status_code == 201, response.text
    account = await user_id(env)
    assert response.json() == {"user_id": str(account), "display_name": "Zee"}
    assert env.whoami().json()["user_id"] == str(account)
    # The new passkey's user handle is the account id, and it signs in.
    assert env.authenticator.passkeys[-1].user_handle == account.bytes
    assert (
        await env.db.fetchval(
            "SELECT count(*) FROM webauthn_credentials WHERE user_id = $1", account
        )
        == 2
    )
    env.client.cookies.clear()
    assert env.signin().status_code == 200


async def test_the_add_passkey_challenge_is_single_use(env: AuthEnv, codes: list[str]) -> None:
    options = recover(env, codes[0]).json()["options"]
    assert finish(env, options).status_code == 201
    env.client.cookies.clear()
    assert finish(env, options).status_code == 400
    assert env.whoami().status_code == 401


async def test_the_add_passkey_challenge_lasts_five_minutes(env: AuthEnv, codes: list[str]) -> None:
    options = recover(env, codes[0]).json()["options"]
    env.clock.advance(minutes=5, seconds=1)
    assert finish(env, options).status_code == 400
    assert env.whoami().status_code == 401


async def test_the_new_passkey_needs_user_verification(env: AuthEnv, codes: list[str]) -> None:
    options = recover(env, codes[0]).json()["options"]
    env.authenticator.user_verification = False
    assert finish(env, options).status_code == 400
    assert env.whoami().status_code == 401


@pytest.mark.parametrize(
    "create",
    [{"origin": "https://evil.test"}, {"rp_id": "evil.test"}, {"alg": "EdDSA"}],
    ids=["origin", "rp-id", "eddsa"],
)
async def test_a_bad_new_passkey_is_rejected(
    env: AuthEnv, codes: list[str], create: dict[str, str]
) -> None:
    options = recover(env, codes[0]).json()["options"]
    assert finish(env, options, **create).status_code == 400
    assert env.whoami().status_code == 401


async def test_a_registration_challenge_cannot_add_a_passkey(
    env: AuthEnv, codes: list[str]
) -> None:
    """Only a recovery challenge names an account to add the passkey to."""
    token = await env.invite()
    options = env.post(
        "/auth/register/options", {"token": token, "name": "X", "email": f"x{DOMAIN}"}
    ).json()
    assert finish(env, options).status_code == 400
    assert env.whoami().status_code == 401


async def test_a_signin_challenge_cannot_add_a_passkey(env: AuthEnv, codes: list[str]) -> None:
    challenge = env.post("/auth/signin/options", {}).json()["challenge"]
    options = {"challenge": challenge, "user": {"id": "AAAAAAAAAAAAAAAAAAAAAA"}}
    assert finish(env, options).status_code == 400
    assert env.whoami().status_code == 401


async def test_a_code_spent_concurrently_does_not_work_twice(
    env: AuthEnv, codes: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hashing runs with no connection held; the code is then spent with a conditional update,
    so an attempt that spent it meanwhile wins and this one fails."""
    real = service._matching_code
    url = env.app.state.settings.database_url.get_secret_value()

    def spent_meanwhile(found: list[tuple[uuid.UUID, str]], code: str) -> uuid.UUID | None:
        result = real(found, code)

        async def spend() -> None:
            conn = await asyncpg.connect(url)
            await conn.execute("UPDATE recovery_codes SET used_at = now() WHERE id = $1", result)
            await conn.close()

        asyncio.run(spend())  # runs in the hashing thread, between the two transactions
        return result

    monkeypatch.setattr(service, "_matching_code", spent_meanwhile)
    assert recover(env, codes[0]).status_code == FAILED
    assert (
        await env.db.fetchval("SELECT count(*) FROM auth_challenges WHERE purpose = 'add_passkey'")
        == 0
    )


async def test_a_code_works_once(env: AuthEnv, codes: list[str]) -> None:
    assert recover(env, codes[0]).status_code == 200
    assert recover(env, codes[0]).status_code == FAILED
    # The other nine still work.
    assert recover(env, codes[1]).status_code == 200
    assert (
        await env.db.fetchval(
            "SELECT count(*) FROM recovery_codes WHERE user_id = $1 AND used_at IS NULL",
            await user_id(env),
        )
        == 8
    )


async def test_codes_are_case_and_separator_insensitive(env: AuthEnv, codes: list[str]) -> None:
    raw = codes[2].replace("-", "")
    typed = f" {raw[:4].lower()} {raw[4:8]}-{raw[8:]} "
    assert recover(env, typed, email=f"ZEE{DOMAIN}").status_code == 200


async def test_wrong_code_reused_code_and_unknown_email_fail_alike(
    env: AuthEnv, codes: list[str]
) -> None:
    assert recover(env, codes[0]).status_code == 200
    failures = [
        recover(env, codes[0]),
        recover(env, "AAAA-AAAA-AAAA"),
        recover(env, codes[1], email=f"nobody{DOMAIN}"),
        recover(env, "short"),
    ]
    assert {r.status_code for r in failures} == {FAILED}
    assert len({r.content for r in failures}) == 1


async def test_a_code_of_another_user_does_not_work(env: AuthEnv, codes: list[str]) -> None:
    other = env.register(await env.invite(), name="Other", email=f"other{DOMAIN}")
    env.client.cookies.clear()
    other_code = other.json()["recovery_codes"][0]
    assert recover(env, other_code).status_code == FAILED
    used = await env.db.fetchval(
        "SELECT count(*) FROM recovery_codes r JOIN users u ON u.id = r.user_id"
        " WHERE u.email LIKE $1 AND r.used_at IS NOT NULL",
        f"%{DOMAIN}",
    )
    assert used == 0


async def test_a_deleted_account_cannot_recover(env: AuthEnv, codes: list[str]) -> None:
    await env.db.execute("UPDATE users SET deleted_at = now() WHERE email = $1", EMAIL)
    assert recover(env, codes[0]).status_code == FAILED


async def test_every_attempt_runs_ten_hash_checks(
    env: AuthEnv, codes: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown email, wrong code and an account with spent codes cost the same (T06 Decisions)."""
    calls: list[int] = []
    real = service.CODE_HASHER

    class Counting:
        def verify(self, code_hash: str, code: str) -> bool:
            calls.append(1)
            return real.verify(code_hash, code)

    monkeypatch.setattr(service, "CODE_HASHER", Counting())
    attempts = [
        (codes[0], EMAIL),  # success
        (codes[0], EMAIL),  # reused: nine codes left
        ("AAAA-AAAA-AAAA", EMAIL),
        (codes[1], f"nobody{DOMAIN}"),
    ]
    for code, email in attempts:
        calls.clear()
        recover(env, code, email=email)
        assert len(calls) == 10, (code, email)
