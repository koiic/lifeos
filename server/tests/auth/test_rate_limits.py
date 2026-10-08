"""T07: AUTH-7 — 5 failed sign-ins per 15 min per account and per IP, then a 15-min lockout.

Decisions (T07.md): the account lockout refuses password, recovery-code and TOTP-confirm attempts;
passkey sign-in stays open (a passkey cannot be guessed, and otherwise anyone knowing her email
could lock her out). The IP lockout refuses every sign-in method from that IP. A failure that
makes 5 inside 15 minutes locks for 15 minutes from itself; attempts refused while locked are
failures too, so steady guessing keeps it locked. Attempts for the same account or IP are
serialised (advisory locks): a concurrent one is refused, so a burst cannot outrun the count.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pyotp
import pytest

from tests.auth.conftest import DOMAIN, HEADERS, AuthEnv

pytestmark = [pytest.mark.integration, pytest.mark.req("AUTH-7")]

EMAIL = f"zee{DOMAIN}"
FIFTEEN_MIN = 15 * 60


def fail_password(env: AuthEnv, ip: str, email: str = EMAIL) -> int:
    env.ip = ip
    status: int = env.signin_password(
        "000000", password="wrong password!!", email=email
    ).status_code
    return status


async def password_user(env: AuthEnv) -> pyotp.TOTP:
    totp = env.password_account(env.register_password(await env.invite()))
    assert env.post("/auth/totp/confirm", {"code": env.code(totp)}).status_code == 200
    env.client.cookies.clear()
    env.clock.advance(minutes=2)
    return totp


async def passkey_user(env: AuthEnv) -> list[str]:
    response = env.register(await env.invite())
    assert response.status_code == 201
    env.client.cookies.clear()
    return list(response.json()["recovery_codes"])


# ---------- per account ----------


async def test_five_failures_lock_the_account_for_15_minutes(env: AuthEnv) -> None:
    totp = await password_user(env)
    for n in range(5):
        assert fail_password(env, f"198.51.100.{n}") == 401
    env.ip = "198.51.100.99"  # a fresh IP: this is the account limit
    locked = env.signin_password(env.code(totp))
    assert locked.status_code == 429
    assert locked.headers["content-type"] == "application/problem+json"
    assert locked.headers["retry-after"] == str(FIFTEEN_MIN)
    assert "lo_session" not in locked.cookies


async def test_four_failures_do_not_lock(env: AuthEnv) -> None:
    totp = await password_user(env)
    for n in range(4):
        assert fail_password(env, f"198.51.100.{n}") == 401
    env.ip = "198.51.100.99"
    assert env.signin_password(env.code(totp)).status_code == 200


async def test_the_lockout_ends_15_minutes_after_the_fifth_failure(env: AuthEnv) -> None:
    totp = await password_user(env)
    for n in range(5):
        fail_password(env, f"198.51.100.{n}")
    env.clock.advance(minutes=15)
    env.ip = "198.51.100.99"
    assert env.signin_password(env.code(totp)).status_code == 200


async def test_spread_out_failures_still_lock_for_15_minutes(env: AuthEnv) -> None:
    """Failures at 0, 1, 2, 3 and 14 minutes: the fifth locks until minute 29, not 15."""
    totp = await password_user(env)
    start = env.clock.now
    for n, minute in enumerate((0, 1, 2, 3, 14)):
        env.clock.now = start + timedelta(minutes=minute)
        assert fail_password(env, f"198.51.100.{n}") == 401
    env.ip = "198.51.100.99"
    env.clock.now = start + timedelta(minutes=28, seconds=59)
    locked = env.signin_password(env.code(totp))
    assert locked.status_code == 429
    assert locked.headers["retry-after"] == "1"
    env.clock.now = start + timedelta(minutes=29)
    assert env.signin_password(env.code(totp)).status_code == 200


async def test_a_refused_attempt_extends_the_lock(env: AuthEnv) -> None:
    totp = await password_user(env)
    for n in range(5):
        fail_password(env, f"198.51.100.{n}")
    env.clock.advance(minutes=14, seconds=59)
    env.ip = "198.51.100.99"
    refused = env.signin_password(env.code(totp))
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == str(FIFTEEN_MIN)
    env.clock.advance(seconds=1)  # 15 min after the first five, but the refused one counts
    assert env.signin_password(env.code(totp)).status_code == 429


async def test_failures_older_than_15_minutes_do_not_count(env: AuthEnv) -> None:
    totp = await password_user(env)
    for n in range(4):
        fail_password(env, f"198.51.100.{n}")
    env.clock.advance(minutes=15, seconds=1)
    for n in range(4):
        fail_password(env, f"198.51.100.{10 + n}")
    env.ip = "198.51.100.99"
    assert env.signin_password(env.code(totp)).status_code == 200


async def test_recovery_codes_are_locked_but_passkeys_still_sign_in(env: AuthEnv) -> None:
    codes = await passkey_user(env)
    for n in range(5):
        env.ip = f"198.51.100.{n}"
        assert (
            env.post(
                "/auth/signin/recovery", {"email": EMAIL, "code": "AAAA-AAAA-AAAA"}
            ).status_code
            == 401
        )
    env.ip = "198.51.100.99"
    locked = env.post("/auth/signin/recovery", {"email": EMAIL, "code": codes[0]})
    assert locked.status_code == 429
    assert (
        await env.db.fetchval("SELECT count(*) FROM recovery_codes WHERE used_at IS NOT NULL") == 0
    )
    assert env.signin().status_code == 200


async def test_password_failures_lock_recovery_too(env: AuthEnv) -> None:
    """The limit is per account, whichever guessable method failed."""
    await password_user(env)
    for n in range(5):
        fail_password(env, f"198.51.100.{n}")
    env.ip = "198.51.100.99"
    response = env.post("/auth/signin/recovery", {"email": EMAIL, "code": "AAAA-AAAA-AAAA"})
    assert response.status_code == 429


async def test_totp_confirm_is_locked_per_account(env: AuthEnv) -> None:
    totp = env.password_account(env.register_password(await env.invite()))
    for n in range(5):
        env.ip = f"198.51.100.{n}"
        assert env.post("/auth/totp/confirm", {"code": env.wrong_code(totp)}).status_code == 401
    env.ip = "198.51.100.99"
    assert env.post("/auth/totp/confirm", {"code": env.code(totp)}).status_code == 429


async def test_one_account_locked_leaves_others_alone(env: AuthEnv) -> None:
    await password_user(env)
    other = env.password_account(
        env.register_password(await env.invite(), email=f"other{DOMAIN}", name="Other")
    )
    assert env.post("/auth/totp/confirm", {"code": env.code(other)}).status_code == 200
    env.client.cookies.clear()
    env.clock.advance(minutes=2)
    for n in range(5):
        fail_password(env, f"198.51.100.{n}")
    env.ip = "198.51.100.99"
    response = env.signin_password(env.code(other), email=f"other{DOMAIN}")
    assert response.status_code == 200


async def test_passkey_failures_count_toward_the_account(env: AuthEnv) -> None:
    """A passkey failure on her credential counts for her account (locking recovery codes), but
    passkey sign-in itself stays open."""
    codes = await passkey_user(env)
    for n in range(5):
        env.ip = f"198.51.100.{n}"
        assert env.signin(user_handle=b"x" * 16).status_code == 401
    env.ip = "198.51.100.99"
    assert env.post("/auth/signin/recovery", {"email": EMAIL, "code": codes[0]}).status_code == 429
    assert env.signin().status_code == 200


async def test_registrations_are_never_counted(env: AuthEnv) -> None:
    await passkey_user(env)
    env.ip = "192.0.2.30"
    env.authenticator.user_verification = False
    for n in range(6):
        response = env.register(await env.invite(), email=f"r{n}{DOMAIN}", name="R")
        assert response.status_code == 400
    env.authenticator.user_verification = True
    assert env.signin(passkey=env.authenticator.passkeys[0]).status_code == 200


async def test_an_already_confirmed_totp_is_not_a_counted_failure(env: AuthEnv) -> None:
    totp = env.password_account(env.register_password(await env.invite()))
    assert env.post("/auth/totp/confirm", {"code": env.code(totp)}).status_code == 200
    env.clock.advance(minutes=2)
    for _ in range(6):
        assert env.post("/auth/totp/confirm", {"code": env.code(totp)}).status_code == 409
    assert await env.db.fetchval("SELECT count(*) FROM auth_events WHERE kind = 'totp'") == 1


# ---------- per IP ----------


async def test_four_failures_from_one_ip_do_not_lock(env: AuthEnv) -> None:
    totp = await password_user(env)
    for n in range(4):
        assert fail_password(env, "192.0.2.7", email=f"nobody{n}{DOMAIN}") == 401
    env.ip = "192.0.2.7"
    assert env.signin_password(env.code(totp)).status_code == 200


async def test_totp_confirm_is_refused_from_a_locked_ip(env: AuthEnv) -> None:
    totp = env.password_account(env.register_password(await env.invite()))
    for n in range(5):
        fail_password(env, "192.0.2.7", email=f"nobody{n}{DOMAIN}")
    env.ip = "192.0.2.7"
    assert env.post("/auth/totp/confirm", {"code": env.code(totp)}).status_code == 429


async def test_retry_after_is_the_longer_of_the_ip_and_account_locks(env: AuthEnv) -> None:
    totp = await password_user(env)
    start = env.clock.now
    for n in range(5):  # this IP: minutes 0-4, locked until minute 19
        env.clock.now = start + timedelta(minutes=n)
        fail_password(env, "192.0.2.7", email=f"nobody{n}{DOMAIN}")
    for n in range(5):  # her account, other IPs: minutes 10-14, locked until minute 29
        env.clock.now = start + timedelta(minutes=10 + n)
        fail_password(env, f"198.51.100.{n}")
    env.clock.now = start + timedelta(minutes=18)
    env.ip = "192.0.2.7"
    response = env.signin_password(env.code(totp))
    assert response.status_code == 429
    # The IP alone would say 1 minute; the account (with this attempt, 6 in 15 min) 15 minutes.
    assert response.headers["retry-after"] == str(FIFTEEN_MIN)


# ---------- concurrency ----------


def post_from(env: AuthEnv, ip: str, path: str, body: dict[str, str]) -> httpx.Response:
    return env.client.post(f"/api/v1{path}", json=body, headers=HEADERS | {"CF-Connecting-IP": ip})


async def test_a_burst_of_guesses_cannot_outrun_the_account_lock(env: AuthEnv) -> None:
    await password_user(env)
    body = {"email": EMAIL, "password": "wrong password!!", "totp": "000000"}
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(
            pool.map(
                lambda n: post_from(env, f"198.51.100.{n}", "/auth/signin/password", body),
                range(10),
            )
        )
    statuses = sorted(r.status_code for r in responses)
    assert statuses.count(401) <= 5  # at most five passwords were actually checked
    assert set(statuses) <= {401, 429}
    signins = "SELECT count(*) FROM auth_events WHERE kind = 'signin_password' AND NOT success"
    assert await env.db.fetchval(signins) == 10  # every attempt logged, refused ones too


async def test_a_burst_from_one_ip_cannot_outrun_the_ip_lock(env: AuthEnv) -> None:
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(
            pool.map(
                lambda n: post_from(
                    env,
                    "192.0.2.99",
                    "/auth/signin/password",
                    {"email": f"n{n}{DOMAIN}", "password": "wrong password!!", "totp": "0"},
                ),
                range(10),
            )
        )
    statuses = [r.status_code for r in responses]
    assert statuses.count(401) <= 5
    assert set(statuses) <= {401, 429}


async def test_five_failures_from_one_ip_lock_that_ip(env: AuthEnv) -> None:
    totp = await password_user(env)
    await passkey_user_with(env, f"pk{DOMAIN}")
    for n in range(5):
        assert fail_password(env, "192.0.2.7", email=f"nobody{n}{DOMAIN}") == 401
    env.ip = "192.0.2.7"
    for response in (
        env.signin_password(env.code(totp)),
        env.signin(),
        env.post("/auth/signin/recovery", {"email": EMAIL, "code": "AAAA-AAAA-AAAA"}),
    ):
        assert response.status_code == 429
        assert response.headers["retry-after"] == str(FIFTEEN_MIN)
    env.ip = "192.0.2.8"
    assert env.signin_password(env.code(totp)).status_code == 200


async def test_passkey_failures_count_toward_the_ip(env: AuthEnv) -> None:
    await passkey_user(env)
    env.ip = "192.0.2.9"
    for _ in range(5):
        assert env.signin(user_handle=b"x" * 16).status_code == 401
    assert env.signin().status_code == 429


async def test_the_ip_lockout_ends_after_15_minutes(env: AuthEnv) -> None:
    totp = await password_user(env)
    for n in range(5):
        fail_password(env, "192.0.2.7", email=f"nobody{n}{DOMAIN}")
    env.clock.advance(minutes=15)
    env.ip = "192.0.2.7"
    assert env.signin_password(env.code(totp)).status_code == 200


async def test_successes_do_not_count(env: AuthEnv) -> None:
    await passkey_user(env)
    for _ in range(6):
        assert env.signin().status_code == 200
        env.client.cookies.clear()


async def passkey_user_with(env: AuthEnv, email: str) -> None:
    response = env.register(await env.invite(), email=email, name="Pk")
    assert response.status_code == 201
    env.client.cookies.clear()


async def test_attempts_while_locked_keep_it_locked(env: AuthEnv) -> None:
    totp = await password_user(env)
    for n in range(5):
        fail_password(env, f"198.51.100.{n}")
    env.ip = "198.51.100.99"
    for _ in range(5):
        env.clock.advance(minutes=2)
        assert env.signin_password(env.code(totp)).status_code == 429
    env.clock.advance(minutes=6)  # 16 min after the first five: the five refused ones remain
    assert env.signin_password(env.code(totp)).status_code == 429
