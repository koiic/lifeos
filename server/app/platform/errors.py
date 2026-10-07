"""RFC 9457 problem details for every error response (spec 9.1)."""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"
# RFC 9110 names; Python 3.12's http module still uses the older phrase for 422.
TITLES = {422: "Unprocessable Content"}
LOCATIONS = {"body", "query", "path", "header", "cookie"}
# Messages from custom validators are free text and could quote the input; use fixed ones.
FIXED_MESSAGES = {"value_error": "Value is not valid.", "assertion_error": "Value is not valid."}
PROBLEM_CONTENT = {PROBLEM_JSON: {"schema": {"$ref": "#/components/schemas/Problem"}}}
# Every mutation can be refused by the CSRF check and the body-size limit (middleware).
MUTATION_PROBLEMS = {
    "403": "Missing X-LifeOS-Client header or wrong Origin.",
    "413": "The request body is too large.",
}
MUTATING_METHODS = {"post", "put", "patch", "delete"}


class FieldError(BaseModel):
    field: str
    code: str
    message: str


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    errors: list[FieldError] | None = None


def problem_response(
    status: int,
    detail: str | None = None,
    errors: list[FieldError] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    phrase = TITLES.get(status, HTTPStatus(status).phrase)
    problem = Problem(title=phrase, status=status, detail=detail or phrase + ".", errors=errors)
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=status,
        media_type=PROBLEM_JSON,
        headers=headers,
    )


def field_path(loc: tuple[int | str, ...]) -> str:
    parts = list(loc[1:] if loc and loc[0] in LOCATIONS else loc)
    return ".".join(str(p) for p in parts)


async def http_error(_request: Request, error: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, error)  # registered for this type only
    detail = exc.detail if isinstance(exc.detail, str) else None
    phrase_default = detail == HTTPStatus(exc.status_code).phrase
    return problem_response(
        exc.status_code, None if phrase_default else detail, headers=exc.headers
    )


async def validation_error(_request: Request, error: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, error)  # registered for this type only
    # Never echo the submitted input: only location, error type and message.
    errors = [
        FieldError(
            field=field_path(tuple(e["loc"])),
            code=e["type"],
            message=FIXED_MESSAGES.get(e["type"], e["msg"]),
        )
        for e in exc.errors()
    ]
    return problem_response(422, "The request has invalid fields.", errors)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)


def install_problem_openapi(app: FastAPI) -> None:
    """Document errors as they are sent: `application/problem+json` with the `Problem` schema.

    FastAPI documents declared error models under `application/json` and adds its own
    `HTTPValidationError` for 422; both would contradict spec 9.1 in the generated client types.
    """

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            routes=app.routes,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        _, definitions = models_json_schema(
            [(Problem, "serialization")], ref_template="#/components/schemas/{model}"
        )
        components.update(definitions["$defs"])
        for unused in ("HTTPValidationError", "ValidationError"):
            components.pop(unused, None)
        for operations in schema.get("paths", {}).values():
            for method, operation in operations.items():
                responses = operation.setdefault("responses", {})
                if method in MUTATING_METHODS:
                    for status, description in MUTATION_PROBLEMS.items():
                        if status in responses:
                            # A route's own reason for this status, plus the middleware's.
                            declared = responses[status]["description"]
                            responses[status]["description"] = f"{declared} Or: {description}"
                        else:
                            responses[status] = {"description": description}
                for status, response in responses.items():
                    # Errors a route declares without a model are problem+json too.
                    if status.startswith(("4", "5")) and "content" not in response:
                        response["content"] = PROBLEM_CONTENT
                    json_schema = response.get("content", {}).get("application/json", {})
                    ref = json_schema.get("schema", {}).get("$ref", "")
                    if ref.endswith(("/Problem", "/HTTPValidationError")):
                        response["content"] = PROBLEM_CONTENT
                        if status == "422":
                            response["description"] = "The request has invalid fields."
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]  # FastAPI's documented override hook
