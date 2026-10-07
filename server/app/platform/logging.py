"""Structured JSON logs that never carry user data (spec 12.5, plan 4.2).

Lines hold request ids, routes, statuses, timings, user ids and job names. Any field whose name ends
in a sensitive suffix (any letter case) is scrubbed, at any depth; values that are not plain data
are rendered by type name only. Exceptions are recorded by type and stack frames only: messages and
local variables can quote user data. Standard-library loggers (uvicorn, SQLAlchemy, asyncpg, later
Procrastinate) go through the same chain.

Free-text log messages are not scrubbed: pass data as fields, never inside the message.
"""

import datetime as dt
import logging
import sys
import traceback
import uuid
from collections.abc import Mapping, Set
from enum import Enum
from typing import TextIO

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

SENSITIVE_SUFFIXES = ("_enc", "note", "body", "title", "name")
SCRUBBED = "[scrubbed]"
PLAIN = (str, int, float, bool, type(None))
STRINGIFIED = (uuid.UUID, dt.date, dt.datetime, dt.time, dt.timedelta, Enum)
# Fields structlog itself adds; never user data.
RESERVED = {"event", "level", "timestamp", "logger"}


def _is_sensitive(key: object) -> bool:
    return isinstance(key, str) and key not in RESERVED and key.lower().endswith(SENSITIVE_SUFFIXES)


def _scrub_value(value: object) -> object:
    if isinstance(value, PLAIN):
        return value
    if isinstance(value, STRINGIFIED):
        return str(value)
    if isinstance(value, Mapping):
        return {k: SCRUBBED if _is_sensitive(k) else _scrub_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple | Set):
        return [_scrub_value(v) for v in value]
    return f"<{type(value).__name__}>"


def scrub(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """structlog processor: replace sensitive fields with a marker, recursively."""
    for key, value in list(event_dict.items()):
        if key.startswith("_"):  # structlog internals (e.g. _record); dropped before rendering
            continue
        event_dict[key] = SCRUBBED if _is_sensitive(key) else _scrub_value(value)
    return event_dict


def exception_fields(exc: BaseException) -> dict[str, object]:
    """Type and frames of an exception, without its message or local variables.

    The frame key is `function`, not `name`: `name` would be scrubbed (spec 12.5 suffix rule).
    """
    frames = [
        {"file": frame.filename, "line": frame.lineno, "function": frame.name}
        for frame in traceback.extract_tb(exc.__traceback__)
    ]
    return {"exc_type": type(exc).__name__, "frames": frames}


def safe_exceptions(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """Replace `exc_info` (structlog or stdlib) with the exception's type and frames only."""
    exc_info = event_dict.pop("exc_info", None)
    if exc_info is True:
        exc_info = sys.exc_info()
    if isinstance(exc_info, BaseException):
        event_dict.update(exception_fields(exc_info))
    elif isinstance(exc_info, tuple) and isinstance(exc_info[1], BaseException):
        event_dict.update(exception_fields(exc_info[1]))
    return event_dict


def configure_logging(stream: TextIO | None = None) -> None:
    """JSON lines to `stream` (stdout by default) through the scrubber, for structlog and stdlib."""
    output = stream or sys.stdout
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        safe_exceptions,
        scrub,
    ]
    structlog.configure(
        processors=[*shared, structlog.processors.JSONRenderer()],
        logger_factory=structlog.WriteLoggerFactory(file=output),
        cache_logger_on_first_use=False,
    )

    # Standard-library records: only the message and level are kept (pass_foreign_args=False and
    # no ExtraAdder, so `extra=` fields are dropped), then the same chain as above.
    handler = logging.StreamHandler(output)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    # Library INFO messages are free text (e.g. httpx/SQLAlchemy quote URLs, paths and SQL);
    # only warnings and errors from libraries are kept. App logs use structlog, not stdlib.
    root.setLevel(logging.WARNING)

    # Uvicorn installs its own plain-text handlers; route its loggers through ours instead.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    # Uvicorn's server log is start-up and shutdown lines only; keep it at INFO.
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    # Uvicorn's access log includes client IP addresses; our own request line replaces it.
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True
