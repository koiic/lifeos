# CR-021 — Counting app-lock PIN tries per session

- Raised by: Claude Code during T08 (spec and security reviews)
- Date: 2026-10-08
- Status: approved (spec re-sync pending)

## Problem

- Spec 9.2: `POST /auth/app-lock/unlock` "Verify PIN" — "5 tries then full sign-in required".
- Spec 7.2: `auth_events (user_id, kind 'pin_unlock', success, ip_hash, at)` has no session
  reference; `sessions` has no counter.

The lock protects one device (an unlocked phone in someone's hands, 12.1). Counting tries per
account from `auth_events` (as built) means a good unlock on her other device resets a stolen
phone's count (endless guesses), and wrong tries elsewhere count against her own device. The
5 tries must belong to the session on that device.

## Options

1. **`sessions.pin_failures smallint NOT NULL DEFAULT 0`.** A wrong PIN increments it (atomically,
   on the row); a good PIN or a passkey `unlock` re-auth resets it; the fifth wrong try revokes the
   session. Events are still logged (AUTH-7 "all attempts logged"). — impact: 7.2 column;
   migration.
2. **`auth_events.session_id uuid`** and count from events. — impact: 7.2 column on an
   append-only, year-long table; every event gains it.
3. **Keep per account** and record the risk. — impact: none; the weakness above stays.

## Recommendation

Option 1: the count lives with the session it protects, and the update is a single row lock.

## Impact if approved

- Spec sections to change: 7.2 (`sessions.pin_failures`), 9.2 note (tries per session; reset by a
  good PIN or passkey unlock).
- Tasks affected: T08 (blocked until decided), T12.

## Decision (Ibrahim)

Approved by Ibrahim, 2026-10-08: option 1 (`sessions.pin_failures`, reset by a good PIN or a passkey unlock; the fifth wrong try revokes the session). Until the spec is re-synced this CR is the
governing text for the sections it changes.

Still to do (Ibrahim): update the spec, re-export, commit `docs: sync spec vN (CR-021)`.
