# CR-029 — T17 depends on T09

- Raised by: Claude Code at the start of T17
- Date: 2026-10-09
- Status: approved (plan re-sync pending)

## Problem

tasks.json T17 ("App shell: bottom navigation, Today greeting, profile and theme settings") owns
SET-1 ("Display name, timezone (auto-detected, editable), week start (Mon default), units for
temperature (°C default)") and SET-2 ("Light (Sorbet), Dark (Night Garden), System (default)").
Both are saved through spec 9.2 `GET /me` ("Bootstraps the client") and `PATCH /me`,
`PATCH /me/settings`, which T09 ("Profile, settings, consent and per-user seeding") builds. CR-025
also gives T17 the app-lock timeout control, which "shows the current value from `/me`, T09".
T17 lists only T12 as a dependency, so the ledger offered it while T09 was still marked blocked
(by CR-004, approved on 2026-10-07 but never unblocked in the ledger). No `/me` endpoint exists.

## Options

1. Do T09 first; T17 depends on T09 and T12. Impact: tasks.json T17 `depends_on`; order only.
2. Build T17 now with the theme kept on the device; profile and saving wait. Impact: SET-1/SET-2
   only partly met in T17; a later task finishes them.
3. Merge T09 into T17. Impact: one larger task; T09 removed or emptied.

## Recommendation

Option 1: T09 is earlier in M1, its blocker is approved, and T17 then meets SET-1/SET-2 in full.

## Impact if approved

- Spec sections to change: none.
- Plan / tasks.json / requirements.json changes: tasks.json T17 `depends_on` = ["T09", "T12"]
  (plan section 7 table likewise).
- Tokens changes: none.
- Tasks affected: T09 (unblocked, done next), T17 (after T09).

## Decision (Ibrahim, 2026-10-09)

Option 1: T09 first, then T17. Plan re-sync (tasks.json and plan 7) is Ibrahim's.
