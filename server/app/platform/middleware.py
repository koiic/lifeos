"""HTTP middleware: request context and logging, CSRF check, security headers (spec 9.1, 12.4,
12.5)."""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

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


class CsrfMiddleware(BaseHTTPMiddleware):
    """Mutations must carry `X-LifeOS-Client: web` and an Origin equal to the app origin."""

    def __init__(self, app: ASGIApp, app_origin: str) -> None:
        super().__init__(app)
        self.app_origin = app_origin

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if requires_csrf_check(request.method) and (
            request.headers.get(CLIENT_HEADER) != CLIENT_VALUE
            or request.headers.get("Origin") != self.app_origin
        ):
            return problem_response(403, "This request must come from the Life OS app.")
        return await call_next(request)
