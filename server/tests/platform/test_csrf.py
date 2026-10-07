"""T02: mutating requests need X-LifeOS-Client: web and the app Origin (spec 9.1)."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.platform.middleware import requires_csrf_check
from tests.platform.conftest import GOOD_HEADERS, ORIGIN

BODY = {"mood": 3, "note": "n"}
MUTATING = ["POST", "PUT", "PATCH", "DELETE"]


def send(client: TestClient, method: str, headers: dict[str, str]) -> httpx.Response:
    if method == "DELETE":
        return client.request(method, "/api/v1/_test/echo", headers=headers)
    return client.request(method, "/api/v1/_test/echo", json=BODY, headers=headers)


@pytest.mark.parametrize("method", MUTATING)
def test_mutation_with_header_and_origin_is_allowed(client: TestClient, method: str) -> None:
    assert send(client, method, GOOD_HEADERS).status_code == 200


@pytest.mark.parametrize("method", MUTATING)
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": ORIGIN},
        {"X-LifeOS-Client": "web"},
        {"Origin": ORIGIN, "X-LifeOS-Client": "mobile"},
        {"Origin": "https://evil.test", "X-LifeOS-Client": "web"},
        {"Origin": ORIGIN + ":444", "X-LifeOS-Client": "web"},
        {"Origin": "null", "X-LifeOS-Client": "web"},
    ],
    ids=[
        "none",
        "origin-only",
        "header-only",
        "wrong-client",
        "other-origin",
        "other-port",
        "null",
    ],
)
def test_mutation_without_both_is_forbidden(
    client: TestClient, method: str, headers: dict[str, str]
) -> None:
    response = send(client, method, headers)
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["title"] == "Forbidden"


def test_reads_need_neither(client: TestClient) -> None:
    assert client.get("/api/v1/_test/items/abc").status_code == 200


def test_unknown_methods_are_checked_too(client: TestClient) -> None:
    response = client.request("PROPFIND", "/api/v1/_test/echo")
    assert response.status_code == 403


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_only_safe_methods_skip_the_check(method: str) -> None:
    assert not requires_csrf_check(method)


@pytest.mark.parametrize("method", ["POST", "post", "Get", "PROPFIND", "PUT", "DELETE"])
def test_everything_else_is_checked(method: str) -> None:
    assert requires_csrf_check(method)
