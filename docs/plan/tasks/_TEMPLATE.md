# Txx — <task title from tasks.json>

Status is tracked in `docs/plan/PROGRESS.md` (change it only with `scripts/ledger.py`).

## Scope

- Spec sections (opened and re-read this session): <e.g. 8.1–8.4>
- Requirements owned: <IDs from tasks.json>; also touches: <IDs>
- Acceptance criteria, quoted from the spec for each owned requirement:
  - <ID>: "<exact text from spec section 4>"
- Done when (from tasks.json): <copy>

## Plan

- Files to create or change: <paths>
- Approach: <short; name the patterns from plan section 4 being followed>
- Migrations: <none | name>
- New dependencies: <none | name + reason; anything new needs a change request>

## Tests (written first, seen failing)

| Test | Tags | Proves |
| --- | --- | --- |
| <path::name> | <req ids> | <behaviour> |

## Out of scope

- <what this task deliberately does not do, with the task that will>

## Decisions

Internal choices the spec leaves open (not change requests):

- <decision and reason>

## Evidence

TODO — fill before `ledger.py done`: commit SHA; `make verify` result; tests added (count) and
coverage of touched modules; `trace.py --task Txx` output; reviewer verdicts (spec, design system,
security) with findings fixed; screenshots or snapshot names for UI tasks.
