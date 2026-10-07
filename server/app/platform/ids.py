"""Primary keys: UUID v7 generated in Python (spec 7.1, CR-012)."""

import uuid

import uuid6


def new_id() -> uuid.UUID:
    """A time-ordered UUID v7, as a plain `uuid.UUID`."""
    return uuid.UUID(int=uuid6.uuid7().int)
