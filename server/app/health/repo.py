"""health: Repository layer: SQL only (plan 4.2)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import text

from app.platform.db import Transaction


@dataclass(frozen=True)
class NewSymptom:
    id: uuid.UUID
    system_key: str
    category: str
    sort_order: int
    payload_enc: bytes


@dataclass(frozen=True)
class DailyLogRow:
    id: uuid.UUID
    user_id: uuid.UUID
    date: date
    payload_enc: bytes
    import_id: uuid.UUID | None
    client_updated_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class UserMeta:
    timezone: str
    dek_wrapped: bytes
    kek_version: int


@dataclass(frozen=True)
class IdempotencyRow:
    key: uuid.UUID
    method: str
    path: str
    request_hash: bytes
    response_status: int
    response_body_enc: bytes


async def insert_symptoms(tx: Transaction, user_id: uuid.UUID, rows: list[NewSymptom]) -> None:
    await tx.execute(
        text(
            "INSERT INTO symptoms (id, user_id, system_key, category, sort_order, payload_enc)"
            " VALUES (:id, :user_id, :system_key, :category, :sort_order, :payload_enc)"
        ),
        [
            {
                "id": row.id,
                "user_id": user_id,
                "system_key": row.system_key,
                "category": row.category,
                "sort_order": row.sort_order,
                "payload_enc": row.payload_enc,
            }
            for row in rows
        ],
    )


async def health_profile(tx: Transaction, user_id: uuid.UUID) -> bytes | None:
    """Her encrypted health profile, if she has one yet."""
    value = await tx.scalar(
        text("SELECT payload_enc FROM health_profile WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    return bytes(value) if value is not None else None


async def user_meta(tx: Transaction, user_id: uuid.UUID) -> UserMeta:
    row = (
        (
            await tx.execute(
                text("SELECT timezone, dek_wrapped, kek_version FROM users WHERE id = :id"),
                {"id": user_id},
            )
        )
        .mappings()
        .one()
    )
    return UserMeta(
        timezone=row["timezone"],
        dek_wrapped=bytes(row["dek_wrapped"]),
        kek_version=row["kek_version"],
    )


LOG_COLUMNS = "id, user_id, date, payload_enc, import_id, client_updated_at, created_at, updated_at"


async def get_daily_log(
    tx: Transaction, user_id: uuid.UUID, log_date: date, for_update: bool = False
) -> DailyLogRow | None:
    sql = f"SELECT {LOG_COLUMNS} FROM daily_logs WHERE user_id = :user_id AND date = :date"  # noqa: S608
    if for_update:
        sql += " FOR UPDATE"
    row = (
        (await tx.execute(text(sql), {"user_id": user_id, "date": log_date}))
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    return DailyLogRow(
        id=row["id"],
        user_id=row["user_id"],
        date=row["date"],
        payload_enc=bytes(row["payload_enc"]),
        import_id=row["import_id"],
        client_updated_at=row["client_updated_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def get_daily_logs_range(
    tx: Transaction, user_id: uuid.UUID, from_date: date, to_date: date
) -> list[DailyLogRow]:
    sql = (
        f"SELECT {LOG_COLUMNS} FROM daily_logs"  # noqa: S608
        " WHERE user_id = :user_id AND date >= :from_date AND date <= :to_date"
        " ORDER BY date ASC"
    )
    rows = (
        (
            await tx.execute(
                text(sql), {"user_id": user_id, "from_date": from_date, "to_date": to_date}
            )
        )
        .mappings()
        .all()
    )
    return [
        DailyLogRow(
            id=r["id"],
            user_id=r["user_id"],
            date=r["date"],
            payload_enc=bytes(r["payload_enc"]),
            import_id=r["import_id"],
            client_updated_at=r["client_updated_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


async def insert_daily_log(
    tx: Transaction,
    *,
    id: uuid.UUID,
    user_id: uuid.UUID,
    log_date: date,
    payload_enc: bytes,
    client_updated_at: datetime,
) -> DailyLogRow:
    sql = (
        "INSERT INTO daily_logs (id, user_id, date, payload_enc, client_updated_at)"  # noqa: S608
        " VALUES (:id, :user_id, :date, :payload_enc, :client_updated_at)"
        f" RETURNING {LOG_COLUMNS}"
    )
    row = (
        (
            await tx.execute(
                text(sql),
                {
                    "id": id,
                    "user_id": user_id,
                    "date": log_date,
                    "payload_enc": payload_enc,
                    "client_updated_at": client_updated_at,
                },
            )
        )
        .mappings()
        .one()
    )
    return DailyLogRow(
        id=row["id"],
        user_id=row["user_id"],
        date=row["date"],
        payload_enc=bytes(row["payload_enc"]),
        import_id=row["import_id"],
        client_updated_at=row["client_updated_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def update_daily_log(
    tx: Transaction,
    *,
    id: uuid.UUID,
    payload_enc: bytes,
    client_updated_at: datetime,
) -> DailyLogRow:
    sql = (
        "UPDATE daily_logs SET payload_enc = :payload_enc, client_updated_at = :client_updated_at"  # noqa: S608
        f" WHERE id = :id RETURNING {LOG_COLUMNS}"
    )
    row = (
        (
            await tx.execute(
                text(sql),
                {
                    "id": id,
                    "payload_enc": payload_enc,
                    "client_updated_at": client_updated_at,
                },
            )
        )
        .mappings()
        .one()
    )
    return DailyLogRow(
        id=row["id"],
        user_id=row["user_id"],
        date=row["date"],
        payload_enc=bytes(row["payload_enc"]),
        import_id=row["import_id"],
        client_updated_at=row["client_updated_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def delete_daily_log(
    tx: Transaction, user_id: uuid.UUID, log_date: date
) -> DailyLogRow | None:
    row = await get_daily_log(tx, user_id, log_date, for_update=True)
    if row is None:
        return None
    await tx.execute(
        text("DELETE FROM daily_logs WHERE id = :id"),
        {"id": row.id},
    )
    return row


async def get_idempotency(
    tx: Transaction, user_id: uuid.UUID, key: uuid.UUID
) -> IdempotencyRow | None:
    row = (
        (
            await tx.execute(
                text(
                    "SELECT key, method, path, request_hash, response_status, response_body_enc"
                    " FROM idempotency_keys WHERE user_id = :user_id AND key = :key"
                ),
                {"user_id": user_id, "key": key},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    return IdempotencyRow(
        key=row["key"],
        method=row["method"],
        path=row["path"],
        request_hash=bytes(row["request_hash"]),
        response_status=row["response_status"],
        response_body_enc=bytes(row["response_body_enc"]),
    )


async def insert_idempotency(
    tx: Transaction,
    *,
    user_id: uuid.UUID,
    key: uuid.UUID,
    method: str,
    path: str,
    request_hash: bytes,
    response_status: int,
    response_body_enc: bytes,
) -> None:
    await tx.execute(
        text(
            "INSERT INTO idempotency_keys ("
            " key, user_id, method, path, request_hash, response_status, response_body_enc"
            ") VALUES ("
            " :key, :user_id, :method, :path, :request_hash, :response_status, :response_body_enc"
            ") ON CONFLICT (user_id, key) DO NOTHING"
        ),
        {
            "key": key,
            "user_id": user_id,
            "method": method,
            "path": path,
            "request_hash": request_hash,
            "response_status": response_status,
            "response_body_enc": response_body_enc,
        },
    )
