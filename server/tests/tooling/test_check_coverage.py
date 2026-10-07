"""T01: scripts/check_coverage.py enforces the per-module thresholds of plan 4.7."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_coverage.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_coverage", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report(files: dict[str, tuple[int, int]]) -> dict[str, object]:
    """Build a coverage.py JSON report from {path: (statements, covered)}."""
    return {
        "files": {
            path: {"summary": {"num_statements": n, "covered_lines": c}}
            for path, (n, c) in files.items()
        }
    }


def test_thresholds_match_plan_4_7() -> None:
    assert load().THRESHOLDS == {
        "app/": 75.0,
        "app/health/": 90.0,
        "app/notify/": 90.0,
        "app/platform/crypto.py": 90.0,
    }


def test_passes_when_every_area_meets_its_threshold() -> None:
    data = report({"app/health/service.py": (10, 9), "app/main.py": (10, 10)})
    assert load().failures(data) == []


def test_fails_when_health_is_below_90_even_if_overall_passes() -> None:
    data = report({"app/health/service.py": (10, 8), "app/main.py": (90, 90)})
    assert load().failures(data) == ["app/health/: 80.0% < 90.0%"]


def test_fails_when_crypto_is_below_90() -> None:
    data = report({"app/platform/crypto.py": (20, 17), "app/main.py": (80, 80)})
    assert load().failures(data) == ["app/platform/crypto.py: 85.0% < 90.0%"]


def test_fails_when_overall_is_below_75() -> None:
    data = report({"app/main.py": (100, 70)})
    assert load().failures(data) == ["app/: 70.0% < 75.0%"]


def test_fails_when_notify_is_below_90() -> None:
    data = report({"app/notify/service.py": (10, 8), "app/main.py": (90, 90)})
    assert load().failures(data) == ["app/notify/: 80.0% < 90.0%"]


def test_areas_with_no_code_yet_pass() -> None:
    data = report({"app/main.py": (4, 4), "app/notify/api.py": (0, 0)})
    assert load().failures(data) == []


def test_exactly_at_the_threshold_passes() -> None:
    data = report({"app/health/service.py": (2000, 1800), "app/main.py": (100, 100)})
    assert load().failures(data) == []


def test_just_below_90_fails_without_rounding_up() -> None:
    data = report({"app/health/service.py": (2000, 1799), "app/main.py": (100, 100)})
    assert load().failures(data) == ["app/health/: 89.95% < 90.0%"]


def test_just_below_75_overall_fails_without_rounding_up() -> None:
    data = report({"app/main.py": (10000, 7499)})
    assert load().failures(data) == ["app/: 74.99% < 75.0%"]


def test_main_exits_1_on_failure_and_0_on_pass(tmp_path: Path) -> None:
    failing = tmp_path / "failing.json"
    failing.write_text(json.dumps(report({"app/main.py": (100, 50)})))
    passing = tmp_path / "passing.json"
    passing.write_text(json.dumps(report({"app/main.py": (100, 100)})))
    module = load()
    assert module.main([str(failing)]) == 1
    assert module.main([str(passing)]) == 0
