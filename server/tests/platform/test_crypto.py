"""T04: field encryption and key hierarchy (spec 7.1, 12.2).

The format is checked independently with cryptography's AESGCM (tests may import it; app code may
not), so the module cannot quietly drift from `0x01 ‖ nonce(12) ‖ ciphertext ‖ tag(16)`.
"""

import pickle
import uuid

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.platform.crypto import (
    DataKey,
    DecryptionError,
    DekCache,
    Keyring,
    MasterKey,
    aad,
    decrypt,
    decrypt_payload,
    encrypt,
    encrypt_payload,
    generate_data_key,
    rewrap_dek,
    unwrap_dek,
    wrap_dek,
)
from app.platform.payloads import Payload

USER = uuid.UUID("0192f1c4-0000-7000-8000-000000000001")
OTHER_USER = uuid.UUID("0192f1c4-0000-7000-8000-000000000002")
ROW = uuid.UUID("0192f1c4-0000-7000-8000-0000000000aa")
OTHER_ROW = uuid.UUID("0192f1c4-0000-7000-8000-0000000000bb")
RAW_DEK = bytes(range(32))
RAW_KEK1 = bytes(range(32, 64))
RAW_KEK2 = bytes(range(64, 96))
AAD = aad("daily_logs", "payload_enc", ROW, USER)


class DailyLog(Payload):
    mood: int | None = None
    note: str | None = None


# ---------- AAD and format ----------


def test_aad_is_table_column_row_user() -> None:
    assert f"daily_logs:payload_enc:{ROW}:{USER}".encode() == AAD


def test_ciphertext_format_is_version_nonce_ciphertext_tag() -> None:
    plaintext = b'{"v":1,"mood":4}'
    blob = encrypt(DataKey(RAW_DEK), plaintext, AAD)
    assert blob[0] == 0x01
    assert len(blob) == 1 + 12 + len(plaintext) + 16
    # Independent check: standard AES-256-GCM with the nonce after the version byte.
    assert AESGCM(RAW_DEK).decrypt(blob[1:13], blob[13:], AAD) == plaintext


def test_round_trip() -> None:
    key = generate_data_key()
    assert decrypt(key, encrypt(key, b"hello", AAD), AAD) == b"hello"


def test_every_write_uses_a_new_nonce() -> None:
    key = DataKey(RAW_DEK)
    blobs = {encrypt(key, b"same", AAD) for _ in range(50)}
    assert len(blobs) == 50
    assert len({blob[1:13] for blob in blobs}) == 50


def test_generated_keys_are_distinct() -> None:
    keys = [generate_data_key() for _ in range(20)]
    blob = encrypt(keys[0], b"x", AAD)
    assert decrypt(keys[0], blob, AAD) == b"x"
    for other in keys[1:]:
        with pytest.raises(DecryptionError):
            decrypt(other, blob, AAD)


# ---------- tamper tests: everything fails closed ----------


def blob_for(plaintext: bytes = b'{"v":1,"note":"private"}') -> bytes:
    return encrypt(DataKey(RAW_DEK), plaintext, AAD)


@pytest.mark.parametrize("position", ["version", "nonce", "ciphertext", "tag"])
def test_any_changed_byte_fails(position: str) -> None:
    blob = bytearray(blob_for())
    index = {"version": 0, "nonce": 5, "ciphertext": 20, "tag": len(blob) - 1}[position]
    blob[index] ^= 0x01
    with pytest.raises(DecryptionError):
        decrypt(DataKey(RAW_DEK), bytes(blob), AAD)


def test_every_single_byte_flip_fails() -> None:
    blob = blob_for()
    for index in range(len(blob)):
        tampered = bytearray(blob)
        tampered[index] ^= 0x80
        with pytest.raises(DecryptionError):
            decrypt(DataKey(RAW_DEK), bytes(tampered), AAD)


@pytest.mark.parametrize(
    "other_aad",
    [
        aad("people", "payload_enc", ROW, USER),
        aad("daily_logs", "other_enc", ROW, USER),
        aad("daily_logs", "payload_enc", OTHER_ROW, USER),
        aad("daily_logs", "payload_enc", ROW, OTHER_USER),
        b"",
    ],
    ids=["table", "column", "row", "user", "empty"],
)
def test_changed_aad_fails(other_aad: bytes) -> None:
    with pytest.raises(DecryptionError):
        decrypt(DataKey(RAW_DEK), blob_for(), other_aad)


@pytest.mark.parametrize("version", [0x00, 0x02, 0xFF])
def test_unknown_version_byte_fails(version: int) -> None:
    blob = bytearray(blob_for())
    blob[0] = version
    with pytest.raises(DecryptionError):
        decrypt(DataKey(RAW_DEK), bytes(blob), AAD)


