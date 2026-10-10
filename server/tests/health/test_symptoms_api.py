"""Integration tests for Symptom Catalogue API (CHK-3, spec 9.2, 7.2, 7.4).

Tests: list seeded symptoms, create custom symptom, rename, update category/order,
archive, resolution of archived symptoms on old daily logs, unarchive, and user isolation.
"""

import uuid
from datetime import UTC, datetime

import pytest

from tests.auth.conftest import DOMAIN, HEADERS, AuthEnv

SYMPTOMS = "/api/v1/symptoms"
DAILY_LOGS = "/api/v1/daily-logs"


async def register_user(env: AuthEnv, email: str = f"zee{DOMAIN}", name: str = "Zee") -> uuid.UUID:
    response = env.register(await env.invite(email), name=name, email=email)
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["user_id"])


@pytest.mark.req("CHK-3")
async def test_list_seeded_symptoms(env: AuthEnv) -> None:
    await register_user(env)
    resp = env.client.get(SYMPTOMS, headers={"CF-Connecting-IP": env.ip})
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 18

    # All seeded symptoms are unarchived and have system_key
    first = items[0]
    assert first["system_key"] == "cramps"
    assert first["category"] == "pain"
    assert first["name"] == "Cramps"
    assert first["archived"] is False
    assert first["archived_at"] is None


