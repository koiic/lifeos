"""API entrypoint (spec 11.1): `uvicorn app.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.platform import probes
from app.platform.config import Settings, load_settings
from app.platform.db import create_engine
from app.platform.errors import install_error_handlers, install_problem_openapi
from app.platform.logging import configure_logging
from app.platform.middleware import (
    CsrfMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_engine(settings.database_url.get_secret_value())
        yield
        await app.state.engine.dispose()

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
    install_error_handlers(app)
    install_problem_openapi(app)
    # Added last runs first: request context wraps security headers, which wrap the CSRF check.
    app.add_middleware(CsrfMiddleware, app_origin=settings.app_origin)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(probes.router)
    return app


configure_logging()
app = create_app(load_settings())
