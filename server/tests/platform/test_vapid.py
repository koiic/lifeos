"""T14: VAPID keys for Web Push (spec 10.4, 14.3): the format browsers and pywebpush use, a pair
that must match, required outside local; generated per process in ENV=local."""

import base64
from pathlib import Path

import pytest

from app.platform.config import ConfigError, Settings, load_settings
from app.platform.crypto import Vapid, generate_vapid_keys, load_vapid, vapid_public_key


def b64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def settings(**extra: object) -> Settings:
    return Settings(
        env="local",
        app_origin="http://localhost:5173",
        database_url="postgresql://x/y",
        webauthn_rp_id="localhost",
        **extra,  # type: ignore[arg-type]
    )


def test_keys_are_a_raw_private_scalar_and_an_uncompressed_public_point() -> None:
    keys = generate_vapid_keys()
    assert len(b64(keys.private_key)) == 32
    public = b64(keys.public_key)
    assert len(public) == 65
    assert public[0] == 0x04
    assert "=" not in keys.public_key + keys.private_key  # unpadded base64url


def test_the_public_key_follows_from_the_private_key() -> None:
    keys = generate_vapid_keys()
    assert vapid_public_key(keys.private_key) == keys.public_key
    assert generate_vapid_keys().public_key != keys.public_key


def test_a_configured_pair_is_used_as_is() -> None:
    keys = generate_vapid_keys()
    vapid = load_vapid(
        settings(
            vapid_public_key=keys.public_key,
            vapid_private_key=keys.private_key,
            vapid_subject="mailto:admin@example.test",
        )
    )
    assert vapid == Vapid(keys.public_key, keys.private_key, "mailto:admin@example.test")


def test_a_pair_that_does_not_match_stops_the_process() -> None:
    one, two = generate_vapid_keys(), generate_vapid_keys()
    with pytest.raises(ConfigError, match="VAPID"):
        load_vapid(
            settings(
                vapid_public_key=two.public_key,
                vapid_private_key=one.private_key,
                vapid_subject="mailto:admin@example.test",
            )
        )


def test_a_private_key_that_is_not_one_stops_the_process() -> None:
    with pytest.raises(ConfigError, match="VAPID"):
        load_vapid(
            settings(
                vapid_public_key=generate_vapid_keys().public_key,
                vapid_private_key="not-a-key",
                vapid_subject="mailto:admin@example.test",
            )
        )


def test_locally_a_pair_is_generated_when_none_is_configured() -> None:
    vapid = load_vapid(settings())
    assert vapid_public_key(vapid.private_key) == vapid.public_key
    assert vapid.subject.startswith("mailto:")


def test_the_subject_must_be_a_mailto_address() -> None:
    keys = generate_vapid_keys()
    with pytest.raises(ConfigError, match="VAPID_SUBJECT"):
        load_vapid(
            settings(
                vapid_public_key=keys.public_key,
                vapid_private_key=keys.private_key,
                vapid_subject="https://example.test",
            )
        )


@pytest.mark.parametrize("missing", ["vapid_public_key", "vapid_private_key", "vapid_subject"])
def test_outside_local_each_vapid_secret_file_is_required(missing: str, tmp_path: Path) -> None:
    environ = {"ENV": "production", "APP_ORIGIN": "https://app.example.test"}
    (tmp_path / "database_url").write_text("postgresql://x/y")
    (tmp_path / "ip_hmac_key").write_text("k" * 40)
    keys = generate_vapid_keys()
    files = {
        "vapid_public_key": keys.public_key,
        "vapid_private_key": keys.private_key,
        "vapid_subject": "mailto:admin@example.test",
    }
    for name, value in files.items():
        if name != missing:
            (tmp_path / name).write_text(value)
    with pytest.raises(ConfigError, match=missing):
        load_settings(environ, secrets_dir=tmp_path)


def test_outside_local_the_three_secret_files_are_required(tmp_path: Path) -> None:
    environ = {"ENV": "production", "APP_ORIGIN": "https://app.example.test"}
    (tmp_path / "database_url").write_text("postgresql://x/y")
    (tmp_path / "ip_hmac_key").write_text("k" * 40)
    with pytest.raises(ConfigError, match="vapid"):
        load_settings(environ, secrets_dir=tmp_path)
    keys = generate_vapid_keys()
    (tmp_path / "vapid_public_key").write_text(keys.public_key)
    (tmp_path / "vapid_private_key").write_text(keys.private_key + "\n")
    (tmp_path / "vapid_subject").write_text("mailto:admin@example.test")
    loaded = load_settings(environ, secrets_dir=tmp_path)
    assert loaded.vapid_public_key == keys.public_key
    assert loaded.vapid_private_key is not None
    assert loaded.vapid_private_key.get_secret_value() == keys.private_key
    assert loaded.vapid_subject == "mailto:admin@example.test"
