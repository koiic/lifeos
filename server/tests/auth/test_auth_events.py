"""T07: AUTH-7 "all attempts logged" — one `auth_events` row per attempt (spec 7.2)."""

import uuid

import asyncpg
import pytest

from tests.auth.conftest import DOMAIN, AuthEnv

pytestmark = [pytest.mark.integration, pytest.mark.req("AUTH-7")]

EMAIL = f"zee{DOMAIN}"


async def events(env: AuthEnv) -> list[asyncpg.Record]:
    return list(
        await env.db.fetch(
            "SELECT user_id, kind, success, ip_hash, at FROM auth_events ORDER BY id"
        )
    )


async def user_id(env: AuthEnv, email: str = EMAIL) -> uuid.UUID:
    found: uuid.UUID = await env.db.fetchval("SELECT id FROM users WHERE email = $1", email)
    return found


def kinds(rows: list[asyncpg.Record]) -> list[tuple[str, bool]]:
    return [(row["kind"], row["success"]) for row in rows]


async def test_passkey_registration_and_sign_in_are_logged(env: AuthEnv) -> None:
    assert env.register(await env.invite()).status_code == 201
    env.client.cookies.clear()
    assert env.signin().status_code == 200
    env.client.cookies.clear()
    assert env.signin(user_handle=b"x" * 16).status_code == 401
    rows = await events(env)
    assert kinds(rows) == [("register", True), ("signin_passkey", True), ("signin_passkey", False)]
    assert {row["user_id"] for row in rows} == {await user_id(env)}
    assert {row["at"] for row in rows} == {env.clock.now}


async def test_an_unknown_passkey_is_logged_without_a_user(env: AuthEnv) -> None:
    assert env.register(await env.invite()).status_code == 201
    await env.db.execute("DELETE FROM webauthn_credentials")
    await env.db.execute("DELETE FROM auth_events")
    env.client.cookies.clear()
    assert env.signin().status_code == 401
    [row] = await events(env)
    assert (row["kind"], row["success"], row["user_id"]) == ("signin_passkey", False, None)


async def test_password_registration_confirm_and_sign_in_are_logged(env: AuthEnv) -> None:
    totp = env.password_account(env.register_password(await env.invite()))
    assert env.post("/auth/totp/confirm", {"code": env.wrong_code(totp)}).status_code == 401
    assert env.post("/auth/totp/confirm", {"code": env.code(totp)}).status_code == 200
    env.client.cookies.clear()
    env.clock.advance(minutes=2)
    assert env.signin_password(env.code(totp)).status_code == 200
    env.client.cookies.clear()
    assert env.signin_password("000000", password="wrong password!!").status_code == 401
    rows = await events(env)
    assert kinds(rows) == [
        ("register", True),
        ("totp", False),
        ("totp", True),
        ("signin_password", True),
        ("signin_password", False),
    ]
    assert {row["user_id"] for row in rows} == {await user_id(env)}


async def test_an_unknown_email_is_logged_without_a_user(env: AuthEnv) -> None:
    assert env.signin_password("000000", email=f"nobody{DOMAIN}").status_code == 401
    assert (
        env.post(
            "/auth/signin/recovery", {"email": f"nobody{DOMAIN}", "code": "AAAA-AAAA-AAAA"}
        ).status_code
        == 401
    )
    rows = await events(env)
    assert kinds(rows) == [("signin_password", False), ("recovery", False)]
    assert {row["user_id"] for row in rows} == {None}


async def test_recovery_is_logged(env: AuthEnv) -> None:
    codes = env.register(await env.invite()).json()["recovery_codes"]
    env.client.cookies.clear()
    await env.db.execute("DELETE FROM auth_events")
    assert (
        env.post("/auth/signin/recovery", {"email": EMAIL, "code": "AAAA-AAAA-AAAA"}).status_code
        == 401
    )
    options = env.post("/auth/signin/recovery", {"email": EMAIL, "code": codes[0]}).json()
    credential = env.authenticator.create(options["options"])
    assert env.post("/auth/passkeys/verify", {"credential": credential}).status_code == 201
    rows = await events(env)
    assert kinds(rows) == [("recovery", False), ("recovery", True), ("register", True)]
    assert {row["user_id"] for row in rows} == {await user_id(env)}


