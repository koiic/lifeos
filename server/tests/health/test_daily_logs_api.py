"""Integration tests for Daily Logs API (spec 9.2, 9.3, 9.4, 4.4, CHK-2, PER-2).

Tests: upsert, future-date rejection, LWW by client_updated_at, idempotent replay,
daily_log.flow_changed outbox event, user isolation.
"""

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.auth.conftest import DOMAIN, HEADERS, AuthEnv

pytestmark = pytest.mark.integration

LOGS = "/api/v1/daily-logs"


async def register_user(env: AuthEnv, email: str = f"zee{DOMAIN}", name: str = "Zee") -> uuid.UUID:
    response = env.register(await env.invite(email), name=name, email=email)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["user_id"])


@pytest.mark.req("CHK-2")
async def test_upsert_new_log(env: AuthEnv) -> None:
    user_id = await register_user(env)
    target_date = "2026-10-06"
    now_utc = datetime(2026, 10, 6, 19, 2, 11, tzinfo=UTC).isoformat()
    symptom_id = str(uuid.uuid4())

    body = {
        "mood": 4,
        "energy": 3,
        "sleep_hours": 6.5,
        "symptom_ids": [symptom_id],
        "flow": "medium",
        "discharge": None,
        "bbt_c": None,
        "intimacy": None,
        "note": "Private note test",
        "checkin_ms": 18400,
        "client_updated_at": now_utc,
    }

    resp = env.client.put(
        f"{LOGS}/{target_date}",
        json=body,
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["date"] == target_date
    assert data["mood"] == 4
    assert data["energy"] == 3
    assert data["sleep_hours"] == 6.5
    assert data["flow"] == "medium"
    assert data["note"] == "Private note test"
    assert data["rebuild"] == "queued"  # Flow changed from none to medium

    # Verify encrypted in DB (no plaintext note or flow in payload_enc)
    row = await env.db.fetchrow(
        "SELECT payload_enc FROM daily_logs WHERE user_id = $1 AND date = $2",
        user_id,
        date(2026, 10, 6),
    )
    assert row is not None
    assert b"Private note test" not in row["payload_enc"]
    assert b"medium" not in row["payload_enc"]


@pytest.mark.req("CHK-2")
async def test_future_date_rejected(env: AuthEnv) -> None:
    await register_user(env)
    # User's profile timezone is Europe/London
    now_london = datetime.now(ZoneInfo("Europe/London"))
    tomorrow = (now_london + timedelta(days=1)).date().isoformat()
    now_utc = datetime.now(UTC).isoformat()

    body = {
        "mood": 3,
        "flow": "none",
        "client_updated_at": now_utc,
    }

    resp = env.client.put(
        f"{LOGS}/{tomorrow}",
        json=body,
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp.status_code == 422, resp.text
    err = resp.json()
    assert "future" in err.get("detail", "").lower()


@pytest.mark.req("CHK-2")
async def test_date_before_1990_rejected(env: AuthEnv) -> None:
    await register_user(env)
    too_early = "1989-12-31"
    now_utc = datetime.now(UTC).isoformat()

    body = {
        "mood": 3,
        "flow": "none",
        "client_updated_at": now_utc,
    }

    resp = env.client.put(
        f"{LOGS}/{too_early}",
        json=body,
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp.status_code == 422, resp.text
    err = resp.json()
    assert "1990" in err.get("detail", "")


@pytest.mark.req("CHK-2")
async def test_lww_newer_write_wins(env: AuthEnv) -> None:
    await register_user(env)
    target_date = "2026-10-06"
    t1 = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC).isoformat()
    t2 = datetime(2026, 10, 6, 12, 5, 0, tzinfo=UTC).isoformat()

    # Initial write at t1
    resp1 = env.client.put(
        f"{LOGS}/{target_date}",
        json={"mood": 2, "flow": "none", "client_updated_at": t1},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp1.status_code == 200
    assert resp1.json()["mood"] == 2

    # Newer write at t2
    resp2 = env.client.put(
        f"{LOGS}/{target_date}",
        json={"mood": 5, "flow": "none", "client_updated_at": t2},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp2.status_code == 200
    assert resp2.json()["mood"] == 5


@pytest.mark.req("CHK-2")
async def test_lww_older_write_ignored(env: AuthEnv) -> None:
    await register_user(env)
    target_date = "2026-10-06"
    t_newer = datetime(2026, 10, 6, 14, 0, 0, tzinfo=UTC).isoformat()
    t_older = datetime(2026, 10, 6, 13, 0, 0, tzinfo=UTC).isoformat()

    # Write with newer timestamp
    resp1 = env.client.put(
        f"{LOGS}/{target_date}",
        json={"mood": 5, "note": "Newest write", "flow": "none", "client_updated_at": t_newer},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp1.status_code == 200
    assert resp1.json()["mood"] == 5

    # Later arrival of an older timestamp write
    resp2 = env.client.put(
        f"{LOGS}/{target_date}",
        json={"mood": 1, "note": "Stale write", "flow": "none", "client_updated_at": t_older},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    # Stored write wins; returns stored record with rebuild: not_needed
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["mood"] == 5
    assert data["note"] == "Newest write"
    assert data["rebuild"] == "not_needed"


@pytest.mark.req("CHK-2")
async def test_flow_changed_emits_outbox_event(env: AuthEnv) -> None:
    user_id = await register_user(env)
    target_date = "2026-10-06"
    t1 = datetime(2026, 10, 6, 10, 0, 0, tzinfo=UTC).isoformat()
    t2 = datetime(2026, 10, 6, 11, 0, 0, tzinfo=UTC).isoformat()

    # Write with flow "medium"
    resp1 = env.client.put(
        f"{LOGS}/{target_date}",
        json={"mood": 3, "flow": "medium", "client_updated_at": t1},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp1.status_code == 200
    assert resp1.json()["rebuild"] == "queued"

    # Outbox event emitted
    events = await env.db.fetch(
        "SELECT topic, body FROM outbox_events WHERE user_id = $1 AND topic = $2",
        user_id,
        "daily_log.flow_changed",
    )
    assert len(events) == 1
    body = json.loads(events[0]["body"])
    assert body["date"] == target_date
    assert "medium" not in json.dumps(body)  # Privacy: no health value in outbox body

    # Update note without changing flow (medium -> medium)
    resp2 = env.client.put(
        f"{LOGS}/{target_date}",
        json={"mood": 4, "flow": "medium", "note": "Updated note", "client_updated_at": t2},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp2.status_code == 200
    assert resp2.json()["rebuild"] == "not_needed"

    # No second outbox event created
    events_after = await env.db.fetch(
        "SELECT topic, body FROM outbox_events WHERE user_id = $1 AND topic = $2",
        user_id,
        "daily_log.flow_changed",
    )
    assert len(events_after) == 1


@pytest.mark.req("CHK-2")
async def test_get_daily_log_by_date(env: AuthEnv) -> None:
    await register_user(env)
    target_date = "2026-10-06"
    now_utc = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC).isoformat()

    # 404 before creation
    not_found = env.client.get(
        f"{LOGS}/{target_date}",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert not_found.status_code == 404

    # Create log
    env.client.put(
        f"{LOGS}/{target_date}",
        json={"mood": 4, "flow": "light", "client_updated_at": now_utc},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )

    # 200 after creation
    found = env.client.get(
        f"{LOGS}/{target_date}",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert found.status_code == 200
    data = found.json()
    assert data["date"] == target_date
    assert data["mood"] == 4
    assert data["flow"] == "light"


@pytest.mark.req("CHK-2")
async def test_get_daily_logs_range(env: AuthEnv) -> None:
    await register_user(env)
    for day in (1, 2, 3):
        d_str = f"2026-10-0{day}"
        env.client.put(
            f"{LOGS}/{d_str}",
            json={
                "mood": day,
                "flow": "none",
                "client_updated_at": datetime(2026, 10, day, 12, 0, tzinfo=UTC).isoformat(),
            },
            headers={"CF-Connecting-IP": env.ip, **HEADERS},
        )

    # Query range
    resp = env.client.get(
        f"{LOGS}?from=2026-10-01&to=2026-10-03",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 3
    assert [x["date"] for x in items] == ["2026-10-01", "2026-10-02", "2026-10-03"]

    # Invalid range: from > to
    invalid = env.client.get(
        f"{LOGS}?from=2026-10-05&to=2026-10-01",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert invalid.status_code == 422

    # Invalid range: > 400 days
    wide = env.client.get(
        f"{LOGS}?from=2024-01-01&to=2026-10-01",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert wide.status_code == 422


@pytest.mark.req("CHK-2")
async def test_delete_daily_log(env: AuthEnv) -> None:
    user_id = await register_user(env)
    target_date = "2026-10-06"
    now_utc = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC).isoformat()

    # Create log with flow
    env.client.put(
        f"{LOGS}/{target_date}",
        json={"mood": 3, "flow": "medium", "client_updated_at": now_utc},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )

    # Delete
    del_resp = env.client.delete(
        f"{LOGS}/{target_date}",
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert del_resp.status_code == 204

    # Subsequent GET returns 404
    get_resp = env.client.get(
        f"{LOGS}/{target_date}",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert get_resp.status_code == 404

    # Flow was removed: outbox event published for flow_changed
    events = await env.db.fetch(
        "SELECT topic FROM outbox_events WHERE user_id = $1 AND topic = $2",
        user_id,
        "daily_log.flow_changed",
    )
    # 1 for initial creation with medium, 1 for deletion clearing medium
    assert len(events) == 2


@pytest.mark.req("CHK-2")
async def test_idempotency_key_replay(env: AuthEnv) -> None:
    await register_user(env)
    target_date = "2026-10-06"
    ikey = str(uuid.uuid4())
    now_utc = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC).isoformat()
    body = {"mood": 4, "flow": "medium", "client_updated_at": now_utc}

    # Initial request
    resp1 = env.client.put(
        f"{LOGS}/{target_date}",
        json=body,
        headers={"CF-Connecting-IP": env.ip, "Idempotency-Key": ikey, **HEADERS},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()

    # Exact replay returns cached response
    resp2 = env.client.put(
        f"{LOGS}/{target_date}",
        json=body,
        headers={"CF-Connecting-IP": env.ip, "Idempotency-Key": ikey, **HEADERS},
    )
    assert resp2.status_code == 200
    assert resp2.json() == data1

    # Replay with different body fails with 422
    different_body = {"mood": 1, "flow": "none", "client_updated_at": now_utc}
    resp3 = env.client.put(
        f"{LOGS}/{target_date}",
        json=different_body,
        headers={"CF-Connecting-IP": env.ip, "Idempotency-Key": ikey, **HEADERS},
    )
    assert resp3.status_code == 422


@pytest.mark.req("CHK-2")
async def test_auth_and_user_isolation(env: AuthEnv) -> None:
    # 401 without session
    unauth = env.client.get(f"{LOGS}/2026-10-06", headers={"CF-Connecting-IP": env.ip})
    assert unauth.status_code == 401

    # User isolation: user 2 cannot see user 1's log
    user1_id = await register_user(env, email=f"user1{DOMAIN}", name="User1")
    target_date = "2026-10-06"
    env.client.put(
        f"{LOGS}/{target_date}",
        json={
            "mood": 5,
            "flow": "none",
            "client_updated_at": datetime(2026, 10, 6, 12, 0, tzinfo=UTC).isoformat(),
        },
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )

    # Register user 2 (this sets session cookie for user 2)
    user2_id = await register_user(env, email=f"user2{DOMAIN}", name="User2")
    assert user1_id != user2_id

    # User 2 gets 404 for user 1's date
    u2_resp = env.client.get(
        f"{LOGS}/{target_date}",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert u2_resp.status_code == 404
