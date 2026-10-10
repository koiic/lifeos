"""Unit tests for symptom schemas, validation, and encryption (CHK-3, spec 9.2)."""

import uuid

import pytest
from pydantic import ValidationError

from app.health.schemas import (
    SymptomCreateIn,
    SymptomPayload,
    SymptomUpdateIn,
)
from app.platform.crypto import (
    aad,
    decrypt_payload,
    encrypt_payload,
    generate_data_key,
)


@pytest.mark.req("CHK-3")
def test_validation_symptom_category() -> None:
    # Valid categories
    for cat in ("pain", "digestion", "skin", "emotional", "energy", "other"):
        item = SymptomCreateIn(name="Fatigue", category=cat)  # type: ignore[arg-type]
        assert item.category == cat

    # Invalid category
    with pytest.raises(ValidationError):
        SymptomCreateIn(name="Fatigue", category="unknown")  # type: ignore[arg-type]


@pytest.mark.req("CHK-3")
def test_validation_symptom_name() -> None:
    # Name trimmed and cleaned
    item = SymptomCreateIn(name="  Brain fog  ")
    assert item.name == "Brain fog"

    # Empty name rejected
    with pytest.raises(ValidationError):
        SymptomCreateIn(name="")
    with pytest.raises(ValidationError):
        SymptomCreateIn(name="   ")

    # Name > 50 chars rejected
    with pytest.raises(ValidationError):
        SymptomCreateIn(name="a" * 51)


@pytest.mark.req("CHK-3")
def test_validation_symptom_update() -> None:
    # None fields allowed
    update = SymptomUpdateIn()
    assert update.name is None
    assert update.category is None
    assert update.sort_order is None
    assert update.archived is None

    # Valid name update
    update = SymptomUpdateIn(name=" Joint pain ")
    assert update.name == "Joint pain"

    # Empty name update rejected
    with pytest.raises(ValidationError):
        SymptomUpdateIn(name="   ")

    # Valid category and archived update
    update = SymptomUpdateIn(category="pain", archived=True)
    assert update.category == "pain"
    assert update.archived is True


@pytest.mark.req("CHK-3")
def test_symptom_encryption_roundtrip() -> None:
    dek = generate_data_key()
    user_id = uuid.uuid4()
    symptom_id = uuid.uuid4()

    payload = SymptomPayload(name="Lower back tightness")
    associated = aad("symptoms", "payload_enc", symptom_id, user_id)

    encrypted = encrypt_payload(dek, payload, associated)
    assert b"Lower back tightness" not in encrypted

    decrypted = decrypt_payload(dek, encrypted, associated, SymptomPayload)
    assert decrypted.name == "Lower back tightness"