@pytest.mark.req("CHK-3")
async def test_create_custom_symptom(env: AuthEnv) -> None:
    user_id = await register_user(env)
    body = {
        "name": "Brain fog",
        "category": "energy",
        "sort_order": 20,
    }

    resp = env.client.post(
        SYMPTOMS,
        json=body,
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Brain fog"
    assert data["category"] == "energy"
    assert data["sort_order"] == 20
    assert data["system_key"] is None
    assert data["archived"] is False
    symptom_id = uuid.UUID(data["id"])

    # Verify encrypted in DB (no plaintext "Brain fog" in payload_enc)
    row = await env.db.fetchrow(
        "SELECT payload_enc FROM symptoms WHERE user_id = $1 AND id = $2",
        user_id,
        symptom_id,
    )
    assert row is not None
    assert b"Brain fog" not in row["payload_enc"]


@pytest.mark.req("CHK-3")
async def test_rename_symptom(env: AuthEnv) -> None:
    await register_user(env)
    # Create symptom
    create_resp = env.client.post(
        SYMPTOMS,
        json={"name": "Migraine", "category": "pain"},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert create_resp.status_code == 201
    symptom_id = create_resp.json()["id"]

    # Rename
    patch_resp = env.client.patch(
        f"{SYMPTOMS}/{symptom_id}",
        json={"name": "Ocular migraine"},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["name"] == "Ocular migraine"

    # Verify GET by ID returns updated name
    get_resp = env.client.get(
        f"{SYMPTOMS}/{symptom_id}",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Ocular migraine"


@pytest.mark.req("CHK-3")
async def test_update_symptom_category_and_order(env: AuthEnv) -> None:
    await register_user(env)
    create_resp = env.client.post(
        SYMPTOMS,
        json={"name": "Skin itch", "category": "skin", "sort_order": 5},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    symptom_id = create_resp.json()["id"]

    # Update category and sort order
    patch_resp = env.client.patch(
        f"{SYMPTOMS}/{symptom_id}",
        json={"category": "other", "sort_order": 99},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["category"] == "other"
    assert data["sort_order"] == 99
    assert data["name"] == "Skin itch"


@pytest.mark.req("CHK-3")
async def test_archive_symptom(env: AuthEnv) -> None:
    await register_user(env)
    create_resp = env.client.post(
        SYMPTOMS,
        json={"name": "Dizziness", "category": "energy"},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    symptom_id = create_resp.json()["id"]

    # Archive via DELETE
    del_resp = env.client.delete(
        f"{SYMPTOMS}/{symptom_id}",
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert del_resp.status_code == 204

    # Default list excludes archived symptom
    list_resp = env.client.get(SYMPTOMS, headers={"CF-Connecting-IP": env.ip})
    assert list_resp.status_code == 200
    ids = [x["id"] for x in list_resp.json()]
    assert symptom_id not in ids

    # List with include_archived=true includes it
    all_resp = env.client.get(
        f"{SYMPTOMS}?include_archived=true", headers={"CF-Connecting-IP": env.ip}
    )
    assert all_resp.status_code == 200
    all_items = {x["id"]: x for x in all_resp.json()}
    assert symptom_id in all_items
    assert all_items[symptom_id]["archived"] is True
    assert all_items[symptom_id]["archived_at"] is not None

    # GET by ID returns the archived symptom
    get_resp = env.client.get(
        f"{SYMPTOMS}/{symptom_id}",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["archived"] is True


@pytest.mark.req("CHK-3")
async def test_archived_symptoms_resolve_on_old_logs(env: AuthEnv) -> None:
    await register_user(env)
    # 1. Create custom symptom
    symptom_resp = env.client.post(
        SYMPTOMS,
        json={"name": "Lower back pain", "category": "pain"},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    symptom_id = symptom_resp.json()["id"]

    # 2. Log symptom on historical day
    log_date = "2026-10-02"
    log_body = {
        "mood": 2,
        "symptom_ids": [symptom_id],
        "flow": "none",
        "client_updated_at": datetime(2026, 10, 2, 12, 0, tzinfo=UTC).isoformat(),
    }
    put_log = env.client.put(
        f"{DAILY_LOGS}/{log_date}",
        json=log_body,
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert put_log.status_code == 200
    assert symptom_id in put_log.json()["symptom_ids"]

    # 3. Archive symptom
    del_symptom = env.client.delete(
        f"{SYMPTOMS}/{symptom_id}",
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert del_symptom.status_code == 204

    # 4. Old daily log still retains the symptom ID
    get_log = env.client.get(
        f"{DAILY_LOGS}/{log_date}",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert get_log.status_code == 200
    assert symptom_id in get_log.json()["symptom_ids"]

    # 5. Archived symptom still resolves by ID to its original name
    resolve_resp = env.client.get(
        f"{SYMPTOMS}/{symptom_id}",
        headers={"CF-Connecting-IP": env.ip},
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["name"] == "Lower back pain"
    assert resolve_resp.json()["archived"] is True


@pytest.mark.req("CHK-3")
async def test_unarchive_symptom(env: AuthEnv) -> None:
    await register_user(env)
    create_resp = env.client.post(
        SYMPTOMS,
        json={"name": "Restlessness", "category": "energy"},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    symptom_id = create_resp.json()["id"]

    # Archive
    env.client.delete(
        f"{SYMPTOMS}/{symptom_id}",
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )

    # Unarchive via PATCH archived=false
    patch_resp = env.client.patch(
        f"{SYMPTOMS}/{symptom_id}",
        json={"archived": False},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["archived"] is False
    assert patch_resp.json()["archived_at"] is None

    # Now back in default list
    list_resp = env.client.get(SYMPTOMS, headers={"CF-Connecting-IP": env.ip})
    assert symptom_id in [x["id"] for x in list_resp.json()]


@pytest.mark.req("CHK-3")
async def test_symptom_not_found(env: AuthEnv) -> None:
    await register_user(env)
    random_id = str(uuid.uuid4())

    assert (
        env.client.get(f"{SYMPTOMS}/{random_id}", headers={"CF-Connecting-IP": env.ip}).status_code
        == 404
    )
    assert (
        env.client.patch(
            f"{SYMPTOMS}/{random_id}",
            json={"name": "Foo"},
            headers={"CF-Connecting-IP": env.ip, **HEADERS},
        ).status_code
        == 404
    )
    assert (
        env.client.delete(
            f"{SYMPTOMS}/{random_id}",
            headers={"CF-Connecting-IP": env.ip, **HEADERS},
        ).status_code
        == 404
    )


@pytest.mark.req("CHK-3")
async def test_symptom_user_isolation(env: AuthEnv) -> None:
    # User 1 registers and creates custom symptom
    user1_id = await register_user(env, email=f"user1{DOMAIN}", name="User1")
    resp1 = env.client.post(
        SYMPTOMS,
        json={"name": "Secret Symptom", "category": "other"},
        headers={"CF-Connecting-IP": env.ip, **HEADERS},
    )
    assert resp1.status_code == 201
    symptom1_id = resp1.json()["id"]

    # User 2 registers
    user2_id = await register_user(env, email=f"user2{DOMAIN}", name="User2")
    assert user1_id != user2_id

    # User 2 cannot GET User 1's symptom
    assert (
        env.client.get(
            f"{SYMPTOMS}/{symptom1_id}",
            headers={"CF-Connecting-IP": env.ip},
        ).status_code
        == 404
    )

    # User 2 cannot PATCH User 1's symptom
    assert (
        env.client.patch(
            f"{SYMPTOMS}/{symptom1_id}",
            json={"name": "Hijacked"},
            headers={"CF-Connecting-IP": env.ip, **HEADERS},
        ).status_code
        == 404
    )

    # User 2 cannot DELETE User 1's symptom
    assert (
        env.client.delete(
            f"{SYMPTOMS}/{symptom1_id}",
            headers={"CF-Connecting-IP": env.ip, **HEADERS},
        ).status_code
        == 404
    )

    # User 2's list does not contain User 1's symptom
    list_resp = env.client.get(SYMPTOMS, headers={"CF-Connecting-IP": env.ip})
    assert symptom1_id not in [x["id"] for x in list_resp.json()]
