"""T09, spec 7.4: on registration the app seeds 18 symptoms for her, their names encrypted
(7.1: `symptoms.payload_enc` = `{name}` under her data key)."""

import json
import uuid

import pytest

from app.platform.crypto import DecryptionError, aad, decrypt, load_keyring, unwrap_dek
from tests.auth.conftest import DOMAIN, AuthEnv

pytestmark = pytest.mark.integration

# 7.4, in its order: (system_key, category, name).
SEEDED = [
    ("cramps", "pain", "Cramps"),
    ("back_pain", "pain", "Back pain"),
    ("headache", "pain", "Headache"),
    ("tender_breasts", "pain", "Tender breasts"),
    ("bloating", "digestion", "Bloating"),
    ("nausea", "digestion", "Nausea"),
    ("constipation", "digestion", "Constipation"),
    ("diarrhoea", "digestion", "Diarrhoea"),
    ("cravings", "digestion", "Cravings"),
    ("spots", "skin", "Spots"),
    ("oily_skin", "skin", "Oily skin"),
    ("low_energy", "energy", "Low energy"),
    ("insomnia", "energy", "Insomnia"),
    ("anxious", "emotional", "Anxious"),
    ("irritable", "emotional", "Irritable"),
    ("sad", "emotional", "Sad"),
    ("calm", "emotional", "Calm"),
    ("happy", "emotional", "Happy"),
]


async def symptoms(env: AuthEnv, user_id: uuid.UUID) -> list[tuple[str, str, str, int]]:
    keyring = load_keyring(env.app.state.settings)
    user = await env.db.fetchrow(
        "SELECT dek_wrapped, kek_version FROM users WHERE id = $1", user_id
    )
    assert user is not None
    dek = unwrap_dek(keyring, user["kek_version"], user["dek_wrapped"], user_id)
    rows = await env.db.fetch(
        "SELECT id, system_key, category, sort_order, payload_enc, archived_at FROM symptoms"
        " WHERE user_id = $1 ORDER BY sort_order",
        user_id,
    )
    seeded = []
    for row in rows:
        assert row["archived_at"] is None
        payload = json.loads(
            decrypt(dek, row["payload_enc"], aad("symptoms", "payload_enc", row["id"], user_id))
        )
        name = payload["name"]
        assert payload == {"v": 1, "name": name}  # 7.1: a versioned payload, nothing else
        assert name.encode() not in row["payload_enc"]  # encrypted, never plaintext (7.1)
        seeded.append((row["system_key"], row["category"], name, row["sort_order"]))
    return seeded


async def test_passkey_registration_seeds_the_18_symptoms_encrypted(env: AuthEnv) -> None:
    response = env.register(await env.invite())
    assert response.status_code == 201, response.text
    user_id = uuid.UUID(response.json()["user_id"])
    assert await symptoms(env, user_id) == [
        (key, category, name, order) for order, (key, category, name) in enumerate(SEEDED)
    ]


async def test_password_registration_seeds_them_too(env: AuthEnv) -> None:
    env.password_account(env.register_password(await env.invite()))
    user_id = await env.db.fetchval("SELECT id FROM users WHERE email = $1", f"zee{DOMAIN}")
    assert len(await symptoms(env, user_id)) == 18


async def test_each_user_gets_her_own_symptoms(env: AuthEnv) -> None:
    first = env.register(await env.invite())
    env.client.cookies.clear()
    second = env.register(await env.invite(f"other{DOMAIN}"), email=f"other{DOMAIN}")
    ids = [uuid.UUID(r.json()["user_id"]) for r in (first, second)]
    expected = [(key, category, name, order) for order, (key, category, name) in enumerate(SEEDED)]
    for user_id in ids:  # each decrypts under her own key and AAD
        assert await symptoms(env, user_id) == expected
    # Another user's key cannot read them.
    keyring = load_keyring(env.app.state.settings)
    user = await env.db.fetchrow("SELECT dek_wrapped, kek_version FROM users WHERE id = $1", ids[0])
    assert user is not None
    first_dek = unwrap_dek(keyring, user["kek_version"], user["dek_wrapped"], ids[0])
    row = await env.db.fetchrow(
        "SELECT id, payload_enc FROM symptoms WHERE user_id = $1 LIMIT 1", ids[1]
    )
    assert row is not None
    with pytest.raises(DecryptionError):
        decrypt(first_dek, row["payload_enc"], aad("symptoms", "payload_enc", row["id"], ids[1]))
