"""T08: AUTH-8 — account recovery when every sign-in method is lost.

"The admin issues a recovery invite (single-use, 24 h) that lets her register a new passkey on
her existing account. Issuing it revokes all sessions, pushes a notice to her registered devices,
and is audited." (spec 4.1; 9.2; CR-018 `invites.recover_user_id`)
"""

import hashlib
import json
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest

from tests.auth.authenticator import SoftAuthenticator
from tests.auth.conftest import DOMAIN, HEADERS, ORIGIN, RP_ID, AuthEnv

pytestmark = [pytest.mark.integration, pytest.mark.req("AUTH-8")]

EMAIL = f"zee{DOMAIN}"


@pytest.fixture
async def zee(env: AuthEnv) -> uuid.UUID:
    response = env.register(await env.invite())
    assert response.status_code == 201
    env.client.cookies.clear()
    return uuid.UUID(response.json()["user_id"])


def as_admin(env: AuthEnv, token: str, user_id: uuid.UUID) -> httpx.Response:
    env.use_session(token)
    response = env.post(f"/admin/users/{user_id}/recovery-invite", {})
    env.client.cookies.clear()
    return response


def recover(env: AuthEnv, token: str, authenticator: SoftAuthenticator) -> httpx.Response:
    options = env.post("/auth/recover/options", {"token": token})
    assert options.status_code == 200, options.text
    credential = authenticator.create(options.json())
    return env.post("/auth/recover/verify", {"token": token, "credential": credential})


async def test_the_admin_issues_a_single_use_24_hour_invite(env: AuthEnv, zee: uuid.UUID) -> None:
    response = as_admin(env, await env.admin_token(), zee)
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    row = await env.invite_row(body["token"])
    assert row["recover_user_id"] == zee
    assert row["expires_at"] == env.clock.now + timedelta(hours=24)
    assert row["created_by"] == env.admin_id
    assert row["token_hash"] == hashlib.sha256(body["token"].encode()).digest()
    assert body["link"] == f"/recover?token={body['token']}"


async def test_issuing_revokes_every_session(env: AuthEnv, zee: uuid.UUID) -> None:
    assert env.signin().status_code == 200
    phone = env.session_token()
    env.client.cookies.clear()
    assert env.signin().status_code == 200
    laptop = env.session_token()
    assert as_admin(env, await env.admin_token(), zee).status_code == 201
    for token in (phone, laptop):
        env.use_session(token)
        assert env.whoami().status_code == 401
    assert (
        await env.db.fetchval(
            "SELECT count(*) FROM sessions WHERE user_id = $1 AND revoked_at IS NULL", zee
        )
        == 0
    )


async def test_issuing_is_audited(env: AuthEnv, zee: uuid.UUID) -> None:
    env.ip = "198.51.100.40"
    assert as_admin(env, await env.admin_token(), zee).status_code == 201
    row = await env.db.fetchrow("SELECT * FROM audit_log WHERE target_user_id = $1", zee)
    assert row is not None
    assert row["actor_user_id"] == env.admin_id
    assert row["actor_role"] == "admin"
    assert row["action"] == "admin.recovery_invite"
    assert row["ip_hash"] == env.ip_hash("198.51.100.40")
    assert row["at"] == env.clock.now


async def test_issuing_queues_a_notice_to_her_devices(env: AuthEnv, zee: uuid.UUID) -> None:
    assert as_admin(env, await env.admin_token(), zee).status_code == 201
    rows = await env.db.fetch("SELECT topic, body FROM outbox_events WHERE user_id = $1", zee)
    assert len(rows) == 1
    assert rows[0]["topic"] == "auth.security_notice"
    assert json.loads(rows[0]["body"]) == {"event": "recovery_invite"}  # no token, no email


async def test_only_an_admin_can_issue(env: AuthEnv, zee: uuid.UUID) -> None:
    assert env.signin().status_code == 200
    response = env.post(f"/admin/users/{zee}/recovery-invite", {})
    assert response.status_code == 403
    env.client.cookies.clear()
    assert env.post(f"/admin/users/{zee}/recovery-invite", {}).status_code == 401
    assert (
        await env.db.fetchval("SELECT count(*) FROM invites WHERE recover_user_id = $1", zee) == 0
    )


async def test_an_unknown_user_is_404(env: AuthEnv, zee: uuid.UUID) -> None:
    assert as_admin(env, await env.admin_token(), uuid.uuid4()).status_code == 404


async def test_she_registers_a_new_passkey_and_gets_fresh_codes(
    env: AuthEnv, zee: uuid.UUID
) -> None:
    codes_query = "SELECT id FROM recovery_codes WHERE user_id = $1"
    old_codes = {row["id"] for row in await env.db.fetch(codes_query, zee)}
    assert len(old_codes) == 10
    token = as_admin(env, await env.admin_token(), zee).json()["token"]
    new_phone = SoftAuthenticator(RP_ID, ORIGIN)
    response = recover(env, token, new_phone)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user_id"] == str(zee)
    assert body["display_name"] == "Zee"
    assert len(set(body["recovery_codes"])) == 10
    assert response.headers["cache-control"] == "no-store"
    assert env.whoami().json()["user_id"] == str(zee)
    assert new_phone.passkeys[0].user_handle == zee.bytes
    assert (
        await env.db.fetchval("SELECT count(*) FROM webauthn_credentials WHERE user_id = $1", zee)
        == 2
    )
    # The old codes are gone; only the ten new ones remain.
    new_codes = {row["id"] for row in await env.db.fetch(codes_query, zee)}
    assert len(new_codes) == 10
    assert not new_codes & old_codes
    row = await env.invite_row(token)
    assert row["used_by"] == zee
    assert row["used_at"] == env.clock.now


