"""health: Service layer: rules and transactions (plan 4.2)."""

import hashlib
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.health import repo
from app.health.schemas import (
    DailyLog,
    DailyLogPayload,
    DailyLogPutIn,
    DailyLogPutResponse,
    HealthProfilePayload,
    Mode,
    SymptomPayload,
)
from app.platform.crypto import (
    DataKey,
    Keyring,
    aad,
    decrypt,
    decrypt_payload,
    encrypt,
    encrypt_payload,
    unwrap_dek,
)
from app.platform.db import Database, Transaction, user_transaction
from app.platform.ids import new_id
from app.platform.outbox import publish

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


class HealthError(Exception):
    status = 400
    detail = "The health request could not be completed."


class FutureDateError(HealthError):
    status = 422
    detail = "Daily log date cannot be in the future."


class DateOutOfRange(HealthError):
    status = 422
    detail = "Daily log date must not be before 1990-01-01."


class InvalidRange(HealthError):
    status = 422
    detail = "Date range is invalid (from <= to, max 400 days)."


class DailyLogNotFound(HealthError):
    status = 404
    detail = "No daily log found for this date."


class IdempotencyMismatch(HealthError):
    status = 422
    detail = "Idempotency key was previously used with a different request body."


def validate_log_date(log_date: date, user_timezone: str) -> None:
    if log_date < date(1990, 1, 1):
        raise DateOutOfRange("Daily log date must not be before 1990-01-01")
    now_local = datetime.now(ZoneInfo(user_timezone))
    today_local = now_local.date()
    if log_date > today_local:
        raise FutureDateError("Daily log date cannot be in the future")


def validate_date_range(from_date: date, to_date: date) -> None:
    if from_date > to_date:
        raise InvalidRange("'from' date must be before or equal to 'to' date")
    if (to_date - from_date).days > 400:
        raise InvalidRange("Date range cannot exceed 400 days")


def should_apply_write(
    existing_client_updated_at: datetime, incoming_client_updated_at: datetime
) -> bool:
    return incoming_client_updated_at >= existing_client_updated_at


def detect_flow_change(prev_flow: str | None, new_flow: str) -> bool:
    normalized_prev = prev_flow or "none"
    normalized_new = new_flow or "none"
    return normalized_prev != normalized_new


def compute_request_hash(body: bytes) -> bytes:
    return hashlib.sha256(body).digest()