@pytest.mark.parametrize("length", [0, 1, 13, 1 + 12 + 15])
def test_truncated_input_fails(length: int) -> None:
    with pytest.raises(DecryptionError):
        decrypt(DataKey(RAW_DEK), blob_for()[:length], AAD)


def test_wrong_key_fails() -> None:
    with pytest.raises(DecryptionError):
        decrypt(DataKey(RAW_KEK1), blob_for(), AAD)


def test_errors_say_nothing_about_the_cause() -> None:
    messages = set()
    blob = blob_for()
    for bad in (blob[:5], b"\x02" + blob[1:], blob[:-1] + bytes([blob[-1] ^ 1])):
        with pytest.raises(DecryptionError) as caught:
            decrypt(DataKey(RAW_DEK), bad, AAD)
        messages.add(str(caught.value))
    assert messages == {"decryption failed"}


# ---------- keys never leak ----------


@pytest.mark.parametrize("key", [DataKey(RAW_DEK), MasterKey(RAW_KEK1)])
def test_keys_never_print_or_pickle(key: DataKey | MasterKey) -> None:
    for text in (repr(key), str(key), f"{key}"):
        assert RAW_DEK.hex() not in text
        assert RAW_KEK1.hex() not in text
        assert "\\x" not in text
    with pytest.raises(TypeError):
        pickle.dumps(key)


@pytest.mark.parametrize("length", [0, 16, 31, 33])
def test_keys_must_be_32_bytes(length: int) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        DataKey(b"\x00" * length)
    with pytest.raises(ValueError, match="32 bytes"):
        MasterKey(b"\x00" * length)


# ---------- DEK wrapping and KEK rotation ----------


def keyring(*versions: int) -> Keyring:
    raw = {1: RAW_KEK1, 2: RAW_KEK2}
    return Keyring({v: MasterKey(raw[v]) for v in versions})


def test_keyring_current_is_the_highest_version() -> None:
    assert keyring(1).current_version == 1
    assert keyring(1, 2).current_version == 2


def test_keyring_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Keyring({})


def test_wrap_uses_the_current_kek_and_dek_user_aad() -> None:
    version, wrapped = wrap_dek(keyring(1), DataKey(RAW_DEK), USER)
    assert version == 1
    assert wrapped[0] == 0x01
    assert AESGCM(RAW_KEK1).decrypt(wrapped[1:13], wrapped[13:], f"dek:{USER}".encode()) == RAW_DEK


def test_unwrap_round_trip() -> None:
    version, wrapped = wrap_dek(keyring(1), DataKey(RAW_DEK), USER)
    dek = unwrap_dek(keyring(1), version, wrapped, USER)
    assert decrypt(dek, encrypt(DataKey(RAW_DEK), b"note", AAD), AAD) == b"note"


def test_a_wrapped_dek_cannot_be_moved_to_another_user() -> None:
    version, wrapped = wrap_dek(keyring(1), DataKey(RAW_DEK), USER)
    with pytest.raises(DecryptionError):
        unwrap_dek(keyring(1), version, wrapped, OTHER_USER)


def test_unknown_kek_version_fails_closed() -> None:
    _, wrapped = wrap_dek(keyring(1), DataKey(RAW_DEK), USER)
    with pytest.raises(DecryptionError):
        unwrap_dek(keyring(1), 2, wrapped, USER)


def test_rewrap_moves_a_dek_to_the_new_kek() -> None:
    # Before rotation: DEK wrapped under KEK v1.
    old_version, old_wrapped = wrap_dek(keyring(1), DataKey(RAW_DEK), USER)
    field = encrypt(DataKey(RAW_DEK), b"note", AAD)
    # Rotation: add v2, re-wrap.
    new_version, new_wrapped = rewrap_dek(keyring(1, 2), old_version, old_wrapped, USER)
    assert (old_version, new_version) == (1, 2)
    assert new_wrapped != old_wrapped
    # Retire v1: the re-wrapped DEK still opens, and so does data encrypted before rotation.
    dek = unwrap_dek(keyring(2), new_version, new_wrapped, USER)
    assert decrypt(dek, field, AAD) == b"note"
    # The old wrapping no longer opens without v1.
    with pytest.raises(DecryptionError):
        unwrap_dek(keyring(2), old_version, old_wrapped, USER)


def test_rewrap_of_an_already_current_dek_is_a_fresh_wrap() -> None:
    version, wrapped = wrap_dek(keyring(1, 2), DataKey(RAW_DEK), USER)
    again_version, again = rewrap_dek(keyring(1, 2), version, wrapped, USER)
    assert again_version == 2
    dek = unwrap_dek(keyring(2), again_version, again, USER)
    assert decrypt(dek, encrypt(DataKey(RAW_DEK), b"note", AAD), AAD) == b"note"


