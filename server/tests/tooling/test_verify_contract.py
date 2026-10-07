"""T01: the verify contract (plan 6.1), pre-commit hooks (plan 4.1) and kit files stay in place.

Later tasks may add steps but never remove one or weaken a threshold (Makefile header).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MAKEFILE = (ROOT / "Makefile").read_text()
PRECOMMIT = (ROOT / ".pre-commit-config.yaml").read_text()

PLAN_6_1_TARGETS = [
    "fmt-check",
    "lint",
    "types",
    "arch",
    "test-server",
    "test-web",
    "migrations",
    "api-contract",
    "tokens",
    "trace",
    "secrets",
]


def recipe(target: str) -> str:
    """Prerequisites line plus the tab-indented recipe lines of a Makefile target."""
    match = re.search(rf"^{re.escape(target)}:(.*)\n((?:\t.*\n?)*)", MAKEFILE, re.M)
    assert match, f"Makefile has no target {target}"
    return match.group(1) + "\n" + match.group(2)


def test_verify_runs_every_plan_6_1_check() -> None:
    prerequisites = recipe("verify").splitlines()[0].split()
    missing = [t for t in PLAN_6_1_TARGETS if t not in prerequisites]
    assert missing == []


@pytest.mark.parametrize(
    ("target", "commands"),
    [
        ("fmt-check", ["ruff format --check", "prettier --check"]),
        ("lint", ["ruff check", "eslint . --max-warnings 0", "stylelint", "--max-warnings 0"]),
        ("types", ["mypy --strict app", "tsc --noEmit"]),
        ("arch", ["lint-imports"]),
        ("test-server", ["pytest", "--cov=app", "scripts/check_coverage.py"]),
        ("test-web", ["--coverage", "npm run build", "size-limit"]),
        ("migrations", ["check_migrations.sh"]),
        ("api-contract", ["check_openapi.sh"]),
        ("tokens", ["build_tokens.py --check", "check_contrast.py"]),
        ("trace", ["scripts/trace.py"]),
        ("secrets", ["gitleaks git", "gitleaks dir"]),
    ],
)
def test_each_check_runs_its_commands(target: str, commands: list[str]) -> None:
    body = recipe(target)
    missing = [c for c in commands if c not in body]
    assert missing == [], f"{target} no longer runs {missing}"


def test_coverage_floor_is_75_percent() -> None:
    assert re.search(r"^fail_under = 75$", (ROOT / "server/.coveragerc").read_text(), re.M)


def hook(hook_id: str) -> str:
    """The YAML block of one local hook, up to the next hook."""
    match = re.search(rf"- id: {re.escape(hook_id)}\n((?:\s{{8}}.*\n?)*)", PRECOMMIT)
    assert match, f".pre-commit-config.yaml has no hook {hook_id}"
    return match.group(1)


def test_precommit_installs_both_hook_types() -> None:
    assert "default_install_hook_types: [pre-commit, commit-msg]" in PRECOMMIT


@pytest.mark.parametrize(
    ("hook_id", "entry"),
    [
        ("ruff-format", "ruff format"),
        ("ruff", "ruff check --fix"),
        ("prettier", "prettier --write"),
        ("eslint", "eslint --fix"),
        ("gitleaks", "gitleaks git --pre-commit --staged"),
    ],
)
def test_plan_4_1_hooks_run_on_staged_files(hook_id: str, entry: str) -> None:
    block = hook(hook_id)
    assert entry in block
    assert "stages:" not in block, f"{hook_id} must run at the default pre-commit stage"


def test_commitlint_runs_on_the_commit_message() -> None:
    block = hook("commitlint")
    assert "scripts/precommit/commitlint.sh" in block
    assert "stages: [commit-msg]" in block


@pytest.mark.parametrize(
    "path",
    [
        "CLAUDE.md",
        "KICKOFF_PROMPT.md",
        "docs/spec.md",
        "docs/plan.md",
        "docs/requirements.json",
        "docs/plan/tasks.json",
        "docs/plan/PROGRESS.md",
        "design/tokens.json",
        "scripts/ledger.py",
        "scripts/trace.py",
        "scripts/build_tokens.py",
        "scripts/check_contrast.py",
        ".claude/settings.json",
        ".claude/hooks/guard.py",
        ".claude/hooks/post_edit.py",
        ".claude/hooks/stop_check.py",
        ".claude/hooks/session_context.py",
        ".claude/agents/spec-reviewer.md",
        ".claude/agents/design-system-reviewer.md",
        ".claude/agents/security-reviewer.md",
        ".claude/agents/test-auditor.md",
        ".claude/skills/next-task/SKILL.md",
        ".claude/skills/verify/SKILL.md",
        ".claude/skills/gate/SKILL.md",
        ".claude/skills/change-request/SKILL.md",
        ".claude/skills/drift-check/SKILL.md",
    ],
)
def test_kit_files_are_in_place(path: str) -> None:
    assert (ROOT / path).is_file()


def test_initial_js_budget_is_250_kb_gzipped() -> None:
    import json

    [budget] = json.loads((ROOT / "web/.size-limit.json").read_text())
    assert budget["limit"] == "250 KB"
    assert budget["gzip"] is True
    assert budget["path"] == "dist/assets/index-*.js"
