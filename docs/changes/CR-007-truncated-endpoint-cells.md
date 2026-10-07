# CR-007 — Spec 9.2 cells truncated by the export: event edit scope and snooze presets

- Raised by: Claude Code, first-session cross-check (affects T30, T32, T35, T36, T38)
- Date: 2026-10-06
- Status: approved (spec re-sync pending)

## Problem

Two rows of the spec 9.2 endpoint table were cut at a `|` character during the Markdown export
(the pipe was read as a column separator):

- `GET/POST /events`, `GET/PATCH/DELETE /events/{id}` — Notes: "Recurring: \`?scope=this |" (ends there).
- `POST /reminders/{id}/snooze` — Notes: "\`{preset: 15m |" (ends there).

So the allowed `scope` values and the snooze `preset` values are not specified. Related sources
disagree on the scopes:

- APT-3: "edit 'this one' or 'all future'" (two scopes).
- tasks.json T35 done when: "this/future/all edits" (three scopes).

Snooze presets are described in words only (REM-3: "15 min, 1 h, tonight (19:00), tomorrow morning
(08:00)"); 10.4/10.5 use the action name `snooze` with title "In 15 min".

## Options

1. **Restore the cells as:** events `?scope=this|future|all` (for PATCH and DELETE on a recurring
   event; default `this`), and snooze body `{preset: "15m" | "1h" | "tonight" | "tomorrow"}`; amend
   APT-3 to "this one, all future, or all". Escape the pipes in Claude Docs (or use "or") so the export
   keeps them. — impact: spec 4.9 APT-3, 9.2; matches tasks.json T35.
2. **Two scopes only** (`this|future`) per APT-3 and change tasks.json T35 to "this/future edits";
   same snooze presets. — impact: tasks.json T35 done-when; spec 9.2.

## Recommendation

Option 1: "all" is cheap once "future" exists (it is "future" from the first occurrence), and it
matches the task list already approved. Please check the original Claude Docs text: if it says
something else, that text wins.

## Impact if approved

- Spec sections to change: 9.2 (two rows), 4.9 APT-3.
- Plan / tasks.json / requirements.json / tokens: none for option 1.
- Tasks affected: T30 (blocked: snooze endpoint), T32, T35, T36, T38.

## Decision (Ibrahim)

Approved by Ibrahim, 2026-10-07: option 1 (`?scope=this|future|all`, snooze presets `15m|1h|tonight|tomorrow`; APT-3 gains "all"; if the original Claude Docs text says otherwise, that text wins). He decided to proceed before re-exporting the spec ("proceed now"): until then this CR is the governing text for the sections it changes.

Still to do (Ibrahim): update the spec in Claude Docs, re-export it with the version bumped, commit `docs: sync spec vN (CR-007)`.