def to_daily_log(row: repo.DailyLogRow, payload: DailyLogPayload) -> DailyLog:
    return DailyLog(
        id=row.id,
        date=row.date,
        mood=payload.mood,
        energy=payload.energy,
        sleep_hours=payload.sleep_hours,
        symptom_ids=payload.symptom_ids,
        flow=payload.flow,
        discharge=payload.discharge,
        bbt_c=payload.bbt_c,
        intimacy=payload.intimacy,
        note=payload.note,
        checkin_ms=payload.checkin_ms,
        client_updated_at=row.client_updated_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
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
    associated = aad("health_profile", "payload_enc", user_id, user_id)
    return decrypt_payload(dek, blob, associated, HealthProfilePayload).mode


class DailyLogService:
    def __init__(self, engine: Database, keyring: Keyring) -> None:
        self._db = engine
        self._keyring = keyring

    async def _user_dek_and_tz(self, tx: Transaction, user_id: uuid.UUID) -> tuple[DataKey, str]:
        meta = await repo.user_meta(tx, user_id)
        dek = unwrap_dek(self._keyring, meta.kek_version, meta.dek_wrapped, user_id)
        return dek, meta.timezone

    async def upsert(
        self,
        user_id: uuid.UUID,
        log_date: date,
        data: DailyLogPutIn,
        idempotency_key: uuid.UUID | None = None,
        raw_body: bytes = b"",
    ) -> tuple[int, DailyLogPutResponse]:
        async with user_transaction(self._db, user_id) as tx:
            dek, tz = await self._user_dek_and_tz(tx, user_id)
            validate_log_date(log_date, tz)

            # Idempotent replay check
            if idempotency_key is not None:
                cached = await repo.get_idempotency(tx, user_id, idempotency_key)
                if cached is not None:
                    req_hash = compute_request_hash(raw_body)
                    if cached.request_hash != req_hash:
                        raise IdempotencyMismatch
                    associated = aad(
                        "idempotency_keys", "response_body_enc", idempotency_key, user_id
                    )
                    body_json = decrypt(dek, cached.response_body_enc, associated)
                    return (
                        cached.response_status,
                        DailyLogPutResponse.model_validate_json(body_json),
                    )

            existing = await repo.get_daily_log(tx, user_id, log_date, for_update=True)

            incoming_payload = DailyLogPayload(
                mood=data.mood,
                energy=data.energy,
                sleep_hours=data.sleep_hours,
                symptom_ids=data.symptom_ids,
                flow=data.flow,
                discharge=data.discharge,
                bbt_c=data.bbt_c,
                intimacy=data.intimacy,
                note=data.note,
                checkin_ms=data.checkin_ms,
            )

            flow_changed = False

            if existing is not None:
                # Last-writer-wins: compare client_updated_at
                if not should_apply_write(existing.client_updated_at, data.client_updated_at):
                    # Stored write is newer; retain stored log
                    existing_payload = decrypt_payload(
                        dek,
                        existing.payload_enc,
                        aad("daily_logs", "payload_enc", existing.id, user_id),
                        DailyLogPayload,
                    )
                    log_resp = DailyLogPutResponse(
                        **to_daily_log(existing, existing_payload).model_dump(),
                        rebuild="not_needed",
                    )
                    return 200, log_resp

                # Incoming write wins
                prev_payload = decrypt_payload(
                    dek,
                    existing.payload_enc,
                    aad("daily_logs", "payload_enc", existing.id, user_id),
                    DailyLogPayload,
                )
                flow_changed = detect_flow_change(prev_payload.flow, incoming_payload.flow)

                new_enc = encrypt_payload(
                    dek,
                    incoming_payload,
                    aad("daily_logs", "payload_enc", existing.id, user_id),
                )
                updated_row = await repo.update_daily_log(
                    tx,
                    id=existing.id,
                    payload_enc=new_enc,
                    client_updated_at=data.client_updated_at,
                )
                active_row = updated_row
            else:
                # Fresh row
                log_id = new_id()
                new_enc = encrypt_payload(
                    dek,
                    incoming_payload,
                    aad("daily_logs", "payload_enc", log_id, user_id),
                )
                created_row = await repo.insert_daily_log(
                    tx,
                    id=log_id,
                    user_id=user_id,
                    log_date=log_date,
                    payload_enc=new_enc,
                    client_updated_at=data.client_updated_at,
                )
                flow_changed = detect_flow_change(None, incoming_payload.flow)
                active_row = created_row

            if flow_changed:
                await publish(
                    tx,
                    user_id,
                    "daily_log.flow_changed",
                    {"log_id": str(active_row.id), "date": str(log_date)},
                )

            response = DailyLogPutResponse(
                **to_daily_log(active_row, incoming_payload).model_dump(),
                rebuild="queued" if flow_changed else "not_needed",
            )

            # Store idempotency response if key provided
            if idempotency_key is not None:
                resp_bytes = response.model_dump_json().encode("utf-8")
                resp_enc = encrypt(
                    dek,
                    resp_bytes,
                    aad("idempotency_keys", "response_body_enc", idempotency_key, user_id),
                )
                await repo.insert_idempotency(
                    tx,
                    user_id=user_id,
                    key=idempotency_key,
                    method="PUT",
                    path=f"/api/v1/daily-logs/{log_date}",
                    request_hash=compute_request_hash(raw_body),
                    response_status=200,
                    response_body_enc=resp_enc,
                )

            return 200, response

    async def get(self, user_id: uuid.UUID, log_date: date) -> DailyLog:
        async with user_transaction(self._db, user_id) as tx:
            dek, _ = await self._user_dek_and_tz(tx, user_id)
            row = await repo.get_daily_log(tx, user_id, log_date)
            if row is None:
                raise DailyLogNotFound
            payload = decrypt_payload(
                dek,
                row.payload_enc,
                aad("daily_logs", "payload_enc", row.id, user_id),
                DailyLogPayload,
            )
            return to_daily_log(row, payload)

    async def get_range(self, user_id: uuid.UUID, from_date: date, to_date: date) -> list[DailyLog]:
        validate_date_range(from_date, to_date)
        async with user_transaction(self._db, user_id) as tx:
            dek, _ = await self._user_dek_and_tz(tx, user_id)
            rows = await repo.get_daily_logs_range(tx, user_id, from_date, to_date)
            items: list[DailyLog] = []
            for row in rows:
                payload = decrypt_payload(
                    dek,
                    row.payload_enc,
                    aad("daily_logs", "payload_enc", row.id, user_id),
                    DailyLogPayload,
                )
                items.append(to_daily_log(row, payload))
            return items

    async def delete(
        self,
        user_id: uuid.UUID,
        log_date: date,
        idempotency_key: uuid.UUID | None = None,
        raw_body: bytes = b"",
    ) -> None:
        async with user_transaction(self._db, user_id) as tx:
            dek, _ = await self._user_dek_and_tz(tx, user_id)

            if idempotency_key is not None:
                cached = await repo.get_idempotency(tx, user_id, idempotency_key)
                if cached is not None:
                    req_hash = compute_request_hash(raw_body)
                    if cached.request_hash != req_hash:
                        raise IdempotencyMismatch
                    return

            deleted_row = await repo.delete_daily_log(tx, user_id, log_date)
            if deleted_row is None:
                raise DailyLogNotFound

            prev_payload = decrypt_payload(
                dek,
                deleted_row.payload_enc,
                aad("daily_logs", "payload_enc", deleted_row.id, user_id),
                DailyLogPayload,
            )
            if detect_flow_change(prev_payload.flow, "none"):
                await publish(
                    tx,
                    user_id,
                    "daily_log.flow_changed",
                    {"log_id": str(deleted_row.id), "date": str(log_date)},
                )

            if idempotency_key is not None:
                empty_enc = encrypt(
                    dek,
                    b"",
                    aad("idempotency_keys", "response_body_enc", idempotency_key, user_id),
                )
                await repo.insert_idempotency(
                    tx,
                    user_id=user_id,
                    key=idempotency_key,
                    method="DELETE",
                    path=f"/api/v1/daily-logs/{log_date}",
                    request_hash=compute_request_hash(raw_body),
                    response_status=204,
                    response_body_enc=empty_enc,
                )
