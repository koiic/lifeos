# CR-009 — CSV import template columns differ between DATA-2 and 13.2

- Raised by: Claude Code, first-session cross-check (affects T41)
- Date: 2026-10-06
- Status: approved (spec re-sync pending)

## Problem

- DATA-2 (4.15): "Template with `date,flow,symptoms,mood,note`".
- 13.2 CSV fallback: "a template: `date,flow,symptoms,mood,energy,sleep_hours,note` where `symptoms`
  is a `;`-separated list of names".

The importer and the downloadable template must use one column set.

## Options

1. **Seven columns (13.2)**; update DATA-2. Energy and sleep are check-in fields (CHK-1), so hand-kept
   records can include them. — impact: spec 4.15 text.
2. **Five columns (DATA-2)**; update 13.2. — impact: energy and sleep cannot be imported from CSV.
3. **Seven columns, with `energy` and `sleep_hours` optional** (the parser accepts either header set).
   — impact: spec 4.15 and 13.2 text; slightly more parser tests.

## Recommendation

Option 1: 13.2 is the detailed definition and matches the check-in fields.

## Impact if approved

- Spec sections to change: 4.15 DATA-2.
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T41 (blocked).

## Decision (Ibrahim)

Approved by Ibrahim, 2026-10-07: option 1 (seven CSV columns as in 13.2; DATA-2 updated). He decided to proceed before re-exporting the spec ("proceed now"): until then this CR is the governing text for the sections it changes.

Still to do (Ibrahim): update the spec in Claude Docs, re-export it with the version bumped, commit `docs: sync spec vN (CR-009)`.
