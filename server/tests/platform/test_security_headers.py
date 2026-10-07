"""T02: the API sets the spec 12.4 security headers; no third-party docs pages."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.platform.config import Settings
from tests.platform.conftest import GOOD_HEADERS, ORIGIN

EXPECTED = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        "font-src 'self'; connect-src 'self'; worker-src 'self'; manifest-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; upgrade-insecure-requests"
    ),
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


@pytest.mark.parametrize(
    "path", ["/api/v1/healthz", "/api/v1/nothing-here", "/api/v1/_test/boom", "/api/v1/_test/echo"]
)
def test_security_headers_on_every_response(client: TestClient, path: str) -> None:
    response = client.get(path)
    for name, value in EXPECTED.items():
        assert response.headers.get(name) == value, name


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/api/v1/docs"])
def test_interactive_docs_are_disabled(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_openapi_document_is_served_only_locally(client: TestClient, database_url: str) -> None:
    assert client.get("/api/v1/openapi.json").status_code == 200
    settings = Settings(env="production", app_origin=ORIGIN, database_url=database_url)
    # Routing only: no lifespan (a production start-up requires a real lifeos_app login, T05).
    prod = TestClient(create_app(settings), base_url=ORIGIN)
    assert prod.get("/api/v1/openapi.json").status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "headers", "status"),
    [
        ("POST", "/api/v1/_test/echo", {}, 403),
        ("POST", "/api/v1/_test/echo", GOOD_HEADERS, 422),
        ("GET", "/api/v1/_test/boom", {}, 500),
    ],
)
def test_headers_and_request_id_on_error_paths(
    client: TestClient, method: str, path: str, headers: dict[str, str], status: int
) -> None:
    response = client.request(method, path, json={}, headers=headers)
    assert response.status_code == status
    assert response.headers.get("X-Request-ID")
    for name, value in EXPECTED.items():
        assert response.headers.get(name) == value, name


def test_headers_on_readyz_503(database_url: str, log_stream: object) -> None:
    settings = Settings(env="local", app_origin=ORIGIN, database_url="postgresql://x@127.0.0.1:1/x")
    with TestClient(create_app(settings), base_url=ORIGIN) as unreachable:
        response = unreachable.get("/api/v1/readyz")
    assert response.status_code == 503
    for name, value in EXPECTED.items():
        assert response.headers.get(name) == value, name
