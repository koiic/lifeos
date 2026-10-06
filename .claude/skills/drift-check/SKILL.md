---
name: drift-check
description: Weekly whole-codebase comparison against the spec, plan and design system (plan section 6.5).
disable-model-invocation: true
---

Delegate to the `spec-reviewer` agent with this brief: compare the whole repository (not a diff)
against `docs/spec.md`, `docs/plan.md` and `design/tokens.json`. Check: data model vs spec 7,
endpoints vs spec 9.2 and the committed OpenAPI file, screens vs spec 5.2, job schedules vs spec 10.1,
security headers and CSP vs spec 12.4, module boundaries vs plan 4.2.

Then delegate to `design-system-reviewer` for all of `web/src`.

Write the combined findings to `docs/plan/drift/<YYYY-MM-DD>.md` as a table (finding, location,
spec/plan reference, severity, proposed action). Do not fix anything in this run. Report the counts
by severity to Ibrahim.
