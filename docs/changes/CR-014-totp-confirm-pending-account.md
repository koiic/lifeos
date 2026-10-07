# CR-014 — How `/auth/totp/confirm` finds the pending password account

- Raised by: Claude Code during T07
- Date: 2026-10-07
- Status: proposed

## Problem

- Spec 9.2: `POST /auth/register/password` — "`{token, name, email, password}` → TOTP
  provisioning URI; account active after `/auth/totp/confirm`".
- Spec 9.2: `POST /auth/totp/confirm` — "Confirm TOTP" — "`{code}`".
- Spec 7.2: `password_credentials (user_id, password_hash, totp_secret_enc, totp_enabled, …)`;
  `users` has no "active" column; `auth_challenges.purpose` has no TOTP value.
- Spec 9.2 `register/verify` (passkey) "Creates user, settings, DEK, seeded symptoms, session;
  returns recovery codes once"; nothing says when the password path does the same.

The confirm request carries only the 6-digit code, so the server cannot tell whose TOTP it is
confirming unless something from the registration response identifies the account. The spec also
does not say what "active" means, or when the session and recovery codes are created.

## Options

1. **Session cookie, inactive until confirmed.** `register/password` creates the user, settings,
   DEK and `password_credentials` (`totp_enabled = false`, secret encrypted with her DEK), uses
   the invite, and sets `lo_session`. An account is *active* when it has a passkey or
   `totp_enabled = true`. `require_session` refuses sessions of inactive accounts everywhere except
   `/auth/totp/confirm`, which reads the account from the session. A valid code sets
   `totp_enabled = true` and returns the 10 recovery codes once (same as `register/verify`).
   `signin/password` needs `totp_enabled`. — impact: 9.2 wording; no schema change.
2. **Confirm before creating anything.** `register/password` stores nothing permanent; it returns
   the URI plus a signed, 10-minute setup token; `totp/confirm` takes `{setup_token, code}` and
   creates the account. — impact: 9.2 request shape changes; the password hash and TOTP secret
   travel in (or are referenced by) the token; needs a new pending store or signing key (14.3).
3. **Add `email` and `password` to confirm.** `{email, password, code}`. — impact: 9.2 shape
   changes; the password is sent twice; confirm becomes a second sign-in endpoint to rate-limit.

## Recommendation

Option 1. It keeps both request shapes as in 9.2, adds no schema or secret, and an inactive
session can do nothing except confirm TOTP. If she never confirms, the account stays inactive and
the admin can delete it (T44) before issuing a new invite.

## Impact if approved

- Spec sections to change: 9.2 (`register/password` sets the cookie; "active" defined;
  `totp/confirm` reads the session and returns recovery codes once).
- Plan / tasks.json / requirements.json: none.
- Tokens: none.
- Tasks affected: T07 (blocked until decided), T08 (session checks), T12 (register screens), T44.

## Decision (Ibrahim)

Pending.
