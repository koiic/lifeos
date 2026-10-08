"""T07: password + TOTP fallback (AUTH-3; spec 9.2, 12.3; CR-014)."""

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import pyotp
import pytest

from app.auth import service
from app.platform.crypto import Keyring, MasterKey, aad, decrypt, unwrap_dek
from tests.auth.conftest import DOMAIN, HEADERS, PASSWORD, AuthEnv

pytestmark = pytest.mark.integration
AUTH_3 = pytest.mark.req("AUTH-3")  # owned by T12; tagged where these tests prove it

LOCAL_KEYRING = Keyring({1: MasterKey(bytes(32))})
EMAIL = f"zee{DOMAIN}"
# Entries of app/auth/data/common_passwords.txt, as typed (case and spaces vary).
ON_THE_LIST = (
    "qwerty123456",
    "Password1234",
    "  QwertyUiop123  ",
)


async def registered(env: AuthEnv) -> pyotp.TOTP:
    return env.password_account(env.register_password(await env.invite()))


async def confirmed(env: AuthEnv) -> pyotp.TOTP:
    totp = await registered(env)
    response = env.post("/auth/totp/confirm", {"code": env.code(totp)})
    assert response.status_code == 200, response.text
    env.client.cookies.clear()
    env.clock.advance(minutes=2)  # past the confirm code's window (no replay)
    return totp


# ---------- registration ----------


@AUTH_3
async def test_password_registration_returns_a_totp_provisioning_uri(env: AuthEnv) -> None:
    response = env.register_password(await env.invite())
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    uri = urlsplit(response.json()["provisioning_uri"])
    assert (uri.scheme, uri.netloc) == ("otpauth", "totp")
    query = parse_qs(uri.query)
    assert query["issuer"] == ["Life OS"]
    totp = env.password_account(response)
    # RFC 6238 defaults the spec names: SHA-1, 6 digits, 30 s.
    assert (totp.digest().name, totp.digits, totp.interval) == ("sha1", 6, 30)
    assert len(totp.byte_secret()) >= 20  # 160 bits (RFC 4226 recommendation)


@AUTH_3
async def test_the_password_is_stored_argon2id_with_the_spec_parameters(env: AuthEnv) -> None:
    await registered(env)
    row = await env.db.fetchrow(
        "SELECT p.password_hash, p.totp_enabled FROM password_credentials p"
        " JOIN users u ON u.id = p.user_id WHERE u.email = $1",
        EMAIL,
    )
    assert row is not None
    assert row["password_hash"].startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert PASSWORD not in row["password_hash"]
    assert row["totp_enabled"] is False


async def test_the_totp_secret_is_stored_only_encrypted(env: AuthEnv) -> None:
    totp = await registered(env)
    user = await env.db.fetchrow(
        "SELECT id, dek_wrapped, kek_version FROM users WHERE email = $1", EMAIL
    )
    assert user is not None
    stored = await env.db.fetchval(
        "SELECT totp_secret_enc FROM password_credentials WHERE user_id = $1", user["id"]
    )
    assert totp.secret.encode() not in stored
    assert totp.byte_secret() not in stored
    dek = unwrap_dek(LOCAL_KEYRING, user["kek_version"], user["dek_wrapped"], user["id"])
    associated = aad("password_credentials", "totp_secret_enc", user["id"], user["id"])
    assert decrypt(dek, stored, associated) == totp.secret.encode()


@pytest.mark.parametrize(
    "password",
    ["short pass1", "x" * 11],
    ids=["11-chars", "11-x"],
)
async def test_passwords_need_12_characters(env: AuthEnv, password: str) -> None:
    response = env.register_password(await env.invite(), password=password)
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "password"
    assert response.json()["errors"][0]["code"] == "password_too_short"
    assert password not in response.text


async def test_12_characters_are_enough(env: AuthEnv) -> None:
    assert env.register_password(await env.invite(), password="zq8!tangerin").status_code == 201


@pytest.mark.parametrize("password", ON_THE_LIST)
async def test_common_passwords_are_refused(env: AuthEnv, password: str) -> None:
    response = env.register_password(await env.invite(), password=password)
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "password_too_common"
    assert password.strip() not in response.text


async def test_password_registration_follows_the_invite_rules(env: AuthEnv) -> None:
    assert env.register_password("nope").status_code == 403
    token = await env.invite(f"other{DOMAIN}")
    assert env.register_password(token).status_code == 403
    token = await env.invite()
    assert env.register_password(token).status_code == 201
    assert env.register_password(token, email=f"z2{DOMAIN}").status_code == 403
    assert env.register_password(await env.invite()).status_code == 409