async def test_the_invite_works_once(env: AuthEnv, zee: uuid.UUID) -> None:
    token = as_admin(env, await env.admin_token(), zee).json()["token"]
    assert recover(env, token, SoftAuthenticator(RP_ID, ORIGIN)).status_code == 201
    env.client.cookies.clear()
    assert env.post("/auth/recover/options", {"token": token}).status_code == 403


async def test_the_invite_expires_after_24_hours(env: AuthEnv, zee: uuid.UUID) -> None:
    token = as_admin(env, await env.admin_token(), zee).json()["token"]
    env.clock.advance(hours=24, seconds=1)
    assert env.post("/auth/recover/options", {"token": token}).status_code == 403


async def test_registration_and_recovery_tokens_do_not_cross(env: AuthEnv, zee: uuid.UUID) -> None:
    recovery = as_admin(env, await env.admin_token(), zee).json()["token"]
    body = {"token": recovery, "name": "X", "email": f"x{DOMAIN}"}
    assert env.post("/auth/register/options", body).status_code == 403
    assert env.post("/auth/invites/verify", {"token": recovery}).json() == {"valid": False}
    registration = await env.invite()
    assert env.post("/auth/recover/options", {"token": registration}).status_code == 403


async def test_a_challenge_from_one_invite_cannot_finish_another(
    env: AuthEnv, zee: uuid.UUID
) -> None:
    other = env.register(await env.invite(), name="O", email=f"other{DOMAIN}")
    other_id = uuid.UUID(other.json()["user_id"])
    env.client.cookies.clear()
    admin = await env.admin_token()
    hers = as_admin(env, admin, zee).json()["token"]
    theirs = as_admin(env, admin, other_id).json()["token"]
    options = env.post("/auth/recover/options", {"token": hers}).json()
    credential = SoftAuthenticator(RP_ID, ORIGIN).create(options)
    response = env.post("/auth/recover/verify", {"token": theirs, "credential": credential})
    assert response.status_code == 403
    assert (
        await env.db.fetchval("SELECT count(*) FROM webauthn_credentials WHERE user_id = $1", zee)
        == 1
    )


async def test_a_recovery_challenge_cannot_be_finished_as_a_recovery_code_passkey(
    env: AuthEnv, zee: uuid.UUID
) -> None:
    token = as_admin(env, await env.admin_token(), zee).json()["token"]
    options: dict[str, Any] = env.post("/auth/recover/options", {"token": token}).json()
    credential = SoftAuthenticator(RP_ID, ORIGIN).create(options)
    assert env.post("/auth/passkeys/verify", {"credential": credential}).status_code == 400
    assert env.whoami().status_code == 401


async def test_recovery_is_logged(env: AuthEnv, zee: uuid.UUID) -> None:
    token = as_admin(env, await env.admin_token(), zee).json()["token"]
    await env.db.execute("DELETE FROM auth_events")
    assert recover(env, token, SoftAuthenticator(RP_ID, ORIGIN)).status_code == 201
    rows = await env.db.fetch("SELECT kind, success, user_id FROM auth_events")
    assert [(r["kind"], r["success"], r["user_id"]) for r in rows] == [("recovery", True, zee)]


async def test_an_invalid_recovery_token_is_403(env: AuthEnv, zee: uuid.UUID) -> None:
    response = env.client.post(
        "/api/v1/auth/recover/options",
        json={"token": "nope"},
        headers=HEADERS | {"CF-Connecting-IP": env.ip},
    )
    assert response.status_code == 403


# ---------- review follow-ups (CR-020, CR-022, security) ----------


async def test_issuing_needs_the_admins_recent_auth(env: AuthEnv, zee: uuid.UUID) -> None:
    admin = await env.admin_token()
    env.clock.advance(minutes=5)
    response = as_admin(env, admin, zee)
    assert response.status_code == 403
    assert response.json()["detail"] == "Confirm it's you to continue."
    assert (
        await env.db.fetchval("SELECT count(*) FROM invites WHERE recover_user_id = $1", zee) == 0
    )


async def test_a_new_invite_revokes_the_earlier_one(env: AuthEnv, zee: uuid.UUID) -> None:
    admin = await env.admin_token()
    first = as_admin(env, admin, zee).json()["token"]
    second = as_admin(env, admin, zee).json()["token"]
    assert env.post("/auth/recover/options", {"token": first}).status_code == 403
    assert env.post("/auth/recover/options", {"token": second}).status_code == 200


