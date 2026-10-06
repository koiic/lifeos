# CR-004 — Optimistic concurrency: integer `version` vs `updated_at` ETag

- Raised by: Claude Code, first-session cross-check (affects T09 and every later PATCH endpoint)
- Date: 2026-10-06
- Status: proposed

## Problem

The spec gives two incompatible designs:

- Spec 9.1: "**Concurrency**: mutable resources return `version` (integer); PATCH sends
  `If-Match: <version>`; mismatch → 409 with the current resource."
- Spec 7.5: "Optimistic concurrency uses `updated_at` as the resource version: responses carry it as
  `ETag`, PATCH sends it in `If-Match`."
- Plan 4.4 says "ETag/If-Match" without choosing.

No table in 7.2 has a `version` column, so the 9.1 design would need a schema change; the 7.5
design would put a timestamp, not an integer, in responses. `user_settings` (T09 `PATCH /me/settings`)
is the first resource affected; events, people, tasks, notes and medications follow.

## Options

1. **`updated_at` as the version (7.5)**: `ETag: "<updated_at as RFC 3339 with microseconds>"`,
   `If-Match` must equal it; response bodies include `version` as that same string. Change 9.1 to
   match. — impact: no schema change; spec 9.1 text; OpenAPI type of `version` is string.
2. **Integer `version` column (9.1)** on every mutable table, incremented by trigger; `ETag: "<n>"`.
   — impact: schema change to ~10 tables in 7.2; 7.5 text; T03 migration grows.

## Recommendation

Option 1: it needs no schema change, `updated_at` is already trigger-maintained (7.1), and
microsecond precision makes collisions impractical for a single user.

## Impact if approved

- Spec sections to change: 9.1 (Concurrency bullet), 9.3 if any payload shows `version`.
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T09 (blocked), T34, T35, T37, T39 and any later PATCH endpoint.

## Decision (Ibrahim)

<approved / rejected, date, notes>. After approval: update the spec in Claude Docs, re-export it
to docs/spec.md with the version bumped, commit `docs: sync spec vN (CR-004)`.
