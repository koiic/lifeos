"""T07: the client IP (spec 14.3 as changed by CR-015) and its HMAC (7.2 `ip_hash`, 12.5)."""

import hashlib
import hmac
import io

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.platform.client_ip import ClientIpMissing, client_ip, hash_ip
from app.platform.config import Settings
from tests.platform.conftest import read_logs

KEY = SecretStr("k" * 32)


def settings(env: str) -> Settings:
    return Settings(
        env=env,  # type: ignore[arg-type]
        app_origin="https://a.example",
        database_url=SecretStr("postgresql://x"),
        ip_hmac_key=KEY,
    )


def probe(env: str) -> TestClient:
    app = FastAPI()
    app.state.settings = settings(env)

    @app.get("/ip")
    async def ip(value: str = Depends(client_ip)) -> dict[str, str]:
        return {"ip": value}

    @app.exception_handler(ClientIpMissing)
    async def missing(_request: object, _error: Exception) -> object:
        from fastapi.responses import JSONResponse

        return JSONResponse({"missing": True}, status_code=500)

    return TestClient(app)


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_envs_read_cf_connecting_ip(env: str) -> None:
    response = probe(env).get("/ip", headers={"CF-Connecting-IP": "203.0.113.5"})
    assert response.json() == {"ip": "203.0.113.5"}


@pytest.mark.parametrize("env", ["staging", "production"])
@pytest.mark.parametrize("value", [None, "", "not-an-ip", "203.0.113.5, 10.0.0.1"])
def test_deployed_envs_refuse_a_missing_or_bad_header(env: str, value: str | None) -> None:
    headers = {} if value is None else {"CF-Connecting-IP": value}
    response = probe(env).get("/ip", headers=headers)
    assert response.status_code == 500
    assert response.json() == {"missing": True}


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_envs_ignore_x_forwarded_for(env: str) -> None:
    response = probe(env).get(
        "/ip", headers={"X-Forwarded-For": "1.2.3.4", "CF-Connecting-IP": "203.0.113.5"}
    )
    assert response.json() == {"ip": "203.0.113.5"}


def test_local_uses_the_socket_address_without_the_header() -> None:
    assert probe("local").get("/ip").json() == {"ip": "testclient"}


def test_local_accepts_the_header_for_development_and_tests() -> None:
    response = probe("local").get("/ip", headers={"CF-Connecting-IP": "2001:db8::1"})
    assert response.json() == {"ip": "2001:db8::1"}


def test_ipv6_is_normalised() -> None:
    response = probe("production").get("/ip", headers={"CF-Connecting-IP": "2001:DB8:0::1"})
    assert response.json() == {"ip": "2001:db8::1"}


def test_the_hash_is_an_hmac_with_the_configured_key() -> None:
    expected = hmac.new(b"k" * 32, b"203.0.113.5", hashlib.sha256).digest()
    assert hash_ip(settings("production"), "203.0.113.5") == expected
    assert hash_ip(settings("production"), "203.0.113.6") != expected
    other = Settings(
        env="production",
        app_origin="https://a.example",
        database_url=SecretStr("postgresql://x"),
        ip_hmac_key=SecretStr("another key of at least 32 bytes!!"),
    )
    assert hash_ip(other, "203.0.113.5") != expected


@pytest.mark.parametrize("env", ["staging", "production"])
def test_a_deployed_api_refuses_to_start_without_the_key(env: str) -> None:
    from app.main import create_app
    from app.platform.config import ConfigError
    from tests.kek import TEST_KEK

    no_key = Settings(
        env=env,  # type: ignore[arg-type]
        app_origin="https://a.example",
        database_url=SecretStr("postgresql://x"),
        lifeos_kek=SecretStr(TEST_KEK),
    )
    with pytest.raises(ConfigError, match="ip_hmac_key"):
        create_app(no_key)


def test_ipv6_is_hashed_by_its_64_prefix() -> None:
    """AUTH-7 per IP: addresses inside one /64 (a home or server network) share a key."""
    production = settings("production")
    assert hash_ip(production, "2001:db8::1") == hash_ip(production, "2001:db8::ffff:2")
    assert hash_ip(production, "2001:db8::1") != hash_ip(production, "2001:db8:0:1::1")
    assert hash_ip(production, "::ffff:203.0.113.5") == hash_ip(production, "203.0.113.5")
    assert hash_ip(production, "203.0.113.5") != hash_ip(production, "203.0.113.6")


@pytest.mark.parametrize("env", ["staging", "production"])
def test_a_deployed_api_refuses_a_short_key(env: str) -> None:
    from app.main import create_app
    from app.platform.config import ConfigError
    from tests.kek import TEST_KEK

    short = Settings(
        env=env,  # type: ignore[arg-type]
        app_origin="https://a.example",
        database_url=SecretStr("postgresql://x"),
        lifeos_kek=SecretStr(TEST_KEK),
        ip_hmac_key=SecretStr("k" * 31),
    )
    with pytest.raises(ConfigError, match="32 bytes"):
        create_app(short)


def production_app() -> TestClient:
    """The real app (no lifespan: routing and middleware only)."""
    from app.main import create_app
    from tests.kek import TEST_IP_KEY, TEST_KEK

    app = create_app(
        Settings(
            env="production",
            app_origin="https://a.example",
            database_url=SecretStr("postgresql://x"),
            lifeos_kek=SecretStr(TEST_KEK),
            ip_hmac_key=SecretStr(TEST_IP_KEY),
        )
    )
    return TestClient(app, base_url="https://a.example")


@pytest.mark.parametrize("value", [None, "", "not-an-ip", "203.0.113.5, 10.0.0.1"])
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/auth/signin/options"),
        ("POST", "/api/v1/client-errors"),
        ("GET", "/api/v1/anything"),
    ],
)
def test_every_api_request_needs_the_header_outside_local(
    value: str | None, method: str, path: str
) -> None:
    """CR-015, app-wide: 500 problem+json and an error log without the value."""
    headers = {"Origin": "https://a.example", "X-LifeOS-Client": "web"}
    if value is not None:
        headers["CF-Connecting-IP"] = value
    response = production_app().request(method, path, headers=headers, json={})
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "The request did not come through the proxy."
    if value:
        assert value not in response.text


def test_the_missing_header_is_logged_without_its_value(log_stream: io.StringIO) -> None:
    production_app().get("/api/v1/anything", headers={"CF-Connecting-IP": "not-an-ip"})
    events = [entry["event"] for entry in read_logs(log_stream)]
    assert "client_ip.missing" in events
    assert "not-an-ip" not in log_stream.getvalue()


def test_the_probes_need_no_header() -> None:
    assert production_app().get("/api/v1/healthz").status_code == 200


@pytest.mark.parametrize("value", ["2a06:98c0:3600::103", "2a06:98c0:3600:1::5"])
def test_the_workers_egress_address_is_refused(value: str) -> None:
    """A cross-zone Pages Function subrequest reports Cloudflare's Workers egress address, which
    would put every client in one bucket: fail closed (T15 keeps one zone)."""
    response = production_app().get("/api/v1/anything", headers={"CF-Connecting-IP": value})
    assert response.status_code == 500
    assert probe("production").get("/ip", headers={"CF-Connecting-IP": value}).status_code == 500
