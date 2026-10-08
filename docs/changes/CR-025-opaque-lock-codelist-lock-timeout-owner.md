# CR-025 — Opaque lock screen, CodeList component, lock-timeout setting owner

- Raised by: Claude Code during T12 (spec, design-system and security reviews)
- Date: 2026-10-08
- Status: approved (spec re-sync pending)

## Problem

1. **Lock screen.** Spec 11.6: "show the LockScreen overlay over a blurred app … The overlay is
   rendered before any data". A blurred app behind the overlay keeps her data rendered in the
   page (readable through a light blur, present in the DOM), and needs a blur value that no token
   holds. T12 built an opaque lock screen and does not render the app while locked.
2. **CodeList.** Recovery codes (AUTH-4) are shown by a new `src/ui/CodeList` component (two
   columns, `translate="no"`, a copy button with a status message). Spec 5.5 is the complete
   component inventory (plan 5.1) and does not list it.
3. **Lock-timeout setting.** `app_lock_timeout_s` (60–3600 s, `PUT /auth/app-lock`) has no task
   that owns its Settings control: T09 builds `/me`, T17 builds profile and theme settings.
4. **Lock layer.** The lock screen sits above sheets (10) and dialogs (20): `z-index: 30`, a
   layering constant not covered by CR-024.

## Decision (Ibrahim, 2026-10-08)

1. **Opaque lock screen.** The LockScreen is an opaque `--bg` screen; while locked the app behind
   it is not rendered (unsaved form input is lost on lock; nothing of her data can show, even for
   a frame on a cold start). While the app is in the background it is covered by the same screen
   (title only), with the app kept and inert.
2. **CodeList added to spec 5.5.**
3. **Lock-timeout control → T17** (its settings scope; it shows the current value from `/me`,
   T09). Until then the app uses the spec default (300 s) and the copy says "5 minutes".
4. **`z-index: 30`** for the lock layer is accepted as a layout constant, like the CR-024 ones.

## Governing text until the spec is re-synced

- **11.6:** "… show the LockScreen, an opaque screen in the page colour; the app is not rendered
  while locked. While the app is in the background it is covered by the lock screen (title
  only), so the iOS app switcher snapshot shows the lock state."
- **5.5:** add "CodeList (one-time codes: in order, two columns, not translated, copy)".
- **T17 scope:** add the app-lock timeout setting (`PUT /auth/app-lock {timeout_s}`).

Still to do (Ibrahim): update spec 5.5 and 11.6 and T17 in tasks.json, re-export, commit
`docs: sync spec vN (CR-025)`.
