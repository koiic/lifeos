# CR-023 — Scrim, focus ring on toned surfaces, and the remaining design constants as tokens

- Raised by: Claude Code during T11 (design-system review)
- Date: 2026-10-08
- Status: approved (spec re-sync pending)

## Problem

- Plan 5.1: `design/tokens.json` is "the only place a design value is defined".
- Spec 5.8: "visible focus ring (2 px `--ink` outline, 2 px offset)".
- Spec 5.3 defines colours, spacing, radii and one shadow, but no overlay (scrim) colour, no
  border width, no opacity and no icon size.

Building the components exposed three gaps:

1. **Scrim.** Sheets and dialogs dim the page behind them. No token is meant for it; `--ink` is
   near-white in Night Garden, so an `--ink` scrim lightens the page instead of dimming it.
2. **Focus ring on toned surfaces.** On accent and pastel cards (the cycle card is an accent card)
   in Night Garden, a `--ink` outline is about 1.2–1.5:1 against the card — not visible.
3. **Raw constants** the lint cannot catch: 2 px borders (chips, inputs, outlines, Sticker
   cards), 0.6 disabled opacity, 0.35 scrim opacity, icon sizes 24/20 px, dialog and empty-state
   text max widths (24 rem, 20 rem).

## Options

1. **Add tokens** (Ibrahim edits `tokens.json`; then `build_tokens.py`):
   - themes: `color.scrim`: Sorbet `#2B1B2E`, Night Garden `#0B0A18` (the darkest ink in each);
   - shared: `size.border: 2px`, `size.icon: 1.5rem`, `size.icon-sm: 1.25rem`,
     `size.dialog-max: 24rem`, `size.text-max: 20rem`, `opacity.scrim: 0.4`,
     `opacity.disabled: 0.6`;
   - spec 5.8 reworded: the focus ring is 2 px in the **current text colour** (`currentColor`),
     which is `--ink` on pages and `--accent-ink` on accent/pastel surfaces — always the colour
     already proven against that background.
   — impact: tokens.json, spec 5.3/5.8 wording; T11 uses them (no visual change except the
   scrim and the ring on toned cards).
2. **Scrim from `--accent-ink`** (dark in both themes) and keep the other constants as documented
   layout constants in T11 Decisions; focus ring stays `--ink` everywhere. — impact: none to the
   tokens; the toned-card focus ring stays invisible in Night Garden.
3. **Leave as built** and record the risks.

## Recommendation

Option 1: it closes the visible problems (scrim, focus ring) and keeps plan 5.1's "one source"
true for the constants.

## Impact if approved

- Tokens: as listed in option 1 (Ibrahim edits `design/tokens.json`; contrast pairs unchanged).
- Spec sections to change: 5.3 (scrim, border, opacity, icon sizes), 5.8 (focus ring colour).
- Tasks affected: T11 (blocked until decided).

## Decision (Ibrahim)

Approved by Ibrahim, 2026-10-08: option 1. Until the spec is re-synced this CR is the governing
text for 5.3 (the new tokens) and 5.8 (the focus ring is 2 px `currentColor` with a 2 px offset).

To do by Ibrahim before T11 can finish (the guard blocks Claude Code from the token file): merge
into the existing objects of the design token file, keeping every current value, then run
`python3 scripts/build_tokens.py`:

```json
"themes": {
  "light": { "color": { "scrim": "#2B1B2E" } },
  "dark":  { "color": { "scrim": "#0B0A18" } }
},
"shared": {
  "size": {
    "border": "2px",
    "icon": "1.5rem",
    "icon-sm": "1.25rem",
    "dialog-max": "24rem",
    "text-max": "20rem"
  },
  "opacity": { "scrim": "0.4", "disabled": "0.6" }
}
```

This produces `--scrim`, `--size-border`, `--size-icon`, `--size-icon-sm`, `--size-dialog-max`,
`--size-text-max`, `--opacity-scrim` and `--opacity-disabled`.

Applied 2026-10-08: Ibrahim was away from the laptop (remote control) and gave Claude Code one-time
permission to run an add-only merge script for exactly this JSON (it refused to change any
existing value), followed by `python3 scripts/build_tokens.py` and `--check`. The script also
re-indented three one-line objects from the CR-005 edit (`font-variation` ×2, `font-weight`);
their values are unchanged.

Still to do (Ibrahim): update spec 5.3 and 5.8, re-export, commit `docs: sync spec vN (CR-023)`.
