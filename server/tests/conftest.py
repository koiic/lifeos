import os

import pytest

# Local default matches infra/docker-compose.dev.yml; CI sets DATABASE_URL to its service container.
LOCAL_DATABASE_URL = "postgresql://lifeos:lifeos@127.0.0.1:54320/lifeos"


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get("DATABASE_URL", LOCAL_DATABASE_URL)
