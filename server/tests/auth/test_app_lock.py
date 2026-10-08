"""T08: app lock (AUTH-6; spec 9.2 `PUT /auth/app-lock`, `POST /auth/app-lock/unlock` "5 tries
then full sign-in required"; 11.6)."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.auth.conftest import DOMAIN, AuthEnv

pytestmark = [pytest.mark.integration, pytest.mark.req("AUTH-6")]

PIN = "482915"


@pytest.fixture
async def user(env: AuthEnv) -> None:
    assert env.register(await env.invite()).status_code == 201


async def settings(env: AuthEnv) -> tuple[str | None, int]:
    row = await env.db.fetchrow(
        "SELECT s.app_lock_pin_hash, s.app_lock_timeout_s FROM user_settings s"
        " JOIN users u ON u.id = s.user_id WHERE u.email = $1",
        f"zee{DOMAIN}",
    )
    assert row is not None
    return row["app_lock_pin_hash"], row["app_lock_timeout_s"]


def unlock(env: AuthEnv, pin: str = PIN) -> int:
    status: int = env.post("/auth/app-lock/unlock", {"pin": pin}).status_code
    return status


async def test_setting_a_pin_and_timeout(env: AuthEnv, user: None) -> None:
    assert env.put("/auth/app-lock", {"pin": PIN, "timeout_s": 600}).status_code == 204
    pin_hash, timeout = await settings(env)
    assert pin_hash is not None
    assert pin_hash.startswith("$argon2id$")
    assert PIN not in pin_hash
    assert timeout == 600


async def test_changing_only_the_timeout_keeps_the_pin(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN, "timeout_s": 600})
    assert env.put("/auth/app-lock", {"timeout_s": 120}).status_code == 204
    pin_hash, timeout = await settings(env)
    assert pin_hash is not None
    assert timeout == 120
    assert unlock(env) == 204


async def test_clearing_the_pin(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN, "timeout_s": 300})
    assert env.put("/auth/app-lock", {"pin": None}).status_code == 204
    assert (await settings(env))[0] is None
    assert unlock(env) == 409


@pytest.mark.parametrize(
    "body",
    [
        {"pin": "12345"},
        {"pin": "1234567"},
        {"pin": "12a456"},
        {"pin": "12 456"},
        {"timeout_s": 59},
        {"timeout_s": 3601},
        {"other": 1},
    ],
)
async def test_invalid_settings(env: AuthEnv, user: None, body: dict[str, object]) -> None:
    response = env.put("/auth/app-lock", body)
    assert response.status_code == 422
    assert str(body.get("pin", "never-echoed")) not in response.text


async def test_unlocking_with_the_pin(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN, "timeout_s": 300})
    assert unlock(env) == 204
    assert unlock(env, "000000") == 401
    assert env.whoami().status_code == 200


async def test_five_wrong_tries_end_the_session(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN, "timeout_s": 300})
    token = env.session_token()
    statuses = [unlock(env, "000000") for _ in range(5)]
    assert statuses == [401] * 5
    env.use_session(token)  # the session itself is revoked, not just the cookie cleared
    assert env.whoami().status_code == 401  # full sign-in required
    assert unlock(env) == 401  # even the right PIN now


async def test_the_fifth_wrong_try_clears_the_cookie(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN, "timeout_s": 300})
    for _ in range(4):
        unlock(env, "000000")
    response = env.post("/auth/app-lock/unlock", {"pin": "000000"})
    assert response.status_code == 401
    assert env.set_cookie_flags(response)["max-age"] == "0"


async def test_a_good_unlock_resets_the_count(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN, "timeout_s": 300})
    for _ in range(4):
        assert unlock(env, "000000") == 401
    assert unlock(env) == 204
    for _ in range(4):
        assert unlock(env, "000000") == 401
    assert env.whoami().status_code == 200


async def test_a_new_sign_in_resets_the_count(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN, "timeout_s": 300})
    for _ in range(5):
        unlock(env, "000000")
    env.client.cookies.clear()
    assert env.signin().status_code == 200  # a new session starts at zero (CR-021)
    assert unlock(env) == 204


async def test_pin_attempts_are_logged(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN, "timeout_s": 300})
    await env.db.execute("DELETE FROM auth_events")
    unlock(env, "000000")
    unlock(env)
    rows = await env.db.fetch("SELECT kind, success FROM auth_events ORDER BY id")
    assert [(r["kind"], r["success"]) for r in rows] == [
        ("pin_unlock", False),
        ("pin_unlock", True),
    ]


async def test_another_users_pin_does_not_unlock(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN, "timeout_s": 300})
    env.client.cookies.clear()
    assert env.register(await env.invite(), name="O", email=f"other{DOMAIN}").status_code == 201
    assert unlock(env) == 409  # her PIN is not theirs; they have none


async def test_app_lock_needs_a_session(env: AuthEnv) -> None:
    assert env.put("/auth/app-lock", {"pin": PIN}).status_code == 401
    assert unlock(env) == 401


# ---------- review follow-ups (CR-020, CR-021) ----------


async def test_the_default_timeout_is_300_seconds(env: AuthEnv, user: None) -> None:
    assert (await settings(env))[1] == 300


@pytest.mark.parametrize("seconds", [60, 3600])
async def test_the_timeout_limits_are_accepted(env: AuthEnv, user: None, seconds: int) -> None:
    assert env.put("/auth/app-lock", {"timeout_s": seconds}).status_code == 204
    assert (await settings(env))[1] == seconds


async def test_changing_or_clearing_the_pin_needs_recent_auth(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN})
    env.clock.advance(minutes=5)
    assert env.put("/auth/app-lock", {"pin": "111111"}).status_code == 403
    assert env.put("/auth/app-lock", {"pin": None}).status_code == 403
    assert env.put("/auth/app-lock", {"timeout_s": 120}).status_code == 204  # timeout alone is fine
    assert unlock(env) == 204  # the PIN is unchanged


async def test_tries_on_another_device_do_not_count_here(env: AuthEnv, user: None) -> None:
    """CR-021: the five tries belong to the session on that device."""
    env.put("/auth/app-lock", {"pin": PIN})
    phone = env.session_token()
    env.client.cookies.clear()
    assert env.signin().status_code == 200
    laptop = env.session_token()
    for _ in range(4):
        assert unlock(env, "000000") == 401  # laptop
    env.use_session(phone)
    assert unlock(env, "000000") == 401  # one on the phone
    env.use_session(laptop)
    assert unlock(env) == 204  # the laptop still has its fifth try


async def test_a_good_unlock_elsewhere_does_not_reset_this_device(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN})
    phone = env.session_token()
    env.client.cookies.clear()
    assert env.signin().status_code == 200
    laptop = env.session_token()
    env.use_session(phone)
    for _ in range(4):
        unlock(env, "000000")
    env.use_session(laptop)
    assert unlock(env) == 204
    env.use_session(phone)
    assert unlock(env, "000000") == 401
    assert env.whoami().status_code == 401  # the phone's fifth wrong try ended it


async def test_a_passkey_unlock_resets_the_tries(env: AuthEnv, user: None) -> None:
    env.put("/auth/app-lock", {"pin": PIN})
    for _ in range(4):
        unlock(env, "000000")
    options = env.post("/auth/reauth/options", {"purpose": "unlock"}).json()
    credential = env.authenticator.get(options)
    assert env.post("/auth/reauth/verify", {"credential": credential}).status_code == 204
    for _ in range(4):
        assert unlock(env, "000000") == 401
    assert env.whoami().status_code == 200


async def test_concurrent_wrong_pins_get_five_checks_at_most(
    env: AuthEnv, user: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.auth import service

    env.put("/auth/app-lock", {"pin": PIN})
    token = env.session_token()
    checks: list[int] = []
    real = service._password_matches

    def counting(stored: str | None, pin: str) -> bool:
        checks.append(1)
        return real(stored, pin)

    monkeypatch.setattr(service, "_password_matches", counting)
    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(lambda _: unlock(env, "000000"), range(10)))
    assert set(statuses) == {401}
    assert len(checks) <= 5
    env.use_session(token)
    assert env.whoami().status_code == 401
