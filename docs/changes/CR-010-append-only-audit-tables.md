# CR-010 — Make the audit tables append-only for the API

- Raised by: Claude Code during T03 (security review finding)
- Date: 2026-10-07
- Status: proposed

## Problem

Spec 7.3: `lifeos_app` has "CRUD on all tables". That includes `audit_log` and `auth_events`.
Spec 12.1 relies on them: "every admin action audited"; server compromise is mitigated by "audit
log"; 4.1 AUTH-7: "all attempts logged". With UPDATE and DELETE, a compromised API process (the
most likely compromise) can erase or rewrite its own trail, and the operator's actions (AUTH-8:
"is audited") can be altered by the same process that performs them.

Retention still needs deletes: `account.purge` removes "old auth events > 1 year" (10.1), and
account purge deletes a user's rows (13.4; `auth_events.user_id` is `ON DELETE SET NULL`, which is
an UPDATE done by the foreign-key action, not by the API role).

## Options

1. **Append-only for `lifeos_app`; retention by `lifeos_jobs`.** `lifeos_app`: INSERT and SELECT on
   `audit_log` and `auth_events` (no UPDATE/DELETE). `lifeos_jobs`: DELETE on `auth_events` rows
   older than 1 year (the purge job). FK `ON DELETE SET NULL` keeps working (referential actions
   run as the table owner). — impact: spec 7.3 roles table; a T07 migration changes the grants;
   tests extend T03's exact-grant test.
2. **Append-only and also hash-chained** (each row stores a hash of the previous row) so tampering
   by the owner role or a restore is detectable. — impact: as option 1 plus schema columns in 7.2
   and verification in the admin console (T44); more work for limited extra benefit in a
   one-household app.
3. **Leave as specified.** — impact: none; the residual risk above stays.

## Recommendation

Option 1: a two-line grant change that removes the easiest way to hide a compromise, with retention
moved to the job role that already finds work across users.

## Impact if approved

- Spec sections to change: 7.3 (`lifeos_app`: "CRUD on all tables except `audit_log` and
  `auth_events`, which are INSERT/SELECT"; `lifeos_jobs`: add "DELETE on `auth_events`").
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T07 (blocked until decided; first writer of `auth_events`; carries the grant
  migration), T08, T43 (purge), T44.

## Decision (Ibrahim)

<approved / rejected, date, notes>. After approval: update the spec in Claude Docs, re-export it
to docs/spec.md with the version bumped, commit `docs: sync spec vN (CR-010)`.
