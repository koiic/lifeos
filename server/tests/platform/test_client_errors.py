"""T10: POST /api/v1/client-errors → 204, rate-limited to 20 per minute (spec 11.7)."""

import io
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.platform.client_errors import FixedWindowLimiter
from tests.platform.conftest import GOOD_HEADERS, read_logs

URL = "/api/v1/client-errors"
REPORT = {"message": "TypeError: x is undefined", "route": "/health/cycle", "version": "0.1.0"}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(app: FastAPI) -> FakeClock:
    """Drive the app's own limiter (as configured in create_app) with a fake clock."""
    fake = FakeClock()
    limiter: FixedWindowLimiter = app.state.client_error_limiter
    limiter.clock = fake
    limiter.window_start = fake()
    return fake


def test_the_app_limits_reports_to_20_per_minute(app: FastAPI) -> None:
    limiter: FixedWindowLimiter = app.state.client_error_limiter
    assert (limiter.limit, limiter.window_s) == (20, 60)


def test_report_is_accepted_and_logged(client: TestClient, log_stream: io.StringIO) -> None:
    response = client.post(URL, json=REPORT, headers=GOOD_HEADERS)
    assert response.status_code == 204
    assert response.content == b""
    [line] = [entry for entry in read_logs(log_stream) if entry["event"] == "client.error"]
    assert set(line) == {"event", "level", "timestamp", "request_id", "message", "route", "version"}
    assert line["message"] == REPORT["message"]
    assert line["route"] == "/health/cycle"
    assert line["version"] == "0.1.0"
    assert line["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("message", "a" * 501),
        ("message", ""),
        ("route", "/today?date=2026-10-06"),
        ("route", "/today#x"),
        ("route", "today"),
        ("route", "/" + "a" * 200),
        ("route", "/health/2026-10-06"),
        ("route", "/meds/doses/0192f2a1"),
        ("route", "/Health"),
        ("version", "v" * 51),
        ("version", "latest"),
    ],
)
def test_invalid_reports_are_rejected(client: TestClient, field: str, value: str) -> None:
    response = client.post(URL, json=REPORT | {field: value}, headers=GOOD_HEADERS)
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field
    assert "2026-10-06" not in response.text


def test_the_csrf_rule_applies(client: TestClient) -> None:
    assert client.post(URL, json=REPORT).status_code == 403


def test_the_21st_report_in_a_minute_is_rate_limited(client: TestClient, clock: FakeClock) -> None:
    for _ in range(20):
        assert client.post(URL, json=REPORT, headers=GOOD_HEADERS).status_code == 204
    response = client.post(URL, json=REPORT, headers=GOOD_HEADERS)
    assert response.status_code == 429
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 429
    assert response.json()["title"] == "Too Many Requests"
    assert response.headers["Retry-After"] == "60"
    clock.now += 59
    retry = client.post(URL, json=REPORT, headers=GOOD_HEADERS)
    assert retry.status_code == 429
    assert retry.headers["Retry-After"] == "1"


def test_the_window_resets_after_a_minute(client: TestClient, clock: FakeClock) -> None:
    for _ in range(20):
        client.post(URL, json=REPORT, headers=GOOD_HEADERS)
    clock.now += 60
    assert client.post(URL, json=REPORT, headers=GOOD_HEADERS).status_code == 204


def test_limiter_counts_per_window() -> None:
    clock = FakeClock()
    limiter = FixedWindowLimiter(limit=2, window_s=60, clock=clock)
    assert limiter.hit() is None
    assert limiter.hit() is None
    assert limiter.hit() == 60
    clock.now += 30.5
    assert limiter.hit() == 30
    clock.now += 29.5
    assert limiter.hit() is None


@pytest.mark.parametrize("route", ["/", "/today", "/health/:tab", "/meds/doses/:id", "/settings/*"])
def test_route_patterns_are_accepted(client: TestClient, route: str) -> None:
    response = client.post(URL, json=REPORT | {"route": route}, headers=GOOD_HEADERS)
    assert response.status_code == 204


@pytest.mark.parametrize(
    ("message", "leaked"),
    [
        (
            'SyntaxError: Unexpected token \'h\', "{"flow":"heavy"}" is not valid JSON',
            ["heavy", "flow"],
        ),
        (
            "RangeError: Invalid date 2026-10-06T09:30:00Z for zee@example.com",
            ["2026-10-06", "zee@"],
        ),
        ("Error: dose 0192f2a1-7c3e-7f00-8a00-000000000001 missing", ["0192f2a1"]),
        ("Error: expected `note` got 'my private note'", ["private"]),
    ],
)
def test_messages_are_cleaned_before_logging(
    client: TestClient, log_stream: io.StringIO, message: str, leaked: list[str]
) -> None:
    response = client.post(URL, json=REPORT | {"message": message}, headers=GOOD_HEADERS)
    assert response.status_code == 204
    text = log_stream.getvalue()
    for value in leaked:
        assert value not in text
    assert "client.error" in text


def test_invalid_reports_count_towards_the_limit(client: TestClient, clock: FakeClock) -> None:
    for _ in range(20):
        assert client.post(URL, json={"bad": 1}, headers=GOOD_HEADERS).status_code == 422
    assert client.post(URL, json=REPORT, headers=GOOD_HEADERS).status_code == 429


def test_oversized_bodies_are_rejected_unread(client: TestClient, log_stream: io.StringIO) -> None:
    big = REPORT | {"message": "x" * 5000}
    response = client.post(URL, json=big, headers=GOOD_HEADERS)
    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"
    assert "client.error" not in log_stream.getvalue()


def test_chunked_bodies_over_the_cap_are_rejected(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"message": "'
        yield b"x" * 5000
        yield b'", "route": "/today", "version": "0.1.0"}'

    response = client.post(
        URL, content=chunks(), headers=GOOD_HEADERS | {"Content-Type": "application/json"}
    )
    assert response.status_code == 413


def test_other_endpoints_keep_the_default_cap(client: TestClient) -> None:
    body = {"mood": 3, "note": "x" * 5000}
    assert client.post("/api/v1/_test/echo", json=body, headers=GOOD_HEADERS).status_code == 200
    huge = {"mood": 3, "note": "x" * (1024 * 1024 + 1)}
    assert client.post("/api/v1/_test/echo", json=huge, headers=GOOD_HEADERS).status_code == 413


@pytest.mark.parametrize(
    ("field", "value"),
    [("message", "a" * 500), ("route", "/" + "a" * 199), ("version", "1.2.3-" + "a" * 44)],
)
def test_values_at_the_limits_are_accepted(client: TestClient, field: str, value: str) -> None:
    response = client.post(URL, json=REPORT | {field: value}, headers=GOOD_HEADERS)
    assert response.status_code == 204


def test_chunked_oversize_bodies_to_model_routes_are_413(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"mood": 3, "note": "'
        yield b"x" * (1024 * 1024 + 1)
        yield b'"}'

    response = client.post(
        "/api/v1/_test/echo",
        content=chunks(),
        headers=GOOD_HEADERS | {"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"
