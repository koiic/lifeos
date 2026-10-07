"""Base for encrypted payload schemas (spec 7.1): every payload has a `v` field for evolution."""

from pydantic import BaseModel, ConfigDict


class Payload(BaseModel):
    """A JSON object stored encrypted in a `payload_enc` column."""

    # Unknown fields are kept (written by newer code): reading and rewriting after a rollback must
    # neither fail nor drop them.
    model_config = ConfigDict(extra="allow")

    v: int = 1
