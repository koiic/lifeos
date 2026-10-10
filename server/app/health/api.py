"""health: HTTP layer: request and response handling only (plan 4.2).

Spec 9.2 `/daily-logs` endpoints (CHK-2, PER-2). Every endpoint requires a valid session.
"""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.auth.api import no_store, require_session
from app.auth.service import SessionContext
from app.health.schemas import DailyLog, DailyLogPutIn, DailyLogPutResponse
from app.health.service import (
    DailyLogService,
    HealthError,
)
from app.platform.errors import problem_response

router = APIRouter(
    prefix="/api/v1/daily-logs", tags=["daily-logs"], dependencies=[Depends(no_store)]
)

SignedIn = Annotated[SessionContext, Depends(require_session)]
SIGNED_IN: dict[int | str, dict[str, Any]] = {
    401: {"description": "Not signed in, or the session has ended."},
    403: {"description": "Account not activated."},
    429: {"description": "More than 300 requests in a minute on this session (9.1)."},
}

IdempotencyKey = Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")]


def get_daily_log_service(request: Request) -> DailyLogService:
    service: DailyLogService = request.app.state.health
    return service


DailyLogs = Annotated[DailyLogService, Depends(get_daily_log_service)]


def error_response(error: HealthError) -> JSONResponse:
    return problem_response(error.status, error.detail)


@router.put(
    "/{log_date}",
    responses=SIGNED_IN
    | {
        404: {"description": "Not found."},
        422: {"description": "Validation failure."},
    },
    response_model=DailyLogPutResponse,
)
async def upsert_daily_log(
    log_date: date,
    body: DailyLogPutIn,
    request: Request,
    session: SignedIn,
    service: DailyLogs,
    idempotency_key: IdempotencyKey = None,
) -> DailyLogPutResponse | JSONResponse:
    """Upsert daily log for date (CHK-2). Last-writer-wins by client_updated_at."""
    try:
        raw_body = await request.body()
        _, result = await service.upsert(
            session.user_id,
            log_date,
            body,
            idempotency_key=idempotency_key,
            raw_body=raw_body,
        )
        return result
    except HealthError as err:
        return error_response(err)


@router.get(
    "/{log_date}",
    responses=SIGNED_IN | {404: {"description": "Daily log not found."}},
    response_model=DailyLog,
)
async def get_daily_log(
    log_date: date,
    session: SignedIn,
    service: DailyLogs,
) -> DailyLog | JSONResponse:
    """Get daily log for a single date (CHK-2)."""
    try:
        return await service.get(session.user_id, log_date)
    except HealthError as err:
        return error_response(err)


@router.get(
    "",
    responses=SIGNED_IN | {422: {"description": "Invalid date range."}},
    response_model=list[DailyLog],
)
async def get_daily_logs(
    session: SignedIn,
    service: DailyLogs,
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
) -> list[DailyLog] | JSONResponse:
    """Get daily logs in a date range (max 400 days)."""
    try:
        return await service.get_range(session.user_id, from_date, to_date)
    except HealthError as err:
        return error_response(err)


@router.delete(
    "/{log_date}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=SIGNED_IN | {404: {"description": "Daily log not found."}},
)
async def delete_daily_log(
    log_date: date,
    request: Request,
    session: SignedIn,
    service: DailyLogs,
    idempotency_key: IdempotencyKey = None,
) -> Response:
    """Delete daily log for date (CHK-2, PER-2). Emits flow_changed if active flow removed."""
    try:
        raw_body = await request.body()
        await service.delete(
            session.user_id,
            log_date,
            idempotency_key=idempotency_key,
            raw_body=raw_body,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HealthError as err:
        return error_response(err)
