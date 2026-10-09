"""Spec 9.4 strings, shared by every module's request schemas."""

import unicodedata
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

NAME_MAX = 100


def clean_text(value: str) -> str:
    """Spec 9.4 strings: Unicode NFC, control (and format) characters stripped, trimmed."""
    value = unicodedata.normalize("NFC", value)
    return "".join(c for c in value if unicodedata.category(c) not in {"Cc", "Cf"}).strip()


def clean_name(value: str) -> str:
    """A display name: cleaned, 1-100 characters."""
    value = clean_text(value)
    if not 1 <= len(value) <= NAME_MAX:
        raise ValueError("invalid name")
    return value


DisplayName = Annotated[str, StringConstraints(max_length=4 * NAME_MAX), AfterValidator(clean_name)]
