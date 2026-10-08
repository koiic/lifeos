# CR-026 — Prove installability with Chrome's own check (Lighthouse 12 has no PWA audit)

- Raised by: Claude Code during T13
- Date: 2026-10-08
- Status: approved (spec re-sync pending)

## Problem

T13's done-when says "Lighthouse installable", and spec 15.1 lists "installable PWA" under
Lighthouse CI. Lighthouse 12 (2024) removed the PWA category and its `installable-manifest` audit;
the current `@lhci/cli` (0.15, Lighthouse 12.6) cannot assert installability. The last `@lhci/cli`
with the audit is 0.13.0 (Lighthouse 11.4).

## Options

1. **Chrome's own installability check** in a Playwright test — CDP
   `Page.getInstallabilityErrors` returns no errors (the check Lighthouse 11's audit wrapped) —
   and keep the current `@lhci/cli` for the `npm run lighthouse` script (performance, best
   practices, accessibility) at gates and in T49.
2. Pin `@lhci/cli` 0.13.0 (Lighthouse 11.4) to keep the audit.

## Decision (Ibrahim, 2026-10-08)

Option 1.

## Governing text until the spec is re-synced

- **T13 done-when:** "Chrome reports the app installable (no installability errors); offline shell
  loads; update toast test; install guide shown only when not standalone".
- **15.1 Performance row:** "Lighthouse CI (mobile) and `size-limit`: Performance ≥ 85, initial JS
  ≤ 250 KB gzipped; installability checked with Chrome's installability API in the e2e suite."

## Implementation note (T13)

Current Chrome reports no installability errors even for a page without a manifest (any site
can be installed as a shortcut), so `Page.getInstallabilityErrors` alone proves nothing (found
by a mutation test). The T13 test also asserts, on Chrome's parsed manifest
(`Page.getAppManifest`), the criteria Lighthouse's installable audit checked: no manifest errors,
a name, `start_url`, `display: standalone`, 192 and 512 px PNG icons that load, and a service
worker controlling the page.

Still to do (Ibrahim): update spec 15.1 and T13 in tasks.json, re-export, commit
`docs: sync spec vN (CR-026)`.
