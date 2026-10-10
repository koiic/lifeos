"""Integration tests for calendar month endpoint (CSC-3, spec 9.2)."""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.health.service import InvalidMonthError, parse_and_validate_month
from tests.auth.conftest import DOMAIN, HEADERS, AuthEnv

CALENDAR_URL = "/api/v1/health/calendar"
DAILY_LOGS = "/api/v1/daily-logs"


async def register_user(env: AuthEnv, email: str = f"zee{DOMAIN}", name: str = "Zee") -> uuid.UUID:
    response = env.register(await env.invite(email), name=name, email=email)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["user_id"])


@pytest.mark.req("CSC-3")
async def test_calendar_month_requires_auth(env: AuthEnv) -> None:
    resp = env.client.get(CALENDAR_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp.status_code == 401


@pytest.mark.req("CSC-3")
async def test_calendar_month_returns_full_month_days(env: AuthEnv) -> None:
    await register_user(env)
    resp = env.client.get(
        f"{CALENDAR_URL}?month=2026-10",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["month"] == "2026-10"
    days = data["days"]
    assert len(days) == 31
    assert days[0]["date"] == "2026-10-01"
    assert days[-1]["date"] == "2026-10-31"

    # All unlogged days have has_log=False, flow=None, and empty placeholders
    for day in days:
        assert day["has_log"] is False
        assert day["flow"] is None
        assert day["predicted"] is False
        assert day["fertile"] is False
        assert day["events"] == []
        assert day["doses"] == []


@pytest.mark.req("CSC-3")
async def test_calendar_month_leap_year_and_month_lengths(env: AuthEnv) -> None:
    await register_user(env)

    # February 2024 is a leap year (29 days)
    resp_leap = env.client.get(
        f"{CALENDAR_URL}?month=2024-02",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert resp_leap.status_code == 200
    days_leap = resp_leap.json()["days"]
    assert len(days_leap) == 29
    assert days_leap[-1]["date"] == "2024-02-29"

    # February 2025 is not a leap year (28 days)
    resp_non_leap = env.client.get(
        f"{CALENDAR_URL}?month=2025-02",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert resp_non_leap.status_code == 200
    days_non_leap = resp_non_leap.json()["days"]
    assert len(days_non_leap) == 28
    assert days_non_leap[-1]["date"] == "2025-02-28"

    # April 2026 has 30 days
    resp_apr = env.client.get(
        f"{CALENDAR_URL}?month=2026-04",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert resp_apr.status_code == 200
    days_apr = resp_apr.json()["days"]
    assert len(days_apr) == 30
    assert days_apr[-1]["date"] == "2026-04-30"


@pytest.mark.req("CSC-3")
async def test_calendar_month_populates_flow_and_logged_dots(env: AuthEnv) -> None:
    await register_user(env)

    # Day 1: Log flow medium
    env.client.put(
        f"{DAILY_LOGS}/2026-10-01",
        json={
            "flow": "medium",
            "client_updated_at": datetime(2026, 10, 1, 12, 0, tzinfo=UTC).isoformat(),
        },
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )

    # Day 2: Log check-in with mood and no flow (flow="none")
    env.client.put(
        f"{DAILY_LOGS}/2026-10-02",
        json={
            "mood": 4,
            "flow": "none",
            "client_updated_at": datetime(2026, 10, 2, 12, 0, tzinfo=UTC).isoformat(),
        },
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )

    # Day 3: Log spotting
    env.client.put(
        f"{DAILY_LOGS}/2026-10-03",
        json={
            "flow": "spotting",
            "client_updated_at": datetime(2026, 10, 3, 12, 0, tzinfo=UTC).isoformat(),
        },
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )

    resp = env.client.get(
        f"{CALENDAR_URL}?month=2026-10",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert resp.status_code == 200
    by_date = {d["date"]: d for d in resp.json()["days"]}

    # Unlogged day
    assert by_date["2026-10-04"]["has_log"] is False
    assert by_date["2026-10-04"]["flow"] is None

    # Medium flow day
    assert by_date["2026-10-01"]["has_log"] is True
    assert by_date["2026-10-01"]["flow"] == "medium"

    # Check-in day with no flow
    assert by_date["2026-10-02"]["has_log"] is True
    assert by_date["2026-10-02"]["flow"] == "none"

    # Spotting day
    assert by_date["2026-10-03"]["has_log"] is True
    assert by_date["2026-10-03"]["flow"] == "spotting"


@pytest.mark.req("CSC-3")
async def test_calendar_month_defaults_to_user_timezone_current_month(env: AuthEnv) -> None:
    await register_user(env)
    resp = env.client.get(
        CALENDAR_URL,
        headers={"CF-Connecting-IP": env.ip},
    )
    assert resp.status_code == 200
    data = resp.json()
    # By default, test env timezone is Europe/London
    expected_month = datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m")
    assert data["month"] == expected_month
    assert len(data["days"]) >= 28


@pytest.mark.req("CSC-3")
async def test_calendar_month_rejects_invalid_month_format(env: AuthEnv) -> None:
    await register_user(env)

    # Invalid month index 13
    assert (
        env.client.get(
            f"{CALENDAR_URL}?month=2026-13",
            headers={"CF-Connecting-IP": env.ip},
        ).status_code
        == 422
    )

    # Non-digit
    assert (
        env.client.get(
            f"{CALENDAR_URL}?month=invalid",
            headers={"CF-Connecting-IP": env.ip},
        ).status_code
        == 422
    )

    # Wrong separator
    assert (
        env.client.get(
            f"{CALENDAR_URL}?month=2026/10",
            headers={"CF-Connecting-IP": env.ip},
        ).status_code
        == 422
    )

    # Year out of range (< 1990)
    assert (
        env.client.get(
            f"{CALENDAR_URL}?month=1899-12",
            headers={"CF-Connecting-IP": env.ip},
        ).status_code
        == 422
    )


@pytest.mark.req("CSC-3")
async def test_calendar_user_isolation(env: AuthEnv) -> None:
    await register_user(env, email=f"user1{DOMAIN}", name="User1")
    # Log flow for user 1
    env.client.put(
        f"{DAILY_LOGS}/2026-10-05",
        json={
            "flow": "heavy",
            "client_updated_at": datetime(2026, 10, 5, 12, 0, tzinfo=UTC).isoformat(),
        },
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )

    # Register user 2
    await register_user(env, email=f"user2{DOMAIN}", name="User2")
    resp = env.client.get(
        f"{CALENDAR_URL}?month=2026-10",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert resp.status_code == 200
    by_date = {d["date"]: d for d in resp.json()["days"]}
    # User 2 does not see User 1's flow
    assert by_date["2026-10-05"]["has_log"] is False
    assert by_date["2026-10-05"]["flow"] is None


def test_parse_and_validate_month_direct() -> None:
    assert parse_and_validate_month("2026-10") == (2026, 10)
    with pytest.raises(InvalidMonthError):
        parse_and_validate_month("2026")
    with pytest.raises(InvalidMonthError):
        parse_and_validate_month("2026-10-01")
    with pytest.raises(InvalidMonthError):
        parse_and_validate_month("1880-05")
    with pytest.raises(InvalidMonthError):
        parse_and_validate_month("2026-00")
