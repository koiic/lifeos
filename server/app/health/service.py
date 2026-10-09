"""health: Service layer: rules and transactions (plan 4.2)."""

import uuid

from app.health import repo
from app.health.schemas import HealthProfilePayload, Mode, SymptomPayload
from app.platform.crypto import DataKey, aad, decrypt_payload, encrypt_payload
from app.platform.db import Transaction
from app.platform.ids import new_id

# Spec 7.4, in its order: (system_key, category, name). Flo names map onto these keys (13).
SEEDED_SYMPTOMS: tuple[tuple[str, str, str], ...] = (
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
)


async def seed_symptoms(tx: Transaction, user_id: uuid.UUID, dek: DataKey) -> None:
    """7.4: her 18 symptoms, names encrypted under her data key; in the caller's (registration)
    transaction."""
    rows = []
    for order, (key, category, name) in enumerate(SEEDED_SYMPTOMS):
        symptom_id = new_id()
        rows.append(
            repo.NewSymptom(
                id=symptom_id,
                system_key=key,
                category=category,
                sort_order=order,
                payload_enc=encrypt_payload(
                    dek,
                    SymptomPayload(name=name),
                    aad("symptoms", "payload_enc", symptom_id, user_id),
                ),
            )
        )
    await repo.insert_symptoms(tx, user_id, rows)


async def health_mode(tx: Transaction, user_id: uuid.UUID, dek: DataKey) -> Mode:
    """Her health mode (MOD-1 to MOD-4); `standard` until the setup wizard or Settings sets one."""
    blob = await repo.health_profile(tx, user_id)
    if blob is None:
        return "standard"
    # health_profile's row id is her user id (its primary key).
    associated = aad("health_profile", "payload_enc", user_id, user_id)
    return decrypt_payload(dek, blob, associated, HealthProfilePayload).mode