# ---------- the inactive account (CR-014) ----------


async def test_before_confirming_the_session_can_only_confirm_totp(env: AuthEnv) -> None:
    await registered(env)
    assert "lo_session" in env.client.cookies
    response = env.whoami()
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"


async def test_confirming_activates_and_returns_recovery_codes_once(env: AuthEnv) -> None:
    totp = await registered(env)
    response = env.post("/auth/totp/confirm", {"code": env.code(totp)})
    assert response.status_code == 200, response.text
    codes = response.json()["recovery_codes"]
    assert len(set(codes)) == 10
    assert env.whoami().status_code == 200
    user_id = await env.db.fetchval("SELECT id FROM users WHERE email = $1", EMAIL)
    assert await env.db.fetchval(
        "SELECT totp_enabled FROM password_credentials WHERE user_id = $1", user_id
    )
    assert (
        await env.db.fetchval("SELECT count(*) FROM recovery_codes WHERE user_id = $1", user_id)
        == 10
    )
    again = env.post("/auth/totp/confirm", {"code": env.code(totp, 30)})
    assert again.status_code == 409


async def test_a_wrong_confirm_code_keeps_the_account_inactive(env: AuthEnv) -> None:
    totp = await registered(env)
    response = env.post("/auth/totp/confirm", {"code": env.wrong_code(totp)})
    assert response.status_code == 401
    assert env.whoami().status_code == 403


async def test_confirm_needs_a_session(env: AuthEnv) -> None:
    totp = await registered(env)
    env.client.cookies.clear()
    assert env.post("/auth/totp/confirm", {"code": env.code(totp)}).status_code == 401


async def test_an_unconfirmed_account_cannot_sign_in_with_a_password(env: AuthEnv) -> None:
    totp = await registered(env)
    env.client.cookies.clear()
    assert env.signin_password(env.code(totp)).status_code == 401


# ---------- password + TOTP sign-in ----------


async def test_password_and_totp_sign_in(env: AuthEnv) -> None:
    totp = await confirmed(env)
    response = env.signin_password(env.code(totp))
    assert response.status_code == 200, response.text
    user_id = await env.db.fetchval("SELECT id FROM users WHERE email = $1", EMAIL)
    assert response.json() == {"user_id": str(user_id), "display_name": "Zee"}
    assert env.whoami().json()["user_id"] == str(user_id)


async def test_the_email_is_case_insensitive(env: AuthEnv) -> None:
    totp = await confirmed(env)
    assert env.signin_password(env.code(totp), email=EMAIL.upper()).status_code == 200


@AUTH_3
@pytest.mark.parametrize("offset", [-30, 30], ids=["previous-step", "next-step"])
async def test_one_step_either_side_is_accepted(env: AuthEnv, offset: int) -> None:
    totp = await confirmed(env)
    assert env.signin_password(env.code(totp, offset)).status_code == 200


@AUTH_3
@pytest.mark.parametrize("offset", [-60, 60], ids=["two-steps-back", "two-steps-ahead"])
async def test_two_steps_away_is_refused(env: AuthEnv, offset: int) -> None:
    totp = await confirmed(env)
    assert env.signin_password(env.code(totp, offset)).status_code == 401


@AUTH_3
async def test_a_code_cannot_be_reused(env: AuthEnv) -> None:
    totp = await confirmed(env)
    step = totp.timecode(env.clock.now)
    code = env.code(totp)
    assert env.signin_password(code).status_code == 200
    env.client.cookies.clear()
    env.clock.advance(seconds=20)
    assert env.signin_password(code).status_code == 401
    # Nor the next step's code (the used one may have matched it, given ±1 step).
    assert env.signin_password(totp.generate_otp(step + 1)).status_code == 401
    # Two steps on is a new code.
    env.clock.advance(seconds=30)
    assert env.signin_password(totp.generate_otp(step + 2)).status_code == 200


async def test_a_new_code_works_once_the_window_has_passed(env: AuthEnv) -> None:
    totp = await confirmed(env)
    assert env.signin_password(env.code(totp)).status_code == 200
    env.client.cookies.clear()
    env.clock.advance(seconds=90)
    assert env.signin_password(env.code(totp)).status_code == 200


async def test_wrong_password_code_or_email_fail_alike(env: AuthEnv) -> None:
    totp = await confirmed(env)
    good = env.code(totp)
    wrong_code = env.wrong_code(totp)
    failures = [
        env.signin_password(good, password="not the password!"),
        env.signin_password(wrong_code),
        env.signin_password(good, email=f"nobody{DOMAIN}"),
    ]
    assert {r.status_code for r in failures} == {401}
    assert len({r.content for r in failures}) == 1
    assert not any("lo_session" in r.cookies for r in failures)


