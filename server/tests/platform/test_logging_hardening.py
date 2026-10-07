"""T02: log privacy holds beyond the happy path (spec 12.5; review findings)."""

import io
import logging
import logging.config
import uuid
from types import MappingProxyType

import pytest
import uvicorn.config
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.platform.logging import SCRUBBED, configure_logging, scrub
from tests.platform.conftest import read_logs

ACCESS_KEYS = {
    "event",
    "level",
    "timestamp",
    "request_id",
    "method",
    "route",
    "status",
    "duration_ms",
}


@pytest.mark.parametrize("key", ["displayName", "Note", "pushBody", "TITLE", "user_NAME"])
def test_scrub_is_case_insensitive(key: str) -> None:
    assert scrub(None, "info", {"event": "x", key: "private"})[key] == SCRUBBED


def test_scrub_walks_any_mapping_and_sets() -> None:
    out = scrub(
        None,
        "info",
        {"event": "x", "m": MappingProxyType({"note": "n"}), "s": frozenset({"a"})},
    )
    assert out["m"] == {"note": SCRUBBED}
    assert out["s"] == ["a"]


def test_scrub_renders_unknown_objects_by_type_only() -> None:
    class Payload(BaseModel):
        body: str

    user_id = uuid.uuid4()
    out = scrub(None, "info", {"event": "x", "payload": Payload(body="secret"), "user_id": user_id})
    assert out["payload"] == "<Payload>"
    assert out["user_id"] == str(user_id)


def test_handler_log_lines_carry_the_request_id(
    client: TestClient, log_stream: io.StringIO
) -> None:
    response = client.get("/api/v1/_test/logs")
    [line] = [entry for entry in read_logs(log_stream) if entry["event"] == "handler.step"]
    assert line["request_id"] == response.headers["X-Request-ID"]


def test_access_line_has_exactly_the_allowed_fields(
    client: TestClient, log_stream: io.StringIO
) -> None:
    client.get(
        "/api/v1/healthz",
        headers={"X-Forwarded-For": "203.0.113.7", "CF-Connecting-IP": "203.0.113.7"},
    )
    [line] = [entry for entry in read_logs(log_stream) if entry["event"] == "http.request"]
    assert set(line) == ACCESS_KEYS
    assert "203.0.113.7" not in log_stream.getvalue()


def test_unknown_methods_are_logged_as_other(client: TestClient, log_stream: io.StringIO) -> None:
    client.request("INJECTED-TEXT", "/api/v1/healthz")
    [line] = [entry for entry in read_logs(log_stream) if entry["event"] == "http.request"]
    assert line["method"] == "OTHER"
    assert "INJECTED-TEXT" not in log_stream.getvalue()


def test_stdlib_logs_go_through_the_scrubber_without_exception_messages(
    log_stream: io.StringIO,
) -> None:
    logger = logging.getLogger("sqlalchemy.engine.test")
    try:
        raise ValueError("duplicate key: (email)=(zee@example.com)")
    except ValueError:
        logger.exception("db.error", extra={"display_name": "Zee"})
    text = log_stream.getvalue()
    assert "zee@example.com" not in text
    assert "Zee" not in text
    [line] = read_logs(log_stream)
    assert line["event"] == "db.error"
    assert line["exc_type"] == "ValueError"
    assert line["level"] == "error"


def test_uvicorn_logging_config_cannot_bring_back_access_logs(log_stream: io.StringIO) -> None:
    logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)
    configure_logging(log_stream)
    assert logging.getLogger("uvicorn.access").disabled
    logging.getLogger("uvicorn.error").error("server.problem")
    assert [line["event"] for line in read_logs(log_stream)] == ["server.problem"]


def test_library_info_messages_are_not_written(log_stream: io.StringIO) -> None:
    logging.getLogger("httpx").info("HTTP Request: GET https://app.test/daily-logs/2026-10-06")
    logging.getLogger("sqlalchemy.engine").info("SELECT ... WHERE date = '2026-10-06'")
    assert "2026-10-06" not in log_stream.getvalue()


def test_structlog_exception_logging_records_type_and_frames_only(log_stream: io.StringIO) -> None:
    import structlog

    log = structlog.get_logger()
    try:
        raise KeyError("note for zee@example.com")
    except KeyError as exc:
        log.exception("job.failed")
        log.error("job.failed_again", exc_info=exc)
    text = log_stream.getvalue()
    assert "zee@example.com" not in text
    first, second = read_logs(log_stream)
    assert first["exc_type"] == second["exc_type"] == "KeyError"
    assert first["frames"]
    assert "exc_info" not in first
    assert "exception" not in first
