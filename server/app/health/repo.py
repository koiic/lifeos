"""health: Repository layer: SQL only (plan 4.2)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import text

from app.platform.db import Transaction


@dataclass(frozen=True)
class NewSymptom:
    id: uuid.UUID
    system_key: str
    category: str
    sort_order: int
    payload_enc: bytes


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
