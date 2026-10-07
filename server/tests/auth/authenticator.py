"""A software WebAuthn authenticator for tests (a passkey without a phone).

It builds real `attestationObject` / `authenticatorData` structures with an ES256 key (or RS256 /
EdDSA on request), the way a platform authenticator does, so the server's verification runs
unmodified.
"""

import base64
import hashlib
import json
import secrets
import struct
from dataclasses import dataclass, field
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

type PrivateKey = ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey | ed25519.Ed25519PrivateKey

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_BE = 0x08
FLAG_BS = 0x10
FLAG_AT = 0x40


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass
class Passkey:
    credential_id: bytes
    private_key: PrivateKey
    user_handle: bytes
    sign_count: int = 0


@dataclass
class SoftAuthenticator:
    rp_id: str
    origin: str
    user_verification: bool = True
    passkeys: list[Passkey] = field(default_factory=list)

    @staticmethod
    def _new_key(alg: str) -> PrivateKey:
        if alg == "RS256":
            return rsa.generate_private_key(public_exponent=65537, key_size=2048)
        if alg == "EdDSA":
            return ed25519.Ed25519PrivateKey.generate()
        return ec.generate_private_key(ec.SECP256R1())

    @staticmethod
    def _cose_key(key: PrivateKey) -> bytes:
        if isinstance(key, rsa.RSAPrivateKey):
            rsa_numbers = key.public_key().public_numbers()
            n = rsa_numbers.n.to_bytes((rsa_numbers.n.bit_length() + 7) // 8, "big")
            return cbor2.dumps({1: 3, 3: -257, -1: n, -2: rsa_numbers.e.to_bytes(3, "big")})
        if isinstance(key, ed25519.Ed25519PrivateKey):
            raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            return cbor2.dumps({1: 1, 3: -8, -1: 6, -2: raw})
        numbers = key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    @staticmethod
    def _sign(key: PrivateKey, data: bytes) -> bytes:
        if isinstance(key, rsa.RSAPrivateKey):
            return key.sign(data, padding.PKCS1v15(), hashes.SHA256())
        if isinstance(key, ed25519.Ed25519PrivateKey):
            return key.sign(data)
        return key.sign(data, ec.ECDSA(hashes.SHA256()))

    def _flags(self, extra: int = 0) -> int:
        return FLAG_UP | (FLAG_UV if self.user_verification else 0) | FLAG_BE | FLAG_BS | extra

    def _client_data(self, kind: str, challenge: str, origin: str | None) -> bytes:
        return json.dumps(
            {
                "type": kind,
                "challenge": challenge,
                "origin": origin or self.origin,
                "crossOrigin": False,
            }
        ).encode()

    def create(
        self,
        options: dict[str, Any],
        *,
        origin: str | None = None,
        rp_id: str | None = None,
        alg: str = "ES256",
    ) -> dict[str, Any]:
        """navigator.credentials.create() for the given creation options (JSON form)."""
        key = self._new_key(alg)
        credential_id = secrets.token_bytes(32)
        user_handle = unb64url(options["user"]["id"])
        passkey = Passkey(credential_id, key, user_handle)
        self.passkeys.append(passkey)
        rp_hash = hashlib.sha256((rp_id or self.rp_id).encode()).digest()
        attested = (
            b"\x00" * 16
            + struct.pack(">H", len(credential_id))
            + credential_id
            + self._cose_key(key)
        )
        auth_data = rp_hash + bytes([self._flags(FLAG_AT)]) + struct.pack(">I", 0) + attested
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        client_data = self._client_data("webauthn.create", options["challenge"], origin)
        return {
            "id": b64url(credential_id),
            "rawId": b64url(credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    def get(
        self,
        options: dict[str, Any],
        passkey: Passkey | None = None,
        *,
        sign_count: int | None = None,
        user_handle: bytes | None = None,
        origin: str | None = None,
        rp_id: str | None = None,
    ) -> dict[str, Any]:
        """navigator.credentials.get() with a discoverable passkey (the most recent by default)."""
        passkey = passkey or self.passkeys[-1]
        passkey.sign_count = passkey.sign_count + 1 if sign_count is None else sign_count
        rp_hash = hashlib.sha256((rp_id or self.rp_id).encode()).digest()
        auth_data = rp_hash + bytes([self._flags()]) + struct.pack(">I", passkey.sign_count)
        client_data = self._client_data("webauthn.get", options["challenge"], origin)
        signature = self._sign(
            passkey.private_key, auth_data + hashlib.sha256(client_data).digest()
        )
        return {
            "id": b64url(passkey.credential_id),
            "rawId": b64url(passkey.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": b64url(
                    user_handle if user_handle is not None else passkey.user_handle
                ),
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }
