# CR-008 — Late-period timing and cycle-card copy differ between sections

- Raised by: Claude Code, first-session cross-check (affects T31, T33)
- Date: 2026-10-06
- Status: proposed

## Problem

1. **When the late-period note is sent.**
   - J5 step 3: "If she is **more than 7 days** past the range end with no period logged, she gets one
     gentle 'Late? Log it when it starts' note".
   - 8.5 step 4: "`late_period` (**3 days after** `range_high`, 09:00)"; 10.2: "09:00, 3 days after
     `range_high`"; TV11: range_high 2026-10-24 → reminder "scheduled for 10-27 09:00" (3 days).
2. **Late-period copy.** J5: "Late? Log it when it starts". 10.7: title "Just checking in", body
   "Your period hasn't been logged yet. Log it when it starts".
3. **"Window" state copy on the Today card.** TOD-2: "Period may start today". 8.4 Window state:
   "Period may start any day now".

## Options

1. **Follow the detailed sections** (8.5, 10.2, 10.7, 8.4, TV11): 3 days after `range_high`; 10.7
   copy; "Period may start any day now". Update J5 and TOD-2 to match. — impact: spec text only;
   TV11 unchanged.
2. **Follow J5 for timing (7 days)** and change 8.5, 10.2 and TV11. — impact: test vector TV11
   changes; copy still needs a choice.

## Recommendation

Option 1: the test vectors are a required CI check and are written against 3 days; the copy in 10.7
and 8.4 is the more specific source.

## Impact if approved

- Spec sections to change: 3 (J5 step 3), 4.3 (TOD-2 example copy).
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T31 (blocked), T33.

## Decision (Ibrahim)

<approved / rejected, date, notes>. After approval: update the spec in Claude Docs, re-export it
to docs/spec.md with the version bumped, commit `docs: sync spec vN (CR-008)`.
