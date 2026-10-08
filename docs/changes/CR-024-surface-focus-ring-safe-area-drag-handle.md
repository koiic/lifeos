# CR-024 — Focus ring follows the surface, safe-area token, Sheet drag handle

- Raised by: Claude Code during T11 (second-round spec and design-system reviews)
- Date: 2026-10-08
- Status: approved (spec re-sync pending)

## Problem

1. **Focus ring.** CR-023 set the ring to "2 px `currentColor`". A *filled* control (primary,
   secondary or danger button, FAB, chip, switch, the nav's add action) draws its ring outside
   itself, on the surface around it, but its own text colour is proven only on its fill. In Night
   Garden that ring was invisible (found by the T11 behaviour test). Hard-coding `--ink` instead
   fails on accent and pastel cards (about 1.2–1.5:1 in Night Garden), and the cycle card is one.
2. **Safe area.** Spec 11: "`viewport-fit=cover` with safe-area padding for the bottom bar". The
   padding is `env(safe-area-inset-bottom)`, which the token-only lint rejects in `padding`, and
   no token holds it.
3. **Drag handle.** Spec 5.5: "Sheet (bottom sheet with drag handle and focus trap)". T11 had built
   the handle as decoration only, so it suggested a gesture that did nothing.

## Options and decision (Ibrahim, 2026-10-08)

1. Focus ring — **surface-aware** (chosen) or always `--ink`.
2. Safe area — **token now** (chosen) or defer to T17.
3. Drag handle — **swipe down to close** (chosen) or reword the spec to a visual handle.
4. Also decided: the remaining layout mechanics (sheet/dialog `z-index`, sheet `max-height`, the
   1 px press offset) are **accepted as layout constants** recorded in T11 Decisions, not tokens.

## Governing text until the spec is re-synced

- **5.8:** "visible focus ring: 2 px, 2 px offset, in the text colour of the surface the control
  sits on — `--ink` on pages, cards and sheets, `--accent-ink` on accent and pastel surfaces. A
  filled control does not use its own fill's text colour for the ring." (Implementation: a
  `--surface-ink` alias, `var(--ink)` at the root and `var(--accent-ink)` on toned cards.)
- **5.3 tokens:** shared `size.safe-bottom: env(safe-area-inset-bottom)` → `--size-safe-bottom`;
  the bottom bar pads its bottom edge by it.
- **5.5:** "Sheet (bottom sheet with a drag handle — dragging it down past a threshold closes the
  sheet; the close button, the scrim and Escape also close it — and a focus trap)". Under
  reduced motion the sheet does not animate back or away.

## Token change

Ibrahim gave one-time permission for Claude Code to apply it with the add-only merge script, then
`python3 scripts/build_tokens.py` and `--check`:

```json
"shared": { "size": { "safe-bottom": "env(safe-area-inset-bottom)" } }
```

Still to do (Ibrahim): update spec 5.3, 5.5 and 5.8 (with CR-023), re-export, commit
`docs: sync spec vN (CR-023, CR-024)`.
