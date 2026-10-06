#!/usr/bin/env python3
"""Progress ledger tool. The ONLY way Claude Code changes docs/plan/PROGRESS.md.

Commands:
  next                     show the task to work on (current in_progress, or next eligible todo)
  show Txx                 show a task's full definition and status
  start Txx                mark in_progress (refuses if another task is in progress or deps not done)
  block Txx "reason"       mark blocked (use with a change request)
  done Txx --commit SHA --evidence "..."   mark done after checks (refuses without evidence)
  gate-ready Mx            mark a milestone gate awaiting-signoff (only Ibrahim marks gates done)
  summary                  counts per milestone and the current task

Plan sections 3, 6.3, 6.5. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRESS = ROOT / "docs" / "plan" / "PROGRESS.md"
TASKS = ROOT / "docs" / "plan" / "tasks.json"
TASK_DIR = ROOT / "docs" / "plan" / "tasks"
STATUSES = {"todo", "in_progress", "blocked", "done", "awaiting-signoff"}
ROW = re.compile(r"^\|\s*(T\d{2}|GATE-M\d)\s*\|")


def load_tasks() -> dict:
    data = json.loads(TASKS.read_text())
    return {t["id"]: t for t in data["tasks"]}, data["milestones"]


def parse_rows(lines: list[str]) -> dict[str, tuple[int, list[str]]]:
    rows = {}
    for i, line in enumerate(lines):
        m = ROW.match(line)
        if m:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows[m.group(1)] = (i, cells)
    return rows


def write_row(lines: list[str], idx: int, cells: list[str]) -> None:
    lines[idx] = "| " + " | ".join(cells) + " |"


def status_of(rows, rid: str) -> str:
    return rows[rid][1][4]


def clean(text: str) -> str:
    return " ".join(text.replace("|", "/").split())


def eligible(tid: str, tasks, rows, milestones) -> tuple[bool, str]:
    t = tasks[tid]
    order = list(milestones)
    for prev in order[: order.index(t["milestone"])]:
        if status_of(rows, f"GATE-{prev}") != "done":
            return False, f"GATE-{prev} is not signed off"
    for dep in t["depends_on"]:
        if status_of(rows, dep) != "done":
            return False, f"dependency {dep} is {status_of(rows, dep)}"
    return True, ""


def describe(t: dict, status: str) -> str:
    return "\n".join([
        f"{t['id']} [{status}] {t['title']}",
        f"  Milestone: {t['milestone']}",
        f"  Spec sections: {t['spec_refs']}",
        f"  Owns requirements: {', '.join(t['owns']) or '(none; supports other tasks)'}",
        f"  Depends on: {', '.join(t['depends_on']) or '-'}",
        f"  Done when: {t['done_when']}",
        f"  Task file: docs/plan/tasks/{t['id']}.md",
    ])


def task_file_ok(tid: str) -> tuple[bool, str]:
    path = TASK_DIR / f"{tid}.md"
    if not path.exists():
        return False, f"missing {path.relative_to(ROOT)}"
    text = path.read_text()
    m = re.search(r"^## Evidence\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    body = (m.group(1) if m else "").strip()
    if not body or "TODO" in body or "<" in body.splitlines()[0]:
        return False, f"{path.relative_to(ROOT)} has no filled '## Evidence' section"
    return True, ""


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("next")
    sub.add_parser("summary")
    for name in ("show", "start"):
        s = sub.add_parser(name)
        s.add_argument("tid")
    b = sub.add_parser("block")
    b.add_argument("tid")
    b.add_argument("reason")
    d = sub.add_parser("done")
    d.add_argument("tid")
    d.add_argument("--commit", required=True)
    d.add_argument("--evidence", required=True)
    g = sub.add_parser("gate-ready")
    g.add_argument("milestone")
    args = p.parse_args()

    tasks, milestones = load_tasks()
    lines = PROGRESS.read_text().splitlines()
    rows = parse_rows(lines)

    if args.cmd == "summary":
        for ms in milestones:
            ids = [t for t in tasks if tasks[t]["milestone"] == ms]
            counts = {s: sum(status_of(rows, t) == s for t in ids) for s in STATUSES}
            done = counts["done"]
            print(f"{ms}: {done}/{len(ids)} done, {counts['in_progress']} in progress, "
                  f"{counts['blocked']} blocked; gate {status_of(rows, f'GATE-{ms}')}")
        current = [t for t in tasks if status_of(rows, t) == "in_progress"]
        print("Current task:", ", ".join(current) or "none")
        return 0

    if args.cmd == "next":
        current = [t for t in tasks if status_of(rows, t) == "in_progress"]
        if current:
            print("RESUME (already in progress):")
            print(describe(tasks[current[0]], "in_progress"))
            return 0
        reasons = []
        for tid in tasks:
            if status_of(rows, tid) != "todo":
                continue
            ok, why = eligible(tid, tasks, rows, milestones)
            if ok:
                print("NEXT:")
                print(describe(tasks[tid], "todo"))
                return 0
            reasons.append(f"{tid}: {why}")
        waiting = [f"GATE-{m}" for m in milestones if status_of(rows, f"GATE-{m}") == "awaiting-signoff"]
        if waiting:
            print(f"STOP: {', '.join(waiting)} awaiting Ibrahim's sign-off. Do not start new work.")
        else:
            print("No eligible task. First blockers:\n  " + "\n  ".join(reasons[:5]))
        return 0

    if args.cmd == "show":
        print(describe(tasks[args.tid], status_of(rows, args.tid)))
        return 0

    if args.cmd == "start":
        tid = args.tid
        busy = [t for t in tasks if status_of(rows, t) == "in_progress" and t != tid]
        if busy:
            print(f"REFUSED: {busy[0]} is in progress. Finish or block it first.", file=sys.stderr)
            return 1
        if status_of(rows, tid) not in {"todo", "blocked"}:
            print(f"REFUSED: {tid} is {status_of(rows, tid)}.", file=sys.stderr)
            return 1
        ok, why = eligible(tid, tasks, rows, milestones)
        if not ok:
            print(f"REFUSED: {why}.", file=sys.stderr)
            return 1
        idx, cells = rows[tid]
        cells[4] = "in_progress"
        write_row(lines, idx, cells)

    elif args.cmd == "block":
        idx, cells = rows[args.tid]
        cells[4] = "blocked"
        cells[6] = clean(f"blocked: {args.reason}")
        write_row(lines, idx, cells)

    elif args.cmd == "done":
        tid = args.tid
        if status_of(rows, tid) != "in_progress":
            print(f"REFUSED: {tid} is {status_of(rows, tid)}, not in_progress.", file=sys.stderr)
            return 1
        ok, why = task_file_ok(tid)
        if not ok:
            print(f"REFUSED: {why}.", file=sys.stderr)
            return 1
        trace = subprocess.run([sys.executable, str(ROOT / "scripts" / "trace.py"), "--task", tid],
                               capture_output=True, text=True)
        if trace.returncode != 0:
            print("REFUSED: traceability check failed:\n" + trace.stdout + trace.stderr, file=sys.stderr)
            return 1
        if len(args.evidence.strip()) < 20:
            print("REFUSED: evidence too thin (plan 6.3 lists what it must include).", file=sys.stderr)
            return 1
        idx, cells = rows[tid]
        cells[4], cells[5], cells[6] = "done", clean(args.commit)[:12], clean(args.evidence)
        write_row(lines, idx, cells)

    elif args.cmd == "gate-ready":
        ms = args.milestone
        open_tasks = [t for t in tasks if tasks[t]["milestone"] == ms and status_of(rows, t) != "done"]
        if open_tasks:
            print(f"REFUSED: not done yet: {', '.join(open_tasks)}", file=sys.stderr)
            return 1
        trace = subprocess.run([sys.executable, str(ROOT / "scripts" / "trace.py"), "--gate", ms],
                               capture_output=True, text=True)
        if trace.returncode != 0:
            print("REFUSED: gate traceability check failed:\n" + trace.stdout + trace.stderr, file=sys.stderr)
            return 1
        if not (ROOT / "docs" / "plan" / "gates" / f"{ms}.md").exists():
            print(f"REFUSED: write docs/plan/gates/{ms}.md first (/gate {ms}).", file=sys.stderr)
            return 1
        idx, cells = rows[f"GATE-{ms}"]
        cells[4] = "awaiting-signoff"
        cells[6] = f"report: docs/plan/gates/{ms}.md"
        write_row(lines, idx, cells)

    PROGRESS.write_text("\n".join(lines) + "\n")
    print(f"ledger updated: {args.cmd} {getattr(args, 'tid', getattr(args, 'milestone', ''))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
