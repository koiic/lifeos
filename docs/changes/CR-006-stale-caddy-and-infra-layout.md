# CR-006 — Spec still mentions Caddy and omits the Pages Function / _headers files

- Raised by: Claude Code, first-session cross-check (affects T15)
- Date: 2026-10-06
- Status: proposed

## Problem

ADR-0001 and plan 2.1 say "Caddy is no longer needed", and spec section 1, 6 and 14 were updated
for hybrid hosting. Two passages were not:

- Spec 11.1 layout: `infra/  docker-compose.yml, Caddyfile, backup scripts, runbooks`.
- Spec 16 M1 row: "Repo and CI (14.5), **VPS and Caddy**, crypto module and tests, ...".

Spec 11.1 also omits two files that 14.1 and ADR-0001 require: `web/functions/api/[[path]].ts`
(Pages Function proxy) and `web/public/_headers` (static security headers, 12.4). Plan 4.1 requires
the monorepo layout to be "exactly as spec 11.1", so the layout and the hosting decision conflict.

## Options

1. **Update spec 11.1 and 16** to remove the Caddyfile/Caddy and add `web/functions/api/[[path]].ts`
   and `web/public/_headers`. — impact: text only; T15 builds the files ADR-0001 describes.
2. **Keep a Caddyfile** for local development only. — impact: an extra component the ADR rejected;
   no requirement needs it.

## Recommendation

Option 1: the ADR is accepted and the rest of the spec already follows it.

## Impact if approved

- Spec sections to change: 11.1, 16 (M1 row).
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T15 (blocked). T01 does not create `infra/` contents, so it is not affected.

## Decision (Ibrahim)

<approved / rejected, date, notes>. After approval: update the spec in Claude Docs, re-export it
to docs/spec.md with the version bumped, commit `docs: sync spec vN (CR-006)`.
