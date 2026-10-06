#!/usr/bin/env python3
"""Stop hook (plan 6.5): if code changed and `make verify-fast` fails, block finishing.

Skips when the Makefile has no verify-fast target yet (before T01), when nothing under server/, web/
or scripts/ changed, or when Claude is already continuing because of this hook.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))


def main() -> None:
    data = json.load(sys.stdin)
    if data.get("stop_hook_active"):
        return
    makefile = ROOT / "Makefile"
    if not makefile.exists() or "verify-fast:" not in makefile.read_text():
        return
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    changed = [l[3:] for l in status.splitlines() if l[3:].startswith(("server/", "web/", "scripts/"))]
    if not changed:
        return
    try:
        p = subprocess.run(["make", "verify-fast"], cwd=ROOT, capture_output=True, text=True, timeout=540)
    except subprocess.TimeoutExpired:
        print(json.dumps({"decision": "block", "reason": "make verify-fast timed out; investigate before stopping."}))
        return
    state = ROOT / ".claude" / "state" / "stop_blocks.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    session = data.get("session_id", "?")
    counts = json.loads(state.read_text()) if state.exists() else {}
    if p.returncode == 0:
        counts.pop(session, None)
        state.write_text(json.dumps(counts))
        return
    counts[session] = counts.get(session, 0) + 1
    state.write_text(json.dumps(counts))
    if counts[session] > 3:
        # Loop breaker: let Claude stop, but it must report the failure honestly.
        print(json.dumps({"systemMessage": "verify-fast still failing after 3 attempts; task stays in_progress."}))
        return
    if p.returncode != 0:
        tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-40:])
        print(json.dumps({
            "decision": "block",
            "reason": "make verify-fast is failing on uncommitted changes. Fix it before finishing "
                      "(or, if the work is genuinely paused, say so and leave the task in_progress).\n\n" + tail,
        }))


if __name__ == "__main__":
    main()
