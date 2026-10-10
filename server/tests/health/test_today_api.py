"""Integration tests for Today API (spec 9.3, TOD-3, TOD-5).

Tests:
- GET /api/v1/today returns 401 when unauthenticated.
- GET /api/v1/today returns greeting, checkin state (done=false, log=null), and streak (0).
- After saving a daily log: checkin.done is true, checkin.log has data, streak is 1.
- Streak increments across multiple consecutive logged days.
- GET /api/v1/today?date=YYYY-MM-DD returns status for the requested day.
- Rejects future date with 422.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from tests.auth.conftest import DOMAIN, HEADERS, AuthEnv

pytestmark = pytest.mark.integration

TODAY = "/api/v1/today"
LOGS = "/api/v1/daily-logs"


async def register_user(env: AuthEnv, email: str = f"zee{DOMAIN}", name: str = "Zee") -> uuid.UUID:
    response = env.register(await env.invite(email), name=name, email=email)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["user_id"])


@pytest.mark.req("TOD-3")
async def test_today_unauthenticated(env: AuthEnv) -> None:
    res = env.client.get(TODAY)
    assert res.status_code == 401


@pytest.mark.req("TOD-3")
async def test_today_initial_state_not_checked_in(env: AuthEnv) -> None:
    await register_user(env)
    res = env.client.get(TODAY)
    assert res.status_code == 200, res.text
    data = res.json()

    assert "date" in data
    assert data["greeting"] in ("morning", "afternoon", "evening", "night")
    assert data["checkin"] == {"done": False, "log": None}
    assert data["streak"] == 0
    assert data["items"] == []


@pytest.mark.req("TOD-3")
@pytest.mark.req("TOD-5")
async def test_today_after_checkin_shows_completed_and_streak(env: AuthEnv) -> None:
    await register_user(env)

    # 1. Check initial state
    res = env.client.get(TODAY)
    assert res.status_code == 200
    today_date = res.json()["date"]

    # 2. Check in for today
    log_body = {
        "mood": 4,
        "energy": 3,
        "sleep_hours": 7.5,
        "flow": "none",
        "symptom_ids": [],
        "note": "Feeling good!",
        "client_updated_at": datetime.now(UTC).isoformat(),
    }
    put_res = env.client.put(f"{LOGS}/{today_date}", json=log_body, headers=HEADERS)
    assert put_res.status_code == 200, put_res.text

    # 3. Check Today response again
    res2 = env.client.get(TODAY)
    assert res2.status_code == 200
    data2 = res2.json()

    assert data2["checkin"]["done"] is True
    assert data2["checkin"]["log"] is not None
    assert data2["checkin"]["log"]["mood"] == 4
    assert data2["checkin"]["log"]["energy"] == 3
    assert data2["checkin"]["log"]["sleep_hours"] == 7.5
    assert data2["checkin"]["log"]["note"] == "Feeling good!"
    assert data2["streak"] == 1


@pytest.mark.req("TOD-5")
async def test_today_streak_consecutive_days(env: AuthEnv) -> None:
    await register_user(env)

    res = env.client.get(TODAY)
    today = date.fromisoformat(res.json()["date"])

    # Log yesterday and 2 days ago
    day_minus_1 = (today - timedelta(days=1)).isoformat()
    day_minus_2 = (today - timedelta(days=2)).isoformat()

    now_iso = datetime.now(UTC).isoformat()
    for d in (day_minus_2, day_minus_1):
        env.client.put(
            f"{LOGS}/{d}",
            json={
                "mood": 3,
                "energy": 3,
                "flow": "none",
                "symptom_ids": [],
                "client_updated_at": now_iso,
            },
            headers=HEADERS,
        )

    # Today is not logged yet, but streak of 2 is preserved
    res_before = env.client.get(TODAY)
    assert res_before.json()["streak"] == 2
    assert res_before.json()["checkin"]["done"] is False

    # Now log today -> streak becomes 3!
    env.client.put(
        f"{LOGS}/{today.isoformat()}",
        json={
            "mood": 5,
            "energy": 4,
            "flow": "none",
            "symptom_ids": [],
            "client_updated_at": now_iso,
        },
        headers=HEADERS,
    )

    res_after = env.client.get(TODAY)
    assert res_after.json()["streak"] == 3
    assert res_after.json()["checkin"]["done"] is True


@pytest.mark.req("TOD-3")
async def test_today_specific_date_query_param(env: AuthEnv) -> None:
    await register_user(env)

    res = env.client.get(TODAY)
    today = date.fromisoformat(res.json()["date"])
    past_date = (today - timedelta(days=3)).isoformat()

    # Query past date without log
    res_past = env.client.get(f"{TODAY}?date={past_date}")
    assert res_past.status_code == 200
    assert res_past.json()["date"] == past_date
    assert res_past.json()["checkin"]["done"] is False

    # Reject future date
    future_date = (today + timedelta(days=1)).isoformat()
    res_future = env.client.get(f"{TODAY}?date={future_date}")
    assert res_future.status_code == 422
