# CR-013 — How a recovery-code sign-in "forces new passkey setup"

- Raised by: Claude Code during T06 (spec and security reviewers, both)
- Date: 2026-10-07
- Status: proposed

## Problem

- Spec 9.2: `POST /auth/signin/recovery` — "`{email, code}`; forces new passkey setup".
- Spec 9.2: `POST /auth/passkeys/options`, `/verify` — "Add another passkey" (T08, signed-in).
- Spec 7.5: `auth_challenges.purpose` includes `'add_passkey'`, and the table has `user_id`.
- Spec 7.2 `sessions` has no column that marks a session as limited.

Nothing in the spec says what "forces" means on the server. If the recovery sign-in returns a
normal 30-day session (what T06 does now, with a `{"next": "add_passkey"}` hint), whoever holds a
code gets full access to her health data and can skip the passkey step; no later task can enforce
it, because the session looks like any other.

## Options

1. **No session until a new passkey exists.** `/auth/signin/recovery` spends the code and returns
   `{"next": "add_passkey", "options": <WebAuthn creation options>}` with an `add_passkey`
   challenge bound to the user (`auth_challenges.user_id`, 5 min). The session cookie is issued
   only when that passkey is verified, via `POST /auth/passkeys/verify` accepting such a
   challenge without a session (T08's endpoint; T06 builds the recovery half and this verify path
   now). — impact: 9.2 wording of both rows; no schema change. If the passkey step fails, the code
   is spent: she uses another code (she has ten).
2. **A limited session.** Add `sessions.scope text NOT NULL DEFAULT 'full' CHECK (scope IN
   ('full','add_passkey'))`; recovery issues an `add_passkey` session that `require_session`
   refuses everywhere except the passkey-add endpoints, upgraded to `full` when a passkey is
   added. — impact: 7.2 DDL + migration; 9.2 wording; every signed-in endpoint relies on the
   check.
3. **Keep a full session; the client insists.** Record that "forces" is a UI rule (T12 screen
   flow). — impact: 9.2 wording; the server does not enforce it (the reviewers' concern stands).

## Recommendation

Option 1: it uses tables the spec already has, no session exists that could be misused, and
nothing outside the auth endpoints needs to know about recovery. Same shape as AUTH-8's
`/auth/recover/options` → `/auth/recover/verify`.

## Impact if approved

- Spec sections to change: 9.2 (`/auth/signin/recovery` response; `/auth/passkeys/verify`
  accepts a recovery `add_passkey` challenge without a session).
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T06 (blocked until decided), T08 (adds the signed-in passkey path to the same
  endpoint), T12 (screen flow).

## Decision (Ibrahim)

Pending.
