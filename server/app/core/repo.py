"""core: Repository layer: SQL only (plan 4.2).

`/me` reads and writes her `users` and `user_settings` rows (RLS: her own only) and the audit
log.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from sqlalchemy import text

from app.platform.db import Transaction


@dataclass(frozen=True)
class ProfileRow:
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    timezone: str
    locale: str
    updated_at: datetime


@dataclass(frozen=True)
class SettingsRow:
    theme: str
    week_start: int
    time_format: str
    temp_unit: str
    checkin_time: time
    quiet_start: time
    quiet_end: time
    notif_prefs: dict[str, bool]
    discreet_notifications: bool
    optional_fields: dict[str, bool]
    app_lock_enabled: bool
    app_lock_timeout_s: int
    appointment_reminder_defaults: list[dict[str, Any]]
    onboarding_completed_at: datetime | None
    health_consent_at: datetime | None
    health_consent_version: str | None
    updated_at: datetime


@dataclass(frozen=True)
class UserKey:
    dek_wrapped: bytes
    kek_version: int


PROFILE_COLUMNS = "id, email, display_name, role, timezone, locale, updated_at"
SETTINGS_COLUMNS = (
    "theme, week_start, time_format, temp_unit, checkin_time, quiet_start, quiet_end,"
    " notif_prefs, discreet_notifications, optional_fields,"
    " app_lock_pin_hash IS NOT NULL AS app_lock_enabled, app_lock_timeout_s,"
    " appointment_reminder_defaults, onboarding_completed_at, health_consent_at,"
    " health_consent_version, updated_at"
)
# Columns PATCH /me/settings may write; jsonb ones are cast.
SETTINGS_WRITABLE = {
    "theme": ":theme",
    "week_start": ":week_start",
    "temp_unit": ":temp_unit",
    "checkin_time": ":checkin_time",
    "quiet_start": ":quiet_start",
    "quiet_end": ":quiet_end",
    "notif_prefs": "CAST(:notif_prefs AS jsonb)",
    "discreet_notifications": ":discreet_notifications",
    "optional_fields": "CAST(:optional_fields AS jsonb)",
}
PROFILE_WRITABLE = {"display_name": ":display_name", "timezone": ":timezone"}


def _json(value: Any) -> Any:
    """jsonb as Python: the driver may hand back text."""
    return json.loads(value) if isinstance(value, str) else value


def _profile(row: Any) -> ProfileRow:
    return ProfileRow(
        row.id, row.email, row.display_name, row.role, row.timezone, row.locale, row.updated_at
    )


def _settings(row: Any) -> SettingsRow:
    return SettingsRow(
        theme=row.theme,
        week_start=row.week_start,
        time_format=row.time_format,
        temp_unit=row.temp_unit,
        checkin_time=row.checkin_time,
        quiet_start=row.quiet_start,
        quiet_end=row.quiet_end,
        notif_prefs=_json(row.notif_prefs),
        discreet_notifications=row.discreet_notifications,
        optional_fields=_json(row.optional_fields),
        app_lock_enabled=row.app_lock_enabled,
        app_lock_timeout_s=row.app_lock_timeout_s,
        appointment_reminder_defaults=_json(row.appointment_reminder_defaults),
        onboarding_completed_at=row.onboarding_completed_at,
        health_consent_at=row.health_consent_at,
        health_consent_version=row.health_consent_version,
        updated_at=row.updated_at,
    )


async def profile(tx: Transaction, user_id: uuid.UUID, *, lock: bool = False) -> ProfileRow:
    suffix = " FOR UPDATE" if lock else ""
    row = (
        await tx.execute(
            text(f"SELECT {PROFILE_COLUMNS} FROM users WHERE id = :id{suffix}"),  # noqa: S608
            {"id": user_id},
        )
    ).one()
    return _profile(row)


async def settings(tx: Transaction, user_id: uuid.UUID, *, lock: bool = False) -> SettingsRow:
    suffix = " FOR UPDATE" if lock else ""
    row = (
        await tx.execute(
            text(
                f"SELECT {SETTINGS_COLUMNS} FROM user_settings"  # noqa: S608
                f" WHERE user_id = :user_id{suffix}"
            ),
            {"user_id": user_id},
        )
    ).one()
    return _settings(row)


async def update_profile(tx: Transaction, user_id: uuid.UUID, values: dict[str, Any]) -> ProfileRow:
    """Write the given profile columns (names from `PROFILE_WRITABLE` only)."""
    if not values.keys() <= PROFILE_WRITABLE.keys():
        raise ValueError("not a writable profile column")
    assignments = ", ".join(f"{name} = {PROFILE_WRITABLE[name]}" for name in values)
    row = (
        await tx.execute(
            text(
                f"UPDATE users SET {assignments} WHERE id = :id"  # noqa: S608
                f" RETURNING {PROFILE_COLUMNS}"
            ),
            values | {"id": user_id},
        )
    ).one()
    return _profile(row)


async def update_settings(
    tx: Transaction, user_id: uuid.UUID, values: dict[str, Any]
) -> SettingsRow:
    """Write the given settings columns (names from `SETTINGS_WRITABLE` only)."""
    if not values.keys() <= SETTINGS_WRITABLE.keys():
        raise ValueError("not a writable settings column")
    assignments = ", ".join(f"{name} = {SETTINGS_WRITABLE[name]}" for name in values)
    params = {
        name: json.dumps(value) if name in ("notif_prefs", "optional_fields") else value
        for name, value in values.items()
    }
    row = (
        await tx.execute(
            text(
                f"UPDATE user_settings SET {assignments} WHERE user_id = :user_id"  # noqa: S608
                f" RETURNING {SETTINGS_COLUMNS}"
            ),
            params | {"user_id": user_id},
        )
    ).one()
    return _settings(row)


async def give_consent(tx: Transaction, user_id: uuid.UUID, version: str, now: datetime) -> bool:
    """Store her consent (12.6) once: False when it was already given."""
    row = (
        await tx.execute(
            text(
                "UPDATE user_settings SET health_consent_at = :now, health_consent_version = :v"
                " WHERE user_id = :user_id AND health_consent_at IS NULL RETURNING user_id"
            ),
            {"user_id": user_id, "v": version, "now": now},
        )
    ).one_or_none()
    return row is not None


async def insert_audit(
    tx: Transaction,
    *,
    user_id: uuid.UUID,
    action: str,
    ip_hash: bytes,
    now: datetime,
) -> None:
    """An audit entry of her own action (7.2 `audit_log`)."""
    await tx.execute(
        text(
            "INSERT INTO audit_log (actor_user_id, actor_role, action, target_user_id, at, ip_hash)"
            " VALUES (:user_id, 'user', :action, :user_id, :now, :ip_hash)"
        ),
        {"user_id": user_id, "action": action, "now": now, "ip_hash": ip_hash},
    )


async def user_key(tx: Transaction, user_id: uuid.UUID) -> UserKey:
    row = (
        await tx.execute(
            text("SELECT dek_wrapped, kek_version FROM users WHERE id = :id"), {"id": user_id}
        )
    ).one()
    return UserKey(bytes(row.dek_wrapped), row.kek_version)
