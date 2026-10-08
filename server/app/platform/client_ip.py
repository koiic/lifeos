"""The client's IP address and its HMAC (spec 7.2 `ip_hash`, 12.5, 14.3 as changed by CR-015).

Outside local the API is reachable only through `cloudflared` (no published port), so every
request has passed Cloudflare and carries `CF-Connecting-IP`; a request without a valid one is
refused — by `ClientIpRequiredMiddleware` for every `/api/` path except the probes (the
container healthcheck calls them directly). `X-Forwarded-For` is never read. Locally the header is
honoured when present (tests and development simulate clients) and the socket address is used
otherwise. IPs are never stored or logged: only `hash_ip`, an HMAC-SHA256 keyed by `IP_HMAC_KEY`.
IPv6 addresses are hashed by their /64 prefix (one home or server network), so rotating addresses
inside a /64 does not escape the per-IP lockout (AUTH-7).
"""

import hashlib
import hmac
import ipaddress

import structlog
from fastapi import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.platform.config import LOCAL_IP_HMAC_KEY, ConfigError, Settings
from app.platform.errors import problem_response

HEADER = "cf-connecting-ip"
MIN_KEY_BYTES = 32
PROBES = frozenset({"/api/v1/healthz", "/api/v1/readyz"})

log = structlog.get_logger()


class ClientIpMissing(Exception):
    """A deployed request without a valid `CF-Connecting-IP`: it did not come through the tunnel."""


# Cloudflare Workers egress: a Pages Function subrequest to another zone arrives with this as
# `CF-Connecting-IP`, which would put every client in one bucket. Treated as missing (fail
# closed); T15 keeps the Pages domain and the tunnel hostname in one zone.
WORKERS_EGRESS = ipaddress.ip_network("2a06:98c0:3600::/48")


def _parse(value: str | None) -> str | None:
    if not value:
        return None
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address in WORKERS_EGRESS:
        return None
    return str(address)


def client_ip(request: Request) -> str:
    settings: Settings = request.app.state.settings
    ip = _parse(request.headers.get(HEADER))
    if ip is not None:
        return ip
    if settings.env != "local":
        raise ClientIpMissing
    return request.client.host if request.client else "unknown"


def ip_hmac_key(settings: Settings) -> bytes:
    """The HMAC key; outside local the secret file is required and at least 32 bytes (a short
    key would let the small IPv4 space be brute-forced back from the hashes)."""
    if settings.ip_hmac_key is not None:
        key = settings.ip_hmac_key.get_secret_value().encode()
        if settings.env != "local" and len(key) < MIN_KEY_BYTES:
            raise ConfigError("secret file ip_hmac_key must hold at least 32 bytes")
        return key
    if settings.env != "local":
        raise ConfigError("secret file ip_hmac_key is required outside local")
    return LOCAL_IP_HMAC_KEY.encode()


def rate_key(ip: str) -> str:
    """What the hash is taken of: the address, or for IPv6 its /64 network."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip  # locally, a socket name such as "testclient"
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def hash_ip(settings: Settings, ip: str) -> bytes:
    return hmac.new(ip_hmac_key(settings), rate_key(ip).encode(), hashlib.sha256).digest()


def client_ip_hash(request: Request) -> bytes:
    """FastAPI dependency: the HMAC of this request's client IP."""
    return hash_ip(request.app.state.settings, client_ip(request))


class ClientIpRequiredMiddleware:
    """Outside local: refuse every `/api/` request (probes excepted) without a valid
    `CF-Connecting-IP` — it did not come through the tunnel (CR-015). Pure ASGI."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path: str = scope["path"]
            if path.startswith("/api/") and path not in PROBES:
                raw = dict(scope["headers"]).get(HEADER.encode())
                if _parse(raw.decode("latin-1") if raw else None) is None:
                    log.error("client_ip.missing")  # never the value (12.5)
                    response = problem_response(500, "The request did not come through the proxy.")
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)
