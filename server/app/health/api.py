"""health: HTTP layer: request and response handling only (plan 4.2).

Spec 9.2 `/daily-logs` and `/symptoms` endpoints (CHK-2, CHK-3, PER-2).
Every endpoint requires a valid session.
"""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.auth.api import no_store, require_session
from app.auth.service import SessionContext
from app.health.schemas import (
    DailyLog,
    DailyLogPutIn,
    DailyLogPutResponse,
    Symptom,
    SymptomCreateIn,
    SymptomUpdateIn,
)
from app.health.service import (
    DailyLogService,
    HealthError,
    SymptomService,
)
from app.platform.errors import problem_response

router = APIRouter(dependencies=[Depends(no_store)])
daily_logs_router = APIRouter(prefix="/api/v1/daily-logs", tags=["daily-logs"])
symptoms_router = APIRouter(prefix="/api/v1/symptoms", tags=["symptoms"])

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


def get_symptom_service(request: Request) -> SymptomService:
    service: SymptomService = request.app.state.symptoms
    return service


SymptomsDep = Annotated[SymptomService, Depends(get_symptom_service)]


def error_response(error: HealthError) -> JSONResponse:
    return problem_response(error.status, error.detail)


# ---------------------------------------------------------------------------
# Daily Logs Endpoints
# ---------------------------------------------------------------------------


@daily_logs_router.put(
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
    """Upsert daily log for date (CHK-2, PER-2). LWW by client_updated_at."""
    try:
        raw_body = await request.body()
        status_code, resp = await service.upsert(
            session.user_id,
            log_date,
            body,
            idempotency_key=idempotency_key,
            raw_body=raw_body,
        )
        return JSONResponse(status_code=status_code, content=resp.model_dump(mode="json"))
    except HealthError as err:
        return error_response(err)


@daily_logs_router.get(
    "/{log_date}",
    responses=SIGNED_IN
    | {
        404: {"description": "Daily log not found."},
        422: {"description": "The request has invalid fields."},
    },
    response_model=DailyLog,
)
async def get_daily_log(
    log_date: date,
    session: SignedIn,
    service: DailyLogs,
) -> DailyLog | JSONResponse:
    """Get single daily log by date (CHK-2)."""
    try:
        return await service.get(session.user_id, log_date)
    except HealthError as err:
        return error_response(err)


@daily_logs_router.get(
    "",
    responses=SIGNED_IN
    | {
        422: {"description": "The request has invalid fields."},
    },
    response_model=list[DailyLog],
)
async def get_daily_logs_range(
    session: SignedIn,
    service: DailyLogs,
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
) -> list[DailyLog] | JSONResponse:
    """Get daily logs in date range [from, to] (max 400 days)."""
    try:
        return await service.get_range(session.user_id, from_date, to_date)
    except HealthError as err:
        return error_response(err)


@daily_logs_router.delete(
    "/{log_date}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=SIGNED_IN
    | {
        404: {"description": "Daily log not found."},
        422: {"description": "The request has invalid fields."},
    },
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


# ---------------------------------------------------------------------------
# Symptoms Catalogue Endpoints (CHK-3, spec 9.2)
# ---------------------------------------------------------------------------


@symptoms_router.get(
    "",
    responses=SIGNED_IN,
    response_model=list[Symptom],
)
async def list_symptoms(
    session: SignedIn,
    service: SymptomsDep,
    include_archived: bool = Query(default=False),
) -> list[Symptom]:
    """List symptoms catalogue, optionally including archived items (CHK-3)."""
    return await service.list(session.user_id, include_archived=include_archived)


@symptoms_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=SIGNED_IN | {422: {"description": "Validation failure."}},
    response_model=Symptom,
)
async def create_symptom(
    body: SymptomCreateIn,
    session: SignedIn,
    service: SymptomsDep,
) -> Symptom:
    """Create a new custom symptom in the catalogue (CHK-3)."""
    return await service.create(session.user_id, body)


@symptoms_router.get(
    "/{symptom_id}",
    responses=SIGNED_IN | {404: {"description": "Symptom not found."}},
    response_model=Symptom,
)
async def get_symptom(
    symptom_id: uuid.UUID,
    session: SignedIn,
    service: SymptomsDep,
) -> Symptom | JSONResponse:
    """Get single symptom by ID, including archived symptoms (CHK-3)."""
    try:
        return await service.get(session.user_id, symptom_id)
    except HealthError as err:
        return error_response(err)


@symptoms_router.patch(
    "/{symptom_id}",
    responses=SIGNED_IN
    | {
        404: {"description": "Symptom not found."},
        422: {"description": "Validation failure."},
    },
    response_model=Symptom,
)
async def update_symptom(
    symptom_id: uuid.UUID,
    body: SymptomUpdateIn,
    session: SignedIn,
    service: SymptomsDep,
) -> Symptom | JSONResponse:
    """Update symptom name, category, sort order, or unarchive (CHK-3)."""
    try:
        return await service.update(session.user_id, symptom_id, body)
    except HealthError as err:
        return error_response(err)


@symptoms_router.delete(
    "/{symptom_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=SIGNED_IN | {404: {"description": "Symptom not found."}},
)
async def delete_symptom(
    symptom_id: uuid.UUID,
    session: SignedIn,
    service: SymptomsDep,
) -> Response:
    """Archive a symptom (soft delete, CHK-3, spec 9.2)."""
    try:
        await service.archive(session.user_id, symptom_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HealthError as err:
        return error_response(err)


router.include_router(daily_logs_router)
router.include_router(symptoms_router)
