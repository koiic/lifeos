#!/usr/bin/env python3
"""PreToolUse guard (plan 6.4, 4.1). Exit 2 blocks the tool call and shows the reason to Claude.

Blocks:
- edits to the read-only sources of truth (spec, plan, requirements, tasks, tokens, generated tokens)
- direct edits to the progress ledger (use scripts/ledger.py)
- touching secrets or env files
- shell commands that write to protected files, skip git hooks, force-push or hard-reset
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))

READ_ONLY = {
    "docs/spec.md": "the specification is read-only; raise a change request with /change-request",
    "docs/plan.md": "the implementation plan is read-only; raise a change request with /change-request",
    "docs/requirements.json": "requirements are read-only; raise a change request",
    "docs/plan/tasks.json": "the task list is read-only; raise a change request",
    "design/tokens.json": "design tokens change only through a change request (plan 5.1)",
    "web/src/ui/tokens.css": "generated file: run python3 scripts/build_tokens.py instead",
    "web/src/ui/tokens.ts": "generated file: run python3 scripts/build_tokens.py instead",
    "docs/plan/PROGRESS.md": "update the ledger only with python3 scripts/ledger.py (plan 6.3)",
}
SECRET = re.compile(r"(^|/)(\.env(\..*)?|secrets/.*|.*\.(pem|key|p12))$")
SHELL_WRITE = re.compile(r"(>|>>|\btee\b|\bsed\s+-i|\bperl\s+-i|\bcp\b|\bmv\b|\brm\b|\btruncate\b)")
SHELL_BANNED = [
    (re.compile(r"--no-verify\b|\bgit\s+commit\b[^|;&]*\s-n\b"), "skipping git hooks is not allowed"),
    (re.compile(r"\bgit\s+push\b[^|;&]*(--force\b|\s-f\b|--force-with-lease)"), "force-push is not allowed"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "hard reset is not allowed; ask Ibrahim"),
    (re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(/|~|\.|\*)(\s|$)"), "recursive delete of a root path is not allowed"),
    (re.compile(r"\bgit\s+(checkout|restore)\s+--?\s*\.\s*$"), "discarding all changes is not allowed; ask Ibrahim"),
]


def rel(path: str) -> str:
    p = Path(path)
    try:
        return str((p if p.is_absolute() else ROOT / p).resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(p)


def block(reason: str) -> None:
    print(f"BLOCKED by .claude/hooks/guard.py: {reason}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {}) or {}

    if tool in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        path = rel(ti.get("file_path") or ti.get("notebook_path") or "")
        if path in READ_ONLY:
            block(f"{path}: {READ_ONLY[path]}")
        if SECRET.search(path):
            block(f"{path}: secret and env files are managed by Ibrahim, never by Claude Code")
        if re.search(r"(^|/)(tests?/fixtures?/).*flo", path, re.I) is None and re.search(r"flo.*export|export.*flo", path, re.I):
            block(f"{path}: real Flo exports never enter the repository; use the anonymised fixture (spec 13.1)")
        return

    if tool == "Bash":
        cmd = ti.get("command", "")
        for pattern, reason in SHELL_BANNED:
            if pattern.search(cmd):
                block(reason)
        if SHELL_WRITE.search(cmd):
            for path in READ_ONLY:
                if path in cmd and not cmd.strip().startswith("python3 scripts/"):
                    block(f"shell command would modify {path}: {READ_ONLY[path]}")
        if re.search(r"(cat|less|head|tail|cp|scp)\s+[^|;&]*(\.env\b|secrets/)", cmd):
            block("reading or copying secrets is not allowed")


if __name__ == "__main__":
    main()
