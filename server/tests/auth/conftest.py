"""Auth API tests: the real app, the real database, a software authenticator and a test clock."""

import hashlib
import hmac
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import httpx
import pyotp
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.api import SessionContext, require_session
from app.auth.service import AuthService
from app.main import create_app
from app.platform.clock import utc_now
from app.platform.config import Settings
from tests.auth.authenticator import SoftAuthenticator

pytestmark = pytest.mark.integration

ORIGIN = "https://app.test"
RP_ID = "app.test"
HEADERS = {"Origin": ORIGIN, "X-LifeOS-Client": "web"}
DOMAIN = "@auth.test"
IP_KEY = "test-ip-hmac-key"
PASSWORD = "tangerine pelican orbit 42"


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC).replace(microsecond=0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@dataclass
class AuthEnv:
    app: FastAPI
    client: TestClient
    clock: Clock
    db: asyncpg.Connection
    admin_id: uuid.UUID
    authenticator: SoftAuthenticator
    # The client address the proxy reports (CF-Connecting-IP, CR-015); tests change it.
    ip: str = "203.0.113.10"

    def post(self, path: str, json: object | None = None) -> httpx.Response:
        return self.client.post(
            f"/api/v1{path}", json=json, headers=HEADERS | {"CF-Connecting-IP": self.ip}
        )

    def ip_hash(self, ip: str | None = None) -> bytes:
        return hmac.new(IP_KEY.encode(), (ip or self.ip).encode(), hashlib.sha256).digest()

    def register_password(
        self,
        token: str,
        password: str = PASSWORD,
        name: str = "Zee",
        email: str = f"zee{DOMAIN}",
    ) -> httpx.Response:
        return self.post(
            "/auth/register/password",
            {"token": token, "name": name, "email": email, "password": password},
        )

    def password_account(self, response: httpx.Response) -> pyotp.TOTP:
        """The TOTP generator for a password registration response."""
        assert response.status_code == 201, response.text
        totp = pyotp.parse_uri(response.json()["provisioning_uri"])
        assert isinstance(totp, pyotp.TOTP)
        return totp

    def code(self, totp: pyotp.TOTP, offset_s: int = 0) -> str:
        return totp.at(self.clock.now + timedelta(seconds=offset_s))

    def wrong_code(self, totp: pyotp.TOTP) -> str:
        """A 6-digit code that is not accepted now (none of the ±1-step codes)."""
        accepted = {self.code(totp, k * 30) for k in (-1, 0, 1)}
        return next(c for c in ("000000", "111111", "222222", "333333") if c not in accepted)

    def signin_password(
        self, code: str, password: str = PASSWORD, email: str = f"zee{DOMAIN}"
    ) -> httpx.Response:
        return self.post(
            "/auth/signin/password", {"email": email, "password": password, "totp": code}
        )

    async def invite(
        self,
        email: str | None = None,
        *,
        expires_in: timedelta | None = None,
        used: bool = False,
        revoked: bool = False,
    ) -> str:
        """Create an invite through the service (as the admin console will, T44), then put it in
        the requested state."""
        service: AuthService = self.app.state.auth
        token: str = self.client.portal.call(  # type: ignore[union-attr]
            service.create_invite, self.admin_id, email, self.clock.now
        )
        token_hash = hashlib.sha256(token.encode()).digest()
        if expires_in is not None:
            await self.db.execute(
                "UPDATE invites SET expires_at = $2 WHERE token_hash = $1",
                token_hash,
                self.clock.now + expires_in,
            )
        if used or revoked:
            await self.db.execute(
                "UPDATE invites SET used_at = $2, revoked_at = $3 WHERE token_hash = $1",
                token_hash,
                self.clock.now if used else None,
                self.clock.now if revoked else None,
            )
        return token

    async def invite_row(self, token: str) -> asyncpg.Record:
        row = await self.db.fetchrow(
            "SELECT * FROM invites WHERE token_hash = $1", hashlib.sha256(token.encode()).digest()
        )
        assert row is not None
        return row

    def register(
        self, token: str, name: str = "Zee", email: str = f"zee{DOMAIN}", **create: Any
    ) -> httpx.Response:
        options = self.post(
            "/auth/register/options", {"token": token, "name": name, "email": email}
        )
        assert options.status_code == 200, options.text
        credential = self.authenticator.create(options.json(), **create)
        return self.post(
            "/auth/register/verify",
            {"token": token, "name": name, "email": email, "credential": credential},
        )

    def set_cookie_flags(self, response: httpx.Response) -> dict[str, str]:
        """The lo_session Set-Cookie attributes of `response`, lower-cased names."""
        [raw] = [h for h in response.headers.get_list("set-cookie") if h.startswith("lo_session=")]
        attributes = {}
        for part in raw.split(";")[1:]:
            name, _, value = part.strip().partition("=")
            attributes[name.lower()] = value
        return attributes

    def signin(self, **get: Any) -> httpx.Response:
        options = self.post("/auth/signin/options", {})
        assert options.status_code == 200, options.text
        return self.post(
            "/auth/signin/verify", {"credential": self.authenticator.get(options.json(), **get)}
        )

    def session_token(self) -> str:
        return self.client.cookies["lo_session"]

    def use_session(self, token: str) -> None:
        """Make `token` the client's only session cookie (as the browser would hold it)."""
        self.client.cookies.clear()
        self.client.cookies.set("lo_session", token, domain=RP_ID)

    def whoami(self) -> httpx.Response:
        return self.client.get("/api/v1/_test/whoami", headers={"CF-Connecting-IP": self.ip})


def whoami_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/_test")

    @router.get("/whoami")
    async def whoami(session: SessionContext = Depends(require_session)) -> dict[str, str]:  # noqa: B008
        return {"user_id": str(session.user_id), "session_id": str(session.session_id)}

    return router


async def clean(db: asyncpg.Connection) -> None:
    await db.execute("DELETE FROM auth_challenges")
    await db.execute("DELETE FROM auth_events")
    await db.execute("DELETE FROM invites")
    await db.execute("DELETE FROM users WHERE email LIKE $1", f"%{DOMAIN}")


@pytest.fixture
async def env(migrated: str) -> AsyncIterator[AuthEnv]:
    db = await asyncpg.connect(migrated)
    await clean(db)
    admin_id = uuid.uuid4()
    await db.execute(
        "INSERT INTO users (id, email, display_name, role, dek_wrapped)"
        " VALUES ($1, $2, 'Ibrahim', 'admin', $3)",
        admin_id,
        f"admin{DOMAIN}",
        b"k",
    )
    settings = Settings(
        env="local",
        app_origin=ORIGIN,
        database_url=migrated,
        webauthn_rp_id=RP_ID,
        ip_hmac_key=IP_KEY,
    )
    app = create_app(settings)
    app.include_router(whoami_router())
    clock = Clock()
    app.dependency_overrides[utc_now] = clock
    with TestClient(app, base_url=ORIGIN) as client:
        yield AuthEnv(app, client, clock, db, admin_id, SoftAuthenticator(RP_ID, ORIGIN))
    await clean(db)
    await db.close()
