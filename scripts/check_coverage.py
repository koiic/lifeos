#!/usr/bin/env python3
"""Per-module coverage thresholds (plan 4.7) over a coverage.py JSON report.

coverage.py's own fail_under covers the overall figure only; this adds health, notify and
platform/crypto at 90%. Areas with no measured statements yet pass.

Usage: check_coverage.py [server/coverage.json]
Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

THRESHOLDS = {
    "app/": 75.0,
    "app/health/": 90.0,
    "app/notify/": 90.0,
    "app/platform/crypto.py": 90.0,
}


def failures(report: dict) -> list[str]:
    out = []
    for prefix, minimum in THRESHOLDS.items():
        statements = covered = 0
        for path, data in report["files"].items():
            if path.startswith(prefix):
                statements += data["summary"]["num_statements"]
                covered += data["summary"]["covered_lines"]
        if statements == 0:
            continue
        # Compare exactly; round only for the message, so 89.95% never passes a 90% gate.
        if covered * 100 < minimum * statements:
            percent = round(100.0 * covered / statements, 2)
            out.append(f"{prefix}: {percent}% < {minimum}%")
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0] if args else "server/coverage.json")
    problems = failures(json.loads(path.read_text()))
    for problem in problems:
        print(f"FAIL  coverage {problem}")
    if not problems:
        print("coverage: per-module thresholds met (plan 4.7)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
