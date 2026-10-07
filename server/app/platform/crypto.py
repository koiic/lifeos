"""Field-level envelope encryption (spec 7.1, 12.2). The only module that imports `cryptography`.

- Field encryption: AES-256-GCM under the user's data key (DEK), random 96-bit nonce per write,
  AAD = `table:column:row_id:user_id`; format `0x01 ‖ nonce(12) ‖ ciphertext ‖ tag(16)`.
- DEKs: 32 random bytes, stored only wrapped by the master key (KEK) with AAD = `dek:<user_id>`, in
  the same format; the KEK version lives in `users.kek_version`.
- KEK rotation: a `Keyring` holds every live KEK version; new wraps use the highest.
- Every failure raises `DecryptionError("decryption failed")` with no cause and no context, so
  callers cannot tell why and no plaintext or key reaches logs. Keys never print or pickle.
"""

import re
import secrets
import time
import uuid
from collections.abc import Callable, Mapping
from typing import NoReturn

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import ValidationError

from app.platform.payloads import Payload

FORMAT_VERSION = 0x01
NONCE_BYTES = 12
TAG_BYTES = 16
KEY_BYTES = 32
MIN_BLOB = 1 + NONCE_BYTES + TAG_BYTES
DEK_CACHE_MAX_S = 300  # spec 12.2: cached for at most 5 minutes
IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")


class DecryptionError(Exception):
    """Decryption or verification failed. Deliberately says nothing about why."""

    def __init__(self) -> None:
        super().__init__("decryption failed")


def _fail() -> NoReturn:
    # Always called outside an `except` block, so the error carries no __context__ (which could
    # hold plaintext, e.g. a validation error quoting the decrypted value).
    raise DecryptionError


class _Key:
    """32 key bytes that never appear in repr, str, logs or pickles."""

    __slots__ = ("_raw",)

    def __init__(self, raw: bytes) -> None:
        if len(raw) != KEY_BYTES:
            raise ValueError(f"keys are {KEY_BYTES} bytes")
        self._raw = raw

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"

    __str__ = __repr__

    def __reduce__(self) -> NoReturn:
        raise TypeError("keys cannot be pickled")


class DataKey(_Key):
    """A user's data key (DEK); the only key field data is encrypted under."""


class MasterKey(_Key):
    """A master key (KEK) version; only ever wraps DEKs."""


def generate_data_key() -> DataKey:
    return DataKey(secrets.token_bytes(KEY_BYTES))


def aad(table: str, column: str, row_id: uuid.UUID, user_id: uuid.UUID) -> bytes:
    """Additional authenticated data binding a ciphertext to its table, column, row and user.

    Names must be plain lower-case identifiers and ids real UUIDs, so the string is unambiguous.
    """
    for name in (table, column):
        if not IDENTIFIER.fullmatch(name):
            raise ValueError("table and column must be lower-case identifiers")
    for value in (row_id, user_id):
        if not isinstance(value, uuid.UUID):
            raise TypeError("row_id and user_id must be UUIDs")
    return f"{table}:{column}:{row_id}:{user_id}".encode()


def _seal(key: _Key, plaintext: bytes, associated: bytes) -> bytes:
    nonce = secrets.token_bytes(NONCE_BYTES)
    return bytes([FORMAT_VERSION]) + nonce + AESGCM(key._raw).encrypt(nonce, plaintext, associated)


def _open(key: _Key, blob: bytes, associated: bytes) -> bytes:
    if len(blob) < MIN_BLOB or blob[0] != FORMAT_VERSION:
        _fail()
    nonce, sealed = blob[1 : 1 + NONCE_BYTES], blob[1 + NONCE_BYTES :]
    try:
        return AESGCM(key._raw).decrypt(nonce, sealed, associated)
    except InvalidTag:
        pass
    _fail()


def _require_data_key(key: DataKey) -> None:
    if not isinstance(key, DataKey):
        raise TypeError("field data is encrypted only under a DataKey (spec 12.2)")


def encrypt(key: DataKey, plaintext: bytes, associated: bytes) -> bytes:
    _require_data_key(key)
    return _seal(key, plaintext, associated)


