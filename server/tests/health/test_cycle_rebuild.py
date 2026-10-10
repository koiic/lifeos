"""Integration tests for cycle rebuild job, predictions storage, and health profile.

Spec sections: 8.5; 9.2, 9.3; 10.1; CYC-1, CYC-5, CYC-7, MOD-1, MOD-2.
"""

import time
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from tests.auth.conftest import DOMAIN, HEADERS, AuthEnv

pytestmark = pytest.mark.integration

DAILY_LOGS = "/api/v1/daily-logs"
CYCLE_URL = "/api/v1/health/cycle"
CYCLES_URL = "/api/v1/health/cycles"
EXCLUSIONS_URL = "/api/v1/health/cycles/exclusions"
CONFIRM_URL = "/api/v1/health/period-starts/confirm"
PROFILE_URL = "/api/v1/health/profile"
TODAY_URL = "/api/v1/today"


async def register_user(env: AuthEnv, email: str = f"zee{DOMAIN}", name: str = "Zee") -> uuid.UUID:
    response = env.register(await env.invite(email), name=name, email=email)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["user_id"])


def log_flow_days(env: AuthEnv, start_date: date, count: int = 5, flow: str = "medium") -> None:
    for offset in range(count):
        d = start_date + timedelta(days=offset)
        now_utc = datetime(d.year, d.month, d.day, 12, 0, tzinfo=UTC).isoformat()
        res = env.client.put(
            f"{DAILY_LOGS}/{d.isoformat()}",
            json={"flow": flow, "client_updated_at": now_utc},
            headers={"CF-Connecting-IP": env.ip, **HEADERS},
        )
        assert res.status_code == 200, res.text


