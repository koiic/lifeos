# CR-028 — Push subscriptions after account recovery and session expiry

- Raised by: Claude Code during T14 (spec and security closure reviews)
- Date: 2026-10-09
- Status: approved (spec re-sync pending)

## Problem

CR-027 B1 turns off a device's push subscription when its session is signed out, revoked
(AUTH-5) or locked out (AUTH-6). Two other ways a session ends leave the device getting reminders
on its lock screen (spec 12.1, "Lost or stolen phone … remote session revocation"):

1. **Account recovery (AUTH-8, CR-018).** An admin recovery invite revokes all her sessions as
   `lifeos_admin` and queues a security notice "for her devices" (10.7 "Account notice"). If the
   subscriptions were turned off in that transaction, the notice would reach no device; if they
   stay on, a stolen phone keeps showing reminders. Recovery is the likeliest lost-phone case.
2. **Session expiry** (idle or the 30-day limit, AUTH-5). Nothing runs when a session expires, and
   9.2 has no way for her to list or remove devices.

Spec 10.3 limits the dispatcher's role to `reminders`, `push_subscriptions`, `user_settings`,
`users(id, timezone, dek_wrapped)` and status columns, so it cannot see whether a subscription's
session is still live.

## Options

**Recovery**

1. Leave them on until the security notice has been sent, then turn them off. Impact: T30's
   dispatcher sends the account notice, then disables the subscriptions of revoked sessions.
2. Turn them off in the recovery transaction; the notice is only in the app (REM-5 inbox).
3. Keep them on (record the exemption).

**Expiry**

1. The dispatcher sends only to subscriptions whose session is live (not revoked, not expired);
   its role may read `sessions(id, revoked_at, expires_at)`. The account notice is the one
   exception (option 1 above). A device turns back on when it saves its subscription after the
   next sign-in (10.5).
2. A device list in Settings (T32) with Remove (new 9.2 endpoints).
3. Both. 4. Leave it.

## Recommendation

Recovery 1 and expiry 1: the warning still reaches a phone someone else holds, and then every
device without a live session goes quiet, with no new screens.

## Impact if approved

- Spec sections to change: 10.3 (the dispatcher skips subscriptions whose session is not live,
  except the account notice, after which a revoked session's subscriptions are turned off; its
  role may read `sessions(id, revoked_at, expires_at)`); 7.2 (`push_subscriptions` note); 12.1
  (lost phone row).
- Plan / tasks.json / requirements.json changes: T30 done-when gains both behaviours; the
  dispatcher role's grants (migration, T30).
- Tokens changes: none.
- Tasks affected: T30 (dispatcher, role grants, tests); T14 records the decision only.

## Decision (Ibrahim, 2026-10-09)

Recovery: option 1 (notice, then off). Expiry: option 1 (the dispatcher checks). After approval:
update the spec in Claude Docs, re-export it to docs/spec.md with the version bumped, commit
`docs: sync spec vN (CR-028)`; plan 7 and tasks.json add both behaviours to T30.
