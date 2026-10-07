"""T01: the API entrypoint exists and produces an OpenAPI document."""

from fastapi import FastAPI

from app.main import app


def test_app_is_a_fastapi_application() -> None:
    assert isinstance(app, FastAPI)


def test_openapi_document_names_the_app() -> None:
    assert app.openapi()["info"]["title"] == "Life OS"
