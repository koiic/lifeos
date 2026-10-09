"""core: Service layer: rules and transactions (plan 4.2).

`MeService`: her profile and settings (SET-1, SET-2, SET-3, SET-5), consent (12.6, CR-030) and
the `/me` bootstrap. Versions are `updated_at` (CR-004): a change names the version it changes
and is refused when that is no longer current.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Any

from app.core import repo
from app.core.schemas import (
    CONSENT_VERSION,
    Consent,
    Me,
    NotifPrefs,
    OptionalFields,
    Profile,
    ProfileChange,
    Settings,
    SettingsChange,
    iana_timezones,
)
from app.health.service import health_mode
from app.platform.crypto import Keyring, unwrap_dek
from app.platform.db import Database, user_transaction
from app.platform.outbox import publish

# 10.2: "A change of timezone, check-in time, quiet hours or notification preferences
# regenerates all future reminders for that user" (7.2 topic `settings.changed`).
REMINDER_FIELDS = frozenset({"timezone", "checkin_time", "quiet_start", "quiet_end", "notif_prefs"})


class MeError(Exception):
    status = 400
    detail = "The request could not be completed."


class VersionMissing(MeError):
    status = 428
    detail = "Send the version you are changing in If-Match."


@dataclass
class VersionConflict(MeError):
    """9.1: the resource changed since she read it; carries the current one (her name and
    email: never logged, so not in the repr)."""

    current: Profile | Settings = field(repr=False)
    status = 409
    detail = "This was changed elsewhere. Here is the current version."


@dataclass
class InvalidSettings(MeError):
    field: str
    code: str
    message: str
    status = 422
    detail = "The request has invalid fields."


def version_of(updated_at: datetime) -> str:
    """CR-004: `updated_at` as RFC 3339 with microseconds."""
    return updated_at.isoformat(timespec="microseconds")


def parse_version(header: str | None) -> datetime | None:
    """`If-Match: "<version>"` (quotes optional); None when absent. An unreadable version is
    never current, so it is a conflict, not a missing header."""
    if header is None or not header.strip():
        return None
    value = header.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def _time(value: str) -> time:
    return time.fromisoformat(value)


def to_profile(row: repo.ProfileRow) -> Profile:
    return Profile(
        id=str(row.id),
        email=row.email,
        display_name=row.display_name,
        role=row.role,  # type: ignore[arg-type]  # the users.role CHECK allows only these
        timezone=row.timezone,
        locale=row.locale,
        version=version_of(row.updated_at),
    )


def to_settings(row: repo.SettingsRow) -> Settings:
    return Settings.model_validate(
        {
            "theme": row.theme,
            "week_start": row.week_start,
            "time_format": row.time_format,
            "temp_unit": row.temp_unit,
            "checkin_time": _hhmm(row.checkin_time),
            "quiet_start": _hhmm(row.quiet_start),
            "quiet_end": _hhmm(row.quiet_end),
            "notif_prefs": row.notif_prefs,
            "discreet_notifications": row.discreet_notifications,
            "optional_fields": row.optional_fields,
            "app_lock_enabled": row.app_lock_enabled,
            "app_lock_timeout_s": row.app_lock_timeout_s,
            "appointment_reminder_defaults": row.appointment_reminder_defaults,
            "onboarding_completed_at": row.onboarding_completed_at,
            "version": version_of(row.updated_at),
        }
    )


def to_consent(row: repo.SettingsRow) -> Consent:
    return Consent(
        current_version=CONSENT_VERSION,
        version=row.health_consent_version,
        given_at=row.health_consent_at,
    )


def device_timezone(header: str | None) -> str | None:
    """CR-030: the client's `X-Timezone`, when it is an IANA zone."""
    value = (header or "").strip()
    return value if value in iana_timezones() else None


