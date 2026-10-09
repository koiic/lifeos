# CR-030 — `/me`: feature flags, recording consent, timezone detection

- Raised by: Claude Code during T09
- Date: 2026-10-09
- Status: approved (spec re-sync pending)

## Problem

T09 ("Profile, settings, consent and per-user seeding"; done when "`/me` bootstrap, settings
validation, 18 symptoms seeded and encrypted, consent time and version stored") meets three
things the spec does not define:

1. **Feature flags.** 9.2: "`GET /me` | Profile, settings, health mode, feature flags | Bootstraps
   the client". No section names a flag, where flags live, or who sets them.
2. **Recording consent.** 12.6: "Explicit consent at registration: a plain-language screen …;
   consent time stored." 7.2 `user_settings.health_consent_at`, `health_consent_version`. No
   endpoint records consent, and nothing defines the version. The screen comes with the setup
   wizard (spec 16: "She completes or skips the setup wizard and gives consent for health data
   (ONB-2, 12.6)").
3. **Timezone detection.** SET-1: "timezone (auto-detected, editable)". 11.7: "the client sends
   `X-Timezone` so the server can warn if the device and profile differ ('You seem to be in Lagos
   — switch timezone?')". Registration (9.2) takes no timezone, so every account starts at the
   7.2 default `Europe/London`, and nothing says how the server's warning reaches the client.

## Options

**1. Feature flags**

1. Drop "feature flags" from `/me`: none are defined, and her per-feature choices are already the
   `optional_fields` setting (BBT, discharge, intimacy). Impact: 9.2 wording only.
2. `GET /me` returns `features: {}` (server-side flags, none yet). Impact: an empty object to
   maintain.

**2. Consent**

1. `POST /me/consent {version}`: `version` must equal the server's current consent version
   (`"1"` until the wording changes); the server stores `health_consent_at` = now and the version,
   and writes the audit log. `GET /me` returns both. Withdrawal is account deletion (DATA-4).
   Impact: one endpoint in 9.2; the consent screen (setup wizard, ONB-2) calls it.
2. `PATCH /me/settings {health_consent_version}` with the same rules. Impact: no new endpoint, but
   a legal record mixed into ordinary settings.

**3. Timezone**

1. The client sends `X-Timezone` (its IANA zone) on every request. `GET /me` returns
   `device_timezone` (the header's zone if valid) and `timezone_differs` (true when it differs
   from her profile timezone). The app (T17) then offers "switch timezone?", and right after
   registration sets her profile timezone to the device's with `PATCH /me` ("auto-detected").
   Impact: 9.2 `/me` fields; T17 uses them.
2. Registration takes `timezone`; the warning as in option 1. Impact: changes the register
   payloads built in T06 and T12.

## Recommendation

1.1, 2.1 and 3.1: nothing is invented that has no use yet, consent is its own audited record,
and timezone detection needs no change to the finished registration flow.

## Impact if approved

- Spec sections to change: 9.2 (`GET /me` without feature flags, with consent and timezone
  fields; `POST /me/consent`); 11.7 (how the warning reaches the client); 12.6 (the consent
  version and its endpoint); 7.2 `audit_log.action` gains `user.health_consent` (added after
  approval, 2026-10-09: the name of the audit entry option 2.1 writes; no change in substance).
- Plan / tasks.json / requirements.json changes: none (T09 and T17 already own these).
- Tokens changes: none.
- Tasks affected: T09 (endpoints), T17 (timezone prompt, auto-detect), the setup-wizard task
  (ONB-2: the consent screen calls `POST /me/consent`).

## Decision (Ibrahim, 2026-10-09)

1.1 (no feature flags), 2.1 (`POST /me/consent`), 3.1 (`X-Timezone`; `/me` returns
`device_timezone` and `timezone_differs`). Still to do (Ibrahim): update the spec in Claude Docs,
re-export it with the version bumped, commit `docs: sync spec vN (CR-030)`.
