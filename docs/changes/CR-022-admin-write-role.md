# CR-022 — Which database role admin endpoints that write use

- Raised by: Claude Code during T08 (spec review)
- Date: 2026-10-08
- Status: approved (spec re-sync pending)

## Problem

- Spec 7.3: `lifeos_admin_ro` — "SELECT on `users(…)`, `sessions`, `invites`, `auth_events`,
  `audit_log`, job tables; nothing else" — "Used by: Admin console endpoints".
- Spec 9.2: admin endpoints that write: `POST /admin/invites`, `DELETE /admin/invites/{id}`,
  `POST /admin/users/{id}/revoke-sessions`, `POST /admin/users/{id}/recovery-invite`.
- Spec 12.1: "Admin role cannot reach health tables; no admin endpoint returns health data;
  every admin action audited."
- Spec 7.2: `outbox_events.topic` and `audit_log.action` comments list the known values; the
  recovery invite adds `auth.security_notice` and `admin.recovery_invite`.

A read-only role cannot write invites, revoke sessions or append to the audit log, so 7.3 and 9.2
contradict each other. T08 (the first admin write) uses `lifeos_app` with the target account as
`app.user_id`, which can technically reach that account's health rows (the code does not).

## Options

1. **A `lifeos_admin` write role** with only: INSERT/UPDATE (`revoked_at`) on `invites`;
   UPDATE (`revoked_at`) on `sessions` (policy for that role); INSERT on `audit_log`,
   `outbox_events` (topic `auth.security_notice` only, via policy); SELECT on the user columns
   it needs. No health tables at all, enforced by grants. Admin read endpoints keep
   `lifeos_admin_ro`. — impact: 7.3 new role and grants; roles.sql; settings for a third
   connection (14.3 `DATABASE_ADMIN_WRITE_URL`) or SET ROLE from the admin connection.
2. **`lifeos_app` scoped to the target account** (as built), documented: admin write code lives
   only in the auth service and touches only auth tables; 7.3 says admin *reads* use
   `lifeos_admin_ro`. — impact: 7.3 wording.
3. **Grant writes to `lifeos_admin_ro`** (rename to `lifeos_admin`). — impact: 7.3; the console's
   reads also get write rights.

## Recommendation

Option 1: 12.1's promise becomes a database guarantee for every admin endpoint, not a code
convention. Also record the two new names (topic and action) in 7.2.

## Impact if approved

- Spec sections to change: 7.3 (new role), 14.3 (its connection), 7.2 comments (topic, action).
- Tasks affected: T08 (blocked until decided; first admin write), T15 (secret), T44.

## Decision (Ibrahim)

Approved by Ibrahim, 2026-10-08: option 1 (a narrow `lifeos_admin` write role; admin reads keep `lifeos_admin_ro`; new secret `database_admin_write_url` for its connection; topic `auth.security_notice` and action `admin.recovery_invite` added to the 7.2 lists). Until the spec is re-synced this CR is the
governing text for the sections it changes.

Still to do (Ibrahim): update the spec, re-export, commit `docs: sync spec vN (CR-022)`.
