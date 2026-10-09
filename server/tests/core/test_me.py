"""T09: `GET /me` (spec 9.2 "Bootstraps the client"), `PATCH /me`, `PATCH /me/settings` and
`POST /me/consent` (CR-030), with `updated_at` as the version (CR-004: `ETag`/`If-Match`)."""

import json
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest

from app.platform.crypto import aad, encrypt, load_keyring, unwrap_dek
from tests.auth.conftest import DOMAIN, HEADERS, AuthEnv

pytestmark = pytest.mark.integration

ME = "/api/v1/me"
SETTINGS = "/api/v1/me/settings"
CONSENT = "/api/v1/me/consent"

DEFAULT_SETTINGS = {
    "theme": "system",
    "week_start": 1,
    "time_format": "24h",
    "temp_unit": "C",
    "checkin_time": "20:00",
    "quiet_start": "22:00",
    "quiet_end": "07:00",
    "notif_prefs": {
        "checkin": True,
        "period_due": True,
        "late_period": True,
        "medication": True,
        "appointment": True,
        "task": True,
    },
    "discreet_notifications": False,
    "optional_fields": {"bbt": False, "discharge": False, "intimacy": False},
    "app_lock_enabled": False,
    "app_lock_timeout_s": 300,
    "appointment_reminder_defaults": [
        {"type": "day_before_at", "time": "19:00"},
        {"type": "minutes_before", "minutes": 60},
    ],
    "onboarding_completed_at": None,
}


async def zee(env: AuthEnv, email: str = f"zee{DOMAIN}", name: str = "Zee") -> uuid.UUID:
    response = env.register(await env.invite(email), name=name, email=email)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["user_id"])


def get_me(env: AuthEnv, device_timezone: str | None = None) -> httpx.Response:
    headers = {"CF-Connecting-IP": env.ip}
    if device_timezone is not None:
        headers["X-Timezone"] = device_timezone
    return env.client.get(ME, headers=headers)


def patch(env: AuthEnv, path: str, body: object, version: str | None) -> httpx.Response:
    headers = HEADERS | {"CF-Connecting-IP": env.ip}
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    return env.client.patch(path, json=body, headers=headers)


def versions(env: AuthEnv) -> tuple[str, str]:
    body = get_me(env).json()
    return body["profile"]["version"], body["settings"]["version"]


# ---------- signed in only (plan 4.6) ----------


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", ME), ("PATCH", ME), ("PATCH", SETTINGS), ("POST", CONSENT)],
)
def test_signed_out_gets_401(env: AuthEnv, method: str, path: str) -> None:
    response = env.client.request(
        method, path, json={}, headers=HEADERS | {"CF-Connecting-IP": env.ip}
    )
    assert response.status_code == 401


# ---------- GET /me ----------


@pytest.mark.req("SET-1")
@pytest.mark.req("SET-2")
async def test_me_bootstraps_the_client_with_profile_settings_and_defaults(env: AuthEnv) -> None:
    user_id = await zee(env)
    response = get_me(env)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {
        "profile",
        "settings",
        "consent",
        "health_mode",
        "device_timezone",
        "timezone_differs",
    }  # CR-030: no feature flags
    profile = body["profile"]
    assert {k: v for k, v in profile.items() if k != "version"} == {
        "id": str(user_id),
        "email": f"zee{DOMAIN}",
        "display_name": "Zee",
        "role": "user",
        "timezone": "Europe/London",
        "locale": "en-GB",
    }
    settings = body["settings"]
    assert {k: v for k, v in settings.items() if k != "version"} == DEFAULT_SETTINGS
    assert body["consent"] == {"current_version": "1", "version": None, "given_at": None}
    assert body["health_mode"] == "standard"  # MOD-1, until the setup wizard sets one
    assert (body["device_timezone"], body["timezone_differs"]) == (None, False)


async def test_versions_are_the_rows_updated_at(env: AuthEnv) -> None:
    """CR-004: the version is `updated_at` as RFC 3339 with microseconds."""
    user_id = await zee(env)
    profile_version, settings_version = versions(env)
    row = await env.db.fetchrow(
        "SELECT u.updated_at AS p, s.updated_at AS s FROM users u"
        " JOIN user_settings s ON s.user_id = u.id WHERE u.id = $1",
        user_id,
    )
    assert row is not None
    assert profile_version == row["p"].isoformat(timespec="microseconds")
    assert settings_version == row["s"].isoformat(timespec="microseconds")


