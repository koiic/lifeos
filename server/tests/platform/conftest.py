import io
import json
from collections.abc import Iterator
from typing import Any

import pytest
import structlog
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, field_validator

from app.main import create_app
from app.platform.config import Settings
from app.platform.logging import configure_logging

ORIGIN = "https://app.test"
GOOD_HEADERS = {"Origin": ORIGIN, "X-LifeOS-Client": "web"}


class EchoIn(BaseModel):
    mood: int = Field(ge=1, le=5)
    note: str


class EchoOut(BaseModel):
    mood: int


class CodeIn(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def careless_validator(cls, value: str) -> str:
        # A validator that (wrongly) quotes the input; the response must not echo it.
        raise ValueError(f"{value} is not allowed")


def test_router() -> APIRouter:
    """Routes that exist only in tests, to exercise the platform behaviour."""
    router = APIRouter(prefix="/api/v1/_test")

    @router.get("/items/{item_id}")
    async def get_item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    @router.post("/echo")
    @router.put("/echo")
    @router.patch("/echo")
    async def echo(body: EchoIn) -> EchoOut:
        return EchoOut(mood=body.mood)

    @router.delete("/echo")
    async def delete_echo() -> dict[str, str]:
        return {"deleted": "yes"}

    @router.post("/code")
    async def code(body: CodeIn) -> dict[str, str]:
        return {"code": body.code}

    @router.get("/logs")
    async def logs_inside_handler() -> dict[str, str]:
        structlog.get_logger().info("handler.step", job="example")
        return {"ok": "yes"}

    @router.get("/conflict")
    async def conflict() -> None:
        raise HTTPException(status_code=409, detail="Version mismatch")

    @router.get("/boom")
    async def boom() -> None:
        note = "my private note"
        raise RuntimeError(f"failed while saving {note}")

    return router


@pytest.fixture
def log_stream() -> io.StringIO:
    stream = io.StringIO()
    configure_logging(stream)
    return stream


def read_logs(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(env="local", app_origin=ORIGIN, database_url=database_url)


@pytest.fixture
def app(settings: Settings, log_stream: io.StringIO) -> FastAPI:
    application = create_app(settings)
    application.include_router(test_router())
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url=ORIGIN) as test_client:
        yield test_client
