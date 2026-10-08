# CR-017 — Where "recent auth" is recorded, and how a password re-authenticates

- Raised by: Claude Code during T08
- Date: 2026-10-08
- Status: approved (spec re-sync pending)

## Problem

- Spec 9.2 note: "'Recent auth' means a passkey or password verification within the last 5
  minutes (`POST /auth/reauth/options`, `/verify`)."
- Spec 12.3: "Sensitive actions (export download, deletion, recovery-code regeneration, removing a
  passkey) need recent authentication within 5 minutes."
- Spec 7.2 `sessions` has no column for a verification time; `auth_events` has no session id and
  no `reauth` kind; 7.5 `auth_challenges.purpose` has `reauth` and `unlock`.
- `/auth/reauth/options` and `/verify` are WebAuthn-shaped; nothing says what a password-only
  account (AUTH-3 fallback) sends to re-authenticate.

Without a per-session record, a verification on one device would count as recent auth for every
session of the account (a stolen session could ride on her re-authenticating elsewhere).

## Options

1. **`sessions.reauth_at timestamptz`.** Set at sign-in (the session's creation is a fresh
   verification) and by `/auth/reauth/verify`; recent auth = `now - reauth_at < 5 min` for *this*
   session. `/auth/reauth/verify` accepts either `{credential}` (passkey, challenge purpose
   `reauth`, bound to the session's user) or `{password, totp}` (password accounts; counted by
   AUTH-7 like a sign-in). — impact: 7.2 column; 9.2 wording; a migration.
2. **Derive from `auth_challenges`.** The newest used `reauth` challenge of the user (or the
   session's `created_at`) within 5 minutes. — impact: none to the schema, but it is per account,
   not per session (the weakness above), and password re-auth has no challenge to record.
3. **Short-lived re-auth token** returned by `/verify`, sent with the sensitive request. — impact:
   9.2 request shapes for every sensitive endpoint; a new header or field; storage or signing.

## Recommendation

Option 1: one nullable column, per-session and simple to check, and both sign-in methods fit.

## Impact if approved

- Spec sections to change: 7.2 (`sessions.reauth_at timestamptz`), 9.2 note on recent auth
  (per session; set at sign-in and by `/auth/reauth/verify`; password body `{password, totp}`).
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T08 (blocked until decided), T41/T42 (export download, deletion use the check).

## Decision (Ibrahim)

Approved by Ibrahim, 2026-10-08: option 1 (`sessions.reauth_at`, per session; set at sign-in and by `/auth/reauth/verify`, which accepts a passkey or `{password, totp}`). Until the spec is re-synced this CR is the
governing text for the sections it changes.

Still to do (Ibrahim): update the spec, re-export, commit `docs: sync spec vN (CR-017)`.
