"""Tests for Daily Logs API with validation, LWW, and outbox events (CHK-2, PER-2).

Spec sections: 9.2, 9.3, 9.4, 4.4, 4.5, 7.1, 11.5.
"""

import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.health.schemas import (
    DailyLogPayload,
    DailyLogPutIn,
    IntimacyPayload,
)
from app.health.service import (
    DateOutOfRange,
    FutureDateError,
    InvalidRange,
)
from app.platform.crypto import (
    aad,
    decrypt_payload,
    encrypt_payload,
    generate_data_key,
)


@pytest.mark.req("CHK-2")
def test_validation_mood_energy_ranges() -> None:
    # Valid values 1..5 and None
    for val in (1, 2, 3, 4, 5, None):
        payload = DailyLogPayload(mood=val, energy=val)
        assert payload.mood == val
        assert payload.energy == val

    # Invalid mood < 1 or > 5
    with pytest.raises(ValidationError):
        DailyLogPayload(mood=0)
    with pytest.raises(ValidationError):
        DailyLogPayload(mood=6)
    with pytest.raises(ValidationError):
        DailyLogPayload(energy=0)
    with pytest.raises(ValidationError):
        DailyLogPayload(energy=6)


@pytest.mark.req("CHK-2")
def test_validation_sleep_hours_step() -> None:
    # 0 to 14 in 0.5 steps
    for val in (0.0, 0.5, 7.0, 7.5, 14.0, None):
        payload = DailyLogPayload(sleep_hours=val)
        assert payload.sleep_hours == val

    # Invalid: negative
    with pytest.raises(ValidationError):
        DailyLogPayload(sleep_hours=-0.5)
    # Invalid: > 14
    with pytest.raises(ValidationError):
        DailyLogPayload(sleep_hours=14.5)
    # Invalid: not 0.5 step
    with pytest.raises(ValidationError):
        DailyLogPayload(sleep_hours=6.3)


@pytest.mark.req("CHK-2")
def test_validation_flow_values() -> None:
    # Flow: none, spotting, light, medium, heavy
    for f in ("none", "spotting", "light", "medium", "heavy"):
        payload = DailyLogPayload(flow=f)  # type: ignore[arg-type]
        assert payload.flow == f

    with pytest.raises(ValidationError):
        DailyLogPayload(flow="other")  # type: ignore[arg-type]


@pytest.mark.req("CHK-2")
def test_validation_bbt_c_range() -> None:
    # 34.0 to 40.0, 2 decimals
    for val in (34.0, 36.65, 40.0, None):
        payload = DailyLogPayload(bbt_c=val)
        assert payload.bbt_c == val

    with pytest.raises(ValidationError):
        DailyLogPayload(bbt_c=33.9)
    with pytest.raises(ValidationError):
        DailyLogPayload(bbt_c=40.1)
    with pytest.raises(ValidationError):
        DailyLogPayload(bbt_c=36.654)


@pytest.mark.req("CHK-2")
def test_validation_note_length() -> None:
    # Note <= 2000 chars, stripped
    payload = DailyLogPayload(note="  Felt great today!  ")
    assert payload.note == "Felt great today!"

    long_note = "a" * 2001
    with pytest.raises(ValidationError):
        DailyLogPayload(note=long_note)


@pytest.mark.req("CHK-2")
def test_validation_intimacy_and_checkin_ms() -> None:
    intimacy = IntimacyPayload(logged=True, protected=True)
    payload = DailyLogPayload(intimacy=intimacy, checkin_ms=15000)
    assert payload.intimacy is not None
    assert payload.intimacy.logged is True
    assert payload.intimacy.protected is True
    assert payload.checkin_ms == 15000

    # Negative checkin_ms invalid
    with pytest.raises(ValidationError):
        DailyLogPayload(checkin_ms=-1)


@pytest.mark.req("CHK-2")
def test_put_request_payload_and_client_updated_at() -> None:
    now = datetime.now(UTC)
    symptom_id = uuid.uuid4()
    req = DailyLogPutIn(
        mood=4,
        energy=3,
        sleep_hours=6.5,
        symptom_ids=[symptom_id],
        flow="none",
        discharge=None,
        bbt_c=None,
        intimacy=None,
        note=None,
        checkin_ms=18400,
        client_updated_at=now,
    )
    assert req.mood == 4
    assert req.client_updated_at == now
    assert req.symptom_ids == [symptom_id]


