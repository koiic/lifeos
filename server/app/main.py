"""API entrypoint (spec 11.1): `uvicorn app.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.admin import api as admin_api
from app.auth import api as auth_api
from app.auth.service import AccountService, AuthService
from app.platform import client_errors, probes
from app.platform.client_ip import ClientIpMissing, ClientIpRequiredMiddleware, ip_hmac_key
from app.platform.config import Settings, load_settings
from app.platform.crypto import load_keyring
from app.platform.db import ADMIN_WRITE_ROLE, APP_ROLE, create_engine, verify_role
from app.platform.errors import install_error_handlers, install_problem_openapi, problem_response
from app.platform.logging import configure_logging
from app.platform.middleware import (
    BodySizeLimitMiddleware,
    CsrfMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)

log = structlog.get_logger()


def create_app(settings: Settings) -> FastAPI:
    # Loaded here, not in the lifespan: a bad master-key file stops the process at import.
    keyring = load_keyring(settings)
    ip_hmac_key(settings)  # outside local the IP_HMAC_KEY file is required (14.3)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_engine(settings.database_url.get_secret_value())
        if settings.env != "local":
            await verify_role(app.state.engine, APP_ROLE)
        app.state.auth = AuthService(
            app.state.engine, keyring, settings.webauthn_rp_id, settings.app_origin
        )
        admin_engine = None
        if settings.database_admin_write_url is not None:
            admin_engine = create_engine(
                settings.database_admin_write_url.get_secret_value(), role=ADMIN_WRITE_ROLE
            )
            if settings.env != "local":
                await verify_role(admin_engine, ADMIN_WRITE_ROLE)
        app.state.account = AccountService(app.state.auth, admin_engine)
        yield
        await app.state.engine.dispose()
        if admin_engine is not None:
            await admin_engine.dispose()

    app = FastAPI(
        title="Life OS",
        version="0.1.0",
        lifespan=lifespan,
        # Swagger UI and ReDoc load assets from a CDN (spec 12.4): never served.
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json" if settings.env == "local" else None,
    )
    app.state.settings = settings
    app.state.client_error_limiter = client_errors.KeyedLimiter(
        limit=client_errors.LIMIT_PER_MINUTE, window_s=60
    )
    install_error_handlers(app)

    async def no_client_ip(_request: Request, _error: Exception) -> JSONResponse:
        # Outside local every request comes through cloudflared with CF-Connecting-IP (CR-015).
        log.error("client_ip.missing")
        return problem_response(500, "The request did not come through the proxy.")

    app.add_exception_handler(ClientIpMissing, no_client_ip)
    install_problem_openapi(app)
    # Added last runs first: request context wraps security headers, which wrap the body-size
    # limit, which wraps the CSRF check.
    if settings.env != "local":
        app.add_middleware(ClientIpRequiredMiddleware)
    app.add_middleware(CsrfMiddleware, app_origin=settings.app_origin)
    app.add_middleware(
        BodySizeLimitMiddleware,
        limits={"/api/v1/client-errors": client_errors.MAX_BODY_BYTES},
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(probes.router)
    app.include_router(client_errors.router)
    app.include_router(auth_api.router)
    app.include_router(admin_api.router)
    return app


configure_logging()
app = create_app(load_settings())
