"""T01: commits are Conventional Commits naming the plan item (plan 4.1, CLAUDE.md rule 8)."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "web"
COMMITLINT = WEB / "node_modules" / ".bin" / "commitlint"
HOOK = ROOT / "scripts" / "precommit" / "commitlint.sh"


def lint(message: str) -> tuple[bool, str]:
    run = subprocess.run(
        [str(COMMITLINT)], cwd=WEB, input=message, capture_output=True, text=True, check=False
    )
    return run.returncode == 0, run.stdout + run.stderr


@pytest.mark.parametrize(
    "message",
    [
        "feat(health): T26 cycle engine calendar-1.0",
        "chore(plan): T01 done",
        "docs(changes): CR-002 to CR-009 from first-session cross-check",
        "docs: sync spec v2 (CR-003)",
        "docs: sync plan v2 (CR-002)",
        "docs(plan): sign off gate M1",
        "docs(plan): gate M1 report",
        "feat(health): T26 cycle engine\n\nImplements spec 8.3.\n\n"
        "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
    ],
)
def test_accepts(message: str) -> None:
    ok, output = lint(message)
    assert output == ""
    assert ok


@pytest.mark.parametrize(
    ("message", "rules"),
    [
        ("added the cycle engine T26", ["type-empty", "subject-empty"]),
        ("stuff(health): T26 cycle engine", ["type-enum"]),
        ("feat(health): cycle engine", ["subject-references-plan-item"]),
        ("feat(health): t26 cycle engine", ["subject-references-plan-item"]),
        ("feat(health): T1 cycle engine", ["subject-references-plan-item"]),
    ],
)
def test_rejects_for_the_right_rule(message: str, rules: list[str]) -> None:
    ok, output = lint(message)
    assert not ok
    missing = [r for r in rules if f"[{r}]" not in output]
    assert missing == [], output


def test_commit_msg_hook_script_lints_the_message_file(tmp_path: Path) -> None:
    good = tmp_path / "good"
    good.write_text("chore(plan): T01 done\n")
    bad = tmp_path / "bad"
    bad.write_text("wip\n")
    # The hook receives the message path relative to the repository root.
    run_good = subprocess.run(
        [str(HOOK), str(good.relative_to(ROOT, walk_up=True))],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    run_bad = subprocess.run(
        [str(HOOK), str(bad.relative_to(ROOT, walk_up=True))],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert run_good.returncode == 0
    assert run_bad.returncode != 0
