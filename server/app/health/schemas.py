"""health: Pydantic request, response and payload schemas."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.platform.payloads import Payload
from app.platform.text import clean_text

Mode = Literal["standard", "postpartum", "ttc", "avoid"]
FlowLevel = Literal["none", "spotting", "light", "medium", "heavy"]
Category = Literal["pain", "digestion", "skin", "emotional", "energy", "other"]


class Symptom(BaseModel):
    id: uuid.UUID
    system_key: str | None = None
    category: Category
    name: str
    sort_order: int = 0
    archived: bool = False
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


def _validate_symptom_name(v: str) -> str:
    cleaned = clean_text(v)
    if not cleaned:
        raise ValueError("name must not be empty")
    if len(cleaned) > 50:
        raise ValueError("name must not exceed 50 characters")
    return cleaned


class SymptomCreateIn(BaseModel):
    name: str
    category: Category = "other"
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_symptom_name(v)


class SymptomUpdateIn(BaseModel):
    name: str | None = None
    category: Category | None = None
    sort_order: int | None = None
    archived: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_symptom_name(v)


class SymptomPayload(Payload):
    """`symptoms.payload_enc` (7.2): `{name}`."""

    name: str


class HealthProfilePayload(Payload):
    """`health_profile.payload_enc` (7.2)."""

    mode: Mode = "standard"
    mode_started_on: date | None = None
    usual_cycle_length: int | None = None
    usual_period_length: int | None = None
    last_period_hint: date | None = None
    excluded_cycle_starts: list[date] = Field(default_factory=list)
    exclusion_reasons: dict[str, str] = Field(default_factory=dict)
    forced_period_starts: list[date] = Field(default_factory=list)


class IntimacyPayload(BaseModel):
    logged: bool
    protected: bool | None = None


def _validate_sleep_hours(v: float | None) -> float | None:
    if v is None:
        return None
    if not (0.0 <= v <= 14.0):
        raise ValueError("sleep_hours must be between 0.0 and 14.0")
    if (v * 2) != int(v * 2):
        raise ValueError("sleep_hours must be in 0.5 steps")
    return v


def _validate_bbt(v: float | None) -> float | None:
    if v is None:
        return None
    if not (34.0 <= v <= 40.0):
        raise ValueError("bbt_c must be between 34.0 and 40.0")
    rounded = round(v, 2)
    if abs(v - rounded) > 1e-6:
        raise ValueError("bbt_c must have at most 2 decimal places")
    return rounded


def _validate_note(v: str | None) -> str | None:
    if v is None:
        return None
    cleaned = clean_text(v)
    if len(cleaned) > 2000:
        raise ValueError("note must not exceed 2000 characters")
    return cleaned


class DailyLogPayload(Payload):
    """`daily_logs.payload_enc` (7.2)."""

    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    sleep_hours: float | None = None
    symptom_ids: list[uuid.UUID] = Field(default_factory=list)
    flow: FlowLevel = "none"
    discharge: str | None = None
    bbt_c: float | None = None
    intimacy: IntimacyPayload | None = None
    note: str | None = None
    checkin_ms: int | None = Field(default=None, ge=0)

    @field_validator("sleep_hours")
    @classmethod
    def check_sleep(cls, v: float | None) -> float | None:
        return _validate_sleep_hours(v)

    @field_validator("bbt_c")
    @classmethod
    def check_bbt(cls, v: float | None) -> float | None:
        return _validate_bbt(v)

    @field_validator("note")
    @classmethod
    def check_note(cls, v: str | None) -> str | None:
        return _validate_note(v)


class DailyLogPutIn(BaseModel):
    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    sleep_hours: float | None = None
    symptom_ids: list[uuid.UUID] = Field(default_factory=list)
    flow: FlowLevel = "none"
    discharge: str | None = None
    bbt_c: float | None = None
    intimacy: IntimacyPayload | None = None
    note: str | None = None
    checkin_ms: int | None = Field(default=None, ge=0)
    client_updated_at: datetime

    @field_validator("sleep_hours")
    @classmethod
    def check_sleep(cls, v: float | None) -> float | None:
        return _validate_sleep_hours(v)

    @field_validator("bbt_c")
    @classmethod
    def check_bbt(cls, v: float | None) -> float | None:
        return _validate_bbt(v)

    @field_validator("note")
    @classmethod
    def check_note(cls, v: str | None) -> str | None:
        return _validate_note(v)


class DailyLog(BaseModel):
    id: uuid.UUID
    date: date
    mood: int | None = None
    energy: int | None = None
    sleep_hours: float | None = None
    symptom_ids: list[uuid.UUID] = Field(default_factory=list)
    flow: FlowLevel = "none"
    discharge: str | None = None
    bbt_c: float | None = None
    intimacy: IntimacyPayload | None = None
    note: str | None = None
    checkin_ms: int | None = None
    client_updated_at: datetime
    created_at: datetime
    updated_at: datetime


class DailyLogPutResponse(DailyLog):
    rebuild: Literal["queued", "not_needed"]


class PeriodStartIn(BaseModel):
    date: date


class PeriodEndIn(BaseModel):
    date: date


class PeriodActionResponse(BaseModel):
    date: date
    flow: FlowLevel
    rebuild: Literal["queued", "not_needed"]


class CalendarDay(BaseModel):
    date: date
    flow: FlowLevel | None = None
    predicted: bool = False
    fertile: bool = False
    has_log: bool = False
    events: list[dict[str, Any]] = Field(default_factory=list)
    doses: list[dict[str, Any]] = Field(default_factory=list)


class CalendarMonthResponse(BaseModel):
    month: str
    days: list[CalendarDay]


class CheckinState(BaseModel):
    done: bool
    log: DailyLog | None = None


class CycleCard(BaseModel):
    cycle_day: int | None = None
    state: str | None = None
    days_until: int | None = None
    range_low: date | None = None
    range_high: date | None = None
    suppressed_reason: str | None = None


class TodayItem(BaseModel):
    type: str
    id: str
    title: str | None = None


class TodayResponse(BaseModel):
    date: date
    greeting: Literal["morning", "afternoon", "evening", "night"]
    cycle_card: CycleCard | None = None
    checkin: CheckinState
    streak: int
    items: list[TodayItem] = Field(default_factory=list)
    unread_inbox: int = 0


# ---------------------------------------------------------------------------
# Cycle, Profile & Prediction Schemas (spec 9.2, 9.3, CYC-1, CYC-5, CYC-7)
# ---------------------------------------------------------------------------


class HealthProfileResponse(BaseModel):
    mode: Mode
    mode_started_on: date | None = None
    usual_cycle_length: int | None = None
    usual_period_length: int | None = None
    last_period_hint: date | None = None


class HealthProfileUpdateIn(BaseModel):
    mode: Mode | None = None
    mode_started_on: date | None = None
    usual_cycle_length: int | None = Field(default=None, ge=15, le=60)
    usual_period_length: int | None = Field(default=None, ge=1, le=15)
    last_period_hint: date | None = None


class CyclePayload(Payload):
    """`cycles.payload_enc` (7.2)."""

    start_date: date
    end_date: date | None = None
    length_days: int | None = None
    period_length_days: int
    is_complete: bool
    excluded: bool = False
    exclusion_reason: str | None = None
    postpartum: bool = False


class CycleHistoryItem(BaseModel):
    seq: int
    start_date: date
    end_date: date | None = None
    length_days: int | None = None
    period_length_days: int
    is_complete: bool
    excluded: bool = False
    exclusion_reason: str | None = None
    postpartum: bool = False


Confidence = Literal["high", "medium", "low", "none"]
Phase = Literal["menstrual", "follicular", "fertile_window", "luteal"]
DerivedStateKind = Literal[
    "on_period",
    "upcoming",
    "window",
    "late",
    "long_gap",
    "irregular",
    "waiting",
    "no_data",
]


class CyclePredictionPayload(Payload):
    """`cycle_predictions.payload_enc` (7.2)."""

    for_cycle_start: date | None = None
    predicted_start: date | None = None
    range_low: date | None = None
    range_high: date | None = None
    ovulation_est: date | None = None
    fertile_start: date | None = None
    fertile_end: date | None = None
    confidence: Confidence = "none"
    n_cycles: int = 0
    mean_len: float | None = None
    sd_len: float | None = None
    mean_period_len: int | None = None
    suppressed_reason: str | None = None


class CyclePredictionResponse(BaseModel):
    predicted_start: date | None = None
    range_low: date | None = None
    range_high: date | None = None
    ovulation_est: date | None = None
    fertile_start: date | None = None
    fertile_end: date | None = None
    confidence: Confidence = "none"
    n_cycles: int = 0
    mean_len: float | None = None
    sd_len: float | None = None
    mean_period_len: int | None = None
    algorithm_version: str = "calendar-1.0"
    suppressed_reason: str | None = None


class PendingPrompt(BaseModel):
    kind: Literal["new_period", "confirm_length"]
    date: date


class CycleNote(BaseModel):
    kind: str
    text: str | None = None


class CycleStateResponse(BaseModel):
    cycle_day: int | None = None
    latest_start: date | None = None
    phase: Phase | None = None
    state: DerivedStateKind
    prediction: CyclePredictionResponse | None = None
    notes: list[CycleNote] = Field(default_factory=list)
    pending_prompt: PendingPrompt | None = None
    mode: Mode = "standard"


class CycleExclusionIn(BaseModel):
    start_date: date
    excluded: bool
    reason: str | None = None


class PeriodStartConfirmIn(BaseModel):
    date: date
    is_new_period: bool
