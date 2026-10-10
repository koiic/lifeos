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
    CalendarMonthResponse,
    CycleExclusionIn,
    CycleHistoryItem,
    CycleStateResponse,
    DailyLog,
    DailyLogPutIn,
    DailyLogPutResponse,
    HealthProfileResponse,
    HealthProfileUpdateIn,
    PeriodActionResponse,
    PeriodEndIn,
    PeriodStartConfirmIn,
    PeriodStartIn,
    Symptom,
    SymptomCreateIn,
    SymptomUpdateIn,
    TodayResponse,
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
period_router = APIRouter(prefix="/api/v1/health/period", tags=["health-period"])

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


# ---------------------------------------------------------------------------
# Period Start / End Endpoints (PER-1, PER-4, spec 9.2)
# ---------------------------------------------------------------------------


@period_router.post(
    "/start",
    responses=SIGNED_IN | {422: {"description": "Validation failure."}},
    response_model=PeriodActionResponse,
)
async def start_period(
    body: PeriodStartIn,
    session: SignedIn,
    service: DailyLogs,
) -> PeriodActionResponse | JSONResponse:
    """Tapping 'Period started' sets flow Medium on that date's log (PER-1)."""
    try:
        return await service.start_period(session.user_id, body.date)
    except HealthError as err:
        return error_response(err)


@period_router.post(
    "/end",
    responses=SIGNED_IN | {422: {"description": "Validation failure."}},
    response_model=PeriodActionResponse,
)
async def end_period(
    body: PeriodEndIn,
    session: SignedIn,
    service: DailyLogs,
) -> PeriodActionResponse | JSONResponse:
    """Tapping 'Period ended' confirms last flow day (PER-1, PER-4)."""
    try:
        return await service.end_period(session.user_id, body.date)
    except HealthError as err:
        return error_response(err)


# ---------------------------------------------------------------------------
# Calendar Month Endpoint (CSC-3, spec 9.2)
# ---------------------------------------------------------------------------

health_router = APIRouter(prefix="/api/v1/health", tags=["health"])


@health_router.get(
    "/profile",
    responses=SIGNED_IN | {422: {"description": "Validation failure."}},
    response_model=HealthProfileResponse,
)
async def get_health_profile(
    session: SignedIn,
    service: DailyLogs,
) -> HealthProfileResponse | JSONResponse:
    """Mode, usual lengths, hints (spec 9.2)."""
    try:
        return await service.get_health_profile(session.user_id)
    except HealthError as err:
        return error_response(err)


@health_router.put(
    "/profile",
    responses=SIGNED_IN | {422: {"description": "Validation failure."}},
    response_model=HealthProfileResponse,
)
async def update_health_profile(
    body: HealthProfileUpdateIn,
    session: SignedIn,
    service: DailyLogs,
) -> HealthProfileResponse | JSONResponse:
    """Update profile: mode, usual lengths, hints. Mode change records mode_started_on."""
    try:
        return await service.update_health_profile(session.user_id, body)
    except HealthError as err:
        return error_response(err)


@health_router.get(
    "/cycle",
    responses=SIGNED_IN | {422: {"description": "Validation failure."}},
    response_model=CycleStateResponse,
)
async def get_cycle(
    session: SignedIn,
    service: DailyLogs,
) -> CycleStateResponse | JSONResponse:
    """Current cycle, prediction, states (spec 8.5, 9.2, 9.3)."""
    try:
        return await service.get_cycle_state(session.user_id)
    except HealthError as err:
        return error_response(err)


@health_router.get(
    "/cycles",
    responses=SIGNED_IN | {422: {"description": "Validation failure."}},
    response_model=list[CycleHistoryItem],
)
async def get_cycles(
    session: SignedIn,
    service: DailyLogs,
) -> list[CycleHistoryItem] | JSONResponse:
    """Cycle history with exclusion reasons (spec 9.2)."""
    try:
        return await service.get_cycles_history(session.user_id)
    except HealthError as err:
        return error_response(err)


@health_router.post(
    "/cycles/exclusions",
    responses=SIGNED_IN | {422: {"description": "Validation failure."}},
)
async def set_cycle_exclusion(
    body: CycleExclusionIn,
    session: SignedIn,
    service: DailyLogs,
) -> Any:
    """Exclude/include a cycle (spec 9.2, CYC-5)."""
    try:
        return await service.set_cycle_exclusion(
            session.user_id, body.start_date, body.excluded, body.reason
        )
    except HealthError as err:
        return error_response(err)


@health_router.post(
    "/period-starts/confirm",
    responses=SIGNED_IN | {422: {"description": "Validation failure."}},
)
async def confirm_period_start(
    body: PeriodStartConfirmIn,
    session: SignedIn,
    service: DailyLogs,
) -> Any:
    """Answer 'Is this a new period?' for intra-cycle bleed (spec 8.1, 9.2)."""
    try:
        return await service.confirm_period_start(session.user_id, body.date, body.is_new_period)
    except HealthError as err:
        return error_response(err)


@health_router.get(
    "/calendar",
    responses=SIGNED_IN | {422: {"description": "Validation failure."}},
    response_model=CalendarMonthResponse,
)
async def get_calendar_month(
    session: SignedIn,
    service: DailyLogs,
    month: Annotated[
        str | None,
        Query(
            pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
            description="Month in YYYY-MM format (defaults to current month in user's timezone)",
        ),
    ] = None,
) -> CalendarMonthResponse | JSONResponse:
    """Month view data (CSC-3, spec 9.2)."""
    try:
        return await service.get_calendar_month(session.user_id, month)
    except HealthError as err:
        return error_response(err)


# ---------------------------------------------------------------------------
# Today Endpoint (TOD-3, TOD-5, spec 9.3)
# ---------------------------------------------------------------------------

today_router = APIRouter(prefix="/api/v1/today", tags=["today"])


@today_router.get(
    "",
    responses=SIGNED_IN | {422: {"description": "Validation failure."}},
    response_model=TodayResponse,
)
async def get_today(
    session: SignedIn,
    service: DailyLogs,
    target_date: Annotated[
        date | None,
        Query(
            alias="date",
            description="Date in YYYY-MM-DD format (defaults to current date in user's timezone)",
        ),
    ] = None,
) -> TodayResponse | JSONResponse:
    """Aggregated Today payload: greeting, cycle card, check-in state, streak (TOD-3, TOD-5)."""
    try:
        return await service.get_today(session.user_id, target_date)
    except HealthError as err:
        return error_response(err)


router.include_router(daily_logs_router)
router.include_router(symptoms_router)
router.include_router(period_router)
router.include_router(health_router)
router.include_router(today_router)
