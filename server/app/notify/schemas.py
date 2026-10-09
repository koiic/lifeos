"""notify: request and response schemas (spec 9.2 push rows)."""

import base64
import binascii
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.platform.payloads import Payload
from app.platform.text import clean_text

ENDPOINT_MAX = 2048


def _b64url_length(value: str, length: int) -> str:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError):
        raise ValueError("not base64url") from None
    if len(raw) != length:
        raise ValueError(f"must decode to {length} bytes")
    return value


def _p256dh(value: str) -> str:
    """The browser's P-256 public key: an uncompressed point (65 bytes, 0x04 first)."""
    _b64url_length(value, 65)
    if not value.startswith("B"):  # base64url of a leading 0x04 byte
        raise ValueError("must be an uncompressed P-256 point")
    return value


def _auth(value: str) -> str:
    return _b64url_length(value, 16)


def _url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("must be an http(s) URL")
    return value


Endpoint = Annotated[str, StringConstraints(max_length=ENDPOINT_MAX), AfterValidator(_url)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubscriptionKeys(Strict):
    p256dh: Annotated[str, StringConstraints(max_length=128), AfterValidator(_p256dh)]
    auth: Annotated[str, StringConstraints(max_length=64), AfterValidator(_auth)]


class SubscriptionIn(Strict):
    endpoint: Endpoint
    keys: SubscriptionKeys
    # 9.4: cleaned like every string (trimmed, control characters stripped, NFC).
    device_label: (
        Annotated[str, AfterValidator(clean_text), StringConstraints(max_length=100)] | None
    ) = None


class SubscriptionRef(Strict):
    endpoint: Endpoint


class ReminderAction(BaseModel):
    action: str
    title: str


class ReminderPayload(Payload):
    """`reminders.payload_enc` (7.2): `{title, body, url, actions[]}`, encrypted with her DEK."""

    title: str
    body: str
    url: str
    actions: list[ReminderAction] = Field(default_factory=list)


class VapidPublicKey(BaseModel):
    public_key: str


class TestPushResult(BaseModel):
    """How many of her devices the push service accepted the test push for."""

    delivered: int
