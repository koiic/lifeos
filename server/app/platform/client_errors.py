"""Client error reports (spec 11.7): `POST /api/v1/client-errors` → 204, 20 per minute.

The limit has no key in the spec; before sign-in there is no session and client IPs are not
trusted yet, so it applies to the endpoint as a whole, per API process (T10 Decisions). It runs
before the body is read, so invalid and oversized reports count too (the body itself is capped by
`BodySizeLimitMiddleware`).

Browser error messages can quote data (JSON.parse snippets, validation issues), so messages are
cleaned before logging: quoted spans, emails, UUIDs, dates and numbers become placeholders.
"""

import math
import re
import time
from collections.abc import Callable
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, StringConstraints, ValidationError

from app.platform.errors import Problem, problem_response

router = APIRouter(prefix="/api/v1", tags=["platform"])
log = structlog.get_logger()

LIMIT_PER_MINUTE = 20
MAX_BODY_BYTES = 4096

# A route pattern such as /health/:tab or /settings/*; no digits, so dates and ids cannot pass.
ROUTE_PATTERN = r"^(/|(/([a-z-]+|:[a-zA-Z]+|\*))+/?)$"
VERSION_PATTERN = r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$"

EMAIL = re.compile(r"[^\s@]+@[^\s@]+")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}(T[0-9:.]+(Z|[+-]\d{2}:?\d{2})?)?")
NUMBER = re.compile(r"\d+")


def clean_message(message: str) -> str:
    """Replace anything that could be user data with placeholders (same rules as the client)."""
    for quote in ('"', "'", "`"):
        first, last = message.find(quote), message.rfind(quote)
        if first != last:  # at least two: everything between the outermost pair goes
            message = message[:first] + "<str>" + message[last + 1 :]
    message = EMAIL.sub("<email>", message)
    message = UUID.sub("<uuid>", message)
    message = DATE.sub("<date>", message)
    return NUMBER.sub("<n>", message)


class FixedWindowLimiter:
    """Allows `limit` hits per window; `hit()` returns None or the seconds until the next window."""

    def __init__(
        self, limit: int, window_s: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self.clock = clock
        self.window_start = clock()
        self.count = 0

    def hit(self) -> int | None:
        now = self.clock()
        if now - self.window_start >= self.window_s:
            self.window_start = now
            self.count = 0
        if self.count >= self.limit:
            return max(1, math.ceil(self.window_start + self.window_s - now))
        self.count += 1
        return None


class ClientErrorReport(BaseModel):
    message: Annotated[
        str, StringConstraints(min_length=1, max_length=500), AfterValidator(clean_message)
    ]
    route: Annotated[str, StringConstraints(max_length=200, pattern=ROUTE_PATTERN)]
    version: Annotated[str, StringConstraints(max_length=50, pattern=VERSION_PATTERN)]


REQUEST_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": ClientErrorReport.model_json_schema()}},
    }
}


@router.post(
    "/client-errors",
    status_code=204,
    response_class=Response,
    response_model=None,
    openapi_extra=REQUEST_BODY,
    responses={
        422: {"model": Problem, "description": "The request has invalid fields."},
        429: {"model": Problem, "description": "Too many reports"},
    },
)
async def client_errors(request: Request) -> Response | JSONResponse:
    """Record a client-side error (message, route pattern, version; no user data)."""
    limiter: FixedWindowLimiter = request.app.state.client_error_limiter
    retry_after = limiter.hit()
    if retry_after is not None:
        return problem_response(
            429, "Too many error reports.", headers={"Retry-After": str(retry_after)}
        )
    try:
        report = ClientErrorReport.model_validate_json(await request.body())
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from None
    log.warning("client.error", message=report.message, route=report.route, version=report.version)
    return Response(status_code=204)