async def test_me_never_shows_keys_or_the_pin(env: AuthEnv) -> None:
    await zee(env)
    assert env.put("/auth/app-lock", {"pin": "482913", "timeout_s": 600}).status_code == 204
    text = get_me(env).text
    for secret in ("dek", "kek", "pin_hash", "app_lock_pin", "482913", "argon2"):
        assert secret not in text
    settings = get_me(env).json()["settings"]
    assert (settings["app_lock_enabled"], settings["app_lock_timeout_s"]) == (True, 600)


@pytest.mark.req("SET-1")
@pytest.mark.parametrize(
    ("device", "expected", "differs"),
    [
        ("Africa/Lagos", "Africa/Lagos", True),
        ("Europe/London", "Europe/London", False),
        ("Mars/Olympus_Mons", None, False),  # not an IANA zone
        ("", None, False),
    ],
)
async def test_the_device_timezone_is_compared_with_hers(
    env: AuthEnv, device: str, expected: str | None, differs: bool
) -> None:
    """CR-030 (11.7): the client sends X-Timezone; /me says whether it differs from her profile."""
    await zee(env)
    body = get_me(env, device).json()
    assert (body["device_timezone"], body["timezone_differs"]) == (expected, differs)


async def test_her_health_mode_comes_from_her_health_profile(env: AuthEnv) -> None:
    user_id = await zee(env)
    keyring = load_keyring(env.app.state.settings)
    user = await env.db.fetchrow(
        "SELECT dek_wrapped, kek_version FROM users WHERE id = $1", user_id
    )
    assert user is not None
    dek = unwrap_dek(keyring, user["kek_version"], user["dek_wrapped"], user_id)
    payload = json.dumps({"v": 1, "mode": "postpartum", "mode_started_on": "2026-09-01"}).encode()
    await env.db.execute(
        "INSERT INTO health_profile (user_id, payload_enc) VALUES ($1, $2)",
        user_id,
        encrypt(dek, payload, aad("health_profile", "payload_enc", user_id, user_id)),
    )
    assert get_me(env).json()["health_mode"] == "postpartum"


# ---------- PATCH /me (SET-1) ----------


@pytest.mark.req("SET-1")
async def test_she_changes_her_name_and_timezone(env: AuthEnv) -> None:
    user_id = await zee(env)
    version, _ = versions(env)
    response = patch(
        env, ME, {"display_name": "  Zee\u0007 Á ", "timezone": "Africa/Lagos"}, version
    )
    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["display_name"] == "Zee Á"  # 9.4: trimmed, controls stripped, NFC
    assert profile["timezone"] == "Africa/Lagos"
    assert profile["version"] != version
    assert response.headers["etag"] == f'"{profile["version"]}"'
    row = await env.db.fetchrow("SELECT display_name, timezone FROM users WHERE id = $1", user_id)
    assert row is not None
    assert (row["display_name"], row["timezone"]) == ("Zee Á", "Africa/Lagos")
    assert get_me(env).json()["profile"] == profile


@pytest.mark.req("SET-1")
@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"timezone": "Mars/Olympus_Mons"}, "timezone"),
        ({"timezone": ""}, "timezone"),
        ({"display_name": "   "}, "display_name"),
        ({"display_name": "x" * 101}, "display_name"),
        ({"display_name": "\u0007"}, "display_name"),  # blank once cleaned
        ({"email": "other@auth.test"}, "email"),  # not editable here
        ({"role": "admin"}, "role"),
    ],
)
async def test_invalid_profile_changes_are_refused(
    env: AuthEnv, body: dict[str, Any], field: str
) -> None:
    await zee(env)
    version, _ = versions(env)
    response = patch(env, ME, body, version)
    assert response.status_code == 422, response.text
    assert field in [e["field"] for e in response.json()["errors"]]
    assert get_me(env).json()["profile"]["version"] == version  # nothing changed


async def test_an_empty_change_is_refused(env: AuthEnv) -> None:
    await zee(env)
    version, settings_version = versions(env)
    assert patch(env, ME, {}, version).status_code == 422
    assert patch(env, SETTINGS, {}, settings_version).status_code == 422
    assert versions(env) == (version, settings_version)


@pytest.mark.parametrize("path", [ME, SETTINGS])
async def test_a_change_without_if_match_is_refused(env: AuthEnv, path: str) -> None:
    """CR-004: PATCH sends the version it changes; without it → 428 Precondition Required."""
    await zee(env)
    body = {"display_name": "Z"} if path == ME else {"theme": "dark"}
    response = patch(env, path, body, None)
    assert response.status_code == 428
    assert response.headers["content-type"] == "application/problem+json"


