# CR-027 — T14 push: the phone check, revoked devices, and aiohttp

- Raised by: Claude Code during T14 (spec and security review findings)
- Date: 2026-10-09
- Status: approved (spec re-sync pending)

## Problem

Three things T14 cannot settle by itself.

**A. The phone check in T14's done-when cannot happen yet.** plan.md section 7 (and tasks.json)
T14 done-when: "Server tests with fake push endpoint (TTL, urgency, 404/410 handling); SW push and
click handlers unit-tested; test push received on Ibrahim's phone". A real push needs the app
served over https with the production VAPID secrets (spec 14.3), which is T15. T15 is `blocked`
(CR-006), and T14 does not depend on it. Plan 8 GATE-M1 already requires "she installs the app on
her iPhone, registers a passkey and receives the test push". Everything else in T14 is done and
tested (server against a fake push service; SW handlers unit-tested; a full-Chromium journey
through the real service worker).

**B. A revoked or signed-out device keeps getting reminders.** Spec 7.2:
`push_subscriptions.session_id uuid REFERENCES sessions(id) ON DELETE SET NULL`. Spec 12.1 (threat
model): "Lost or stolen phone | Phone lock, app lock, remote session revocation, …". Revoking
the lost phone's session (AUTH-5) or signing out deletes the session, but the subscription
stays active with `session_id` NULL, so the phone keeps showing reminders on its lock screen,
including medication names and the "Taken" action unless discreet mode is on (10.4). The spec
says nothing about what revocation does to that device's subscription.

**C. aiohttp is used directly.** Spec 6.1 lists `pywebpush` with VAPID keys. pywebpush's async
API (`webpush_async`) sends with `aiohttp`, which it installs. `notify/sender.py` imports
`aiohttp` itself (the response type and its network errors). The security review also asks that
pushes never follow redirects. Today a push service answering 307/308 would make aiohttp resend
the encrypted body and the VAPID header to any address, internal ones included, because the
endpoint allowlist is checked before sending, not on redirects. Refusing redirects needs our own
`aiohttp.ClientSession` passed to `webpush_async`. CLAUDE.md rule 9: "Only those in spec 6.1 and
plan 4; anything else needs a change request".

## Options

**A. The phone check**

1. Move "test push received on Ibrahim's phone" from T14's done-when to T15's done-when, where
   the deployment and secrets are made. GATE-M1 keeps her iPhone check. Impact: T14 can be done;
   T15 gains one manual check; no code.
2. Keep it on T14 and leave T14 open until T15 is unblocked and deployed. Impact: T14 stays in
   progress for an unknown time; T17 and later M1 work, which does not depend on T14, can still go
   ahead, but the M1 count stays open.

**B. Revoked devices**

1. Revoking a session or signing out turns off that session's subscriptions (`disabled_at = now`)
   in the same transaction. The device re-registers on its next signed-in start (10.5), which
   turns it back on. Spec 7.2 gains a note; AUTH-5 revocation, sign-out and the AUTH-6 PIN lockout get a test each. Impact: the auth
   service calls the notify service (allowed: modules talk through services); a few lines plus
   tests, in T14.
2. As 1, and also delete the row instead of disabling it. Impact: the same, but no history of
   failures for that device.
3. Leave it to Settings (T32): she removes the device by hand. Impact: a lost phone keeps showing
   reminders until she does; it does not meet 12.1.

**C. aiohttp**

1. Add `aiohttp` to spec 6.1 and pyproject as a direct, pinned dependency: "pywebpush's async
   transport, used directly to refuse redirects". `sender.py` passes a session that does not
   follow redirects (a redirect counts as `rejected`). Impact: no new package in the image (it is
   already installed); one test (a 307 is not followed).
2. Do not import aiohttp. Catch pywebpush's errors and treat unknown network errors as
   `rejected`, and accept that redirects are followed. Impact: transient network errors are no
   longer retried; the redirect risk stays (low: only big push services are allowed, and the
   payload is end-to-end encrypted).

## Recommendation

A1, B1 and C1. A1 matches where the work really happens and GATE-M1 already covers her phone.
B1 makes revocation do what 12.1 promises, and re-registering on start already brings a device
back. C1 removes the redirect path for a package that is already in the image.

## Impact if approved

- Spec sections to change: 6.1 (aiohttp beside pywebpush); 7.2 (`push_subscriptions`: "disabled
  when its session is revoked or signed out"); 12.1 (the lost-phone row: "revocation also stops
  that device's notifications").
- Plan / tasks.json / requirements.json changes: plan 7 and tasks.json, T14 done-when without the
  phone check; T15 done-when "+ test push received on Ibrahim's phone".
- Tokens changes: none.
- Tasks affected: T14 (B1 and C1 code and tests), T15 (A1 manual check).

## Decision (Ibrahim, 2026-10-09)

The recommended options: A1, B1 and C1. After the spec re-sync: update the spec in Claude Docs,
re-export it to docs/spec.md with the version bumped, commit `docs: sync spec vN (CR-027)`; plan 7
and tasks.json move the phone check from T14 to T15.

Corrected after approval (Claude Code, 2026-10-09): the body said revoking a session was AUTH-6;
it is AUTH-5 (AUTH-6 is the app lock). B1's tests also cover the app lock's fifth wrong PIN,
which ends the session the same way. The behaviour approved is unchanged.
