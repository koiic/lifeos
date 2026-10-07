"""T06: the master-key file (spec 12.2 item 1 as changed by CR-011) is parsed strictly."""

import base64
import secrets
import uuid

import pytest
from pydantic import SecretStr

from app.platform.config import ConfigError, Settings
from app.platform.crypto import (
    DataKey,
    Keyring,
    KeyringError,
    MasterKey,
    generate_data_key,
    load_keyring,
    parse_keyring,
    unwrap_dek,
    wrap_dek,
)

KEY_A = secrets.token_bytes(32)
KEY_B = secrets.token_bytes(32)


def line(version: int, key: bytes) -> str:
    return f"{version} {base64.b64encode(key).decode()}"


def holds(keyring: Keyring, version: int, key: bytes) -> bool:
    """True when the keyring's `version` is exactly `key` (it unwraps what `key` wrapped)."""
    user = uuid.uuid4()
    _, wrapped = wrap_dek(parse_keyring(line(1, key)), generate_data_key(), user)
    return isinstance(unwrap_dek(keyring, version, wrapped, user), DataKey)


def test_one_line_is_version_one() -> None:
    keyring = parse_keyring(line(1, KEY_A) + "\n")
    assert keyring.current_version == 1
    assert isinstance(keyring.key(1), MasterKey)
    assert holds(keyring, 1, KEY_A)


def test_the_highest_version_is_current_and_old_versions_stay_readable() -> None:
    text = f"{line(1, KEY_A)}\n{line(2, KEY_B)}\n"
    keyring = parse_keyring(text)
    assert keyring.current_version == 2
    assert holds(keyring, 1, KEY_A)
    assert holds(keyring, 2, KEY_B)


def test_line_order_does_not_matter() -> None:
    assert parse_keyring(f"{line(2, KEY_B)}\n{line(1, KEY_A)}").current_version == 2


def test_blank_lines_are_ignored() -> None:
    assert parse_keyring(f"\n{line(1, KEY_A)}\n\n").current_version == 1


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\n\n",
        line(0, KEY_A),
        f"{line(1, KEY_A)}\n{line(1, KEY_B)}",
        line(1, KEY_A[:31]),
        line(1, KEY_A + b"x"),
        "1  " + base64.b64encode(KEY_A).decode(),
        " " + line(1, KEY_A),
        line(1, KEY_A) + " ",
        "v1 " + base64.b64encode(KEY_A).decode(),
        "1 " + base64.urlsafe_b64encode(b"\xfb" * 32).decode(),
        "1 " + base64.b64encode(KEY_A).decode().rstrip("="),
        "1 not base64!",
        "-1 " + base64.b64encode(KEY_A).decode(),
        "1\t" + base64.b64encode(KEY_A).decode(),
    ],
    ids=[
        "empty",
        "blank",
        "version-0",
        "duplicate",
        "short-key",
        "long-key",
        "two-spaces",
        "leading-space",
        "trailing-space",
        "prefix",
        "urlsafe",
        "unpadded",
        "garbage",
        "negative",
        "tab",
    ],
)
def test_malformed_files_are_rejected(text: str) -> None:
    with pytest.raises(KeyringError):
        parse_keyring(text)


def test_errors_never_echo_the_line() -> None:
    secret = base64.b64encode(KEY_A[:31]).decode()
    with pytest.raises(KeyringError) as caught:
        parse_keyring(f"7 {secret}")
    assert secret not in str(caught.value)
    assert str(caught.value) == "lifeos_kek line 1 is invalid"
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def settings(env: str, kek: str | None) -> Settings:
    return Settings(
        env=env,  # type: ignore[arg-type]
        app_origin="https://a.example",
        database_url=SecretStr("postgresql://x"),
        webauthn_rp_id="a.example",
        lifeos_kek=SecretStr(kek) if kek is not None else None,
    )


def test_local_without_a_file_uses_the_fixed_development_key() -> None:
    keyring = load_keyring(settings("local", None))
    assert keyring.current_version == 1
    # Fixed, so local data survives restarts.
    assert holds(keyring, 1, bytes(32))


def test_a_configured_file_wins_locally() -> None:
    keyring = load_keyring(settings("local", f"{line(1, KEY_A)}\n{line(3, KEY_B)}"))
    assert keyring.current_version == 3
    assert holds(keyring, 3, KEY_B)


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_envs_require_the_file(env: str) -> None:
    with pytest.raises(ConfigError, match="lifeos_kek"):
        load_keyring(settings(env, None))


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_envs_refuse_the_development_key(env: str) -> None:
    with pytest.raises(ConfigError, match="lifeos_kek"):
        load_keyring(settings(env, line(1, bytes(32))))


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_envs_load_the_file(env: str) -> None:
    keyring = load_keyring(settings(env, line(4, KEY_A)))
    assert keyring.current_version == 4
    assert holds(keyring, 4, KEY_A)
