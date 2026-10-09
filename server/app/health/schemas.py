"""health: Pydantic request, response and payload schemas."""

from typing import Literal

from app.platform.payloads import Payload

Mode = Literal["standard", "postpartum", "ttc", "avoid"]


class SymptomPayload(Payload):
    """`symptoms.payload_enc` (7.2): `{name}`."""

    name: str


class HealthProfilePayload(Payload):
    """`health_profile.payload_enc` (7.2); only the mode is read here (the health-profile task
    owns the rest)."""

    mode: Mode = "standard"
