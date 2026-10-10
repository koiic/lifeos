"""Integration tests for period start and end endpoints (PER-1, PER-4, spec 9.2)."""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.auth.conftest import DOMAIN, HEADERS, AuthEnv

PERIOD_START = "/api/v1/health/period/start"
PERIOD_END = "/api/v1/health/period/end"
DAILY_LOGS = "/api/v1/daily-logs"


async def register_user(env: AuthEnv, email: str = f"zee{DOMAIN}", name: str = "Zee") -> uuid.UUID:
    response = env.register(await env.invite(email), name=name, email=email)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["user_id"])


@pytest.mark.req("PER-1", "PER-4")
async def test_period_start_creates_log_with_medium_flow(env: AuthEnv) -> None:
    user_id = await register_user(env)
    target_date = "2026-10-06"

    resp = env.client.post(
        PERIOD_START,
        json={"date": target_date},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["date"] == target_date
    assert data["flow"] == "medium"
    assert data["rebuild"] == "queued"

    # Daily log exists with flow medium
    get_log = env.client.get(
        f"{DAILY_LOGS}/{target_date}",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert get_log.status_code == 200
    assert get_log.json()["flow"] == "medium"

    # Outbox event emitted
    events = await env.db.fetch(
        "SELECT topic FROM outbox_events WHERE user_id = $1 AND topic = $2",
        user_id,
        "daily_log.flow_changed",
    )
    assert len(events) == 1


@pytest.mark.req("PER-1")
async def test_period_start_preserves_existing_flow(env: AuthEnv) -> None:
    await register_user(env)
    target_date = "2026-10-06"
    now_utc = datetime(2026, 10, 6, 12, 0, tzinfo=UTC).isoformat()

    # Pre-existing log with Heavy flow
    env.client.put(
        f"{DAILY_LOGS}/{target_date}",
        json={"flow": "heavy", "mood": 4, "client_updated_at": now_utc},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )

    # Tap Period started
    resp = env.client.post(
        PERIOD_START,
        json={"date": target_date},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == target_date
    assert data["flow"] == "heavy"  # preserved, not downgraded
    assert data["rebuild"] == "not_needed"


@pytest.mark.req("PER-1")
async def test_period_start_updates_none_or_spotting(env: AuthEnv) -> None:
    await register_user(env)
    target_date = "2026-10-06"
    now_utc = datetime(2026, 10, 6, 12, 0, tzinfo=UTC).isoformat()

    # Existing log with spotting
    env.client.put(
        f"{DAILY_LOGS}/{target_date}",
        json={"flow": "spotting", "note": "Spotting note", "client_updated_at": now_utc},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )

    # Tap Period started
    resp = env.client.post(
        PERIOD_START,
        json={"date": target_date},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["flow"] == "medium"
    assert data["rebuild"] == "queued"

    # Note is preserved in daily log
    get_log = env.client.get(
        f"{DAILY_LOGS}/{target_date}",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert get_log.json()["note"] == "Spotting note"
    assert get_log.json()["flow"] == "medium"


@pytest.mark.req("PER-1")
async def test_period_start_rejects_future_date(env: AuthEnv) -> None:
    await register_user(env)
    now_london = datetime.now(ZoneInfo("Europe/London"))
    tomorrow = (now_london + timedelta(days=1)).date().isoformat()

    resp = env.client.post(
        PERIOD_START,
        json={"date": tomorrow},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp.status_code == 422


@pytest.mark.req("PER-1", "PER-4")
async def test_period_end_confirms_last_flow_day(env: AuthEnv) -> None:
    await register_user(env)
    # Log flow for 2026-10-01 through 2026-10-05
    for day in range(1, 6):
        d_str = f"2026-10-0{day}"
        env.client.put(
            f"{DAILY_LOGS}/{d_str}",
            json={
                "flow": "medium",
                "client_updated_at": datetime(2026, 10, day, 12, 0, tzinfo=UTC).isoformat(),
            },
            headers={"CF-Connecting-IP": env.ip, **HEADERS},
        )

    # Tap Period ended specifying 2026-10-03 as last flow day
    resp = env.client.post(
        PERIOD_END,
        json={"date": "2026-10-03"},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["date"] == "2026-10-03"
    assert data["flow"] == "medium"
    assert data["rebuild"] == "queued"

    # Days after 10-03 (10-04 and 10-05) have flow cleared to "none"
    log4 = env.client.get(f"{DAILY_LOGS}/2026-10-04", headers={"CF-Connecting-IP": env.ip})
    assert log4.json()["flow"] == "none"

    log5 = env.client.get(f"{DAILY_LOGS}/2026-10-05", headers={"CF-Connecting-IP": env.ip})
    assert log5.json()["flow"] == "none"

    # Day 10-03 still has medium flow
    log3 = env.client.get(f"{DAILY_LOGS}/2026-10-03", headers={"CF-Connecting-IP": env.ip})
    assert log3.json()["flow"] == "medium"


@pytest.mark.req("PER-1")
async def test_period_endpoints_require_auth(env: AuthEnv) -> None:
    # 401 without session
    assert (
        env.client.post(
            PERIOD_START,
            json={"date": "2026-10-06"},
            headers={"CF-Connecting-IP": env.ip, **HEADERS},
        ).status_code
        == 401
    )
    assert (
        env.client.post(
            PERIOD_END,
            json={"date": "2026-10-06"},
            headers={"CF-Connecting-IP": env.ip, **HEADERS},
        ).status_code
        == 401
    )
