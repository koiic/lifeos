"""health: Pydantic request, response and payload schemas."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.platform.payloads import Payload
from app.platform.text import clean_text

Mode = Literal["standard", "postpartum", "ttc", "avoid"]
FlowLevel = Literal["none", "spotting", "light", "medium", "heavy"]


class SymptomPayload(Payload):
    """`symptoms.payload_enc` (7.2): `{name}`."""

    name: str


class HealthProfilePayload(Payload):
    """`health_profile.payload_enc` (7.2); only the mode is read here (the health-profile task
    owns the rest)."""

    mode: Mode = "standard"


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