@pytest.mark.req("CHK-2")
def test_future_date_check_logic() -> None:
    # User in Europe/London
    tz = "Europe/London"
    now_london = datetime.now(ZoneInfo(tz))
    today_london = now_london.date()
    yesterday = today_london - timedelta(days=1)
    tomorrow = today_london + timedelta(days=1)

    from app.health.service import validate_log_date

    # Past date and today are allowed
    validate_log_date(yesterday, tz)
    validate_log_date(today_london, tz)

    # Future date rejected with FutureDateError
    with pytest.raises(FutureDateError):
        validate_log_date(tomorrow, tz)

    # Date before 1990-01-01 rejected with DateOutOfRange
    with pytest.raises(DateOutOfRange):
        validate_log_date(date(1989, 12, 31), tz)


@pytest.mark.req("CHK-2")
def test_date_range_validation_logic() -> None:
    from app.health.service import validate_date_range

    start = date(2026, 1, 1)
    end = date(2026, 1, 31)
    validate_date_range(start, end)

    # from > to
    with pytest.raises(InvalidRange):
        validate_date_range(end, start)

    # > 400 days
    far_end = start + timedelta(days=401)
    with pytest.raises(InvalidRange):
        validate_date_range(start, far_end)


@pytest.mark.req("CHK-2")
def test_daily_log_payload_encryption_roundtrip() -> None:
    dek = generate_data_key()
    user_id = uuid.uuid4()
    log_id = uuid.uuid4()
    symptom_id = uuid.uuid4()

    payload = DailyLogPayload(
        mood=4,
        energy=3,
        sleep_hours=7.5,
        symptom_ids=[symptom_id],
        flow="medium",
        note="Felt fine",
        checkin_ms=12000,
    )

    associated = aad("daily_logs", "payload_enc", log_id, user_id)
    encrypted = encrypt_payload(dek, payload, associated)
    assert b"Felt fine" not in encrypted
    assert b"medium" not in encrypted

    decrypted = decrypt_payload(dek, encrypted, associated, DailyLogPayload)
    assert decrypted.mood == 4
    assert decrypted.flow == "medium"
    assert decrypted.note == "Felt fine"
    assert decrypted.symptom_ids == [symptom_id]


@pytest.mark.req("CHK-2")
def test_lww_timestamp_comparison() -> None:
    t1 = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 6, 12, 5, 0, tzinfo=UTC)

    from app.health.service import should_apply_write

    # Newer timestamp wins
    assert should_apply_write(existing_client_updated_at=t1, incoming_client_updated_at=t2) is True
    # Equal timestamp wins (idempotent / same write)
    assert should_apply_write(existing_client_updated_at=t1, incoming_client_updated_at=t1) is True
    # Older timestamp loses
    assert should_apply_write(existing_client_updated_at=t2, incoming_client_updated_at=t1) is False


@pytest.mark.req("CHK-2")
def test_flow_change_detection() -> None:
    from app.health.service import detect_flow_change

    # Fresh log with flow "none": no change
    assert detect_flow_change(prev_flow=None, new_flow="none") is False
    # Fresh log with flow "medium": flow changed
    assert detect_flow_change(prev_flow=None, new_flow="medium") is True

    # Existing "medium" to "light": flow changed
    assert detect_flow_change(prev_flow="medium", new_flow="light") is True
    # Existing "medium" to "none": flow changed
    assert detect_flow_change(prev_flow="medium", new_flow="none") is True
    # Existing "none" to "medium": flow changed
    assert detect_flow_change(prev_flow="none", new_flow="medium") is True
    # Existing "medium" to "medium": flow unchanged
    assert detect_flow_change(prev_flow="medium", new_flow="medium") is False
    # Existing "none" to "none": flow unchanged
    assert detect_flow_change(prev_flow="none", new_flow="none") is False


@pytest.mark.req("CHK-2")
def test_idempotency_hash_calculation() -> None:
    from app.health.service import compute_request_hash

    body1 = b'{"mood": 4, "flow": "none"}'
    body2 = b'{"mood": 5, "flow": "none"}'

    h1 = compute_request_hash(body1)
    h2 = compute_request_hash(body2)
    assert h1 == hashlib.sha256(body1).digest()
    assert h1 != h2