async def test_a_deleted_account_cannot_sign_in(env: AuthEnv) -> None:
    totp = await confirmed(env)
    await env.db.execute("UPDATE users SET deleted_at = now() WHERE email = $1", EMAIL)
    assert env.signin_password(env.code(totp)).status_code == 401


async def test_a_passkey_account_has_no_password(env: AuthEnv) -> None:
    assert env.register(await env.invite()).status_code == 201
    env.client.cookies.clear()
    assert env.signin_password("123456").status_code == 401


# ---------- review follow-ups ----------


async def test_256_characters_are_accepted_and_257_refused(env: AuthEnv) -> None:
    longest = "q" * 255 + "!"
    assert env.register_password(await env.invite(), password=longest).status_code == 201
    too_long = "q" * 256 + "!"
    response = env.register_password(await env.invite(), password=too_long, email=f"z2{DOMAIN}")
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "password"
    assert too_long not in response.text


async def test_an_overlong_sign_in_password_is_refused_unread(env: AuthEnv) -> None:
    """422 before any work: nothing is guessed, so nothing is logged or counted."""
    response = env.signin_password("123456", password="x" * 257)
    assert response.status_code == 422
    assert "x" * 257 not in response.text
    assert await env.db.fetchval("SELECT count(*) FROM auth_events") == 0


async def test_passwords_are_compared_after_nfc_normalisation(env: AuthEnv) -> None:
    decomposed = "cafe" + chr(0x301) + " tangerine 42"
    composed = "caf" + chr(0xE9) + " tangerine 42"
    totp = env.password_account(env.register_password(await env.invite(), password=decomposed))
    assert env.post("/auth/totp/confirm", {"code": env.code(totp)}).status_code == 200
    env.client.cookies.clear()
    env.clock.advance(minutes=2)
    assert env.signin_password(env.code(totp), password=composed).status_code == 200


async def test_the_confirm_code_cannot_be_reused_to_sign_in(env: AuthEnv) -> None:
    totp = await registered(env)
    step = totp.timecode(env.clock.now)
    code = env.code(totp)
    assert env.post("/auth/totp/confirm", {"code": code}).status_code == 200
    env.client.cookies.clear()
    env.clock.advance(seconds=10)
    assert env.signin_password(code).status_code == 401
    env.clock.advance(seconds=30)
    assert env.signin_password(totp.generate_otp(step + 2)).status_code == 200


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", "12 34 5"])
async def test_malformed_codes_fail(env: AuthEnv, code: str) -> None:
    totp = await confirmed(env)
    assert totp
    assert env.signin_password(code).status_code == 401


async def test_spaces_inside_a_code_are_ignored(env: AuthEnv) -> None:
    totp = await confirmed(env)
    code = env.code(totp)
    assert env.signin_password(f"{code[:3]} {code[3:]}").status_code == 200


async def test_an_overlong_code_is_a_validation_error(env: AuthEnv) -> None:
    await confirmed(env)
    assert env.signin_password("1" * 17).status_code == 422


@pytest.mark.parametrize("case", ["known-email", "unknown-email"])
async def test_each_attempt_runs_one_argon2id_verification(
    env: AuthEnv, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """Unknown emails do the same work as a wrong password (T07 Decisions: enumeration)."""
    await confirmed(env)
    calls: list[int] = []
    real = service.PASSWORD_HASHER

    class Counting:
        def verify(self, password_hash: str, password: str) -> bool:
            calls.append(1)
            return real.verify(password_hash, password)

    monkeypatch.setattr(service, "PASSWORD_HASHER", Counting())
    email = EMAIL if case == "known-email" else f"nobody{DOMAIN}"
    assert (
        env.signin_password("000000", password="not the password!", email=email).status_code == 401
    )
    assert len(calls) == 1


async def test_a_code_used_concurrently_gives_one_session(env: AuthEnv) -> None:
    """12.3 replay, under concurrency: the account's advisory lock lets one attempt through."""
    totp = await confirmed(env)
    body = {"email": EMAIL, "password": PASSWORD, "totp": env.code(totp)}

    def attempt(ip: str) -> int:
        response = env.client.post(
            "/api/v1/auth/signin/password", json=body, headers=HEADERS | {"CF-Connecting-IP": ip}
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(attempt, ["198.51.100.1", "198.51.100.2"]))
    assert statuses[0] == 200
    assert statuses[1] in {401, 429}
    user_id = await env.db.fetchval("SELECT id FROM users WHERE email = $1", EMAIL)
    assert await env.db.fetchval("SELECT count(*) FROM sessions WHERE user_id = $1", user_id) == 2
