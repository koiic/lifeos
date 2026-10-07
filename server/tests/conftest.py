import os
import subprocess
import sys
from pathlib import Path

import pytest

# Tests run as a local deployment; app.main builds the app from settings at import (spec 14.3).
os.environ.setdefault("ENV", "local")

# Local default matches infra/docker-compose.dev.yml; CI sets DATABASE_URL to its service container.
LOCAL_DATABASE_URL = "postgresql://lifeos:lifeos@127.0.0.1:54320/lifeos"


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get("DATABASE_URL", LOCAL_DATABASE_URL)


SERVER = Path(__file__).resolve().parents[1]
APPLY_ROLES = SERVER / "migrations" / "apply_roles.py"


def plain_dsn(database_url: str) -> str:
    return database_url.replace("+asyncpg", "")


@pytest.fixture(scope="session")
def migrated(database_url: str) -> str:
    """Apply roles.sql and `alembic upgrade head` once per session (in a subprocess: env.py runs
    its own event loop)."""
    run = subprocess.run(
        [sys.executable, str(APPLY_ROLES), plain_dsn(database_url)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVER,
        env={**os.environ, "ENV": "local", "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgrade.returncode == 0, upgrade.stderr
    return plain_dsn(database_url)
