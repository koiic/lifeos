# CR-016 — A shared counter for the 300 requests/min per-session limit

- Raised by: Claude Code during T07 (spec review)
- Date: 2026-10-07
- Status: approved (spec re-sync pending)

## Problem

- Spec 9.1: "Rate limits: … all others 300 requests/min per session → 429 with `Retry-After`."
- Spec 11.1: the API runs `uvicorn app.main:app --workers 2`.
- Spec 7.2 / 7.5 have no table for request counts, and there is no Redis (6.1: Procrastinate on
  Postgres, "No Redis to run or back up").

A counter kept in each worker's memory lets one session make up to 600 requests/min, so the spec
limit needs state shared by both workers.

## Options

1. **A small unlogged table in Postgres**, upserted once per signed-in request:
   `session_request_counts (session_id PK → sessions ON DELETE CASCADE, window_start, count)`;
   exact across workers; one extra statement per request (in the session check's transaction).
   — impact: 7.5 gains the table; a migration.
2. **Per worker, 150 each** — no shared state; ≈300 only when requests spread evenly.
3. **Per worker, 300 each** — up to ~600/min; 9.1 reworded.

## Recommendation

Option 1: exact, no new service, and the counts are disposable (`UNLOGGED`: lost on a crash,
never backed up, which is harmless for one-minute windows).

## Impact if approved

- Spec sections to change: 7.5 (new supporting table, below), 7.3 (`lifeos_app` CRUD on it).

```sql
CREATE UNLOGGED TABLE session_request_counts (  -- 9.1 per-session limit, shared by API workers
  session_id uuid PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
  window_start timestamptz NOT NULL,
  count int NOT NULL
);
```

- System table (no RLS, like `auth_challenges`): it holds no personal data, only a count per
  session id, and only the API's session check touches it.
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T07 (builds it).

## Decision (Ibrahim)

Approved by Ibrahim, 2026-10-07: option 1 (shared count in Postgres). Until the spec is re-synced
this CR is the governing text for the sections it changes.

Still to do (Ibrahim): add the table to spec 7.5 and the grant to 7.3, re-export, commit
`docs: sync spec vN (CR-016)`.
