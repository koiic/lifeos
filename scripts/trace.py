#!/usr/bin/env python3
"""Requirement traceability check (plan section 6.2).

Rules:
  1. Every requirement tag in tests is a real ID from docs/requirements.json.
  2. Every MUST requirement owned by a task marked done has at least one tagged test.
  3. --gate Mx: every MUST requirement in milestones up to Mx has tests; SHOULD ones without
     tests are reported as deferred (warning).
  4. Every task marked done has docs/plan/tasks/Txx.md with a filled Evidence section.

Tags: Python  @pytest.mark.req("CYC-2")   (several allowed: req("A", "B"))
      TS      test('[CYC-2] ...') / it('[CYC-2][CYC-3] ...') / describe('[CYC-2] ...')

Usage: trace.py [--task Txx] [--gate Mx] [--matrix out.md]
Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQS = ROOT / "docs" / "requirements.json"
TASKS = ROOT / "docs" / "plan" / "tasks.json"
PROGRESS = ROOT / "docs" / "plan" / "PROGRESS.md"
TASK_DIR = ROOT / "docs" / "plan" / "tasks"

PY_TAG = re.compile(r"""mark\.req\(([^)]*)\)""")
ID = re.compile(r"""["']([A-Z]+-\d+)["']""")
TS_TITLE = re.compile(r"""\b(?:test|it|describe)(?:\.\w+)?\(\s*['"`]((?:\[[A-Z]+-\d+\])+)""")
TS_ID = re.compile(r"\[([A-Z]+-\d+)\]")
TEST_GLOBS = {
    "server/tests": ["**/test_*.py", "**/*_test.py"],
    "web": ["src/**/*.test.ts", "src/**/*.test.tsx", "tests/**/*.spec.ts", "tests/**/*.test.ts",
            "e2e/**/*.spec.ts"],
}


def scan() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for base, globs in TEST_GLOBS.items():
        root = ROOT / base
        if not root.exists():
            continue
        for g in globs:
            for path in root.glob(g):
                if "node_modules" in path.parts:
                    continue
                text = path.read_text(errors="ignore")
                rel = str(path.relative_to(ROOT))
                ids: list[str] = []
                if path.suffix == ".py":
                    for args in PY_TAG.findall(text):
                        ids += ID.findall(args)
                else:
                    for group in TS_TITLE.findall(text):
                        ids += TS_ID.findall(group)
                for rid in ids:
                    found.setdefault(rid, []).append(rel)
    return found


def statuses() -> dict[str, str]:
    out = {}
    for line in PROGRESS.read_text().splitlines():
        m = re.match(r"^\|\s*(T\d{2}|GATE-M\d)\s*\|", line)
        if m:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out[m.group(1)] = cells[4]
    return out


def evidence_ok(tid: str) -> bool:
    path = TASK_DIR / f"{tid}.md"
    if not path.exists():
        return False
    m = re.search(r"^## Evidence\s*$(.*?)(?=^## |\Z)", path.read_text(), re.M | re.S)
    body = (m.group(1) if m else "").strip()
    return bool(body) and "TODO" not in body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task")
    ap.add_argument("--gate")
    ap.add_argument("--matrix")
    a = ap.parse_args()

    reqs = {r["id"]: r for r in json.loads(REQS.read_text())["requirements"]}
    tasks_data = json.loads(TASKS.read_text())
    order = list(tasks_data["milestones"])
    st = statuses()
    found = scan()
    errors: list[str] = []
    warnings: list[str] = []

    # Rule 1
    for rid, files in sorted(found.items()):
        if rid not in reqs:
            errors.append(f"unknown requirement tag {rid} in {sorted(set(files))}")

    # Rules 2 and 4 (all done tasks, or one task with --task)
    check_tasks = [a.task] if a.task else [t for t, s in st.items() if t.startswith("T") and s == "done"]
    for tid in check_tasks:
        for rid, r in reqs.items():
            if r["task"] == tid and r["priority"] == "must" and rid not in found:
                errors.append(f"{tid} owns MUST {rid} but no test is tagged with it")
        if not evidence_ok(tid):
            errors.append(f"{tid}: docs/plan/tasks/{tid}.md missing or Evidence section not filled")

    # Rule 3
    if a.gate:
        limit = order.index(a.gate)
        for rid, r in reqs.items():
            if order.index(r["milestone"]) > limit:
                continue
            if rid not in found:
                if r["priority"] == "must":
                    errors.append(f"gate {a.gate}: MUST {rid} ({r['task']}) has no tagged test")
                else:
                    warnings.append(f"gate {a.gate}: SHOULD {rid} ({r['task']}) has no test - list as deferred")
        for t in tasks_data["tasks"]:
            if order.index(t["milestone"]) <= limit and st.get(t["id"]) != "done":
                errors.append(f"gate {a.gate}: {t['id']} is {st.get(t['id'])}, not done")

    if a.matrix:
        lines = ["| Requirement | Priority | Milestone | Task | Task status | Tests |",
                 "| --- | --- | --- | --- | --- | --- |"]
        for rid, r in reqs.items():
            tests = "<br>".join(sorted(set(found.get(rid, [])))) or "—"
            lines.append(f"| {rid} | {r['priority']} | {r['milestone']} | {r['task']} | {st.get(r['task'], '?')} | {tests} |")
        Path(a.matrix).write_text("\n".join(lines) + "\n")
        print(f"matrix written to {a.matrix}")

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"FAIL  {e}")
    covered = sum(1 for r in reqs if r in found)
    print(f"trace: {covered}/{len(reqs)} requirements have tagged tests; "
          f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