async def test_a_stale_profile_version_is_a_conflict_with_the_current_profile(
    env: AuthEnv,
) -> None:
    """9.1: mismatch → 409 with the current resource (and its version as the ETag)."""
    await zee(env)
    old, _ = versions(env)
    assert patch(env, ME, {"display_name": "Zee B"}, old).status_code == 200
    response = patch(env, ME, {"display_name": "Zee C"}, old)
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    current = response.json()["current"]
    assert current["display_name"] == "Zee B"
    assert response.headers["etag"] == f'"{current["version"]}"'
    assert get_me(env).json()["profile"]["display_name"] == "Zee B"


async def test_the_version_may_be_sent_without_quotes(env: AuthEnv) -> None:
    await zee(env)
    version, _ = versions(env)
    response = env.client.patch(
        ME,
        json={"display_name": "Zee B"},
        headers=HEADERS | {"CF-Connecting-IP": env.ip, "If-Match": version},
    )
    assert response.status_code == 200, response.text


# ---------- PATCH /me/settings (SET-1, SET-2, SET-3, SET-5) ----------


@pytest.mark.req("SET-1")
@pytest.mark.req("SET-2")
async def test_she_changes_theme_week_start_and_units(env: AuthEnv) -> None:
    user_id = await zee(env)
    _, version = versions(env)
    response = patch(env, SETTINGS, {"theme": "dark", "week_start": 7, "temp_unit": "F"}, version)
    assert response.status_code == 200, response.text
    settings = response.json()
    assert (settings["theme"], settings["week_start"], settings["temp_unit"]) == ("dark", 7, "F")
    assert response.headers["etag"] == f'"{settings["version"]}"'
    row = await env.db.fetchrow(
        "SELECT theme, week_start, temp_unit FROM user_settings WHERE user_id = $1", user_id
    )
    assert row is not None
    assert tuple(row) == ("dark", 7, "F")
    assert get_me(env).json()["settings"] == settings


@pytest.mark.req("SET-2")
@pytest.mark.parametrize("theme", ["system", "light", "dark"])
async def test_each_theme_can_be_chosen(env: AuthEnv, theme: str) -> None:
    await zee(env)
    _, version = versions(env)
    response = patch(env, SETTINGS, {"theme": theme}, version)
    assert response.status_code == 200, response.text
    assert response.json()["theme"] == theme


async def test_notification_preferences_quiet_hours_and_discreet_mode(env: AuthEnv) -> None:
    """SET-3, SET-5: one type off keeps the others; quiet hours and check-in time as HH:MM."""
    await zee(env)
    _, version = versions(env)
    response = patch(
        env,
        SETTINGS,
        {
            "notif_prefs": {"medication": False},
            "optional_fields": {"bbt": True},
            "quiet_start": "23:30",
            "quiet_end": "06:45",
            "checkin_time": "21:15",
            "discreet_notifications": True,
        },
        version,
    )
    assert response.status_code == 200, response.text
    settings = response.json()
    assert settings["notif_prefs"] == DEFAULT_SETTINGS["notif_prefs"] | {"medication": False}
    assert settings["optional_fields"] == {"bbt": True, "discharge": False, "intimacy": False}
    assert (settings["quiet_start"], settings["quiet_end"]) == ("23:30", "06:45")
    assert settings["checkin_time"] == "21:15"
    assert settings["discreet_notifications"] is True


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"theme": "sepia"}, "theme"),
        ({"week_start": 0}, "week_start"),
        ({"week_start": 8}, "week_start"),
        ({"week_start": "7"}, "week_start"),
        ({"week_start": True}, "week_start"),
        ({"temp_unit": "K"}, "temp_unit"),
        ({"checkin_time": "24:00"}, "checkin_time"),
        ({"checkin_time": "8:00"}, "checkin_time"),
        ({"checkin_time": "08:00:00"}, "checkin_time"),
        ({"quiet_start": "22:00", "quiet_end": "22:00"}, "quiet_end"),
        ({"notif_prefs": {"marketing": True}}, "notif_prefs.marketing"),
        ({"notif_prefs": {"checkin": "yes"}}, "notif_prefs.checkin"),
        ({"optional_fields": {"weight": True}}, "optional_fields.weight"),
        ({"discreet_notifications": "on"}, "discreet_notifications"),
        ({"app_lock_timeout_s": 60}, "app_lock_timeout_s"),  # /auth/app-lock sets it
        ({"time_format": "12h"}, "time_format"),  # not a setting she can change
        ({"health_consent_version": "1"}, "health_consent_version"),  # POST /me/consent
    ],
)
async def test_invalid_settings_are_refused(env: AuthEnv, body: dict[str, Any], field: str) -> None:
    await zee(env)
    _, version = versions(env)
    response = patch(env, SETTINGS, body, version)
    assert response.status_code == 422, response.text
    assert field in [e["field"] for e in response.json()["errors"]]
    assert get_me(env).json()["settings"]["version"] == version


