"""core: Pydantic request, response and payload schemas.

`/me` (spec 9.2, CR-030): her profile, settings, consent and health mode; versions are
`updated_at` (CR-004).
"""

from datetime import datetime
from functools import cache
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_validator,
)

from app.platform.text import DisplayName, clean_text

Theme = Literal["system", "light", "dark"]
# 9.1 "local times as `HH:MM`".
LocalTime = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]

# 12.6, CR-030: the consent wording's version; it changes when the consent screen's text does.
CONSENT_VERSION = "1"


@cache
def iana_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def check_timezone(value: str) -> str:
    if value not in iana_timezones():
        raise ValueError("not an IANA timezone")
    return value


# 9.4: every string is cleaned (trimmed, controls stripped, NFC) before it is checked.
Cleaned = BeforeValidator(lambda v: clean_text(v) if isinstance(v, str) else v)
Timezone = Annotated[str, StringConstraints(max_length=64), Cleaned, AfterValidator(check_timezone)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Change(Strict):
    """A partial change: at least one field, and no field set to null."""

    @model_validator(mode="after")
    def _something_set(self) -> "Change":
        if not self.model_fields_set:
            raise ValueError("nothing to change")
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        return self


# ---------- profile (SET-1) ----------


class Profile(BaseModel):
    id: str
    email: str
    display_name: str
    role: Literal["user", "admin"]
    timezone: str
    locale: str
    version: str


class ProfileChange(Change):
    display_name: DisplayName | None = None
    timezone: Timezone | None = None


# ---------- settings (SET-1, SET-2, SET-3, SET-5) ----------


class NotifPrefs(BaseModel):
    checkin: bool
    period_due: bool
    late_period: bool
    medication: bool
    appointment: bool
    task: bool


class NotifPrefsChange(Change):
    checkin: StrictBool | None = None
    period_due: StrictBool | None = None
    late_period: StrictBool | None = None
    medication: StrictBool | None = None
    appointment: StrictBool | None = None
    task: StrictBool | None = None


class OptionalFields(BaseModel):
    bbt: bool
    discharge: bool
    intimacy: bool


class OptionalFieldsChange(Change):
    bbt: StrictBool | None = None
    discharge: StrictBool | None = None
    intimacy: StrictBool | None = None


class DayBeforeAt(BaseModel):
    type: Literal["day_before_at"]
    time: str


class MinutesBefore(BaseModel):
    type: Literal["minutes_before"]
    minutes: int


AppointmentReminder = Annotated[DayBeforeAt | MinutesBefore, Field(discriminator="type")]


class Settings(BaseModel):
    theme: Theme
    week_start: int
    time_format: str
    temp_unit: Literal["C", "F"]
    checkin_time: str
    quiet_start: str
    quiet_end: str
    notif_prefs: NotifPrefs
    discreet_notifications: bool
    optional_fields: OptionalFields
    app_lock_enabled: bool
    app_lock_timeout_s: int
    appointment_reminder_defaults: list[AppointmentReminder]
    onboarding_completed_at: datetime | None
    version: str


class SettingsChange(Change):
    theme: Theme | None = None
    week_start: Annotated[StrictInt, Field(ge=1, le=7)] | None = (
        None  # ISO: 1 = Monday … 7 = Sunday
    )
    temp_unit: Literal["C", "F"] | None = None
    checkin_time: LocalTime | None = None
    quiet_start: LocalTime | None = None
    quiet_end: LocalTime | None = None
    notif_prefs: NotifPrefsChange | None = None
    optional_fields: OptionalFieldsChange | None = None
    discreet_notifications: StrictBool | None = None


# ---------- consent (12.6, CR-030) ----------


def current_consent_version(value: str) -> str:
    if value != CONSENT_VERSION:
        raise ValueError(f"consent is to version {CONSENT_VERSION}")
    return value


class ConsentIn(Strict):
    version: Annotated[str, Cleaned, AfterValidator(current_consent_version)]


class Consent(BaseModel):
    current_version: str
    version: str | None
    given_at: datetime | None


# ---------- GET /me ----------


class Me(BaseModel):
    """Bootstraps the client (9.2). CR-030: no feature flags; `device_timezone` is the client's
    `X-Timezone` when it is an IANA zone, and `timezone_differs` says it is not hers."""

    profile: Profile
    settings: Settings
    consent: Consent
    health_mode: Literal["standard", "postpartum", "ttc", "avoid"]
    device_timezone: str | None
    timezone_differs: bool


class ProfileConflict(BaseModel):
    """409 (9.1): the problem, with the current profile."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    current: Profile


class SettingsConflict(BaseModel):
    """409 (9.1): the problem, with the current settings."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    current: Settings
