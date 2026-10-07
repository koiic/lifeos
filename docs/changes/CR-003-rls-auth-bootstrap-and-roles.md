# CR-003 — Row-level security: pre-auth lookups, cross-user jobs and missing roles

- Raised by: Claude Code, first-session cross-check (affects T03, T05, T06, T30, T44)
- Date: 2026-10-06
- Status: approved (spec re-sync pending)

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

Approved by Ibrahim, 2026-10-07: option 1 (narrow, explicit bypasses). Still to do (Ibrahim):
update the spec in Claude Docs (draft text below), re-export it to docs/spec.md with the version
bumped, commit `docs: sync spec vN (CR-003)`. T03 stays blocked until then.

## Appendix: draft spec text (for the Claude Docs update)

Drafted by Claude Code from option 1; edit freely. Section numbers refer to spec version 1.

**7.1, replace the row-level security bullet with:**

> - Row-level security, enabled and forced, on every user-owned table: every table with a `user_id`
>   column, with `USING (user_id = current_setting('app.user_id', true)::uuid)`, and `users` itself
>   with `USING (id = current_setting('app.user_id', true)::uuid)`. The app runs
>   `SET LOCAL app.user_id` per transaction; when it is not set, the policies match no rows.
> - System tables without RLS, reached only through the `auth` and `admin` services: `invites`,
>   `auth_challenges`, `auth_events`, `audit_log`, `pending_deletions`. They hold no health data.
> - Sign-in looks up rows before the user is known through three `SECURITY DEFINER` functions owned
>   by `lifeos_owner`, executable only by `lifeos_app`, each returning only what authentication
>   needs: `auth_find_credential(credential_id)` (user id, public key, sign count),
>   `auth_find_session(token_hash)` (session id, user id, expiry, revoked flag) and
>   `auth_find_user_by_email(email)` (user id). After the lookup the app sets `app.user_id` and
>   reads everything else under RLS.

**7.3, add these rows to the roles table and amend `lifeos_admin_ro`:**

> | `lifeos_jobs` | Role-specific policies `USING (true)` (no `BYPASSRLS`) granting: SELECT and `UPDATE (processed_at)` on `outbox_events`; SELECT on `users(id, timezone)`, `reminders(id, user_id, status, fire_at)`, `medication_doses(id, user_id, status, scheduled_at)`, `pending_deletions`. Finds work across users; the work itself runs as `lifeos_app` with `app.user_id` set | Worker (relay, horizon, nightly predict, missed doses, purge) |
> | `lifeos_dispatcher` | Role-specific policies `USING (true)` on, and only on: `reminders`, `push_subscriptions`, `user_settings`, `users(id, timezone, dek_wrapped)` (10.3) | Reminder dispatcher |
>
> `lifeos_admin_ro`: add "through role-specific policies `USING (true)` on the tables listed".

**10.3, last sentence, replace "a dedicated database role whose RLS policy permits it" with:**

> the `lifeos_dispatcher` role (7.3), whose role-specific RLS policies permit it

**14.3, add rows to the configuration table:**

> | `DATABASE_OWNER_URL` | secret | `lifeos_owner` connection; `migrate` container only |
> | `DATABASE_JOBS_URL` | secret | `lifeos_jobs` connection; worker |
> | `DATABASE_DISPATCHER_URL` | secret | `lifeos_dispatcher` connection; worker |

(As files: `database_owner_url`, `database_jobs_url`, `database_dispatcher_url` in `/run/secrets`,
matching T02's `database_url`.)
