#!/usr/bin/env python3
"""SessionStart hook (plan 6.5): inject where the build is, so no session works from memory."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))


def run(args: list[str]) -> str:
    p = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
    return (p.stdout + p.stderr).strip()


def main() -> None:
    parts = ["## Life OS build status (injected at session start)"]
    parts.append(run(["scripts/ledger.py", "summary"]))
    parts.append(run(["scripts/ledger.py", "next"]))
    proposed = []
    for cr in sorted((ROOT / "docs" / "changes").glob("CR-*.md")):
        if re.search(r"Status:\s*proposed", cr.read_text()):
            proposed.append(cr.name)
    if proposed:
        parts.append("Open change requests awaiting Ibrahim: " + ", ".join(proposed))
    parts.append(
        "Rules: work only on the task above; re-open the cited spec sections in docs/spec.md before "
        "coding; tests first; `make verify` green; reviewer agents; ledger via scripts/ledger.py; "
        "stop at gates and at any spec gap (/change-request). Use /next-task to proceed."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": "\n\n".join(parts)}}))


if __name__ == "__main__":
    main()
