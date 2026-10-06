# CR-001 — Night Garden outline colour fails non-text contrast

- Raised by: Claude, while generating the design tokens for the implementation plan
- Date: 2026-10-06
- Status: applied (spec 5.3 and design/tokens.json updated together)

## Problem

Spec 5.3 set `--border-strong` to #4A4578 in Night Garden. Against `--surface` (#221F45) that is
1.79:1, below the 3:1 WCAG 2.2 minimum for UI component boundaries (1.4.11) that NFR-4 requires.
Chip outlines and Sticker Book borders would be hard to see in the dark theme.

## Options

1. Lighten to #7A72B4: 3.62:1 on surface, 4.25:1 on bg, 3.09:1 on surface-tint. Keeps the hue.
2. Lighten to #8A82C6: more contrast (4.51:1) but outlines become visually loud at night.

## Recommendation

Option 1.

## Impact

- Spec 5.3 token table: Night `--border-strong` = #7A72B4 (done).
- design/tokens.json updated; contrast pairs for border on bg and surface-tint added.
- No task changes. `--butter` keeps #4A4578 as a tile fill (text on it passes 7.66:1).

## Decision (Ibrahim)

<confirm or revert>
