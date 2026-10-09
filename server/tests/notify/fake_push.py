"""Test-only: a fake Web Push service (a real HTTP server on 127.0.0.1) and a browser-side
subscriber that can decrypt what was sent to it (RFC 8291, aes128gcm)."""

import base64
import json
import secrets
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import http_ece
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass
class Received:
    path: str
    headers: dict[str, str]
    body: bytes


@dataclass
class FakePushService:
    """Records every push; answers with `statuses[path]` (default 201 Created), and with a
    `Location` header for the paths in `redirects`."""

    port: int = 0
    received: list[Received] = field(default_factory=list)
    statuses: dict[str, int] = field(default_factory=dict)
    redirects: dict[str, str] = field(default_factory=dict)

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def to(self, path: str) -> list[Received]:
        return [r for r in self.received if r.path == path]


@contextmanager
def fake_push_service() -> Iterator[FakePushService]:
    service = FakePushService()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            headers = {k.lower(): v for k, v in self.headers.items()}
            service.received.append(Received(self.path, headers, body))
            self.send_response(service.statuses.get(self.path, 201))
            if self.path in service.redirects:
                self.send_header("Location", service.redirects[self.path])
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    service.port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield service
    finally:
        server.shutdown()
        server.server_close()


@dataclass
class Subscriber:
    """A browser's push subscription: its keys, and decryption of what it receives."""

    private_key: ec.EllipticCurvePrivateKey
    auth: bytes

    @classmethod
    def new(cls) -> "Subscriber":
        return cls(ec.generate_private_key(ec.SECP256R1()), secrets.token_bytes(16))

    @property
    def p256dh(self) -> str:
        return b64(
            self.private_key.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
            )
        )

    @property
    def auth_secret(self) -> str:
        return b64(self.auth)

    def subscription(self, endpoint: str) -> dict[str, Any]:
        return {"endpoint": endpoint, "keys": {"p256dh": self.p256dh, "auth": self.auth_secret}}

    def decrypt(self, body: bytes) -> dict[str, Any]:
        plain = http_ece.decrypt(body, private_key=self.private_key, auth_secret=self.auth)
        message: dict[str, Any] = json.loads(plain)
        return message
