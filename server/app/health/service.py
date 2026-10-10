"""health: Service layer: rules and transactions (plan 4.2)."""

import calendar
import hashlib
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from app.health import engine, repo
from app.health.schemas import (
    CalendarDay,
    CalendarMonthResponse,
    CheckinState,
    CycleCard,
    CycleHistoryItem,
    CycleNote,
    CyclePayload,
    CyclePredictionPayload,
    CyclePredictionResponse,
    CycleStateResponse,
    DailyLog,
    DailyLogPayload,
    DailyLogPutIn,
    DailyLogPutResponse,
    DerivedStateKind,
    FlowLevel,
    HealthProfilePayload,
    HealthProfileResponse,
    HealthProfileUpdateIn,
    Mode,
    PendingPrompt,
    PeriodActionResponse,
    Phase,
    Symptom,
    SymptomCreateIn,
    SymptomPayload,
    SymptomUpdateIn,
    TodayResponse,
)
from app.health.streak import compute_streak
from app.platform.clock import utc_now
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
from app.platform.jobs import defer_for_user
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


class SymptomNotFound(HealthError):
    status = 404
    detail = "Symptom not found."


class IdempotencyMismatch(HealthError):
    status = 422
    detail = "Idempotency key was previously used with a different request body."


class InvalidMonthError(HealthError):
    status = 422
    detail = "Month must be in YYYY-MM format between 1990 and 2100."


class CycleNotFound(HealthError):
    status = 404
    detail = "Cycle with this start date was not found."


