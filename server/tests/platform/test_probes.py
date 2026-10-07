"""T02: liveness and readiness, no auth, no data (spec 9.2)."""

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.platform.config import Settings
from tests.platform.conftest import ORIGIN
from tests.platform.test_errors import assert_problem


def test_healthz_is_ok_without_a_database(log_stream: io.StringIO) -> None:
    settings = Settings(env="local", app_origin=ORIGIN, database_url="postgresql://x@127.0.0.1:1/x")
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.fixture
def unreachable_client(log_stream: io.StringIO) -> Iterator[TestClient]:
    settings = Settings(env="local", app_origin=ORIGIN, database_url="postgresql://x@127.0.0.1:1/x")
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        yield client


def test_readyz_is_a_503_problem_when_the_database_is_unreachable(
    unreachable_client: TestClient, log_stream: io.StringIO
) -> None:
    response = unreachable_client.get("/api/v1/readyz")
    assert_problem(response, 503, "Service Unavailable")
    assert "readyz.database_unavailable" in log_stream.getvalue()
    for leaked in ["127.0.0.1", "x@", ":1/x", "Connect call failed"]:
        assert leaked not in response.text
        assert leaked not in log_stream.getvalue()


@pytest.mark.integration
def test_readyz_is_ok_with_the_database(client: TestClient) -> None:
    response = client.get("/api/v1/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_probes_need_no_auth_headers(client: TestClient) -> None:
    assert client.get("/api/v1/healthz").status_code == 200