# ---------- payloads ----------


def test_payload_round_trip_with_version_field() -> None:
    blob = encrypt_payload(DataKey(RAW_DEK), DailyLog(mood=4, note="private"), AAD)
    plaintext = AESGCM(RAW_DEK).decrypt(blob[1:13], blob[13:], AAD)
    assert plaintext.decode("utf-8").startswith("{")
    assert b'"v":1' in plaintext
    restored = decrypt_payload(DataKey(RAW_DEK), blob, AAD, DailyLog)
    assert restored == DailyLog(mood=4, note="private")


def test_payload_that_does_not_match_its_schema_fails_closed() -> None:
    bad = encrypt(DataKey(RAW_DEK), b'{"v":1,"mood":"not a number"}', AAD)
    with pytest.raises(DecryptionError):
        decrypt_payload(DataKey(RAW_DEK), bad, AAD, DailyLog)


def test_payload_that_is_not_json_fails_closed() -> None:
    bad = encrypt(DataKey(RAW_DEK), b"\xff\xfe not json", AAD)
    with pytest.raises(DecryptionError):
        decrypt_payload(DataKey(RAW_DEK), bad, AAD, DailyLog)


def test_unknown_payload_fields_survive_a_read_and_rewrite() -> None:
    # Written by newer code (a field this version does not know), read and rewritten by older code
    # after a rollback: the newer field must not be lost or make the row unreadable.
    newer = encrypt(DataKey(RAW_DEK), b'{"v":2,"mood":3,"added_later":"x"}', AAD)
    payload = decrypt_payload(DataKey(RAW_DEK), newer, AAD, DailyLog)
    assert payload.mood == 3
    rewritten = encrypt_payload(DataKey(RAW_DEK), payload, AAD)
    plaintext = AESGCM(RAW_DEK).decrypt(rewritten[1:13], rewritten[13:], AAD)
    assert b'"added_later":"x"' in plaintext
    assert b'"v":2' in plaintext


def test_payload_errors_do_not_echo_plaintext() -> None:
    bad = encrypt(DataKey(RAW_DEK), b'{"v":1,"mood":"my private note"}', AAD)
    with pytest.raises(DecryptionError) as caught:
        decrypt_payload(DataKey(RAW_DEK), bad, AAD, DailyLog)
    assert "private" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


# ---------- DEK cache ----------


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_cache_returns_keys_for_up_to_five_minutes() -> None:
    clock = FakeClock()
    cache = DekCache(clock=clock)
    key = DataKey(RAW_DEK)
    cache.put(USER, key)
    clock.now = 299.9
    assert cache.get(USER) is key
    clock.now = 300.0
    assert cache.get(USER) is None


def test_cache_ttl_cannot_exceed_five_minutes() -> None:
    with pytest.raises(ValueError, match="5 minutes"):
        DekCache(ttl_s=301)


def test_cache_entries_are_per_user_and_can_be_evicted() -> None:
    cache = DekCache(clock=FakeClock())
    cache.put(USER, DataKey(RAW_DEK))
    assert cache.get(OTHER_USER) is None
    cache.evict(USER)
    assert cache.get(USER) is None
    cache.put(USER, DataKey(RAW_DEK))
    cache.put(OTHER_USER, DataKey(RAW_KEK1))
    cache.clear()
    assert cache.get(USER) is None
    assert cache.get(OTHER_USER) is None


def test_cache_does_not_print_keys() -> None:
    cache = DekCache(clock=FakeClock())
    cache.put(USER, DataKey(RAW_DEK))
    assert RAW_DEK.hex() not in repr(cache)
    assert "\\x" not in repr(cache)


def test_keyring_prints_versions_but_never_keys() -> None:
    text = repr(keyring(1, 2))
    assert text == "<Keyring versions=[1, 2]>"
    assert RAW_KEK1.hex() not in text


# ---------- review: keyring order, exception context, boundaries ----------

RAW_KEK3 = bytes(range(96, 128))
RAW_KEK5 = bytes(range(128, 160))


@pytest.mark.parametrize(
    ("keys", "current"),
    [
        ({3: RAW_KEK3, 1: RAW_KEK1}, 3),
        ({2: RAW_KEK2, 5: RAW_KEK5}, 5),
        ({5: RAW_KEK5, 2: RAW_KEK2, 3: RAW_KEK3}, 5),
    ],
    ids=["out-of-order", "gap", "unsorted-with-gap"],
)
def test_current_is_the_highest_version_whatever_the_order(
    keys: dict[int, bytes], current: int
) -> None:
    ring = Keyring({version: MasterKey(raw) for version, raw in keys.items()})
    assert ring.current_version == current
    version, wrapped = wrap_dek(ring, DataKey(RAW_DEK), USER)
    assert version == current
    # The blob opens with the highest key only.
    raw = keys[current]
    assert AESGCM(raw).decrypt(wrapped[1:13], wrapped[13:], f"dek:{USER}".encode()) == RAW_DEK


