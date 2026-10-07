"""T05: job runtime configuration and topic subscriptions (no database)."""

import pytest

from app.platform import outbox
from app.platform.config import ConfigError, Settings
from app.platform.jobs import create_runtime, new_job_app


def settings_without_jobs_url() -> Settings:
    return Settings(env="production", app_origin="https://a.example", database_url="postgresql://x")


def test_the_worker_needs_the_jobs_connection() -> None:
    with pytest.raises(ConfigError, match="database_jobs_url"):
        create_runtime(settings_without_jobs_url())
    with pytest.raises(ConfigError, match="database_jobs_url"):
        new_job_app(settings_without_jobs_url())


def test_subscriptions_are_unique(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(outbox, "_subscriptions", {})
    outbox.subscribe("t.topic", "t.task")
    outbox.subscribe("t.topic", "t.task")
    outbox.subscribe("t.topic", "t.other")
    assert outbox._subscriptions == {"t.topic": ["t.task", "t.other"]}
