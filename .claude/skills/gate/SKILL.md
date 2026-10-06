---
name: gate
description: Prepare the milestone gate report (plan section 8) and stop for Ibrahim's sign-off.
disable-model-invocation: true
argument-hint: "<milestone, e.g. M1>"
allowed-tools: Bash(make verify*) Bash(python3 scripts/trace.py *) Bash(python3 scripts/ledger.py *) Bash(git log *)
---

# Gate $ARGUMENTS

!`python3 scripts/ledger.py summary`

1. Confirm every task in $ARGUMENTS is `done` in the ledger. If not, list what is missing and stop.
2. Run `make verify-full`.
3. Run `python3 scripts/trace.py --gate $ARGUMENTS --matrix docs/plan/gates/$ARGUMENTS-matrix.md`.
4. Copy `docs/plan/gates/_TEMPLATE.md` to `docs/plan/gates/$ARGUMENTS.md` and fill sections 1–3 and 5
   from the results, the ledger and each task file's Evidence. In section 4 list the exact journeys
   (spec section 3) and the gate condition for this milestone from `docs/plan.md` section 8, as
   checkboxes for Ibrahim. Leave section 6 (Decision) empty.
5. If any automated check failed, do not mark the gate ready: report the failures and stop.
6. Otherwise run `python3 scripts/ledger.py gate-ready $ARGUMENTS`, commit
   `docs(plan): gate $ARGUMENTS report`, and tell Ibrahim the report is ready.

Then STOP. Never mark a gate `done`; never start the next milestone's tasks.
