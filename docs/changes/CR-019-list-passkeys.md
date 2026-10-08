# CR-019 — Listing passkeys so one can be removed

- Raised by: Claude Code during T08
- Date: 2026-10-08
- Status: approved (spec re-sync pending)

## Problem

- Spec 9.2: `POST /auth/passkeys/options`, `/verify` "Add another passkey"; `DELETE
  /auth/passkeys/{id}` "Remove a passkey" — "Not the last sign-in method".
- Spec 5.2: Settings → "security and sessions".
- Spec 9.2 lists `GET /auth/sessions` (device label, last seen, current flag) but no way to list
  passkeys, and `GET /me` is described as "Profile, settings, health mode, feature flags".

The client cannot show her passkeys or know the id to delete.

## Options

1. **`GET /auth/passkeys`** → `{items: [{id, nickname, created_at, last_used_at, backed_up}],
   next_cursor: null}` (her own credentials; no key material). — impact: 9.2 gains one row.
2. **Include passkeys in `GET /me`.** — impact: 9.2 `/me` description; `/me` is built in another
   task and grows a security-only field.

## Recommendation

Option 1: it mirrors `GET /auth/sessions` and keeps security data in the auth module.

## Impact if approved

- Spec sections to change: 9.2 (new row `GET /auth/passkeys`).
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T08 (builds it), T12 (settings screen uses it).

## Decision (Ibrahim)

Approved by Ibrahim, 2026-10-08: option 1 (`GET /auth/passkeys`). Until the spec is re-synced this CR
is the governing text for the row it adds.

Still to do (Ibrahim): add the row to the spec, re-export, commit `docs: sync spec vN (CR-019)`.
