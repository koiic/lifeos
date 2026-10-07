"""T02: every error is RFC 9457 problem+json (spec 9.1)."""

from typing import Any

from fastapi.testclient import TestClient

from tests.platform.conftest import GOOD_HEADERS

PROBLEM = "application/problem+json"


def assert_problem(response: Any, status: int, title: str) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM
    body: dict[str, Any] = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == title
    assert body["status"] == status
    assert isinstance(body["detail"], str)
    assert body["detail"]
    return body


def test_unknown_route_is_a_404_problem(client: TestClient) -> None:
    assert_problem(client.get("/api/v1/nothing-here"), 404, "Not Found")


def test_wrong_method_is_a_405_problem(client: TestClient) -> None:
    assert_problem(client.get("/api/v1/_test/echo"), 405, "Method Not Allowed")


def test_http_exception_keeps_its_detail(client: TestClient) -> None:
    body = assert_problem(client.get("/api/v1/_test/conflict"), 409, "Conflict")
    assert body["detail"] == "Version mismatch"
    assert "errors" not in body


def test_validation_error_lists_field_code_and_message(client: TestClient) -> None:
    response = client.post(
        "/api/v1/_test/echo", json={"mood": 9, "note": "keep this private"}, headers=GOOD_HEADERS
    )
    body = assert_problem(response, 422, "Unprocessable Content")
    assert body["errors"] == [
        {
            "field": "mood",
            "code": "less_than_equal",
            "message": "Input should be less than or equal to 5",
        }
    ]
    assert "keep this private" not in response.text
    assert "9" not in str(body["errors"][0]["message"])


def test_missing_field_is_reported_by_name(client: TestClient) -> None:
    response = client.post("/api/v1/_test/echo", json={"mood": 3}, headers=GOOD_HEADERS)
    body = assert_problem(response, 422, "Unprocessable Content")
    assert body["errors"] == [{"field": "note", "code": "missing", "message": "Field required"}]


def test_unhandled_error_is_a_generic_500_problem(client: TestClient) -> None:
    response = client.get("/api/v1/_test/boom")
    body = assert_problem(response, 500, "Internal Server Error")
    assert "private note" not in response.text
    assert "RuntimeError" not in response.text
    assert body["detail"] == "Something went wrong."