async def test_sign_out_is_logged_as_a_revoke(env: AuthEnv) -> None:
    assert env.register(await env.invite()).status_code == 201
    await env.db.execute("DELETE FROM auth_events")
    assert env.post("/auth/signout").status_code == 204
    [row] = await events(env)
    assert (row["kind"], row["success"], row["user_id"]) == ("revoke", True, await user_id(env))


async def test_attempts_refused_by_an_ip_lock_are_logged(env: AuthEnv) -> None:
    env.ip = "192.0.2.50"
    statuses = [
        env.signin_password("000000", email=f"nobody{n}{DOMAIN}").status_code for n in range(6)
    ]
    assert statuses == [401] * 5 + [429]
    rows = await events(env)
    assert kinds(rows) == [("signin_password", False)] * 6
    assert {row["ip_hash"] for row in rows} == {env.ip_hash("192.0.2.50")}


@pytest.mark.parametrize("method", ["password", "recovery"])
async def test_attempts_refused_by_an_account_lock_are_logged_with_the_account(
    env: AuthEnv, method: str
) -> None:
    assert env.register(await env.invite()).status_code == 201
    env.client.cookies.clear()
    await env.db.execute("DELETE FROM auth_events")

    def attempt() -> int:
        if method == "password":
            return env.signin_password("000000", password="wrong password!!").status_code
        body = {"email": EMAIL, "code": "AAAA-AAAA-AAAA"}
        return env.post("/auth/signin/recovery", body).status_code

    statuses = []
    for n in range(6):
        env.ip = f"198.51.100.{n}"
        statuses.append(attempt())
    assert statuses == [401] * 5 + [429]
    rows = await events(env)
    kind = "signin_password" if method == "password" else "recovery"
    assert kinds(rows) == [(kind, False)] * 6
    assert {row["user_id"] for row in rows} == {await user_id(env)}


async def test_failed_registrations_are_logged(env: AuthEnv) -> None:
    env.authenticator.user_verification = False
    assert env.register(await env.invite()).status_code == 400
    [row] = await events(env)
    assert (row["kind"], row["success"], row["user_id"]) == ("register", False, None)


async def test_the_ip_is_stored_only_as_its_hmac(env: AuthEnv) -> None:
    env.ip = "192.0.2.77"
    env.signin_password("000000", email=f"nobody{DOMAIN}")
    [row] = await events(env)
    assert row["ip_hash"] == env.ip_hash("192.0.2.77")
    assert b"192.0.2.77" not in row["ip_hash"]
    assert row["ip_hash"] != env.ip_hash("192.0.2.78")


async def test_sessions_record_the_ip_hash(env: AuthEnv) -> None:
    env.ip = "192.0.2.80"
    assert env.register(await env.invite()).status_code == 201
    stored = await env.db.fetchval(
        "SELECT ip_hash FROM sessions WHERE user_id = $1", await user_id(env)
    )
    assert stored == env.ip_hash("192.0.2.80")


async def test_an_unexpected_error_is_logged_as_a_counted_failure(
    env: AuthEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any exception during an attempt is a failure ("all attempts logged"), not only the
    expected ones."""
    from app.auth import service

    def broken(_hash: str | None, _password: str) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_password_matches", broken)
    assert env.signin_password("000000", email=f"nobody{DOMAIN}").status_code == 500
    [row] = await events(env)
    assert (row["kind"], row["success"]) == ("signin_password", False)


async def test_a_database_error_in_the_lockout_check_is_still_logged(
    env: AuthEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.auth import repo

    async def broken(tx: object, **_kwargs: object) -> list[object]:
        from sqlalchemy import text

        await tx.execute(text("SELECT 1 / 0"))  # type: ignore[attr-defined]  # a real DB error
        return []

    monkeypatch.setattr(repo, "recent_failures", broken)
    assert env.signin_password("000000", email=f"nobody{DOMAIN}").status_code == 500
    [row] = await events(env)
    assert (row["kind"], row["success"]) == ("signin_password", False)


async def test_an_event_the_gate_cannot_write_is_written_on_its_own(
    env: AuthEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.auth import repo

    real = repo.insert_auth_event
    calls: list[int] = []

    async def first_fails(*args: object, **kwargs: object) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("gate write failed")
        await real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(repo, "insert_auth_event", first_fails)
    assert env.signin_password("000000", email=f"nobody{DOMAIN}").status_code == 401
    [row] = await events(env)
    assert (row["kind"], row["success"]) == ("signin_password", False)
    assert len(calls) == 2
