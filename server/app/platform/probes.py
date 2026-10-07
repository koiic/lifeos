"""Liveness and readiness probes: no auth, no data (spec 9.2, 14.1, 14.2)."""

from typing import Literal

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.platform.db import ping
from app.platform.errors import Problem, problem_response
from app.platform.logging import exception_fields

router = APIRouter(prefix="/api/v1", tags=["platform"])
log = structlog.get_logger()


class Status(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/healthz")
async def healthz() -> Status:
    """The API process is up."""
    return Status()


@router.get(
    "/readyz",
    response_model=Status,
    responses={503: {"model": Problem, "description": "Database unavailable"}},
)
async def readyz(request: Request) -> Status | JSONResponse:
    """The API can reach its database."""
    try:
        await ping(request.app.state.engine)
    except Exception as exc:
        log.warning("readyz.database_unavailable", **exception_fields(exc))
        return problem_response(503, "The database is not reachable.")
    return Status()