async def test_issuing_is_audited_exactly_once_and_spares_the_admin(
    env: AuthEnv, zee: uuid.UUID
) -> None:
    admin = await env.admin_token()
    assert as_admin(env, admin, zee).status_code == 201
    assert (
        await env.db.fetchval("SELECT count(*) FROM audit_log WHERE target_user_id = $1", zee) == 1
    )
    env.use_session(admin)
    assert env.whoami().status_code == 200  # only her sessions were revoked


@pytest.mark.parametrize("who", ["her", "nobody"])
async def test_a_refused_request_changes_nothing(env: AuthEnv, zee: uuid.UUID, who: str) -> None:
    assert env.signin().status_code == 200
    hers = env.session_token()
    if who == "her":  # not an admin
        response = env.post(f"/admin/users/{zee}/recovery-invite", {})
        assert response.status_code == 403
    else:
        env.client.cookies.clear()
        assert env.post(f"/admin/users/{zee}/recovery-invite", {}).status_code == 401
    assert (
        await env.db.fetchval("SELECT count(*) FROM audit_log WHERE target_user_id = $1", zee) == 0
    )
    assert await env.db.fetchval("SELECT count(*) FROM outbox_events WHERE user_id = $1", zee) == 0
    env.use_session(hers)
    assert env.whoami().status_code == 200


async def test_an_unknown_user_changes_nothing(env: AuthEnv, zee: uuid.UUID) -> None:
    nobody = uuid.uuid4()
    assert as_admin(env, await env.admin_token(), nobody).status_code == 404
    count = "SELECT count(*) FROM audit_log WHERE target_user_id = $1"
    assert await env.db.fetchval(count, nobody) == 0


async def test_old_codes_stop_working_and_the_new_passkey_signs_in(env: AuthEnv) -> None:
    registered = env.register(await env.invite())
    zee = uuid.UUID(registered.json()["user_id"])
    old_codes = registered.json()["recovery_codes"]
    env.client.cookies.clear()
    token = as_admin(env, await env.admin_token(), zee).json()["token"]
    new_phone = SoftAuthenticator(RP_ID, ORIGIN)
    assert recover(env, token, new_phone).status_code == 201
    env.client.cookies.clear()
    body = {"email": EMAIL, "code": old_codes[0]}
    assert env.post("/auth/signin/recovery", body).status_code == 401
    env.authenticator = new_phone
    assert env.signin().status_code == 200


async def test_two_recoveries_in_flight_on_one_invite_add_one_passkey(
    env: AuthEnv, zee: uuid.UUID
) -> None:
    token = as_admin(env, await env.admin_token(), zee).json()["token"]
    first = env.post("/auth/recover/options", {"token": token}).json()
    second = env.post("/auth/recover/options", {"token": token}).json()
    phone = SoftAuthenticator(RP_ID, ORIGIN)
    body = {"token": token, "credential": phone.create(first)}
    assert env.post("/auth/recover/verify", body).status_code == 201
    env.client.cookies.clear()
    late = {"token": token, "credential": phone.create(second)}
    assert env.post("/auth/recover/verify", late).status_code == 403
    count = "SELECT count(*) FROM webauthn_credentials WHERE user_id = $1"
    assert await env.db.fetchval(count, zee) == 2


async def test_options_fetched_in_time_do_not_outlive_the_invite(
    env: AuthEnv, zee: uuid.UUID
) -> None:
    token = as_admin(env, await env.admin_token(), zee).json()["token"]
    env.clock.advance(hours=23, minutes=59, seconds=59)
    options = env.post("/auth/recover/options", {"token": token})
    assert options.status_code == 200  # still valid one second before 24 h
    env.clock.advance(seconds=2)
    credential = SoftAuthenticator(RP_ID, ORIGIN).create(options.json())
    response = env.post("/auth/recover/verify", {"token": token, "credential": credential})
    assert response.status_code == 403


async def test_issuing_spends_her_pending_challenges(env: AuthEnv, zee: uuid.UUID) -> None:
    """A passkey-add challenge her (now revoked) session asked for cannot be finished without a
    cookie afterwards, so it cannot mint a new session."""
    assert env.signin().status_code == 200
    options = env.post("/auth/passkeys/options", {}).json()
    env.client.cookies.clear()
    assert as_admin(env, await env.admin_token(), zee).status_code == 201
    credential = env.authenticator.create(options)
    assert env.post("/auth/passkeys/verify", {"credential": credential}).status_code == 400
    assert env.whoami().status_code == 401


async def test_admin_writes_need_their_connection(env: AuthEnv, zee: uuid.UUID) -> None:
    """CR-022: without the lifeos_admin connection, admin writes are unavailable (503)."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.platform.clock import utc_now

    settings = env.app.state.settings.model_copy(update={"database_admin_write_url": None})
    other = create_app(settings)
    other.dependency_overrides[utc_now] = env.clock
    admin = await env.admin_token()
    with TestClient(other, base_url=ORIGIN) as client:
        client.cookies.set("lo_session", admin, domain=RP_ID)
        response = client.post(
            f"/api/v1/admin/users/{zee}/recovery-invite", json={}, headers=HEADERS
        )
    assert response.status_code == 503
