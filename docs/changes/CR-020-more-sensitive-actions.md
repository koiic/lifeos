# CR-020 — Adding a passkey and issuing a recovery invite need recent authentication

- Raised by: Claude Code during T08 (security review)
- Date: 2026-10-08
- Status: approved (spec re-sync pending)

## Problem

- Spec 12.3: "Sensitive actions (export download, deletion, recovery-code regeneration, removing a
  passkey) need recent authentication within 5 minutes."
- Spec 9.2: `POST /auth/passkeys/options`, `/verify` "Add another passkey" (no condition);
  `POST /admin/users/{id}/recovery-invite` (admin, audited).

Adding a passkey is not on the list, but it defeats the list: with a stale stolen session someone
can add their own passkey, use it at `/auth/reauth/verify` to gain recent auth, then remove her
passkeys and regenerate (take) her recovery codes. The added passkey also survives every session
revocation. Likewise a stolen admin session can issue a recovery invite — a working takeover link
— with no step-up.

## Options

1. **Add both to 12.3's list** (and changing or clearing the app-lock PIN, optional): the API
   answers 403 "Confirm it's you" without a passkey/password verification in the last 5 minutes
   on this session (CR-017). — impact: 12.3 wording; T12 screens ask for re-auth first.
2. **Add only "adding a passkey"**; leave the admin step-up to T44's admin console design.
3. **Leave as specified**; record the residual risk.

## Recommendation

Option 1, including the PIN change (a PIN set by a thief would let them pass the lock screen on
her unlocked phone later).

## Impact if approved

- Spec sections to change: 12.3 (list), 9.2 rows (passkeys add, admin recovery-invite, app-lock
  PUT: "Requires recent auth").
- Tasks affected: T08 (blocked until decided), T12, T44.

## Decision (Ibrahim)

Approved by Ibrahim, 2026-10-08: option 1 (adding a passkey, issuing a recovery invite and changing or clearing the app-lock PIN need recent auth). Until the spec is re-synced this CR is the
governing text for the sections it changes.

Still to do (Ibrahim): update the spec, re-export, commit `docs: sync spec vN (CR-020)`.
