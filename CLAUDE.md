# Life OS — instructions for Claude Code

You are building the Life OS MVP: a private, installable web app (PWA) that replaces Flo for one
person, Zee. It covers cycle tracking, daily check-ins, appointments, medications and reminders.
The build follows three documents exactly. Read this file fully at the start of every session.

## Sources of truth (read-only for you)

| File | What it is |
| --- | --- |
| `docs/spec.md` | Product and technical specification. What to build. |
| `docs/plan.md` | Implementation plan: standards (section 4), design system rules (5), verification (6), tasks (7), gates (8). |
| `docs/requirements.json` | Every requirement ID, priority, milestone and owning task. |
| `docs/plan/tasks.json` | The 52 tasks, their spec references, dependencies and "done when". |
| `design/tokens.json` | Every design value. Generated into `web/src/ui/tokens.css` / `tokens.ts`. |
| `docs/plan/PROGRESS.md` | The progress ledger. Change it only with `python3 scripts/ledger.py`. |

A hook blocks edits to these files. If one of them is wrong, missing something, or contradicts
another, run `/change-request` and stop. Never guess, never work around the spec, never "improve"
it silently. Choices the spec genuinely leaves open go in the task file's Decisions section.

## How you work

- Use `/next-task` for all implementation work. It runs the delivery loop in `docs/plan.md` section 3:
  start → re-read spec → task file → tests first → implement → `make verify` → reviewer agents →
  evidence → commit → ledger.
- Exactly one task at a time. Do not start a task whose dependencies or previous gate are not done.
- Re-open and read the cited spec sections every session. Do not rely on memory or summaries.
- When a milestone's last task is done, run `/gate Mx` and stop. Only Ibrahim signs gates.
- Report briefly and honestly. If something failed or was skipped, say so plainly.

## Non-negotiable rules

1. **Spec fidelity.** Names, fields, endpoints, payloads, statuses, copy and limits exactly as in the
   spec. Every acceptance criterion of an owned requirement has a test tagged with its ID:
   Python `@pytest.mark.req("CYC-2")`; TS test titles start with `[CYC-2]`.
2. **Tests first.** Write tests, see them fail for the right reason, then implement.
3. **`make verify` green** before any commit. Web tasks also `make verify-e2e`. Never weaken, skip or
   delete a test to get green; never lower a threshold.
4. **Design system.** Only token values (`var(--…)`), only `src/ui` components in features, CSS
   Modules, both themes (Sorbet light, Night Garden dark), WCAG 2.2 AA, strings in `src/copy/en-GB.ts`.
5. **Privacy.** Health values only inside encrypted `payload_enc` columns. Never log payloads,
   bodies, names or notes. No third-party scripts, SDKs, fonts or origins. No real personal data in
   the repo; Zee's Flo export never enters it (use the anonymised fixture).
6. **Security.** RLS on every user table with a test; every endpoint has auth and other-user tests;
   only `server/app/platform/crypto.py` imports `cryptography`.
7. **Architecture.** Module layering `api → service → repo`; modules talk via services or outbox
   events; pure functions for domain logic (cycle engine, reminder times, recurrence).
8. **Git.** One branch and one pull request per task; Conventional Commits with the task ID
   (`feat(health): T26 cycle engine`); never `--no-verify`, never force-push, never rewrite `main`.
9. **Dependencies.** Only those in spec 6.1 and plan 4; anything else needs a change request.
10. **No scope creep.** Out-of-scope items (spec 4.18) are not built, not even "quickly".

## Project facts

- Hosting (ADR-0001): PWA on Cloudflare Pages; `/api/*` forwarded by a Pages Function to a VPS through
  a Cloudflare Tunnel; FastAPI + Procrastinate worker + PostgreSQL 16 in Docker Compose on the VPS.
- Server: Python 3.12, `uv`, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, Procrastinate.
- Web: React 18 + TypeScript (strict), Vite, vite-plugin-pwa (injectManifest), TanStack Query,
  Zustand, React Router 6, React Hook Form + Zod, date-fns(-tz), @simplewebauthn/browser, Ladle,
  Vitest, Playwright.
- Timezone default Europe/London; UK English; 24-hour time.

## Commands

| Command | Use |
| --- | --- |
| `make verify` | Every check in plan 6.1. Must be green before commit. |
| `make verify-fast` | Format, lint, types, unit tests (used by the Stop hook). |
| `make verify-e2e` | Playwright against a local stack. |
| `make verify-full` | verify + e2e + Lighthouse + ZAP + dependency/image scans (gates). |
| `python3 scripts/ledger.py next/show/start/block/done/summary` | The ledger. |
| `python3 scripts/trace.py [--task Txx] [--gate Mx]` | Traceability. |
| `python3 scripts/build_tokens.py [--check]` | Regenerate token CSS/TS. |
| `/next-task`, `/verify`, `/gate Mx`, `/change-request`, `/drift-check` | Workflow commands. |

Reviewer agents: `spec-reviewer`, `design-system-reviewer`, `security-reviewer`, `test-auditor`.
