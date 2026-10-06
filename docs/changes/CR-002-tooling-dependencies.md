# CR-002 — Tooling dependencies required by plan 6.1 are not on the allowed list

- Raised by: Claude Code, first-session cross-check (affects T01)
- Date: 2026-10-06
- Status: approved (plan re-sync pending)

## Problem

CLAUDE.md rule 9: "Only those in spec 6.1 and plan 4; anything else needs a change request."
But the verification contract itself (plan 6.1, `Makefile`) cannot run with only the packages named
in spec 6.1 and plan 4:

- `pytest -q --cov=app --cov-config=.coveragerc` (Makefile `test-server`) needs **pytest-cov**.
- `vitest run --coverage` (plan 6.1, Makefile `test-web`) needs a coverage provider, **@vitest/coverage-v8**.
- Testing FastAPI async endpoints (spec 15.1 "every endpoint's happy path") needs **httpx** (the
  FastAPI test client) and **pytest-asyncio** (or anyio's plugin) for async tests.
- Vitest + Testing Library (spec 15.1) needs a DOM environment (**jsdom**).
- "commitlint in CI" (plan 4.1) needs **@commitlint/cli** and a rule set (**@commitlint/config-conventional**).
- "ESLint (typescript-eslint strict, react, react-hooks, jsx-a11y), Prettier" (plan 4.3) needs ESLint's
  base packages (**eslint**, **@eslint/js**, **globals**) and **eslint-config-prettier** to avoid rule clashes.
- Plan 4.3 names the rule "`no-literal-string`", which exists only in eslint-plugin-i18next (not
  listed). `react/jsx-no-literals` from the already-allowed eslint-plugin-react does the same job.
- "TypeScript strict" and React 18 + Vite need **typescript**, **@types/react**, **@types/react-dom**,
  **@vitejs/plugin-react**.
- `size-limit` (spec 11.7) needs a preset plugin (**@size-limit/preset-app** or **@size-limit/file**).
- Lighthouse CI (spec 15.1) is the **@lhci/cli** package; axe in Playwright (spec 15.1) is **@axe-core/playwright**.
- mypy `--strict` over code using python-dateutil needs **types-python-dateutil**.
- stylelint needs a base config to be useful (**stylelint-config-standard**); the plan only names the
  `declaration-strict-value` plugin.

## Options

1. **Approve the list above as "implied tooling"** (dev-only; never shipped to the browser or the
   server image except where already implied), recorded in plan 4 as an explicit allow-list.
   Use `react/jsx-no-literals` instead of adding eslint-plugin-i18next. — impact: T01 proceeds;
   later tasks still need a CR for anything not on the list.
2. **Approve case by case** as each task first needs a package. — impact: T01 blocked on the
   coverage, test-client and commitlint packages anyway; many small CRs later.
3. **Loosen rule 9** to "runtime dependencies need a CR; dev tooling that a plan 6.1 check requires
   does not". — impact: less friction, but weaker control over the supply chain (spec 12.8).

## Recommendation

Option 1. It keeps rule 9 strict for runtime code while making the verification contract runnable,
and decides the question once.

## Impact if approved

- Spec sections to change: none.
- Plan: section 4 (add a "dev tooling allow-list" table with the packages above); 4.3 rule name
  `no-literal-string` → `react/jsx-no-literals`.
- tasks.json / requirements.json / tokens: none.
- Tasks affected: T01 (blocked until decided); T10, T11, T13, T16 use some of these.

## Decision (Ibrahim)

Approved by Ibrahim, 2026-10-06: option 1, the list above as the dev-tooling allow-list, with
`react/jsx-no-literals` in place of `no-literal-string`. Still to do (Ibrahim): update the plan in
Claude Docs, re-export it to docs/plan.md with the version bumped, commit
`docs: sync plan vN (CR-002)`.