def parse_and_validate_month(month_str: str) -> tuple[int, int]:
    try:
        parts = month_str.split("-")
        if len(parts) != 2:
            raise ValueError
        year = int(parts[0])
        month = int(parts[1])
        if not (1990 <= year <= 2100 and 1 <= month <= 12):
            raise ValueError
        return year, month
    except Exception as err:
        raise InvalidMonthError from err


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

    async def start_period(
        self,
        user_id: uuid.UUID,
        start_date: date,
    ) -> PeriodActionResponse:
        async with user_transaction(self._db, user_id) as tx:
            dek, tz = await self._user_dek_and_tz(tx, user_id)
            validate_log_date(start_date, tz)

            existing = await repo.get_daily_log(tx, user_id, start_date)
            now = utc_now()
            rebuild: Literal["queued", "not_needed"] = "not_needed"
            final_flow: FlowLevel = "medium"

            if existing is None:
                log_id = new_id()
                payload = DailyLogPayload(flow="medium")
                associated = aad("daily_logs", "payload_enc", log_id, user_id)
                enc = encrypt_payload(dek, payload, associated)
                await repo.insert_daily_log(
                    tx,
                    id=log_id,
                    user_id=user_id,
                    log_date=start_date,
                    payload_enc=enc,
                    client_updated_at=now,
                )
                rebuild = "queued"
                await publish(
                    tx,
                    user_id,
                    "daily_log.flow_changed",
                    {"log_id": str(log_id), "date": str(start_date)},
                )
            else:
                associated = aad("daily_logs", "payload_enc", existing.id, user_id)
                payload = decrypt_payload(dek, existing.payload_enc, associated, DailyLogPayload)
                prev_flow = payload.flow
                if prev_flow in ("light", "medium", "heavy"):
                    final_flow = prev_flow
                    rebuild = "not_needed"
                else:
                    final_flow = "medium"
                    updated_payload = payload.model_copy(update={"flow": "medium"})
                    enc = encrypt_payload(dek, updated_payload, associated)
                    await repo.update_daily_log(
                        tx,
                        id=existing.id,
                        payload_enc=enc,
                        client_updated_at=now,
                    )
                    rebuild = "queued"
                    await publish(
                        tx,
                        user_id,
                        "daily_log.flow_changed",
                        {"log_id": str(existing.id), "date": str(start_date)},
                    )

            return PeriodActionResponse(date=start_date, flow=final_flow, rebuild=rebuild)

    async def end_period(
        self,
        user_id: uuid.UUID,
        last_flow_date: date,
    ) -> PeriodActionResponse:
        async with user_transaction(self._db, user_id) as tx:
            dek, tz = await self._user_dek_and_tz(tx, user_id)
            validate_log_date(last_flow_date, tz)

            existing = await repo.get_daily_log(tx, user_id, last_flow_date)
            now = utc_now()
            final_flow: FlowLevel = "medium"
            rebuild: Literal["queued", "not_needed"] = "not_needed"

            if existing is None:
                log_id = new_id()
                payload = DailyLogPayload(flow="medium")
                associated = aad("daily_logs", "payload_enc", log_id, user_id)
                enc = encrypt_payload(dek, payload, associated)
                await repo.insert_daily_log(
                    tx,
                    id=log_id,
                    user_id=user_id,
                    log_date=last_flow_date,
                    payload_enc=enc,
                    client_updated_at=now,
                )
                rebuild = "queued"
                await publish(
                    tx,
                    user_id,
                    "daily_log.flow_changed",
                    {"log_id": str(log_id), "date": str(last_flow_date)},
                )
            else:
                associated = aad("daily_logs", "payload_enc", existing.id, user_id)
                payload = decrypt_payload(dek, existing.payload_enc, associated, DailyLogPayload)
                final_flow = (
                    payload.flow if payload.flow in ("light", "medium", "heavy") else "medium"
                )
                if payload.flow != final_flow:
                    updated_payload = payload.model_copy(update={"flow": final_flow})
                    enc = encrypt_payload(dek, updated_payload, associated)
                    await repo.update_daily_log(
                        tx,
                        id=existing.id,
                        payload_enc=enc,
                        client_updated_at=now,
                    )
                    rebuild = "queued"
                    await publish(
                        tx,
                        user_id,
                        "daily_log.flow_changed",
                        {"log_id": str(existing.id), "date": str(last_flow_date)},
                    )

            # Clear trailing flow days in the same episode (within 14 days after last_flow_date)
            future_cutoff = last_flow_date + timedelta(days=14)
            trailing_logs = await repo.get_daily_logs_range(
                tx, user_id, last_flow_date + timedelta(days=1), future_cutoff
            )
            for row in trailing_logs:
                row_associated = aad("daily_logs", "payload_enc", row.id, user_id)
                row_payload = decrypt_payload(dek, row.payload_enc, row_associated, DailyLogPayload)
                if row_payload.flow in ("light", "medium", "heavy", "spotting"):
                    cleared_payload = row_payload.model_copy(update={"flow": "none"})
                    cleared_enc = encrypt_payload(dek, cleared_payload, row_associated)
                    await repo.update_daily_log(
                        tx,
                        id=row.id,
                        payload_enc=cleared_enc,
                        client_updated_at=now,
                    )
                    rebuild = "queued"
                    await publish(
                        tx,
                        user_id,
                        "daily_log.flow_changed",
                        {"log_id": str(row.id), "date": str(row.date)},
                    )

            return PeriodActionResponse(date=last_flow_date, flow=final_flow, rebuild=rebuild)

    async def get_calendar_month(
        self,
        user_id: uuid.UUID,
        month_str: str | None = None,
    ) -> CalendarMonthResponse:
        async with user_transaction(self._db, user_id) as tx:
            dek, tz = await self._user_dek_and_tz(tx, user_id)

            if month_str is None:
                local_now = datetime.now(ZoneInfo(tz))
                year = local_now.year
                month = local_now.month
                month_str = f"{year:04d}-{month:02d}"
            else:
                year, month = parse_and_validate_month(month_str)

            _, num_days = calendar.monthrange(year, month)
            start_date = date(year, month, 1)
            end_date = date(year, month, num_days)

            logs = await repo.get_daily_logs_range(tx, user_id, start_date, end_date)
            flow_by_date: dict[date, FlowLevel] = {}
            for row in logs:
                associated = aad("daily_logs", "payload_enc", row.id, user_id)
                payload = decrypt_payload(dek, row.payload_enc, associated, DailyLogPayload)
                flow_by_date[row.date] = payload.flow

            days: list[CalendarDay] = []
            for day_num in range(1, num_days + 1):
                d = date(year, month, day_num)
                if d in flow_by_date:
                    days.append(
                        CalendarDay(
                            date=d,
                            flow=flow_by_date[d],
                            predicted=False,
                            fertile=False,
                            has_log=True,
                            events=[],
                            doses=[],
                        )
                    )
                else:
                    days.append(
                        CalendarDay(
                            date=d,
                            flow=None,
                            predicted=False,
                            fertile=False,
                            has_log=False,
                            events=[],
                            doses=[],
                        )
                    )

            return CalendarMonthResponse(month=month_str, days=days)

    async def get_today(
        self, user_id: uuid.UUID, target_date_param: date | None = None
    ) -> TodayResponse:
        """Aggregated Today payload for date (spec 9.3, TOD-3, TOD-5)."""
        async with user_transaction(self._db, user_id) as tx:
            meta = await repo.user_meta(tx, user_id)
            dek = unwrap_dek(self._keyring, meta.kek_version, meta.dek_wrapped, user_id)

            local_now = datetime.now(ZoneInfo(meta.timezone))
            today_local = local_now.date()

            if target_date_param is not None:
                if target_date_param > today_local:
                    raise FutureDateError("Requested date cannot be in the future")
                target_date = target_date_param
                is_today = target_date == today_local
            else:
                target_date = today_local
                is_today = True

            # Daily log on target_date
            row = await repo.get_daily_log(tx, user_id, target_date)
            if row is not None:
                associated = aad("daily_logs", "payload_enc", row.id, user_id)
                payload = decrypt_payload(dek, row.payload_enc, associated, DailyLogPayload)
                checkin = CheckinState(done=True, log=to_daily_log(row, payload))
            else:
                checkin = CheckinState(done=False, log=None)

            # Streak calculation
            logged_dates = await repo.get_logged_dates(tx, user_id, up_to_date=target_date)
            streak = compute_streak(logged_dates, target_date, is_today=is_today)

            # Greeting based on local hour
            hour = local_now.hour
            greeting: Literal["morning", "afternoon", "evening", "night"]
            if 5 <= hour < 12:
                greeting = "morning"
            elif 12 <= hour < 17:
                greeting = "afternoon"
            elif 17 <= hour < 22:
                greeting = "evening"
            else:
                greeting = "night"

            # Cycle card calculation
            _, pred, derived_state = await self._rebuild_for_user_tx(
                tx, user_id, dek, meta.timezone, today_param=target_date
            )
            if derived_state.state == "waiting":
                cycle_card = CycleCard(
                    cycle_day=derived_state.cycle_day,
                    state="waiting",
                    days_until=None,
                    range_low=None,
                    range_high=None,
                    suppressed_reason=pred.suppressed_reason or "postpartum_waiting",
                )
            elif derived_state.state == "no_data":
                cycle_card = CycleCard(
                    cycle_day=None,
                    state="no_data",
                    days_until=None,
                    range_low=None,
                    range_high=None,
                    suppressed_reason=pred.suppressed_reason or "no_data",
                )
            else:
                cycle_card = CycleCard(
                    cycle_day=derived_state.cycle_day,
                    state=derived_state.state,
                    days_until=derived_state.days_until,
                    range_low=pred.range_low,
                    range_high=pred.range_high,
                    suppressed_reason=pred.suppressed_reason,
                )

            return TodayResponse(
                date=target_date,
                greeting=greeting,
                cycle_card=cycle_card,
                checkin=checkin,
                streak=streak,
                items=[],
                unread_inbox=0,
            )

    async def _rebuild_for_user_tx(
        self,
        tx: Transaction,
        user_id: uuid.UUID,
        dek: DataKey,
        tz: str,
        profile_payload: HealthProfilePayload | None = None,
        today_param: date | None = None,
    ) -> tuple[list[engine.Cycle], engine.Prediction, engine.DerivedState]:
        if profile_payload is None:
            p_row = await repo.get_health_profile(tx, user_id)
            if p_row is not None:
                p_aad = aad("health_profile", "payload_enc", user_id, user_id)
                profile_payload = decrypt_payload(
                    dek, p_row.payload_enc, p_aad, HealthProfilePayload
                )
            else:
                profile_payload = HealthProfilePayload()

        engine_profile = engine.CycleEngineProfile(
            mode=profile_payload.mode,
            mode_started_on=profile_payload.mode_started_on,
            usual_cycle_length=profile_payload.usual_cycle_length,
            usual_period_length=profile_payload.usual_period_length or 5,
            last_period_hint=profile_payload.last_period_hint,
            user_excluded_cycles=frozenset(profile_payload.excluded_cycle_starts),
            forced_period_starts=frozenset(profile_payload.forced_period_starts),
        )

        log_rows = await repo.get_all_daily_logs_for_rebuild(tx, user_id)
        flow_by_date: dict[date, Any] = {}
        logged_dates: set[date] = set()

        for lr in log_rows:
            logged_dates.add(lr.date)
            l_aad = aad("daily_logs", "payload_enc", lr.id, user_id)
            l_payload = decrypt_payload(dek, lr.payload_enc, l_aad, DailyLogPayload)
            if l_payload.flow in ("spotting", "light", "medium", "heavy"):
                flow_by_date[lr.date] = l_payload.flow

        if today_param is not None:
            today = today_param
        else:
            local_now = datetime.now(ZoneInfo(tz))
            today = local_now.date()

        cycles, pred, derived_state = engine.rebuild_and_predict(
            today=today,
            flow_by_date=flow_by_date,
            profile=engine_profile,
            logged_dates=logged_dates,
        )

        new_cycle_rows: list[repo.NewCycleRow] = []
        for seq_idx, c in enumerate(cycles, start=1):
            c_id = new_id()
            c_payload = CyclePayload(
                start_date=c.start_date,
                end_date=c.end_date,
                length_days=c.length_days,
                period_length_days=c.period_length_days,
                is_complete=c.is_complete,
                excluded=c.excluded,
                exclusion_reason=c.exclusion_reason,
                postpartum=(c.exclusion_reason == "postpartum"),
            )
            c_aad = aad("cycles", "payload_enc", c_id, user_id)
            c_enc = encrypt_payload(dek, c_payload, c_aad)
            new_cycle_rows.append(repo.NewCycleRow(id=c_id, seq=seq_idx, payload_enc=c_enc))

        await repo.replace_cycles(tx, user_id, new_cycle_rows)

        now = utc_now()
        await repo.supersede_active_predictions(tx, user_id, now)

        pred_id = new_id()
        for_start = cycles[-1].start_date if cycles else profile_payload.last_period_hint
        pred_payload = CyclePredictionPayload(
            for_cycle_start=for_start,
            predicted_start=pred.predicted_start,
            range_low=pred.range_low,
            range_high=pred.range_high,
            ovulation_est=pred.ovulation_est,
            fertile_start=pred.fertile[0] if pred.fertile else None,
            fertile_end=pred.fertile[1] if pred.fertile else None,
            confidence=pred.confidence,  # type: ignore[arg-type]
            n_cycles=pred.n_cycles,
            mean_len=pred.mean_len,
            sd_len=pred.sd_len,
            mean_period_len=round(pred.mean_period_len)
            if pred.mean_period_len is not None
            else None,
            suppressed_reason=pred.suppressed_reason,
        )
        p_aad = aad("cycle_predictions", "payload_enc", pred_id, user_id)
        p_enc = encrypt_payload(dek, pred_payload, p_aad)
        await repo.insert_prediction(
            tx,
            pred_id=pred_id,
            user_id=user_id,
            algorithm_version=engine.ALGO_VERSION,
            payload_enc=p_enc,
            created_at=now,
        )

        await publish(
            tx,
            user_id,
            "prediction.updated",
            {"user_id": str(user_id), "prediction_id": str(pred_id)},
        )

        return cycles, pred, derived_state

    async def rebuild_for_user(
        self, user_id: uuid.UUID
    ) -> tuple[list[engine.Cycle], engine.Prediction, engine.DerivedState]:
        async with user_transaction(self._db, user_id) as tx:
            dek, tz = await self._user_dek_and_tz(tx, user_id)
            return await self._rebuild_for_user_tx(tx, user_id, dek, tz)

    async def get_health_profile(self, user_id: uuid.UUID) -> HealthProfileResponse:
        async with user_transaction(self._db, user_id) as tx:
            dek, _ = await self._user_dek_and_tz(tx, user_id)
            row = await repo.get_health_profile(tx, user_id)
            if row is None:
                return HealthProfileResponse(mode="standard")
            associated = aad("health_profile", "payload_enc", user_id, user_id)
            payload = decrypt_payload(dek, row.payload_enc, associated, HealthProfilePayload)
            return HealthProfileResponse(
                mode=payload.mode,
                mode_started_on=payload.mode_started_on,
                usual_cycle_length=payload.usual_cycle_length,
                usual_period_length=payload.usual_period_length,
                last_period_hint=payload.last_period_hint,
            )

    async def update_health_profile(
        self, user_id: uuid.UUID, update_in: HealthProfileUpdateIn
    ) -> HealthProfileResponse:
        async with user_transaction(self._db, user_id) as tx:
            dek, tz = await self._user_dek_and_tz(tx, user_id)
            row = await repo.get_health_profile(tx, user_id)
            associated = aad("health_profile", "payload_enc", user_id, user_id)
            if row is None:
                current_payload = HealthProfilePayload()
            else:
                current_payload = decrypt_payload(
                    dek, row.payload_enc, associated, HealthProfilePayload
                )

            mode_changed = update_in.mode is not None and update_in.mode != current_payload.mode
            new_mode = update_in.mode if update_in.mode is not None else current_payload.mode

            new_mode_started_on: date | None
            if mode_changed:
                if update_in.mode_started_on is not None:
                    new_mode_started_on = update_in.mode_started_on
                else:
                    local_now = datetime.now(ZoneInfo(tz))
                    new_mode_started_on = local_now.date()
            else:
                new_mode_started_on = (
                    update_in.mode_started_on
                    if update_in.mode_started_on is not None
                    else current_payload.mode_started_on
                )

            updated_payload = current_payload.model_copy(
                update={
                    "mode": new_mode,
                    "mode_started_on": new_mode_started_on,
                    "usual_cycle_length": (
                        update_in.usual_cycle_length
                        if update_in.usual_cycle_length is not None
                        else current_payload.usual_cycle_length
                    ),
                    "usual_period_length": (
                        update_in.usual_period_length
                        if update_in.usual_period_length is not None
                        else current_payload.usual_period_length
                    ),
                    "last_period_hint": (
                        update_in.last_period_hint
                        if update_in.last_period_hint is not None
                        else current_payload.last_period_hint
                    ),
                }
            )
            enc = encrypt_payload(dek, updated_payload, associated)
            await repo.upsert_health_profile(tx, user_id, enc)
            await publish(tx, user_id, "health_profile.changed", {"user_id": str(user_id)})
            await self._rebuild_for_user_tx(tx, user_id, dek, tz, updated_payload)

            return HealthProfileResponse(
                mode=updated_payload.mode,
                mode_started_on=updated_payload.mode_started_on,
                usual_cycle_length=updated_payload.usual_cycle_length,
                usual_period_length=updated_payload.usual_period_length,
                last_period_hint=updated_payload.last_period_hint,
            )

    async def set_cycle_exclusion(
        self,
        user_id: uuid.UUID,
        start_date: date,
        excluded: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        async with user_transaction(self._db, user_id) as tx:
            dek, tz = await self._user_dek_and_tz(tx, user_id)
            row = await repo.get_health_profile(tx, user_id)
            associated = aad("health_profile", "payload_enc", user_id, user_id)
            current_payload = (
                decrypt_payload(dek, row.payload_enc, associated, HealthProfilePayload)
                if row is not None
                else HealthProfilePayload()
            )
            excluded_starts = list(current_payload.excluded_cycle_starts)
            reasons = dict(current_payload.exclusion_reasons)

            date_key = start_date.isoformat()
            if excluded:
                if start_date not in excluded_starts:
                    excluded_starts.append(start_date)
                if reason:
                    reasons[date_key] = reason
            else:
                if start_date in excluded_starts:
                    excluded_starts.remove(start_date)
                reasons.pop(date_key, None)

            updated_payload = current_payload.model_copy(
                update={
                    "excluded_cycle_starts": excluded_starts,
                    "exclusion_reasons": reasons,
                }
            )
            enc = encrypt_payload(dek, updated_payload, associated)
            await repo.upsert_health_profile(tx, user_id, enc)
            await publish(tx, user_id, "health_profile.changed", {"user_id": str(user_id)})
            await self._rebuild_for_user_tx(tx, user_id, dek, tz, updated_payload)

            return {
                "start_date": start_date,
                "excluded": excluded,
                "reason": reason,
                "rebuild": "queued",
            }

    async def confirm_period_start(
        self, user_id: uuid.UUID, date_val: date, is_new_period: bool
    ) -> dict[str, Any]:
        async with user_transaction(self._db, user_id) as tx:
            dek, tz = await self._user_dek_and_tz(tx, user_id)
            row = await repo.get_health_profile(tx, user_id)
            associated = aad("health_profile", "payload_enc", user_id, user_id)
            current_payload = (
                decrypt_payload(dek, row.payload_enc, associated, HealthProfilePayload)
                if row is not None
                else HealthProfilePayload()
            )
            forced = list(current_payload.forced_period_starts)
            if is_new_period:
                if date_val not in forced:
                    forced.append(date_val)
            else:
                if date_val in forced:
                    forced.remove(date_val)

            updated_payload = current_payload.model_copy(update={"forced_period_starts": forced})
            enc = encrypt_payload(dek, updated_payload, associated)
            await repo.upsert_health_profile(tx, user_id, enc)
            await publish(tx, user_id, "health_profile.changed", {"user_id": str(user_id)})
            await self._rebuild_for_user_tx(tx, user_id, dek, tz, updated_payload)

            return {"date": date_val, "is_new_period": is_new_period, "rebuild": "queued"}

    async def get_cycle_state(self, user_id: uuid.UUID) -> CycleStateResponse:
        async with user_transaction(self._db, user_id) as tx:
            dek, tz = await self._user_dek_and_tz(tx, user_id)
            p_row = await repo.get_health_profile(tx, user_id)
            if p_row is not None:
                p_aad = aad("health_profile", "payload_enc", user_id, user_id)
                profile_payload = decrypt_payload(
                    dek, p_row.payload_enc, p_aad, HealthProfilePayload
                )
            else:
                profile_payload = HealthProfilePayload()

            cycles, pred, derived_state = await self._rebuild_for_user_tx(
                tx, user_id, dek, tz, profile_payload
            )

            log_rows = await repo.get_all_daily_logs_for_rebuild(tx, user_id)
            flow_by_date: dict[date, Any] = {}
            for lr in log_rows:
                l_aad = aad("daily_logs", "payload_enc", lr.id, user_id)
                l_payload = decrypt_payload(dek, lr.payload_enc, l_aad, DailyLogPayload)
                if l_payload.flow in ("spotting", "light", "medium", "heavy"):
                    flow_by_date[lr.date] = l_payload.flow

            forced = frozenset(profile_payload.forced_period_starts)
            episodes = engine.find_bleed_episodes(flow_by_date)
            classified = engine.classify_episodes(episodes, forced)
            intra_bleeds = [ep for ep in classified if ep.is_intra_cycle]
            pending_prompt: PendingPrompt | None = None
            if intra_bleeds:
                pending_prompt = PendingPrompt(
                    kind="new_period",
                    date=intra_bleeds[-1].start_date,
                )

            notes: list[CycleNote] = []
            if derived_state.is_irregular:
                notes.append(
                    CycleNote(
                        kind="irregular",
                        text=derived_state.message if derived_state.state == "irregular" else None,
                    )
                )
            if derived_state.has_long_gap:
                notes.append(
                    CycleNote(
                        kind="long_gap",
                        text=derived_state.message if derived_state.state == "long_gap" else None,
                    )
                )

            pred_resp = CyclePredictionResponse(
                predicted_start=pred.predicted_start,
                range_low=pred.range_low,
                range_high=pred.range_high,
                ovulation_est=pred.ovulation_est,
                fertile_start=pred.fertile[0] if pred.fertile else None,
                fertile_end=pred.fertile[1] if pred.fertile else None,
                confidence=pred.confidence,  # type: ignore[arg-type]
                n_cycles=pred.n_cycles,
                mean_len=pred.mean_len,
                sd_len=pred.sd_len,
                mean_period_len=round(pred.mean_period_len)
                if pred.mean_period_len is not None
                else None,
                algorithm_version=engine.ALGO_VERSION,
                suppressed_reason=pred.suppressed_reason,
            )

            latest_start = cycles[-1].start_date if cycles else profile_payload.last_period_hint

            return CycleStateResponse(
                cycle_day=derived_state.cycle_day,
                latest_start=latest_start,
                phase=cast(Phase | None, derived_state.phase),
                state=cast(DerivedStateKind, derived_state.state),
                prediction=pred_resp,
                notes=notes,
                pending_prompt=pending_prompt,
                mode=profile_payload.mode,
            )

    async def get_cycles_history(self, user_id: uuid.UUID) -> list[CycleHistoryItem]:
        async with user_transaction(self._db, user_id) as tx:
            dek, tz = await self._user_dek_and_tz(tx, user_id)
            await self._rebuild_for_user_tx(tx, user_id, dek, tz)
            rows = await repo.get_cycles(tx, user_id)
            items: list[CycleHistoryItem] = []
            for r in rows:
                c_aad = aad("cycles", "payload_enc", r.id, user_id)
                p = decrypt_payload(dek, r.payload_enc, c_aad, CyclePayload)
                items.append(
                    CycleHistoryItem(
                        seq=r.seq,
                        start_date=p.start_date,
                        end_date=p.end_date,
                        length_days=p.length_days,
                        period_length_days=p.period_length_days,
                        is_complete=p.is_complete,
                        excluded=p.excluded,
                        exclusion_reason=p.exclusion_reason,
                        postpartum=p.postpartum,
                    )
                )
            return items

    async def nightly_predict_all_users(self, job_app: Any, jobs_engine: Database) -> None:
        async with jobs_engine.begin() as conn:
            user_ids = await repo.get_all_users_for_nightly_predict(conn)
        for uid in user_ids:
            await defer_for_user(job_app, "health.rebuild_cycles", uid)


class SymptomService:
    def __init__(self, engine: Database, keyring: Keyring) -> None:
        self._db = engine
        self._keyring = keyring

    async def _user_dek(self, tx: Transaction, user_id: uuid.UUID) -> DataKey:
        meta = await repo.user_meta(tx, user_id)
        return unwrap_dek(self._keyring, meta.kek_version, meta.dek_wrapped, user_id)

    async def list(self, user_id: uuid.UUID, include_archived: bool = False) -> list[Symptom]:
        async with user_transaction(self._db, user_id) as tx:
            dek = await self._user_dek(tx, user_id)
            rows = await repo.list_symptoms(tx, user_id, include_archived=include_archived)
            results = []
            for r in rows:
                associated = aad("symptoms", "payload_enc", r.id, user_id)
                payload = decrypt_payload(dek, r.payload_enc, associated, SymptomPayload)
                results.append(
                    Symptom(
                        id=r.id,
                        system_key=r.system_key,
                        category=r.category,  # type: ignore[arg-type]
                        name=payload.name,
                        sort_order=r.sort_order,
                        archived=r.archived_at is not None,
                        archived_at=r.archived_at,
                        created_at=r.created_at,
                        updated_at=r.updated_at,
                    )
                )
            return results

    async def get(self, user_id: uuid.UUID, symptom_id: uuid.UUID) -> Symptom:
        async with user_transaction(self._db, user_id) as tx:
            dek = await self._user_dek(tx, user_id)
            r = await repo.get_symptom(tx, user_id, symptom_id)
            if r is None:
                raise SymptomNotFound()
            associated = aad("symptoms", "payload_enc", r.id, user_id)
            payload = decrypt_payload(dek, r.payload_enc, associated, SymptomPayload)
            return Symptom(
                id=r.id,
                system_key=r.system_key,
                category=r.category,  # type: ignore[arg-type]
                name=payload.name,
                sort_order=r.sort_order,
                archived=r.archived_at is not None,
                archived_at=r.archived_at,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )

    async def create(self, user_id: uuid.UUID, data: SymptomCreateIn) -> Symptom:
        symptom_id = new_id()
        async with user_transaction(self._db, user_id) as tx:
            dek = await self._user_dek(tx, user_id)
            associated = aad("symptoms", "payload_enc", symptom_id, user_id)
            payload_enc = encrypt_payload(dek, SymptomPayload(name=data.name), associated)
            new_row = repo.NewSymptom(
                id=symptom_id,
                system_key=None,
                category=data.category,
                sort_order=data.sort_order,
                payload_enc=payload_enc,
            )
            r = await repo.insert_symptom(tx, user_id, new_row)
            return Symptom(
                id=r.id,
                system_key=r.system_key,
                category=r.category,  # type: ignore[arg-type]
                name=data.name,
                sort_order=r.sort_order,
                archived=r.archived_at is not None,
                archived_at=r.archived_at,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )

    async def update(
        self, user_id: uuid.UUID, symptom_id: uuid.UUID, data: SymptomUpdateIn
    ) -> Symptom:
        async with user_transaction(self._db, user_id) as tx:
            existing = await repo.get_symptom(tx, user_id, symptom_id)
            if existing is None:
                raise SymptomNotFound()

            dek = await self._user_dek(tx, user_id)
            payload_enc = None
            name = None
            if data.name is not None:
                name = data.name
                associated = aad("symptoms", "payload_enc", symptom_id, user_id)
                payload_enc = encrypt_payload(dek, SymptomPayload(name=name), associated)
            else:
                associated = aad("symptoms", "payload_enc", symptom_id, user_id)
                existing_payload = decrypt_payload(
                    dek, existing.payload_enc, associated, SymptomPayload
                )
                name = existing_payload.name

            archived_at = None
            touch_archived = False
            if data.archived is not None:
                touch_archived = True
                archived_at = (existing.archived_at or utc_now()) if data.archived else None

            r = await repo.update_symptom(
                tx,
                user_id=user_id,
                symptom_id=symptom_id,
                category=data.category,
                sort_order=data.sort_order,
                payload_enc=payload_enc,
                archived_at=archived_at,
                touch_archived=touch_archived,
            )
            if r is None:
                raise SymptomNotFound()

            return Symptom(
                id=r.id,
                system_key=r.system_key,
                category=r.category,  # type: ignore[arg-type]
                name=name,
                sort_order=r.sort_order,
                archived=r.archived_at is not None,
                archived_at=r.archived_at,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )

    async def archive(self, user_id: uuid.UUID, symptom_id: uuid.UUID) -> None:
        async with user_transaction(self._db, user_id) as tx:
            found = await repo.archive_symptom(tx, user_id, symptom_id)
            if not found:
                raise SymptomNotFound()
