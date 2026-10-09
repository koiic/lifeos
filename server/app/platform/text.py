"""Spec 9.4 strings, shared by every module's request schemas."""

import unicodedata


def clean_text(value: str) -> str:
    """Spec 9.4 strings: Unicode NFC, control (and format) characters stripped, trimmed."""
    value = unicodedata.normalize("NFC", value)
    return "".join(c for c in value if unicodedata.category(c) not in {"Cc", "Cf"}).strip()
