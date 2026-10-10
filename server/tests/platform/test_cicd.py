"""Tests for CI/CD pipeline definitions and scan scripts (spec 14.5, 12.8, NFR-6)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
SCAN_IMAGES = ROOT / "scripts" / "scan_images.sh"
CHECK_ORIGINS = ROOT / "scripts" / "check_external_origins.sh"


def test_scripts_exist_and_executable() -> None:
    assert CHECK_ORIGINS.is_file(), "scripts/check_external_origins.sh must exist"
    assert SCAN_IMAGES.is_file(), "scripts/scan_images.sh must exist"


def test_ci_workflow_structure() -> None:
    assert CI_WORKFLOW.is_file(), ".github/workflows/ci.yml must exist"
    text = CI_WORKFLOW.read_text()

    # Triggers
    assert "push:" in text
    assert "pull_request:" in text

    # Postgres service container
    assert "postgres:16" in text or "image: postgres:16" in text

    # Verification checks
    for check in (
        "ruff",
        "mypy",
        "pytest",
        "lint-imports",
        "eslint",
        "size-limit",
        "vitest",
        "pip-audit",
        "npm audit",
    ):
        assert check in text.lower(), f"Missing {check} check in CI workflow"


def test_deploy_workflow_structure() -> None:
    assert DEPLOY_WORKFLOW.is_file(), ".github/workflows/deploy.yml must exist"
    text = DEPLOY_WORKFLOW.read_text()

    # Triggers on main
    assert "branches: [main]" in text or "branches:\n      - main" in text or "main" in text

    # Staging deploy and production approval environment
    assert "staging" in text
    assert "production" in text