@pytest.mark.req("CYC-1", "CYC-7")
async def test_rebuild_cycles_flow_change_creates_and_supersedes_prediction(env: AuthEnv) -> None:
    """Spec 8.5, CYC-1, CYC-7: Daily-log flow changes trigger rebuild, storing predictions."""
    user_id = await register_user(env)

    # 4 complete cycles with 5 days medium flow:
    # 2026-05-01, 2026-05-29 (28d), 2026-06-27 (29d), 2026-07-26 (29d), 2026-08-24 (29d)
    starts = [
        date(2026, 5, 1),
        date(2026, 5, 29),
        date(2026, 6, 27),
        date(2026, 7, 26),
        date(2026, 8, 24),
    ]
    for s in starts:
        log_flow_days(env, s, count=5)

    # Query GET /health/cycle (triggers synchronous rebuild if pending)
    t0 = time.perf_counter()
    resp = env.client.get(CYCLE_URL, headers={"CF-Connecting-IP": env.ip})
    duration = time.perf_counter() - t0
    assert resp.status_code == 200, resp.text
    assert duration < 2.0, f"Rebuild took {duration}s, target is < 2s"

    data = resp.json()
    assert data["latest_start"] == "2026-08-24"
    assert data["prediction"] is not None
    pred = data["prediction"]
    assert pred["algorithm_version"] == "calendar-1.0"
    assert pred["predicted_start"] == "2026-09-22"
    assert pred["range_low"] == "2026-09-21"
    assert pred["range_high"] == "2026-09-23"
    assert pred["confidence"] == "medium"
    assert pred["n_cycles"] == 4

    # Verify cycles stored in database
    cycles_rows = await env.db.fetch(
        "SELECT seq, computed_at FROM cycles WHERE user_id = $1 ORDER BY seq ASC",
        user_id,
    )
    # 4 complete cycles (seq 1..4) + 1 incomplete cycle (seq 5)
    assert len(cycles_rows) == 5
    assert [r["seq"] for r in cycles_rows] == [1, 2, 3, 4, 5]

    # Verify prediction stored in database
    pred_rows = await env.db.fetch(
        "SELECT id, algorithm_version, superseded_at FROM cycle_predictions WHERE user_id = $1",
        user_id,
    )
    assert len(pred_rows) == 1
    assert pred_rows[0]["algorithm_version"] == "calendar-1.0"
    assert pred_rows[0]["superseded_at"] is None
    first_pred_id = pred_rows[0]["id"]

    # Verify outbox event prediction.updated emitted
    events = await env.db.fetch(
        "SELECT topic FROM outbox_events WHERE user_id = $1 AND topic = $2",
        user_id,
        "prediction.updated",
    )
    assert len(events) >= 1

    # Now add another period start: 2026-09-22
    log_flow_days(env, date(2026, 9, 22), count=5)

    # Re-query GET /health/cycle
    resp2 = env.client.get(CYCLE_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["latest_start"] == "2026-09-22"

    # Verify previous prediction was superseded in cycle_predictions
    sql = (
        "SELECT id, superseded_at FROM cycle_predictions WHERE user_id = $1 ORDER BY created_at ASC"
    )
    pred_rows_after = await env.db.fetch(sql, user_id)
    assert len(pred_rows_after) == 2
    # First prediction is now superseded
    assert pred_rows_after[0]["id"] == first_pred_id
    assert pred_rows_after[0]["superseded_at"] is not None
    # Second prediction is active
    assert pred_rows_after[1]["superseded_at"] is None


@pytest.mark.req("CYC-1")
async def test_rebuild_cycles_idempotent(env: AuthEnv) -> None:
    """Spec 8.5, CYC-1: Re-running rebuild without changes is idempotent."""
    await register_user(env)
    starts = [date(2026, 7, 1), date(2026, 7, 29), date(2026, 8, 27)]
    for s in starts:
        log_flow_days(env, s, count=5)

    resp1 = env.client.get(CYCLE_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp1.status_code == 200
    data1 = resp1.json()

    resp2 = env.client.get(CYCLE_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert data1 == data2


@pytest.mark.req("CYC-1", "CYC-5")
async def test_cycle_exclusions_survive_rebuild(env: AuthEnv) -> None:
    """Spec 8.2, 9.2, CYC-5: User-excluded cycles survive rebuilds and update predictions."""
    await register_user(env)
    starts = [
        date(2026, 6, 1),
        date(2026, 6, 29),
        date(2026, 7, 28),
        date(2026, 8, 26),
        date(2026, 9, 24),
    ]
    for s in starts:
        log_flow_days(env, s, count=5)

    # Initial prediction uses 4 complete cycles
    resp = env.client.get(CYCLE_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp.status_code == 200
    assert resp.json()["prediction"]["n_cycles"] == 4

    # Exclude cycle starting 2026-06-29 due to travel
    ex_resp = env.client.post(
        EXCLUSIONS_URL,
        json={"start_date": "2026-06-29", "excluded": True, "reason": "travel"},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert ex_resp.status_code == 200, ex_resp.text

    # Verify cycle history reflects exclusion
    hist_resp = env.client.get(CYCLES_URL, headers={"CF-Connecting-IP": env.ip})
    assert hist_resp.status_code == 200
    cycles = hist_resp.json()
    excluded_cycle = next(c for c in cycles if c["start_date"] == "2026-06-29")
    assert excluded_cycle["excluded"] is True
    assert excluded_cycle["exclusion_reason"] == "user_excluded"

    # Prediction now uses 3 cycles
    resp_after = env.client.get(CYCLE_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp_after.status_code == 200
    assert resp_after.json()["prediction"]["n_cycles"] == 3


@pytest.mark.req("CYC-1")
async def test_forced_period_starts_survive_rebuild(env: AuthEnv) -> None:
    """Spec 8.1, 9.2, CYC-1: Intra-cycle bleed confirmed as new period survives rebuild."""
    await register_user(env)
    # Start 1: 2026-09-01 (5 days)
    log_flow_days(env, date(2026, 9, 1), count=5)

    # Intra-cycle flow 10 days later: 2026-09-11
    log_flow_days(env, date(2026, 9, 11), count=3)

    # GET /health/cycle shows pending prompt for intra-cycle bleed
    resp = env.client.get(CYCLE_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_prompt"] is not None
    assert data["pending_prompt"]["date"] == "2026-09-11"
    assert data["pending_prompt"]["kind"] == "new_period"

    # Confirm that 2026-09-11 is a new period
    confirm_resp = env.client.post(
        CONFIRM_URL,
        json={"date": "2026-09-11", "is_new_period": True},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert confirm_resp.status_code == 200, confirm_resp.text

    # After confirmation: 2026-09-11 is now a period start (latest start)
    resp_after = env.client.get(CYCLE_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp_after.status_code == 200
    data_after = resp_after.json()
    assert data_after["latest_start"] == "2026-09-11"
    assert data_after["pending_prompt"] is None

    # Check cycles list: cycle from 09-01 to 09-10 (length 10) is complete and outlier
    hist = env.client.get(CYCLES_URL, headers={"CF-Connecting-IP": env.ip}).json()
    cycle_10 = next(c for c in hist if c["start_date"] == "2026-09-01")
    assert cycle_10["length_days"] == 10
    assert cycle_10["excluded"] is True
    assert cycle_10["exclusion_reason"] == "outlier"


@pytest.mark.req("CYC-1", "MOD-2")
async def test_postpartum_mode_suppression(env: AuthEnv) -> None:
    """Spec 8.2, 8.3, MOD-2: Postpartum mode suppresses predictions until 2 complete cycles."""
    await register_user(env)
    # Cycles: 2026-06-01, 2026-07-01, 2026-08-01 (before/around postpartum mode)
    starts = [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]
    for s in starts:
        log_flow_days(env, s, count=5)

    # Set mode to postpartum starting 2026-07-15
    profile_resp = env.client.put(
        PROFILE_URL,
        json={"mode": "postpartum", "mode_started_on": "2026-07-15"},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert profile_resp.status_code == 200, profile_resp.text

    # Query GET /health/cycle: Only 1 complete cycle after 2026-07-15
    # (07-01 to 08-01 started before mode began)
    resp = env.client.get(CYCLE_URL, headers={"CF-Connecting-IP": env.ip})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "postpartum"
    assert data["state"] == "waiting"
    assert data["prediction"]["suppressed_reason"] == "postpartum_waiting"
    assert data["prediction"]["confidence"] == "none"

    # Query GET /today: Today cycle card displays state waiting and suppressed reason
    today_resp = env.client.get(TODAY_URL, headers={"CF-Connecting-IP": env.ip})
    assert today_resp.status_code == 200
    today_data = today_resp.json()
    assert today_data["cycle_card"] is not None
    assert today_data["cycle_card"]["state"] == "waiting"
    assert today_data["cycle_card"]["suppressed_reason"] == "postpartum_waiting"
