#!/usr/bin/env python3
"""PostToolUse check after Edit/Write (plan 4, 5.2).

Formats and lints the single changed file with the project's own tools when they exist, and
catches raw colour values in web code. Exit 2 shows the problems to Claude (the edit already happened,
so Claude must fix them next). Tools that are not installed yet (before T01/T10) are skipped.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RGB = re.compile(r"\b(rgba?|hsla?)\(")


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=90)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 0, f"(skipped: {exc})"
    return p.returncode, (p.stdout + p.stderr).strip()


def main() -> None:
    data = json.load(sys.stdin)
    path = Path((data.get("tool_input") or {}).get("file_path", ""))
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return
    rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    problems: list[str] = []

    if path.suffix == ".py" and str(rel).startswith("server/") and (ROOT / "server/pyproject.toml").exists() and shutil.which("uv"):
        server = ROOT / "server"
        run(["uv", "run", "ruff", "format", str(path)], server)
        code, out = run(["uv", "run", "ruff", "check", "--fix", str(path)], server)
        if code:
            problems.append(f"ruff:\n{out}")

    web = ROOT / "web"
    if str(rel).startswith("web/") and (web / "node_modules").exists():
        if path.suffix in {".ts", ".tsx", ".css", ".json", ".md"}:
            run(["npx", "--no-install", "prettier", "--write", str(path)], web)
        if path.suffix in {".ts", ".tsx"}:
            code, out = run(["npx", "--no-install", "eslint", "--fix", str(path)], web)
            if code:
                problems.append(f"eslint:\n{out}")
        if path.suffix == ".css":
            code, out = run(["npx", "--no-install", "stylelint", "--fix", str(path)], web)
            if code:
                problems.append(f"stylelint:\n{out}")

    generated = {"web/src/ui/tokens.css", "web/src/ui/tokens.ts"}
    if str(rel).startswith("web/src/") and str(rel) not in generated and path.suffix in {".css", ".tsx", ".ts"}:
        text = path.read_text(errors="ignore")
        for n, line in enumerate(text.splitlines(), 1):
            if "eslint-disable" in line or line.strip().startswith("//") or "url(" in line:
                continue
            if HEX.search(line) or RGB.search(line):
                problems.append(f"{rel}:{n}: raw colour value; use a design token var(--…) from design/tokens.json (plan 5.2)")

    if problems:
        print("Post-edit checks found problems; fix them before continuing:\n\n" + "\n\n".join(problems), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
