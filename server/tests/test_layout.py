"""T01: the server layout follows spec 11.1."""

from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1]
MODULES = ["auth", "core", "health", "notify", "data", "admin"]
LAYER_FILES = ["api.py", "service.py", "repo.py", "schemas.py", "models.py", "jobs.py"]


@pytest.mark.parametrize("module", MODULES)
def test_each_module_has_the_spec_files(module: str) -> None:
    missing = [f for f in LAYER_FILES if not (SERVER / "app" / module / f).is_file()]
    assert missing == [], f"app/{module} is missing {missing}"


@pytest.mark.parametrize(
    "path",
    ["app/platform/__init__.py", "app/main.py", "app/worker.py", "migrations/env.py"],
)
def test_entrypoints_and_platform_exist(path: str) -> None:
    assert (SERVER / path).is_file()
