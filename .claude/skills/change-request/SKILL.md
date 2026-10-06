---
name: change-request
description: Raise a change request when the spec or plan is missing, ambiguous, contradictory or wrong, and block the current task (plan section 6.4).
argument-hint: "<short title>"
allowed-tools: Bash(python3 scripts/ledger.py *) Bash(git add *) Bash(git commit *)
---

1. Find the next free number: list `docs/changes/CR-*.md`.
2. Copy `docs/changes/_TEMPLATE.md` to `docs/changes/CR-<nnn>-<slug>.md` and fill it: problem with
   exact quotes and section numbers, at least two options with impact, a recommendation, and the full
   list of documents and tasks it would change. Status: proposed.
3. `python3 scripts/ledger.py block <current task> "CR-<nnn>: <title>"`.
4. Commit `docs(changes): CR-<nnn> <title>`.
5. Tell Ibrahim in three lines: the problem, your recommendation, what is blocked. Then STOP and wait.

Do not implement any option before Ibrahim approves and the spec has been re-synced.
