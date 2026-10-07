"""T02: request logs carry ids, routes, statuses and timings only (spec 12.5)."""

import io
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from app.platform.logging import scrub
from tests.platform.conftest import GOOD_HEADERS, read_logs


def request_logs(stream: io.StringIO) -> list[dict[str, object]]:
    return [line for line in read_logs(stream) if line["event"] == "http.request"]


def test_each_request_logs_one_line_with_a_request_id(
    client: TestClient, log_stream: io.StringIO
) -> None:
    response = client.get("/api/v1/_test/items/2026-10-06?q=heavy")
    [line] = request_logs(log_stream)
    request_id = response.headers["X-Request-ID"]
    assert uuid.UUID(request_id)
    assert line["request_id"] == request_id
    assert line["method"] == "GET"
    assert line["route"] == "/api/v1/_test/items/{item_id}"
    assert line["status"] == 200
    assert isinstance(line["duration_ms"], float)
    assert line["level"] == "info"


def test_request_ids_are_unique_and_incoming_ids_ignored(
    client: TestClient, log_stream: io.StringIO
) -> None:
    first = client.get("/api/v1/healthz", headers={"X-Request-ID": "attacker-chosen"})
    second = client.get("/api/v1/healthz")
    assert first.headers["X-Request-ID"] != "attacker-chosen"
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


def test_logs_never_contain_paths_queries_bodies_or_ips(
    client: TestClient, log_stream: io.StringIO
) -> None:
    client.get("/api/v1/_test/items/2026-10-06?q=heavy")
    client.post("/api/v1/_test/echo", json={"mood": 2, "note": "a secret"}, headers=GOOD_HEADERS)
    text = log_stream.getvalue()
    for leaked in ["2026-10-06", "heavy", "a secret", "testclient", "127.0.0.1"]:
        assert leaked not in text


def test_unmatched_routes_are_logged_without_the_raw_path(
    client: TestClient, log_stream: io.StringIO
) -> None:
    client.get("/api/v1/daily-logs-typo/2026-10-06")
    [line] = request_logs(log_stream)
    assert line["route"] == "<unmatched>"
    assert line["status"] == 404
    assert "2026-10-06" not in log_stream.getvalue()


def test_unhandled_errors_log_type_and_frames_but_no_message_or_locals(
    client: TestClient, log_stream: io.StringIO
) -> None:
    response = client.get("/api/v1/_test/boom")
    errors = [line for line in read_logs(log_stream) if line["event"] == "http.unhandled_error"]
    assert len(errors) == 1
    error = errors[0]
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert error["exc_type"] == "RuntimeError"
    assert any(frame["function"] == "boom" for frame in error["frames"])
    assert "my private note" not in log_stream.getvalue()
    assert "failed while saving" not in log_stream.getvalue()
    [request_line] = request_logs(log_stream)
    assert request_line["status"] == 500


@pytest.mark.parametrize(
    "key", ["payload_enc", "note", "body", "title", "name", "display_name", "medication_name"]
)
def test_scrub_replaces_fields_with_sensitive_suffixes(key: str) -> None:
    out = scrub(None, "info", {"event": "x", key: "private"})
    assert out[key] == "[scrubbed]"


def test_scrub_recurses_into_nested_values() -> None:
    event = {
        "event": "x",
        "context": {"items": [{"title": "Vitamin D", "id": 1}], "nested": {"notes_body": "b"}},
    }
    out = scrub(None, "info", event)
    assert out["context"] == {
        "items": [{"title": "[scrubbed]", "id": 1}],
        "nested": {"notes_body": "[scrubbed]"},
    }


def test_scrub_keeps_safe_fields() -> None:
    event = {"event": "x", "route": "/a", "status": 200, "request_id": "r", "user_id": "u"}
    assert scrub(None, "info", dict(event)) == event


def test_scrub_applies_to_every_log_line(log_stream: io.StringIO) -> None:
    import structlog

    structlog.get_logger().info("job.done", job="health.rebuild_cycles", note="hidden")
    [line] = read_logs(log_stream)
    assert line["note"] == "[scrubbed]"
    assert line["job"] == "health.rebuild_cycles"
    assert "timestamp" in line


def test_uvicorn_access_log_is_disabled(log_stream: io.StringIO) -> None:
    assert logging.getLogger("uvicorn.access").disabled