def decrypt(key: DataKey, blob: bytes, associated: bytes) -> bytes:
    _require_data_key(key)
    return _open(key, blob, associated)


# ---------- DEK wrapping and KEK rotation ----------


class Keyring:
    """Live KEK versions (integers from 1); the highest wraps new DEKs (spec 12.2 item 5)."""

    def __init__(self, keys: Mapping[int, MasterKey]) -> None:
        if not keys:
            raise ValueError("a keyring needs at least one master key")
        for version, key in keys.items():
            if type(version) is not int:
                raise TypeError("KEK versions are integers")
            if version < 1:
                raise ValueError("KEK versions are positive integers (users.kek_version >= 1)")
            if not isinstance(key, MasterKey):
                raise TypeError("keyring values must be MasterKey")
        self._keys = dict(keys)
        self.current_version = max(self._keys)

    def key(self, version: int) -> MasterKey:
        key = self._keys.get(version)
        if key is None:
            _fail()
        return key

    def __repr__(self) -> str:
        return f"<Keyring versions={sorted(self._keys)}>"


def _dek_aad(user_id: uuid.UUID) -> bytes:
    return f"dek:{user_id}".encode()


def wrap_dek(keyring: Keyring, dek: DataKey, user_id: uuid.UUID) -> tuple[int, bytes]:
    """Wrap a DEK under the current KEK; returns (kek_version, wrapped)."""
    version = keyring.current_version
    return version, _seal(keyring.key(version), dek._raw, _dek_aad(user_id))


def unwrap_dek(keyring: Keyring, version: int, wrapped: bytes, user_id: uuid.UUID) -> DataKey:
    raw = _open(keyring.key(version), wrapped, _dek_aad(user_id))
    if len(raw) != KEY_BYTES:
        _fail()
    return DataKey(raw)


def rewrap_dek(
    keyring: Keyring, version: int, wrapped: bytes, user_id: uuid.UUID
) -> tuple[int, bytes]:
    """Re-wrap a DEK under the current KEK (rotation); returns (kek_version, wrapped)."""
    return wrap_dek(keyring, unwrap_dek(keyring, version, wrapped, user_id), user_id)


# ---------- payloads ----------


def encrypt_payload(dek: DataKey, payload: Payload, associated: bytes) -> bytes:
    return encrypt(dek, payload.model_dump_json().encode("utf-8"), associated)


def decrypt_payload[P: Payload](dek: DataKey, blob: bytes, associated: bytes, model: type[P]) -> P:
    plaintext = decrypt(dek, blob, associated)
    try:
        return model.model_validate_json(plaintext)
    except ValidationError:
        pass  # the validation error quotes the plaintext; fail outside the except block
    _fail()


# ---------- DEK cache ----------


class DekCache:
    """Unwrapped DEKs per user, kept for at most 5 minutes from `put`, in process memory only.

    Every call sweeps expired entries, so a key nobody reads again does not linger. Account deletion
    and session revocation must call `evict` (T06, T08, T43).
    """

    def __init__(
        self, ttl_s: float = DEK_CACHE_MAX_S, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if ttl_s > DEK_CACHE_MAX_S:
            raise ValueError("DEKs are cached for at most 5 minutes (spec 12.2)")
        self._ttl_s = ttl_s
        self._clock = clock
        self._entries: dict[uuid.UUID, tuple[float, DataKey]] = {}

    def _sweep(self) -> None:
        now = self._clock()
        expired = [
            u for u, (stored_at, _) in self._entries.items() if now - stored_at >= self._ttl_s
        ]
        for user_id in expired:
            del self._entries[user_id]

    def get(self, user_id: uuid.UUID) -> DataKey | None:
        self._sweep()
        entry = self._entries.get(user_id)
        return None if entry is None else entry[1]

    def put(self, user_id: uuid.UUID, key: DataKey) -> None:
        self._sweep()
        self._entries[user_id] = (self._clock(), key)

    def evict(self, user_id: uuid.UUID) -> None:
        self._entries.pop(user_id, None)

    def clear(self) -> None:
        self._entries.clear()

    def __repr__(self) -> str:
        return f"<DekCache entries={len(self._entries)}>"