@pytest.mark.parametrize("version", [0, -1])
def test_kek_versions_start_at_one(version: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        Keyring({version: MasterKey(RAW_KEK1)})


def test_payload_errors_carry_no_exception_context() -> None:
    import traceback

    bad = encrypt(DataKey(RAW_DEK), b'{"v":1,"mood":"my private note"}', AAD)
    with pytest.raises(DecryptionError) as caught:
        decrypt_payload(DataKey(RAW_DEK), bad, AAD, DailyLog)
    assert caught.value.__context__ is None
    assert "private" not in "".join(traceback.format_exception(caught.value))


def test_tag_errors_carry_no_exception_context() -> None:
    blob = bytearray(blob_for())
    blob[-1] ^= 1
    with pytest.raises(DecryptionError) as caught:
        decrypt(DataKey(RAW_DEK), bytes(blob), AAD)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_empty_plaintext_is_the_smallest_valid_blob() -> None:
    blob = encrypt(DataKey(RAW_DEK), b"", AAD)
    assert len(blob) == 1 + 12 + 16
    assert decrypt(DataKey(RAW_DEK), blob, AAD) == b""


def test_cache_ttl_cap_is_exactly_five_minutes() -> None:
    DekCache(ttl_s=300)
    with pytest.raises(ValueError, match="5 minutes"):
        DekCache(ttl_s=300.001)


def test_unknown_kek_version_errors_carry_no_context() -> None:
    _, wrapped = wrap_dek(keyring(1), DataKey(RAW_DEK), USER)
    with pytest.raises(DecryptionError) as caught:
        unwrap_dek(keyring(1), 9, wrapped, USER)
    assert caught.value.__context__ is None


def test_an_unwrapped_key_of_the_wrong_length_fails_closed() -> None:
    # Only someone holding the KEK can produce this; it must still be a DecryptionError.
    nonce = b"\x00" * 12
    sealed = AESGCM(RAW_KEK1).encrypt(nonce, b"\x01" * 16, f"dek:{USER}".encode())
    with pytest.raises(DecryptionError):
        unwrap_dek(keyring(1), 1, b"\x01" + nonce + sealed, USER)


@pytest.mark.parametrize(
    "keys",
    [{True: RAW_KEK1}, {1: RAW_KEK1, 2.0: RAW_KEK2}],
    ids=["bool-version", "float-version"],
)
def test_kek_versions_must_be_integers(keys: dict[object, bytes]) -> None:
    with pytest.raises((TypeError, ValueError)):
        Keyring({version: MasterKey(raw) for version, raw in keys.items()})  # type: ignore[misc]


def test_keyring_values_must_be_master_keys() -> None:
    with pytest.raises(TypeError, match="MasterKey"):
        Keyring({1: RAW_KEK1})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="MasterKey"):
        Keyring({1: DataKey(RAW_DEK)})  # type: ignore[dict-item]


def test_field_encryption_refuses_a_master_key() -> None:
    with pytest.raises(TypeError, match="DataKey"):
        encrypt(MasterKey(RAW_KEK1), b"x", AAD)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="DataKey"):
        decrypt(MasterKey(RAW_KEK1), blob_for(), AAD)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("table", "column"),
    [("a:b", "c"), ("a", "b:c"), ("Daily_Logs", "payload_enc"), ("daily logs", "x"), ("", "x")],
)
def test_aad_names_must_be_plain_identifiers(table: str, column: str) -> None:
    with pytest.raises(ValueError, match="identifier"):
        aad(table, column, ROW, USER)


def test_aad_ids_must_be_uuids() -> None:
    with pytest.raises(TypeError, match="UUID"):
        aad("daily_logs", "payload_enc", str(ROW).upper(), USER)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="UUID"):
        aad("daily_logs", "payload_enc", ROW, str(USER))  # type: ignore[arg-type]


def test_cache_sweeps_expired_keys_for_other_users() -> None:
    clock = FakeClock()
    cache = DekCache(clock=clock)
    cache.put(USER, DataKey(RAW_DEK))
    clock.now = 10_000
    cache.get(OTHER_USER)
    assert repr(cache) == "<DekCache entries=0>"
    cache.put(USER, DataKey(RAW_DEK))
    clock.now = 20_000
    cache.put(OTHER_USER, DataKey(RAW_KEK1))
    assert repr(cache) == "<DekCache entries=1>"
