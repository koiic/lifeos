# CR-012 — `uuid6` package named for primary keys but not in the dependency list

- Raised by: Claude Code during T06
- Date: 2026-10-07
- Status: proposed

## Problem

- Spec 7.1: "Primary keys: UUID v7 generated in Python (`uuid6` package), time-ordered for index
  locality."
- Spec 6.1 and plan 4 (and the CR-002 tooling list) do not include `uuid6`; CLAUDE.md rule 9:
  "Only those in spec 6.1 and plan 4; anything else needs a change request."
- Python 3.12 has no `uuid.uuid7()` (added in 3.14). T06 is the first task that generates primary
  keys in application code (users, sessions, credentials, recovery codes, challenges).

## Options

1. **Add `uuid6` (pinned) to the server dependencies** as spec 7.1 says. — impact: spec 6.1 list
   gains one line; one small pure-Python package (no transitive dependencies).
2. **Generate UUID v7 with a ~10-line helper in `app/platform/ids.py`** (RFC 9562 layout:
   48-bit ms timestamp, version 7, variant, 74 random bits from `secrets`). — impact: spec 7.1
   wording drops "(`uuid6` package)"; no new dependency.

## Recommendation

Option 1: it is what spec 7.1 already says, and the package is tiny and well known. Either way all
code calls one function, `app.platform.ids.new_id()`, so switching later is a one-line change.

## Impact if approved

- Spec sections to change: 6.1 (option 1) or 7.1 (option 2).
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T06 (blocked until decided), every later task that inserts rows.

## Decision (Ibrahim)

Pending.
