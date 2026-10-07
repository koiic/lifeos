"""T02: the generated contract matches the wire format for errors (spec 9 intro, 9.1)."""

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.platform.conftest import GOOD_HEADERS

PROBLEM_REF = {"$ref": "#/components/schemas/Problem"}


def responses(app: FastAPI, path: str, method: str) -> dict[str, Any]:
    result: dict[str, Any] = app.openapi()["paths"][path][method]["responses"]
    return result


def test_declared_problem_responses_use_problem_json(app: FastAPI) -> None:
    unavailable = responses(app, "/api/v1/readyz", "get")["503"]
    assert unavailable["content"] == {"application/problem+json": {"schema": PROBLEM_REF}}


def test_validation_errors_are_documented_as_problems(app: FastAPI) -> None:
    invalid = responses(app, "/api/v1/_test/items/{item_id}", "get")["422"]
    assert invalid["content"] == {"application/problem+json": {"schema": PROBLEM_REF}}
    schemas = app.openapi()["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas
    assert {"Problem", "FieldError"} <= set(schemas)


def test_custom_validator_messages_never_echo_input(client: TestClient) -> None:
    response = client.post("/api/v1/_test/code", json={"code": "Zee-1987"}, headers=GOOD_HEADERS)
    assert response.status_code == 422
    assert "Zee-1987" not in response.text
    assert response.json()["errors"] == [
        {"field": "code", "code": "value_error", "message": "Value is not valid."}
    ]
