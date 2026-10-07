"""HTTP middleware: request context and logging, CSRF check, security headers (spec 9.1, 12.4,
12.5)."""

import time
import uuid

import structlog
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.platform.errors import problem_response
from app.platform.logging import exception_fields

# Deny by default: every method except these (compared exactly) needs the CSRF check.
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LOGGED_METHODS = SAFE_METHODS | {"POST", "PUT", "PATCH", "DELETE"}
CLIENT_HEADER = "X-LifeOS-Client"
CLIENT_VALUE = "web"

SECURITY_HEADERS = {
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

log = structlog.get_logger()


def route_template(request: Request) -> str:
    """The matched route's path template; never the raw path, which can hold dates and ids."""
    route = request.scope.get("route")
    return str(getattr(route, "path", None) or "<unmatched>")


def requires_csrf_check(method: str) -> bool:
    return method not in SAFE_METHODS


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Request id, one access log line per request, and a problem+json 500 for anything unhandled.

    Outermost of our middleware, so its log line and 500 cover the others too.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            log.error("http.unhandled_error", **exception_fields(exc))
            response = problem_response(500, "Something went wrong.")
            for name, value in SECURITY_HEADERS.items():
                response.headers[name] = value
        response.headers["X-Request-ID"] = request_id
        log.info(
            "http.request",
            # The method is client-controlled text; only known values reach the logs.
            method=request.method if request.method in LOGGED_METHODS else "OTHER",
            route=route_template(request),
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        structlog.contextvars.clear_contextvars()
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response


class CsrfMiddleware:
    """Mutations must carry `X-LifeOS-Client: web` and an Origin equal to the app origin.

    Pure ASGI (headers only): it never wraps `receive`, so body errors raised further out (the
    body-size limit) reach the route's error handling unchanged.
    """

    def __init__(self, app: ASGIApp, app_origin: str) -> None:
        self.app = app
        self.app_origin = app_origin.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and requires_csrf_check(scope["method"]):
            headers = dict(scope["headers"])
            if (
                headers.get(CLIENT_HEADER.lower().encode()) != CLIENT_VALUE.encode()
                or headers.get(b"origin") != self.app_origin
            ):
                response = problem_response(403, "This request must come from the Life OS app.")
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


DEFAULT_MAX_BODY_BYTES = 1024 * 1024


class BodySizeLimitMiddleware:
    """Reject request bodies over a per-path limit (413 problem+json) without buffering them.

    A declared `Content-Length` over the limit is refused before the app runs; a chunked body is
    counted as it streams and fails with 413 once it passes the limit. Later tasks with larger
    uploads (imports, spec 13.2) add their path to `limits`.
    """

    def __init__(
        self, app: ASGIApp, limits: dict[str, int], default: int = DEFAULT_MAX_BODY_BYTES
    ) -> None:
        self.app = app
        self.limits = limits
        self.default = default

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limits.get(scope["path"], self.default)
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            response = problem_response(413, "The request body is too large.")
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail="The request body is too large.")
            return message

        await self.app(scope, limited_receive, send)
