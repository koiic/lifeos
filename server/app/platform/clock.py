"""The current time, as a FastAPI dependency that tests replace (services take `now`)."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)