async def test_quiet_hours_must_not_be_equal_after_a_partial_change(env: AuthEnv) -> None:
    """Only quiet_end sent, equal to the saved quiet_start (22:00): refused."""
    await zee(env)
    _, version = versions(env)
    response = patch(env, SETTINGS, {"quiet_end": "22:00"}, version)
    assert response.status_code == 422
    assert "quiet_end" in [e["field"] for e in response.json()["errors"]]


async def test_a_stale_settings_version_is_a_conflict_with_the_current_settings(
    env: AuthEnv,
) -> None:
    await zee(env)
    _, old = versions(env)
    assert patch(env, SETTINGS, {"theme": "dark"}, old).status_code == 200
    response = patch(env, SETTINGS, {"theme": "light"}, old)
    assert response.status_code == 409
    current = response.json()["current"]
    assert current["theme"] == "dark"
    assert response.headers["etag"] == f'"{current["version"]}"'


# ---------- reminders follow her settings (10.2) ----------


async def outbox(env: AuthEnv, user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await env.db.fetch(
        "SELECT topic, body FROM outbox_events WHERE user_id = $1 AND topic = 'settings.changed'"
        " ORDER BY id",
        user_id,
    )
    return [json.loads(row["body"]) for row in rows]


async def test_changes_that_move_reminders_publish_settings_changed(env: AuthEnv) -> None:
    """10.2: "A change of timezone, check-in time, quiet hours or notification preferences
    regenerates all future reminders" — announced as `settings.changed` (7.2 topics)."""
    user_id = await zee(env)
    profile_version, version = versions(env)
    assert patch(env, SETTINGS, {"theme": "dark", "week_start": 7}, version).status_code == 200
    assert patch(env, ME, {"display_name": "Zee B"}, profile_version).status_code == 200
    assert await outbox(env, user_id) == []  # nothing a reminder depends on
    profile_version, version = versions(env)
    body = {"checkin_time": "21:00", "notif_prefs": {"task": False}}
    assert patch(env, SETTINGS, body, version).status_code == 200
    _, version = versions(env)
    assert patch(env, SETTINGS, {"quiet_start": "23:00"}, version).status_code == 200
    _, version = versions(env)
    assert patch(env, SETTINGS, {"quiet_end": "06:00"}, version).status_code == 200
    assert patch(env, ME, {"timezone": "Africa/Lagos"}, profile_version).status_code == 200
    assert await outbox(env, user_id) == [
        {"fields": ["checkin_time", "notif_prefs"]},
        {"fields": ["quiet_start"]},
        {"fields": ["quiet_end"]},
        {"fields": ["timezone"]},
    ]


async def test_saving_an_unchanged_value_publishes_nothing(env: AuthEnv) -> None:
    user_id = await zee(env)
    _, version = versions(env)
    for body in ({"checkin_time": "20:00"}, {"notif_prefs": {"medication": True}}):
        response = patch(env, SETTINGS, body, version)
        assert response.status_code == 200
        assert response.json()["version"] == version  # nothing written
    assert await outbox(env, user_id) == []


# ---------- consent (12.6, CR-030) ----------


async def test_consent_stores_time_and_version_and_is_audited(env: AuthEnv) -> None:
    user_id = await zee(env)
    response = env.post("/me/consent", {"version": "1"})
    assert response.status_code == 200, response.text
    given_at = env.clock.now.isoformat().replace("+00:00", "Z")
    assert response.json() == {"current_version": "1", "version": "1", "given_at": given_at}
    row = await env.db.fetchrow(
        "SELECT health_consent_at, health_consent_version FROM user_settings WHERE user_id = $1",
        user_id,
    )
    assert row is not None
    assert (row["health_consent_at"], row["health_consent_version"]) == (env.clock.now, "1")
    audit = await env.db.fetch(
        "SELECT actor_user_id, actor_role, action, target_user_id, ip_hash FROM audit_log"
        " WHERE action = 'user.health_consent' AND actor_user_id = $1",
        user_id,
    )
    assert [tuple(a) for a in audit] == [
        (user_id, "user", "user.health_consent", user_id, env.ip_hash())
    ]
    assert get_me(env).json()["consent"] == response.json()


@pytest.mark.parametrize("version", ["0", "2", "", "1.0"])
async def test_consent_to_another_version_is_refused(env: AuthEnv, version: str) -> None:
    user_id = await zee(env)
    response = env.post("/me/consent", {"version": version})
    assert response.status_code == 422
    stored = await env.db.fetchval(
        "SELECT health_consent_at FROM user_settings WHERE user_id = $1", user_id
    )
    assert stored is None
    audited = await env.db.fetchval(
        "SELECT count(*) FROM audit_log WHERE actor_user_id = $1", user_id
    )
    assert audited == 0


async def test_consenting_again_keeps_the_first_time(env: AuthEnv) -> None:
    user_id = await zee(env)
    first = env.post("/me/consent", {"version": "1"}).json()
    env.clock.advance(days=1)
    again = env.post("/me/consent", {"version": "1"})
    assert again.status_code == 200
    assert again.json() == first
    stored = await env.db.fetchval(
        "SELECT health_consent_at FROM user_settings WHERE user_id = $1", user_id
    )
    assert stored == env.clock.now - timedelta(days=1)
    count = await env.db.fetchval(
        "SELECT count(*) FROM audit_log WHERE action = 'user.health_consent'"
        " AND actor_user_id = $1",
        user_id,
    )
    assert count == 1


# ---------- other users (plan 4.6) ----------


async def test_each_user_sees_and_changes_only_her_own(env: AuthEnv) -> None:
    first = await zee(env)
    env.client.cookies.clear()
    await zee(env, f"other{DOMAIN}", name="Other")
    body = get_me(env).json()
    assert body["profile"]["email"] == f"other{DOMAIN}"
    profile_version, settings_version = body["profile"]["version"], body["settings"]["version"]
    assert patch(env, ME, {"display_name": "Changed"}, profile_version).status_code == 200
    assert patch(env, SETTINGS, {"theme": "dark"}, settings_version).status_code == 200
    assert env.post("/me/consent", {"version": "1"}).status_code == 200
    row = await env.db.fetchrow(
        "SELECT u.display_name, s.theme, s.health_consent_at FROM users u"
        " JOIN user_settings s ON s.user_id = u.id WHERE u.id = $1",
        first,
    )
    assert row is not None
    assert tuple(row) == ("Zee", "system", None)


async def test_another_users_version_cannot_be_used(env: AuthEnv) -> None:
    """A version is checked against her own row only."""
    await zee(env)
    her_version, _ = versions(env)
    env.client.cookies.clear()
    await zee(env, f"other{DOMAIN}", name="Other")
    response = patch(env, ME, {"display_name": "Changed"}, her_version)
    assert response.status_code == 409
    assert response.json()["current"]["email"] == f"other{DOMAIN}"


async def test_an_unreadable_version_is_a_conflict(env: AuthEnv) -> None:
    """A version that is not a timestamp can never be current: 409, not 428."""
    await zee(env)
    response = patch(env, ME, {"display_name": "Zee B"}, "yesterday")
    assert response.status_code == 409
    assert response.json()["current"]["display_name"] == "Zee"


@pytest.mark.parametrize(("path", "body"), [(ME, {"timezone": None}), (SETTINGS, {"theme": None})])
async def test_a_field_cannot_be_set_to_null(env: AuthEnv, path: str, body: object) -> None:
    await zee(env)
    profile_version, settings_version = versions(env)
    response = patch(env, path, body, profile_version if path == ME else settings_version)
    assert response.status_code == 422
    assert versions(env) == (profile_version, settings_version)


async def test_an_unchanged_profile_keeps_its_version(env: AuthEnv) -> None:
    user_id = await zee(env)
    version, _ = versions(env)
    response = patch(env, ME, {"timezone": "Europe/London"}, version)
    assert response.status_code == 200
    assert response.json()["version"] == version
    assert await outbox(env, user_id) == []


async def test_strings_are_trimmed_before_they_are_checked(env: AuthEnv) -> None:
    """9.4 "Strings: Trimmed; control characters stripped; Unicode NFC" — every string."""
    user_id = await zee(env)
    version, _ = versions(env)
    response = patch(env, ME, {"timezone": " Africa/Lagos "}, version)
    assert response.status_code == 200, response.text
    assert response.json()["timezone"] == "Africa/Lagos"
    consent = env.post("/me/consent", {"version": " 1 "})
    assert consent.status_code == 200, consent.text
    stored = await env.db.fetchval(
        "SELECT health_consent_version FROM user_settings WHERE user_id = $1", user_id
    )
    assert stored == "1"


@pytest.mark.parametrize("name", ["x" * 100, " " + "x" * 100 + " "])
async def test_a_100_character_name_is_accepted(env: AuthEnv, name: str) -> None:
    await zee(env)
    version, _ = versions(env)
    response = patch(env, ME, {"display_name": name}, version)
    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "x" * 100
