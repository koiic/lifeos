"""A valid lifeos_kek file (CR-011) for deployed-env test apps; not the local dev key."""

import base64
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from app.platform.crypto import generate_vapid_keys

TEST_KEK = "1 " + base64.b64encode(bytes(range(32))).decode()

# A test IP_HMAC_KEY for the same apps.
TEST_IP_KEY = "test-ip-hmac-key-for-deployed-apps"

# A VAPID key pair and subject for the same apps (T14: required outside local, spec 14.3).
TEST_VAPID = generate_vapid_keys()
TEST_VAPID_SUBJECT = "mailto:admin@example.test"


def vapid_settings() -> dict[str, Any]:
    """The VAPID fields of a deployed-env `Settings`."""
    return {
        "vapid_public_key": TEST_VAPID.public_key,
        "vapid_private_key": SecretStr(TEST_VAPID.private_key),
        "vapid_subject": TEST_VAPID_SUBJECT,
    }


def write_vapid_secrets(secrets_dir: Path) -> None:
    """The three VAPID secret files a deployed env reads."""
    (secrets_dir / "vapid_public_key").write_text(TEST_VAPID.public_key + "\n")
    (secrets_dir / "vapid_private_key").write_text(TEST_VAPID.private_key + "\n")
    (secrets_dir / "vapid_subject").write_text(TEST_VAPID_SUBJECT + "\n")