def _settings_values(row: repo.SettingsRow, change: SettingsChange) -> dict[str, Any]:
    """The columns this change sets, with nested preferences merged into the saved ones."""
    values: dict[str, Any] = {}
    for name in change.model_fields_set:
        if name == "notif_prefs" and change.notif_prefs is not None:
            merged = row.notif_prefs | change.notif_prefs.model_dump(exclude_unset=True)
            values[name] = NotifPrefs.model_validate(merged).model_dump()
        elif name == "optional_fields" and change.optional_fields is not None:
            merged = row.optional_fields | change.optional_fields.model_dump(exclude_unset=True)
            values[name] = OptionalFields.model_validate(merged).model_dump()
        elif name in ("checkin_time", "quiet_start", "quiet_end"):
            values[name] = _time(getattr(change, name))
        else:
            values[name] = getattr(change, name)
    return values


def _changed(saved: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in values.items() if saved.get(name) != value}


class MeService:
    def __init__(self, engine: Database, keyring: Keyring) -> None:
        self._db = engine
        self._keyring = keyring

    async def me(self, user_id: uuid.UUID, device: str | None) -> Me:
        async with user_transaction(self._db, user_id) as tx:
            profile = await repo.profile(tx, user_id)
            settings = await repo.settings(tx, user_id)
            key = await repo.user_key(tx, user_id)
            dek = unwrap_dek(self._keyring, key.kek_version, key.dek_wrapped, user_id)
            mode = await health_mode(tx, user_id, dek)
        zone = device_timezone(device)
        return Me(
            profile=to_profile(profile),
            settings=to_settings(settings),
            consent=to_consent(settings),
            health_mode=mode,
            device_timezone=zone,
            timezone_differs=zone is not None and zone != profile.timezone,
        )

    async def change_profile(
        self, user_id: uuid.UUID, change: ProfileChange, version: datetime | None
    ) -> Profile:
        if version is None:
            raise VersionMissing
        async with user_transaction(self._db, user_id) as tx:
            row = await repo.profile(tx, user_id, lock=True)
            if row.updated_at != version:
                raise VersionConflict(to_profile(row))
            saved = {"display_name": row.display_name, "timezone": row.timezone}
            values = _changed(saved, change.model_dump(exclude_unset=True))
            if not values:
                return to_profile(row)
            row = await repo.update_profile(tx, user_id, values)
            if "timezone" in values:
                await publish(tx, user_id, "settings.changed", {"fields": ["timezone"]})
        return to_profile(row)

    async def change_settings(
        self, user_id: uuid.UUID, change: SettingsChange, version: datetime | None
    ) -> Settings:
        if version is None:
            raise VersionMissing
        async with user_transaction(self._db, user_id) as tx:
            row = await repo.settings(tx, user_id, lock=True)
            if row.updated_at != version:
                raise VersionConflict(to_settings(row))
            values = _settings_values(row, change)
            start = values.get("quiet_start", row.quiet_start)
            end = values.get("quiet_end", row.quiet_end)
            if start == end:
                field = "quiet_end" if "quiet_end" in values else "quiet_start"
                raise InvalidSettings(
                    field, "quiet_hours_empty", "Quiet hours must start and end at different times"
                )
            saved = {name: getattr(row, name) for name in values}
            values = _changed(saved, values)
            if not values:
                return to_settings(row)
            row = await repo.update_settings(tx, user_id, values)
            moved = sorted(REMINDER_FIELDS.intersection(values))
            if moved:
                await publish(tx, user_id, "settings.changed", {"fields": moved})
        return to_settings(row)

    async def consent(
        self, user_id: uuid.UUID, version: str, now: datetime, ip_hash: bytes
    ) -> Consent:
        """12.6: her consent's time and version, stored once and audited."""
        async with user_transaction(self._db, user_id) as tx:
            if await repo.give_consent(tx, user_id, version, now):
                await repo.insert_audit(
                    tx, user_id=user_id, action="user.health_consent", ip_hash=ip_hash, now=now
                )
            row = await repo.settings(tx, user_id)
        return to_consent(row)
