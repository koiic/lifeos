"""API tests for health profile, cycle history, and cycle exclusions.

Spec sections: 9.2, CYC-1, CYC-5, MOD-1, MOD-2.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from tests.auth.conftest import DOMAIN, HEADERS, AuthEnv

pytestmark = pytest.mark.integration

PROFILE_URL = "/api/v1/health/profile"
CYCLE_URL = "/api/v1/health/cycle"
CYCLES_URL = "/api/v1/health/cycles"
EXCLUSIONS_URL = "/api/v1/health/cycles/exclusions"
CONFIRM_URL = "/api/v1/health/period-starts/confirm"
DAILY_LOGS = "/api/v1/daily-logs"


async def register_user(env: AuthEnv, email: str = f"zee{DOMAIN}", name: str = "Zee") -> uuid.UUID:
    response = env.register(await env.invite(email), name=name, email=email)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["user_id"])


@pytest.mark.req("MOD-1", "MOD-2")
async def test_health_profile_get_and_put_endpoints(env: AuthEnv) -> None:
    """Spec 9.2, MOD-1, MOD-2: GET and PUT /health/profile."""
    user_id = await register_user(env)

    # 1. Default profile
    resp = env.client.get(PROFILE_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "standard"
    assert data["usual_cycle_length"] is None
    assert data["usual_period_length"] is None
    assert data["last_period_hint"] is None
    assert data["mode_started_on"] is None

    # 2. Update profile with usual lengths
    put_resp = env.client.put(
        PROFILE_URL,
        json={
            "usual_cycle_length": 28,
            "usual_period_length": 5,
            "last_period_hint": "2026-09-15",
        },
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert put_resp.status_code == 200, put_resp.text
    put_data = put_resp.json()
    assert put_data["usual_cycle_length"] == 28
    assert put_data["usual_period_length"] == 5
    assert put_data["last_period_hint"] == "2026-09-15"

    # 3. Switching mode records mode_started_on automatically
    mode_resp = env.client.put(
        PROFILE_URL,
        json={"mode": "postpartum"},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert mode_resp.status_code == 200, mode_resp.text
    mode_data = mode_resp.json()
    assert mode_data["mode"] == "postpartum"
    assert mode_data["mode_started_on"] is not None

    # Outbox event emitted
    events = await env.db.fetch(
        "SELECT topic FROM outbox_events WHERE user_id = $1 AND topic = $2",
        user_id,
        "health_profile.changed",
    )
    assert len(events) >= 1


@pytest.mark.req("CYC-5")
async def test_get_health_cycles_history_endpoint(env: AuthEnv) -> None:
    """Spec 9.2, CYC-5: GET /health/cycles returns cycle history with exclusion reasons."""
    await register_user(env)

    # Empty initially
    resp = env.client.get(CYCLES_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    # Add 2 cycles: starts 2026-08-01 and 2026-08-29
    for s in (date(2026, 8, 1), date(2026, 8, 29)):
        for offset in range(5):
            d = s + timedelta(days=offset)
            env.client.put(
                f"{DAILY_LOGS}/{d.isoformat()}",
                json={
                    "flow": "medium",
                    "client_updated_at": datetime(
                        d.year, d.month, d.day, 12, 0, tzinfo=UTC
                    ).isoformat(),
                },
                headers={"CF-Connecting-IP": env.ip, **HEADERS},
            )

    resp2 = env.client.get(CYCLES_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp2.status_code == 200
    cycles = resp2.json()
    assert len(cycles) == 2
    # Cycle 1: complete, length 28
    assert cycles[0]["seq"] == 1
    assert cycles[0]["start_date"] == "2026-08-01"
    assert cycles[0]["end_date"] == "2026-08-28"
    assert cycles[0]["length_days"] == 28
    assert cycles[0]["is_complete"] is True
    assert cycles[0]["excluded"] is False
    # Cycle 2: incomplete
    assert cycles[1]["seq"] == 2
    assert cycles[1]["start_date"] == "2026-08-29"
    assert cycles[1]["is_complete"] is False


@pytest.mark.req("CYC-1")
async def test_get_health_cycle_empty_state(env: AuthEnv) -> None:
    """Spec 8.4, 9.3, CYC-1: GET /health/cycle when no data is logged."""
    await register_user(env)
    resp = env.client.get(CYCLE_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cycle_day"] is None
    assert data["latest_start"] is None
    assert data["state"] == "no_data"
    assert data["phase"] is None
    assert data["prediction"] is not None
    assert data["prediction"]["confidence"] == "none"
    assert data["prediction"]["suppressed_reason"] == "no_data"
