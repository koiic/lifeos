"""core: HTTP layer: request and response handling only (plan 4.2).

Spec 9.2 `/me` rows and CR-030: the bootstrap, her profile and settings (versions as `ETag`, a
change sends `If-Match`, CR-004), and her consent (12.6). Every endpoint needs a session.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.api import Client, Now, SessionContext, no_store, require_session
from app.core.schemas import (
    Consent,
    ConsentIn,
    Me,
    Profile,
    ProfileChange,
    ProfileConflict,
    Settings,
    SettingsChange,
    SettingsConflict,
)
from app.core.service import (
    InvalidSettings,
    MeError,
    MeService,
    VersionConflict,
    parse_version,
)
from app.platform.errors import PROBLEM_JSON, FieldError, problem_response

router = APIRouter(prefix="/api/v1/me", tags=["me"], dependencies=[Depends(no_store)])

SignedIn = Annotated[SessionContext, Depends(require_session)]
SIGNED_IN: dict[int | str, dict[str, Any]] = {
    401: {"description": "Not signed in, or the session has ended."},
    403: {"description": "Account not activated (CR-014)."},
    429: {"description": "More than 300 requests in a minute on this session (9.1)."},
}


def change_responses(conflict: type[BaseModel]) -> dict[int | str, dict[str, Any]]:
    return SIGNED_IN | {
        409: {
            "description": "The version in If-Match is not current; `current` holds it.",
            "model": conflict,
            "content": {"application/problem+json": {}},
        },
        428: {"description": "If-Match is missing (CR-004)."},
    }


IfMatch = Annotated[str | None, Header(alias="If-Match")]
DeviceTimezone = Annotated[str | None, Header(alias="X-Timezone")]


def get_service(request: Request) -> MeService:
    service: MeService = request.app.state.me
    return service


Service = Annotated[MeService, Depends(get_service)]


def etag(version: str) -> dict[str, str]:
    return {"ETag": f'"{version}"'}


def error_response(error: MeError) -> JSONResponse:
    if isinstance(error, VersionConflict):
        body = {
            "type": "about:blank",
            "title": "Conflict",
            "status": 409,
            "detail": error.detail,
            "current": error.current.model_dump(mode="json"),
        }
        return JSONResponse(
            body, status_code=409, media_type=PROBLEM_JSON, headers=etag(error.current.version)
        )
    if isinstance(error, InvalidSettings):
        field = FieldError(field=error.field, code=error.code, message=error.message)
        return problem_response(422, error.detail, [field])
    return problem_response(error.status, error.detail)


@router.get("", responses=SIGNED_IN)
async def get_me(session: SignedIn, service: Service, x_timezone: DeviceTimezone = None) -> Me:
    """Bootstraps the client (9.2): profile, settings, consent, health mode and how the device's
    timezone compares with hers (CR-030)."""
    return await service.me(session.user_id, x_timezone)


@router.patch("", responses=change_responses(ProfileConflict), response_model=Profile)
async def change_profile(
    body: ProfileChange,
    session: SignedIn,
    service: Service,
    response: Response,
    if_match: IfMatch = None,
) -> Profile | JSONResponse:
    """SET-1: her display name and timezone."""
    try:
        profile = await service.change_profile(session.user_id, body, parse_version(if_match))
    except MeError as error:
        return error_response(error)
    response.headers.update(etag(profile.version))
    return profile


@router.patch("/settings", responses=change_responses(SettingsConflict), response_model=Settings)
async def change_settings(
    body: SettingsChange,
    session: SignedIn,
    service: Service,
    response: Response,
    if_match: IfMatch = None,
) -> Settings | JSONResponse:
    """SET-1 (week start, units), SET-2 (theme), SET-3 (notifications, quiet hours, check-in
    time), SET-5 (discreet) and optional fields."""
    try:
        settings = await service.change_settings(session.user_id, body, parse_version(if_match))
    except MeError as error:
        return error_response(error)
    response.headers.update(etag(settings.version))
    return settings


@router.post("/consent", responses=SIGNED_IN)
async def give_consent(
    body: ConsentIn, session: SignedIn, service: Service, client: Client, now: Now
) -> Consent:
    """12.6, CR-030: her explicit consent to health data, at the current version; stored once."""
    return await service.consent(session.user_id, body.version, now, client.ip_hash)
