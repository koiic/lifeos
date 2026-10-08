"""auth: Pydantic request, response and payload schemas."""

import re
import unicodedata
import uuid
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic_core import PydanticCustomError

# A practical shape check (one @, a dot in the domain, no spaces); the invite proves ownership.
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
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


def check_email(value: str) -> str:
    value = clean_text(value)
    if EMAIL.fullmatch(value) is None:
        raise ValueError("invalid email")
    return value


Token = Annotated[str, StringConstraints(max_length=200)]
DisplayName = Annotated[str, StringConstraints(max_length=4 * NAME_MAX), AfterValidator(clean_name)]
Email = Annotated[str, StringConstraints(max_length=254), AfterValidator(clean_text)]
NewEmail = Annotated[Email, AfterValidator(check_email)]
# A WebAuthn PublicKeyCredential in its JSON form; verified by py_webauthn, not by shape here.
Credential = dict[str, Any]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InviteCheck(Strict):
    token: Token


class InviteStatus(BaseModel):
    valid: bool
    email: str | None


class Registration(Strict):
    token: Token
    name: DisplayName
    email: NewEmail


class RegistrationVerify(Registration):
    credential: Credential


class Registered(BaseModel):
    user_id: uuid.UUID
    display_name: str
    # Shown once (9.2); only argon2id hashes are stored.
    recovery_codes: list[str]


class SignInOptions(Strict):
    pass


class SignInVerify(Strict):
    credential: Credential


class SignedIn(BaseModel):
    user_id: uuid.UUID
    display_name: str


class RecoverySignIn(Strict):
    email: Email
    code: Annotated[str, StringConstraints(max_length=64)]


class WebAuthnOptions(BaseModel):
    """WebAuthn creation or request options (JSON form) for the browser."""

    model_config = ConfigDict(extra="allow")


class Recovered(BaseModel):
    """A spent recovery code: register a new passkey with these options next (no session yet;
    9.2 "forces new passkey setup", CR-013)."""

    next: Literal["add_passkey"] = "add_passkey"
    options: WebAuthnOptions


class PasskeyVerify(Strict):
    credential: Credential


# ---------- password + TOTP (12.3, 9.2, CR-014) ----------

PASSWORD_MIN = 12
PASSWORD_MAX = 256  # bounds the Argon2id input; far above any real passphrase
COMMON_PASSWORDS_FILE = Path(__file__).parent / "data" / "common_passwords.txt"


@cache
def common_passwords() -> frozenset[str]:
    lines = COMMON_PASSWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line for line in lines if line and not line.startswith("#"))


def nfc(value: str) -> str:
    """Passwords are NFC-normalised (9.4), so the same characters typed on different devices
    match; they are not trimmed or otherwise changed (every character counts)."""
    return unicodedata.normalize("NFC", value)


def check_password(value: str) -> str:
    """12.3: at least 12 characters and not on the local common-password list. Messages are
    fixed, so a refused password is never echoed."""
    value = nfc(value)
    if len(value) < PASSWORD_MIN:
        raise PydanticCustomError("password_too_short", "Use at least 12 characters.")
    if value.strip().lower() in common_passwords():
        raise PydanticCustomError("password_too_common", "This password is too common.")
    return value


NewPassword = Annotated[
    str, StringConstraints(max_length=PASSWORD_MAX), AfterValidator(check_password)
]
TotpCode = Annotated[str, StringConstraints(max_length=16)]


class PasswordRegistration(Registration):
    password: NewPassword


class PasswordRegistered(BaseModel):
    """Add this to an authenticator app, then confirm a code (the account is inactive until
    then; CR-014)."""

    provisioning_uri: str


class TotpConfirm(Strict):
    code: TotpCode


class TotpConfirmed(BaseModel):
    # Shown once (as at passkey registration); only argon2id hashes are stored.
    recovery_codes: list[str]


class PasswordSignIn(Strict):
    email: Email
    password: Annotated[str, StringConstraints(max_length=PASSWORD_MAX), AfterValidator(nfc)]
    totp: TotpCode


# ---------- T08: sessions, passkeys, re-auth, app lock, recovery (9.2; CR-017/018/019) ----------


class SessionOut(BaseModel):
    id: uuid.UUID
    device_label: str | None
    created_at: datetime
    last_seen_at: datetime
    current: bool


class SessionList(BaseModel):
    items: list[SessionOut]
    next_cursor: None = None  # 9.1 list shape; her live sessions always fit one page


class PasskeyOut(BaseModel):
    id: uuid.UUID
    nickname: str
    created_at: datetime
    last_used_at: datetime | None
    backed_up: bool


class PasskeyList(BaseModel):
    items: list[PasskeyOut]
    next_cursor: None = None


class ReauthOptionsRequest(Strict):
    purpose: Literal["reauth", "unlock"]


class ReauthVerify(Strict):
    """A passkey assertion (`credential`), or `password` and `totp` for a password account."""

    credential: Credential | None = None
    password: (
        Annotated[str, StringConstraints(max_length=PASSWORD_MAX), AfterValidator(nfc)] | None
    ) = None
    totp: TotpCode | None = None

    @model_validator(mode="after")
    def _one_method(self) -> "ReauthVerify":
        passkey = self.credential is not None
        password = self.password is not None and self.totp is not None
        if passkey == password or (self.password is None) != (self.totp is None):
            raise ValueError("send a credential, or a password and a code")
        return self


class RecoveryCodes(BaseModel):
    # Shown once; only argon2id hashes are stored. The previous codes no longer work.
    recovery_codes: list[str]


Pin = Annotated[str, StringConstraints(pattern=r"^\d{6}$")]


class AppLockSettings(Strict):
    """`pin`: six digits to set it, null to clear it, absent to keep it (AUTH-6)."""

    pin: Pin | None = None
    timeout_s: Annotated[int, Field(ge=60, le=3600)] | None = None


class PinUnlock(Strict):
    pin: Annotated[str, StringConstraints(max_length=16)]


class RecoveryInvite(BaseModel):
    """Shown once to the admin, who sends her the link (AUTH-8)."""

    token: str
    link: str
    expires_at: datetime


class RecoverOptions(Strict):
    token: Token


class RecoverVerify(Strict):
    token: Token
    credential: Credential
