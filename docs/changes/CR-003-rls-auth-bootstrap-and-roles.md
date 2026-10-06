# CR-003 — Row-level security: pre-auth lookups, cross-user jobs and missing roles

- Raised by: Claude Code, first-session cross-check (affects T03, T05, T06, T30, T44)
- Date: 2026-10-06
- Status: proposed

## Problem

Spec 7.1: "Row-level security on every user table: `USING (user_id = current_setting('app.user_id')::uuid)`;
the app runs `SET LOCAL app.user_id` per transaction." Spec 7.3: `lifeos_app` has "RLS enforced
(`FORCE ROW LEVEL SECURITY`)". Taken literally, several required operations cannot work, and the
spec does not say how they should:

1. **Sign-in before the user is known.** `POST /auth/signin/verify` must find a
   `webauthn_credentials` row by `credential_id`; every request must find a `sessions` row by
   `token_hash`; `/auth/signin/password` and `/auth/signin/recovery` must find `users` by `email`.
   At that point `app.user_id` is not set, so RLS returns no rows. (Also `current_setting` without
   `missing_ok` raises an error when the setting is absent.)
2. **`users` has no `user_id` column** (its key is `id`), so the 7.1 policy cannot apply as written.
3. **Tables with no single owner**: `invites` (`created_by`, `used_by`), `auth_events` (nullable
   `user_id`), `audit_log` (`actor_user_id`, `target_user_id`), `auth_challenges` (nullable `user_id`),
   `pending_deletions`, `outbox_events`. The spec does not say which are "user tables".
4. **Cross-user jobs.** The outbox relay reads all users' `outbox_events` (10.1); `notify.extend_horizon`,
   `health.nightly_predict`, `meds.mark_missed` and `account.purge` iterate over all users. 7.3 only
   says "each job ... sets `app.user_id` for the user it serves", not how a job lists the users.
5. **Undefined roles.** 10.3: the dispatcher "uses a dedicated database role whose RLS policy permits
   it" — no such role is in 7.3, and 14.3 has no connection secret for it. 14.3 also has no
   connection for `lifeos_owner` (Alembic). 7.3 gives `lifeos_admin_ro` SELECT on `users` and
   `sessions` across users, which RLS on those tables would also block.

## Options

1. **Narrow, explicit bypasses (recommended).**
   - Policies use `current_setting('app.user_id', true)`; `users` policy is on `id`.
   - Add a small set of `SECURITY DEFINER` SQL functions owned by `lifeos_owner` for the pre-auth
     lookups only (`auth_find_credential(credential_id)`, `auth_find_session(token_hash)`,
     `auth_find_user_by_email(email)`), each returning only the columns auth needs.
   - Add role `lifeos_dispatcher` (as 10.3 describes) and role `lifeos_jobs` (no `BYPASSRLS`;
     role-specific policies `USING (true)`), each granted only the tables and columns it needs to
     find work across users: `outbox_events`, `users(id, timezone)`, `reminders` and
     `medication_doses` status columns, `pending_deletions`, plus the dispatcher's list in 10.3.
     Jobs then do the per-user work in transactions with `app.user_id` set, as `lifeos_app`.
   - Classify `invites`, `audit_log`, `auth_events`, `auth_challenges`, `pending_deletions` as
     system tables: no RLS, `lifeos_app` access only through the auth/admin services, and covered
     by the generated RLS test's explicit allow-list.
   - Add `DATABASE_OWNER_URL`, `DATABASE_DISPATCHER_URL` to 14.3.
   — impact: T03 schema/roles, T05 relay, T06 auth repo, T30 dispatcher, T44 admin; spec 7.1, 7.3, 10.3, 14.3.
2. **Auth and jobs connect as a `BYPASSRLS` role.** — impact: simpler, but every auth and job query
   then runs without RLS, which weakens spec 12's isolation guarantee and the T03 RLS test.
3. **Set `app.user_id` from a lookup table outside RLS** (e.g. a `session_index` table without health
   data). — impact: adds tables not in the 28-table schema; still leaves jobs and roles undefined.

## Recommendation

Option 1: it keeps `FORCE ROW LEVEL SECURITY` on every health and user-owned table, confines the
bypasses to named functions and roles the security reviewer can audit, and matches the dispatcher
role 10.3 already describes.

## Impact if approved

- Spec sections to change: 7.1 (policy text, list of system tables), 7.3 (roles `lifeos_dispatcher`,
  `lifeos_jobs_ro`, auth lookup functions), 10.3 (role name), 14.3 (connection secrets).
- Plan / tasks.json / requirements.json: none (T03 "done when" still holds; the RLS test gets an
  explicit list of system tables).
- Tokens: none.
- Tasks affected: T03 (blocked), T05, T06, T30, T44.

## Decision (Ibrahim)

<approved / rejected, date, notes>. After approval: update the spec in Claude Docs, re-export it
to docs/spec.md with the version bumped, commit `docs: sync spec vN (CR-003)`.
