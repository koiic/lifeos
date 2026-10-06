# Life OS MVP — Implementation Plan

Oct 6, 2026 · @ibrahim

## 1. Summary

This plan turns the *Life OS MVP — Product & Technical Specification* into 52 ordered tasks, each traced to requirement IDs and closed only by automated checks plus review. A Claude Code operating kit (section 9) enforces the plan inside the repository so the build cannot quietly drift from it.

Three documents, three jobs:

| Document | Answers | Who may change it |
| --- | --- | --- |
| Specification | What to build and why | Ibrahim only, through a change request (section 6.4) |
| This plan | In what order, to what standards, how each step is proven | Ibrahim only |
| Progress ledger (`docs/plan/PROGRESS.md`) | Where we are, with evidence | Claude Code, one task at a time |

The working rule for Claude Code is simple: take the next task from the ledger, prove it with tests and checks, get it reviewed, record the evidence, commit, and stop at every milestone gate for a human sign-off. Anything the spec does not answer becomes a change request, never a guess. Plan version 1, built against spec version 1.

## 2. Decisions since the spec

Hosting is now hybrid: the PWA on Cloudflare Pages, the API, worker and database on one small VPS reached only through a Cloudflare Tunnel. The spec's section 14 has been updated to match (ADR-001).

### 2.1 ADR-001 — Hybrid hosting

|  |  |
| --- | --- |
| Context | Ibrahim wants to start on Vercel or Cloudflare. Reminders need a job every minute; Vercel's free Hobby plan only allows cron jobs once a day with ±59 min precision ([Vercel docs](https://vercel.com/docs/cron-jobs/usage-and-pricing)), and Pro costs money and removes the long-running worker the spec relies on. |
| Decision | Static PWA on **Cloudflare Pages**. Same-origin API: a Pages Function at `/api/*` forwards requests to the VPS over a **Cloudflare Tunnel** protected by a Cloudflare Access service token. FastAPI, the Procrastinate worker and PostgreSQL run on the VPS with Docker Compose, unchanged from the spec. |
| Consequences | The VPS exposes no public ports (SSH only, ideally also via the tunnel). Caddy is no longer needed. Security headers for static files come from a Pages `_headers` file; the API sets its own. Cookies, CSP and WebAuthn keep working because the browser only ever sees one origin. |
| Rejected | Vercel Hobby (daily cron only); Vercel Pro (paid, and the job design would change); everything on the VPS (works, but he asked to use Cloudflare/Vercel). |

### 2.2 The domain must be fixed before Zee registers

Passkeys are bound to the domain they were created on. If Zee registers on a temporary `*.pages.dev` address and the app later moves to the final domain, every passkey stops working and she must re-register. Cloudflare Tunnel public hostnames also need a domain on Cloudflare.

- **Weeks 1–2 (development and staging):** `*.pages.dev` plus a staging tunnel is fine; only test accounts exist.
- **Before the M1 gate test on her iPhone:** the production domain is bought and added to Cloudflare, and `WEBAUTHN_RP_ID` is set to it. This is task T15's exit condition.

### 2.3 Answers recorded from the spec's open questions

- Her iPhone runs iOS 16.4 or later: web push is possible (installed PWA only).
- Alerts go to both ntfy and email.
- Domain: to be decided; blocking only at the point in 2.2.

## 3. The delivery loop

Every task follows the same loop, run by the `/next-task` command in Claude Code; nothing is marked done without passing automated checks and the reviewer agents.

_[Diagram, as text] Pick next task → Restate + plan → Tests first → Implement → make verify all green? (no: back to Implement; yes:) → Reviewer agents (findings: back to Implement) → Record + commit (evidence in ledger) → Milestone complete? (no: next task; yes: human gate on her phone)._

If restating the task reveals a gap or contradiction in the spec, the loop stops: Claude Code writes a change request (section 6.4) and waits for Ibrahim instead of guessing.

1. **Pick next task.** The first task in `PROGRESS.md` whose status is `todo` and whose dependencies are `done`.
2. **Restate and plan.** Quote the spec sections and requirement IDs it covers, list files to touch and tests to write, and state what is out of scope. Saved to `docs/plan/tasks/Txx.md`.
3. **Tests first.** Write tests named with requirement IDs; run them and confirm they fail for the right reason.
4. **Implement.** Smallest change that makes the tests pass, following the standards (section 4) and design system (section 5).
5. **Verify.** `make verify` must be fully green: format, lint, types, unit and integration tests, coverage thresholds, traceability, design-token checks.
6. **Review.** The `spec-reviewer`, `design-system-reviewer` (web tasks) and `security-reviewer` (auth, crypto, data, infra tasks) agents read the diff against the spec. Every finding is fixed or explicitly answered.
7. **Record and commit.** Update the ledger row with evidence (test counts, coverage, review verdicts), then a Conventional Commit tagged with the task ID.
8. **Milestone gate.** When the last task of a milestone is done, `/gate Mx` produces the gate report and Claude Code stops for Ibrahim's sign-off (section 8).

## 4. Engineering standards

These rules apply to every commit; most are enforced by tooling, and the rest by the reviewer agents. Where a rule and the spec disagree, the spec wins and the rule gets a change request.

### 4.1 Repository and git

| Rule | Enforced by |
| --- | --- |
| Monorepo layout exactly as spec 11.1, plus `design/`, `scripts/`, `.claude/` | `spec-reviewer` |
| Trunk-based: `main` always deployable; one short branch per task named `t07-auth-fallback` | Convention, CI on branch |
| Conventional Commits with the task ID: `feat(health): T26 cycle engine calendar-1.0` | `commitlint` in CI |
| One task per pull request (self-merged after checks); no unrelated changes | `spec-reviewer` |
| Never commit secrets, real health data or her Flo file; `.env*`, `*.pem`, `secrets/` ignored | `gitleaks` pre-commit and CI; Claude Code guard hook |
| Lockfiles committed (`uv.lock`, `package-lock.json`); exact versions | CI fails on lockfile drift |
| `pre-commit` hooks: ruff format, ruff, prettier, eslint --fix on staged files, gitleaks | `pre-commit` |

### 4.2 Python (server)

| Rule | Enforced by |
| --- | --- |
| Python 3.12, managed by `uv`; FastAPI, SQLAlchemy 2.0 async, Pydantic v2 | `pyproject.toml` |
| Format and lint: ruff (rules E, F, I, B, UP, S, ASYNC, PT, SIM, RUF), line length 100 | `ruff` |
| Types: mypy `--strict` for all of `app/`; no `Any` in public functions; no `# type: ignore` without a reason | `mypy` |
| Layering per module: `api.py` (HTTP only) → `service.py` (rules, transactions) → `repo.py` (SQL only); modules talk through services or outbox events, never each other's repos | `import-linter` contracts |
| `platform/crypto.py` is the only importer of `cryptography`; only `repo.py` files import SQLAlchemy sessions | `import-linter` |
| Every request and response is a Pydantic model; every endpoint declares its error responses | OpenAPI diff check |
| Pure functions for domain logic (cycle engine, reminder times, recurrence); no I/O inside them | Review; unit tests without DB |
| Datetimes always aware (`datetime.now(UTC)`); local dates computed with `zoneinfo` from the user's timezone | ruff `DTZ` rules |
| Logging through `structlog` with event names; never log payloads (spec 12.5) | `security-reviewer`; log scrub test |

### 4.3 TypeScript (web)

| Rule | Enforced by |
| --- | --- |
| TypeScript `strict`, `noUncheckedIndexedAccess`; no `any`, no non-null `!` in `lib/` | `tsc`, ESLint |
| ESLint (typescript-eslint strict, react, react-hooks, jsx-a11y), Prettier | CI |
| Feature folders own their screens, hooks and queries; shared UI only from `src/ui`; features never import other features | ESLint `no-restricted-imports` boundaries |
| API calls only through `lib/api` generated types; never hand-written fetch in features | ESLint rule |
| Server state in TanStack Query; local UI state in Zustand; no other global state | Review |
| All user-facing text in `src/copy/en-GB.ts` | ESLint `no-literal-string` in JSX (feature folders) |
| Dates via `date-fns`/`date-fns-tz` helpers in `lib/dates.ts` only | ESLint restricted globals for `Date` methods in features |

### 4.4 API

REST conventions in spec 9.1 are mandatory: problem+json errors, idempotency keys, cursor pagination, ETag/If-Match, `/api/v1` prefix. Breaking changes need a new path version; the generated OpenAPI file is committed and diffed in CI.

### 4.5 Database

| Rule | Enforced by |
| --- | --- |
| Schema changes only through Alembic migrations; one migration per task at most; reversible `downgrade` | CI runs upgrade → downgrade → upgrade |
| Expand-then-contract for any change to existing columns | `spec-reviewer` |
| Every user table: `user_id`, RLS enabled and forced, policy tested | Migration test + RLS test generator that checks every table |
| Health values only inside `payload_enc` (spec 7.1); new plaintext columns on health tables need a change request | `security-reviewer` |

### 4.6 Security

Spec section 12 is the standard. In addition: dependency updates through Renovate only; any new third-party service or origin needs a change request; secrets only via settings loaded from files; every endpoint has an authorization test (signed out → 401, other user → 404).

### 4.7 Testing

| Rule | Detail |
| --- | --- |
| Test first | Each task's tests are written and seen failing before implementation |
| Requirement tags | Python: `@pytest.mark.req("CYC-2")`; Vitest and Playwright: test title starts with `[CYC-2]` |
| Coverage | ≥ 90% lines for `health`, `notify`, `platform/crypto`; ≥ 75% overall; web ≥ 80% for `lib/` |
| No flaky tests | A test that fails intermittently is fixed or quarantined with an issue the same day |
| Real Postgres | Integration tests never mock the database |
| Test data | Factories (`factory_boy`, test builders); no real personal data anywhere |

### 4.8 Documentation

Each architectural decision gets an ADR in `docs/adr/` (template provided). Each task leaves `docs/plan/tasks/Txx.md` with its plan and evidence. Runbooks live in `infra/runbooks/`. README explains local setup in under 10 commands.

## 5. Design system enforcement

The design system is code, not a picture: one token file drives every colour, font, radius, space and motion value, and lint rules make it impossible to ship a value from outside it.

### 5.1 Source of truth

| Artifact | Role |
| --- | --- |
| `design/tokens.json` | The only place a design value is defined: both themes' colours (spec 5.3), typography (5.4), spacing, radii, shadows, motion, and the list of text/background pairs that must pass contrast |
| `scripts/build_tokens.py` | Generates `web/src/ui/tokens.css` (CSS custom properties per theme) and `web/src/ui/tokens.ts` (typed names); both files carry a "generated, do not edit" header |
| `scripts/check_contrast.py` | Fails if any listed pair is below 4.5:1 (3:1 for large text) in either theme |
| Canvas *Life OS UI Directions* | Visual reference for Sorbet and Night Garden; where it differs from tokens, tokens win |
| Spec 5.5 component list | The complete component inventory for the MVP |

Changing a token is a change request, because it changes how everything looks.

### 5.2 Rules the tooling enforces

| Rule | Tool |
| --- | --- |
| No hex, rgb, hsl or named colours outside `tokens.css` | stylelint `color-no-hex`, `color-named: never`, `declaration-strict-value` for colour, fill, stroke and border properties |
| Fonts, radii, spacing, shadows and durations only through tokens (`var(--…)`) | `declaration-strict-value` for `font-family`, `border-radius`, `margin*`, `padding*`, `gap`, `box-shadow`, `transition*` |
| Styles in CSS Modules next to the component; no inline `style` except setting a CSS custom property (`style={{'--progress': p}}`) | ESLint rule `no-restricted-syntax` on `style` objects with non-custom keys |
| Features build screens only from `src/ui` components and layout primitives (`Stack`, `Grid`) | ESLint import boundaries |
| Generated token files never edited by hand | Claude Code guard hook; CI regenerates and diffs |
| Icons only from `src/ui/icons` (24 px grid, 2 px stroke, `currentColor`); no emoji, no icon fonts | ESLint; `design-system-reviewer` |
| Fonts self-hosted WOFF2 from Fontsource; no external font requests | CSP + external-origin check (spec 12.4) |

### 5.3 Rules every component meets

1. Lives in `src/ui/<Name>/` with `Name.tsx`, `Name.module.css`, `Name.stories.tsx` (Ladle) and `Name.test.tsx`.
2. Stories cover each variant and state in **both themes** (Sorbet, Night Garden).
3. Tests include an axe check with zero violations and keyboard operation where interactive.
4. Playwright visual snapshots of the stories in both themes at 390 px wide; any pixel change needs an explicit snapshot update in the same task, which the reviewer must approve.
5. Touch targets ≥ 44 × 44 px; visible focus ring (spec 5.8); honours `prefers-reduced-motion`.
6. Props are typed; no component accepts arbitrary `className` or `style` from features (variants instead), so screens cannot drift visually.

### 5.4 Copy and tone

All strings live in `src/copy/en-GB.ts`, grouped by screen. The `design-system-reviewer` checks new copy against spec 5.7: ranges and "about" for predictions, "estimated fertile window", no blame, no medical claims, UK spelling.

### 5.5 Screen acceptance

A screen is done when it matches the spec's screen inventory row (5.2), uses only `src/ui` components, has an empty, loading, error and offline state, passes axe in both themes, and has a Playwright test for its journey step.

## 6. Verification, validation and drift control

Verification proves each task was built as specified (automated, every task); validation proves the right thing was built (Zee using it, at every milestone gate). Drift control keeps both tied to the current spec.

### 6.1 `make verify`: the checks every task must pass

| Check | Command (inside `make verify`) | Pass condition |
| --- | --- | --- |
| Format | `ruff format --check`, `prettier --check` | No changes needed |
| Lint | `ruff check`, `eslint`, `stylelint` | Zero errors, zero warnings |
| Types | `mypy --strict server/app`, `tsc --noEmit` | Zero errors |
| Architecture | `lint-imports` | All contracts kept |
| Server tests | `pytest` with Postgres | All pass; coverage thresholds (4.7) |
| Web tests | `vitest run --coverage` | All pass; coverage thresholds |
| Migrations | `scripts/check_migrations.sh` | upgrade → downgrade → upgrade clean |
| API contract | `scripts/check_openapi.sh` | Committed `openapi.json` and generated TS types match the code |
| Design tokens | `python scripts/build_tokens.py --check`, `python scripts/check_contrast.py` | Generated files current; every pair passes |
| Traceability | `python scripts/trace.py` | Rules in 6.2 hold |
| Secrets | `gitleaks detect` | Nothing found |

`make verify-e2e` (Playwright against a local stack) runs at the end of every web task and in CI; `make verify-full` adds Lighthouse, ZAP and dependency scans and runs at each gate.

### 6.2 Traceability

`docs/requirements.json` lists every requirement ID from the spec with its priority, milestone and owning task. `scripts/trace.py` enforces:

1. Every test tag refers to a real requirement ID (no typos, no invented IDs).
2. Every **must** requirement owned by a task marked `done` in `PROGRESS.md` has at least one test tagged with it.
3. At a gate (`trace.py --gate M3`), every must requirement of that milestone and earlier has tests, and every should requirement either has tests or is listed as deferred in the gate report.
4. Every task marked `done` has a `docs/plan/tasks/Txx.md` with plan and evidence sections filled.

The gate report includes the generated traceability matrix (requirement → tests → task → commit).

### 6.3 Evidence in the ledger

A ledger row moves to `done` only with: commit SHA, test counts added, coverage of touched modules, `make verify` result, reviewer verdicts (pass or the findings fixed), and for web tasks the screenshot or snapshot names. A row without evidence is not done.

### 6.4 Change requests

The spec, this plan, `design/tokens.json` and `docs/requirements.json` are read-only for Claude Code (a hook blocks edits). When a task reveals a gap, contradiction or better approach:

1. Claude Code writes `docs/changes/CR-xxx.md`: the problem, spec references, options, recommendation, impact on tasks.
2. It marks the task `blocked` in the ledger and stops.
3. Ibrahim decides, updates the spec in Claude Docs, re-exports it to `docs/spec.md` (version bumped in its header), and commits `docs: sync spec vN (CR-xxx)`.
4. The task resumes against the new spec.

Small, purely internal choices that the spec leaves open (a helper's name, an index) are recorded in the task file instead, not raised as change requests.

### 6.5 Keeping long-running work on track

- **Small tasks.** Each task fits in one or two Claude Code sessions; bigger ones were split in section 7.
- **Fresh context every session.** A `SessionStart` hook injects the current task, its spec references and the last ledger entries, so no session relies on memory of a previous one.
- **One task at a time.** `/next-task` refuses to start a new task while another is `in_progress`.
- **Stop check.** A `Stop` hook runs the fast checks when files changed and blocks finishing while they fail.
- **Re-read, don't recall.** Commands instruct Claude Code to open the cited spec sections every time rather than paraphrase from earlier turns.
- **Weekly drift review.** Ibrahim runs `/drift-check`: the `spec-reviewer` compares the whole codebase against the spec and lists divergences.

### 6.6 Validation

| When | Activity | Pass condition |
| --- | --- | --- |
| Each milestone gate | Ibrahim runs the milestone's journeys on staging on his own phone | Every step works; issues logged as tasks |
| M1, M2, M3 and M5 gates | Zee tries the new parts on her iPhone (from M2 with real logging alongside Flo) | She can do it without help; her feedback recorded in the gate report |
| Weeks 10–11 | Beta (spec 15.4) | Weekly feedback; bugs triaged in 48 hours |
| Launch | Spec section 17 checklist | Every box ticked with evidence |

## 7. Work breakdown

52 tasks in five milestones, in build order. Each task owns the requirements it finally proves (listed in the ledger and `docs/requirements.json`), and "Done when" is the verification that closes it.

Where this plan proves a requirement earlier than spec section 16 lists it (for example NFR-5 at M4 with the first restore drill), the earlier milestone applies. Every task also passes `make verify` and the reviewer agents; that is not repeated in each row. T41 needs her real Flo export, requested in week 1.

### M1 Foundation (weeks 1–2)

| ID | Task | Spec | Depends on | Done when (verification) |
| --- | --- | --- | --- | --- |
| T01 | Repository scaffold, tooling and verify pipeline | 11.1, 14.5; plan 4, 6.1 | — | `make verify` runs every check in plan 6.1 (empty suites pass); pre-commit installed; commitlint, gitleaks active; kit files in place |
| T02 | Server skeleton: config, logging, errors, middleware | 6.2, 9.1, 12.5 | T01 | Tests: problem+json shape, Origin and custom-header check on mutations, request ids in logs, log scrubber, `/healthz` and `/readyz` |
| T03 | Database schema, roles and row-level security | 7.1–7.5 | T02 | Migration upgrade/downgrade/upgrade clean; generated RLS test proves every user table isolates users; `lifeos_admin_ro` denied on health tables |
| T04 | Encryption module and encrypted payload types | 12.2, 7.1 | T03 | 100% line coverage of `platform/crypto.py`; tamper tests (changed AAD, byte, version) fail closed; KEK re-wrap test |
| T05 | Job queue, worker and outbox relay | 6.2, 10.1 | T03 | Integration test: outbox event → relay → job runs with `app.user_id` set; periodic task registered; per-user serialisation lock |
| T06 | Invites, passkey registration and sign-in, sessions, recovery codes | 9.2 auth, 12.3, 7.2 auth tables | T04 | API tests with a WebAuthn test authenticator: invite rules, register, sign in, cookie flags, session expiry, recovery codes single-use |
| T07 | Password + TOTP fallback, rate limits, auth events | 4.1 AUTH-3, AUTH-7; 12.3 | T06 | Tests: Argon2id params, TOTP window and replay, lockout after 5 failures per account and IP, auth events written |
| T08 | App-lock PIN, re-auth, session management, passkey management, recovery invite | 4.1 AUTH-5, AUTH-6, AUTH-8; 9.2 | T07 | Tests: PIN 5-try limit, recent-auth enforcement, revoke session, last-method protection, recovery invite revokes sessions and is audited |
| T09 | Profile, settings, consent and per-user seeding | 4.2 SET-1, SET-2; 7.4; 12.6 | T06 | Tests: `/me` bootstrap, settings validation, 18 symptoms seeded and encrypted, consent time and version stored |
| T10 | Web scaffold: router, query client, generated API client, error boundary | 11.1, 11.4, 11.7 | T01 | `tsc`, ESLint boundaries, Vitest pass; `size-limit` budget enforced; OpenAPI types regenerate with no diff |
| T11 | Design system foundation: tokens, fonts, themes, base components | 5.3–5.6, 5.8; plan 5 | T10 | `build_tokens.py --check` and `check_contrast.py` pass; each base component has stories in both themes, axe-clean tests, visual snapshots |
| T12 | Web auth flows: register, sign-in, fallback, recovery, lock screen, sessions | 3 J1, J11; 5.2; 11.6 | T08, T11 | Playwright with virtual authenticator: register, sign out, sign in, lock after timeout, unlock, revoke session |
| T13 | PWA: manifest, service worker, update prompt, install guide | 11.2, 11.3; ONB-1 | T11 | Lighthouse installable; offline shell loads; update toast test; install guide shown only when not standalone |
| T14 | Web Push end to end: VAPID, subscriptions, test push, permission card | 10.4–10.6; ONB-3 | T05, T13 | Server tests with fake push endpoint (TTL, urgency, 404/410 handling); SW push and click handlers unit-tested; test push received on Ibrahim's phone |
| T15 | Infrastructure: VPS, Docker Compose, Cloudflare Pages, Pages Function proxy, Tunnel, Access, secrets | 14 (as amended); plan 2 | T02, T13 | Staging reachable at one origin with `/api` proxied; VPS has no inbound web ports; runbook written; production domain on Cloudflare and RP ID set before the gate |
| T16 | CI/CD: pipelines, staging deploy, production approval, scans, external-origin check | 14.5, 12.8; NFR-6 | T15 | Pipeline green on `main`; staging auto-deploys; production needs approval; build fails if any external origin appears in the web bundle |
| T17 | App shell: bottom navigation, Today greeting, profile and theme settings | 5.1, 5.2; TOD-1, SET-1, SET-2 | T12 | Playwright: navigation reaches every tab; theme switch follows system and override; greeting by local time; en-GB date formats |

### M2 Logging (weeks 3–4)

| ID | Task | Spec | Depends on | Done when (verification) |
| --- | --- | --- | --- | --- |
| T18 | Daily logs API with validation and last-writer-wins | 9.2, 9.3, 9.4; CHK-2, PER-2 | T09, T05 | Tests: upsert, future-date rejection, LWW by `client_updated_at`, idempotent replay, `daily_log.flow_changed` outbox event |
| T19 | Symptom catalogue API with custom symptoms | CHK-3; 9.2 | T09 | Tests: create, rename, archive; archived symptoms still resolve on old logs |
| T20 | Period start/end endpoints and bleed-episode logic | 8.1; PER-1, PER-4, PER-5 | T18 | Pure-function tests: episodes with ≤2-day gaps, spotting never starts a period, auto-close after 3 dry days, >10-day prompt; TV6, TV9, TV10 |
| T21 | Calendar month endpoint | 9.2; CSC-3 | T20 | Tests: flow, logged-day dots and placeholders for predictions per day; month boundaries in her timezone |
| T22 | Check-in sheet UI: mood, energy, sleep, symptoms, flow, note, optional fields | 4.4; 5.2; CHK-1, CHK-3, CHK-4, PER-2 | T18, T19, T11 | Playwright J3 completes in one sheet; component tests for pickers; optional fields hidden until enabled; axe clean both themes |
| T23 | Offline layer: IndexedDB outbox, encrypted query cache, sync engine, sync chip | 11.4, 11.5; CHK-5, TOD-7 | T22 | Vitest with fake IndexedDB: ordering, idempotency keys, retries, rollback on 422; Playwright J9 offline check-in syncs once |
| T24 | Health calendar screen, day editing and period start/end controls | 5.2; PER-1, PER-3, CSC-3 | T21, T23 | Playwright J4: start, daily flow, end; edit a past day; calendar updates |
| T25 | Today: check-in card and streak | TOD-3, TOD-5; 9.3 /today | T22 | Tests: streak counting across days and timezones; completed state; Playwright Today after check-in |

### M3 Predictions (weeks 5–6)

| ID | Task | Spec | Depends on | Done when (verification) |
| --- | --- | --- | --- | --- |
| T26 | Cycle engine calendar-1.0 (pure) | 8.1–8.4; CYC-2, CYC-3, CYC-4, CYC-6 | T20 | TV1–TV12 pass as named tests; Hypothesis properties pass; 100% branch coverage of the engine module |
| T27 | Rebuild job, predictions storage, nightly predict, health profile, exclusions, new-period confirm | 8.5; CYC-1, CYC-5, CYC-7, MOD-1, MOD-2 | T26, T05 | Integration: log change → rebuild < 2 s → prediction superseded; exclusions and forced starts survive rebuild; postpartum suppression |
| T28 | Cycle screen: ring, prediction card, states, history, exclusions | 5.2; 8.4; CSC-1, CSC-2, CSC-4, CYC-4, CYC-5, CYC-6 | T27, T11 | Component tests for CycleRing aria text; every 8.4 state rendered in stories; Playwright J5 view |
| T29 | Setup wizard and health mode settings | 3 J1; ONB-2, SET-4, MOD-1, MOD-2 | T27 | Playwright: wizard steps skippable and re-runnable; mode change records start date and hides predictions in postpartum |
| T30 | Reminder engine: model, horizon job, dispatcher, quiet hours, DST, retries, inbox API | 10.1–10.3; REM-1, REM-2, REM-4, REM-6, REM-7 | T14, T27 | Time-machine tests across 2026-10-25 and 2027-03-28; dispatcher SKIP LOCKED concurrency test; crash recovery of `sending`; dedupe keys |
| T31 | Check-in, period-due and late-period reminders | 10.2; TV11, TV12 | T30 | Tests: schedules from predictions; skip rules; rescheduling without duplicates; notification copy matches spec 10.7 |
| T32 | Notification settings, snooze and reminder inbox UI | SET-3, REM-3, REM-5 | T30, T17 | Playwright: change check-in time and quiet hours; snooze presets; inbox lists sent reminders |
| T33 | Today cycle card and complete /today aggregate for cycle | TOD-2; 9.3 | T27, T25 | Tests: every state's copy from 8.4; Playwright Today shows the right card for seeded histories |

### M4 Feature complete (weeks 7–8)

| ID | Task | Spec | Depends on | Done when (verification) |
| --- | --- | --- | --- | --- |
| T34 | People: API and screens | APT-4; 9.2 | T17 | API tests incl. encryption of fields; Playwright create, edit, call link |
| T35 | Events API: CRUD, recurrence, occurrence edits, reminder rules, timeline | APT-1, APT-2, APT-3, CAL-2; 9.2 | T30 | Tests: RRULE expansion caps, this/future/all edits, reminders per occurrence, DST; timeline merges events, doses, tasks, flow days |
| T36 | Appointment screens and Calendar (month and agenda) | APT-1, APT-2, APT-3, CAL-1; 5.2 | T35, T34 | Playwright J6: create appointment with person and reminders; calendar shows it; agenda for a day |
| T37 | Medications and doses API: schedules, generation, actions, missed job | MED-2, MED-4, MED-5; 10.1 | T30 | Tests: dose generation 14 days ahead across DST; schedule edit regenerates only future untaken doses; missed after 6 h |
| T38 | Medication screens, dose confirm, notification Taken and snooze actions | MED-1, MED-3, MED-4, MED-5; 10.5 | T37, T14 | Playwright J7; SW notificationclick test posts with idempotency key; iOS fallback to confirm screen |
| T39 | Tasks and notes: API and screens | TSK-1, NOTE-1 | T30, T17 | API and Playwright tests; note bodies encrypted; task reminders created and cancelled on completion |
| T40 | Today list and quick-add sheet | TOD-4, TOD-6, TSK-2 | T36, T38, T39 | Playwright: items sorted by time, untimed last, overdue in Earlier; every quick-add action works |
| T41 | Flo and CSV import with preview and undo | 13.1, 13.2; DATA-1, DATA-2 | T27 | Fixture-based mapper tests from her anonymised export; preview counts; conflicts untouched; undo removes only unedited imported rows |
| T42 | Data export | 13.3; DATA-3 | T41 | Test: ZIP contains every file in 13.3 with decrypted contents; expires after first download or 24 h; recent auth required |
| T43 | Account deletion, grace period and purge | 13.4; DATA-4 | T42 | Test: purge removes every row of the user across all tables; cancel during grace; `pending_deletions` honoured after a restore |
| T44 | Admin console | ADM-1, ADM-2, ADM-3; AUTH-8 UI | T43 | Tests: admin role cannot reach any health endpoint or table; invites and session revocation audited; status page fields |
| T45 | Backups, restore drill, alerts and operations status | 14.6, 14.8; NFR-3, NFR-5 | T16 | Restore drill on staging under 4 h with a decrypted record; alerts reach ntfy and email when API is stopped and backup skipped |

### M5 Beta and launch (weeks 9–12)

| ID | Task | Spec | Depends on | Done when (verification) |
| --- | --- | --- | --- | --- |
| T46 | Should items: discreet notifications, TTC and avoid modes, averages, .ics, as-needed doses | SET-5, MOD-3, MOD-4, CSC-5, APT-5, MED-6 | T40 | Each item has tagged tests; avoid-pregnancy banner text matches spec 12.7 |
| T47 | Insights | INS-1, INS-2, INS-3 | T27 | Tests: thresholds (≥5 occurrences, ≥2 cycles); copy has no medical interpretation |
| T48 | Accessibility pass | 5.8; NFR-4 | T46, T47 | axe zero serious/critical on every screen in both themes; VoiceOver walkthrough of J3 and J4 recorded in the task file |
| T49 | Performance pass | NFR-2, TOD-8 | T46, T47 | Lighthouse mobile ≥ 85; JS ≤ 250 KB gzipped; API p95 < 300 ms on staging load script |
| T50 | Security pass | 12; NFR-6 | T46, T47 | ZAP baseline no high findings; headers and CSP verified on staging; dependency and image scans clean; threat model re-reviewed |
| T51 | Device matrix and beta support | 15.2, 15.4; NFR-1, NFR-7 | T48, T49, T50 | Spec 15.2 matrix completed on her iPhone and desktop; beta issues triaged within 48 h |
| T52 | Launch: final Flo import, readiness review, acceptance checklist | 17; 13 | T51 | Every spec 17 box ticked with evidence; `trace.py --gate M5` clean; Zee confirms |

Before writing code for a task, Claude Code creates `docs/plan/tasks/Txx.md` from the template (plan, files, tests, out of scope, evidence).

## 8. Human checkpoints and gate reviews

Claude Code cannot pass a milestone on its own: the ledger refuses to start the next milestone until Ibrahim marks its gate `done`, and only he can.

### 8.1 Gate conditions

| Gate | Automated (from `/gate`) | Human checks (Ibrahim) | Validation with Zee |
| --- | --- | --- | --- |
| GATE-M1 | `make verify-full`; `trace.py --gate M1` clean; all M1 evidence filled | Register, sign in, lock and unlock on staging on his phone; staging origin serves `/api` through the tunnel; VPS has no open web ports | On the production domain: she installs the app on her iPhone, registers a passkey and receives the test push |
| GATE-M2 | As M1 for M2 | J3, J4 and J9 on his phone, offline included | She logs daily in the app beside Flo for at least 5 days |
| GATE-M3 | As above; TV1–TV12 named in the report | Predictions match her logged history; reminders arrive with the app closed; DST tests listed | She reads her Cycle screen and confirms it makes sense to her |
| GATE-M4 | As above; restore drill evidence | J6, J7, J10 on staging; Flo import preview checked against Flo; admin console shows no health data | — |
| GATE-M5 | As above; Lighthouse, ZAP, axe results | Spec section 17 checklist | Beta feedback recorded; she deletes her Flo account |

### 8.2 Other moments that need Ibrahim

| When | What | Why |
| --- | --- | --- |
| First session | Review Claude Code's cross-check and restatement, then say "go" | Catches misreadings before any code |
| Any time | Decide change requests | The spec stays the single source of truth |
| Week 1 | Request Zee's Flo export; buy domain and add to Cloudflare; create VPS, Pages project, tunnel, object storage; generate and store keys | Claude Code cannot do these, and T15 and T41 depend on them |
| Before GATE-M1 | Production domain live and `WEBAUTHN_RP_ID` set | Passkeys are bound to the domain (section 2.2) |
| Weekly | `/drift-check` and a skim of the ledger | Catches slow drift that per-task reviews miss |
| Each pull request (optional) | Skim the task file's Evidence and the reviewer verdicts | Cheap spot-check of the process |

### 8.3 Signing a gate

1. Read `docs/plan/gates/Mx.md` and the traceability matrix next to it.
2. Do every check in its section 4; write findings in section 5.
3. Write Go or No-go in section 6. For No-go, ask Claude Code to add fix tasks via a change request.
4. For Go, edit `docs/plan/PROGRESS.md` yourself: set `GATE-Mx` to `done`, commit `docs(plan): sign off gate Mx`.

## 9. Claude Code operating kit

The kit is a set of files copied into the empty repository before the first session. The scripts and hooks were tested before delivery: the ledger refuses out-of-order work and thin evidence, the trace check catches untagged requirements, the guard blocks edits to the sources of truth, and the stop hook blocks finishing on a failing check.

### 9.1 What enforces what

| Mechanism | File | Enforces |
| --- | --- | --- |
| Standing instructions | `CLAUDE.md` | Sources of truth, the loop, the 10 non-negotiable rules |
| Delivery loop | `.claude/skills/next-task` (`/next-task`) | Section 3, step by step, one task per run |
| Ledger tool | `scripts/ledger.py` | Order, dependencies, one task at a time, evidence before done, gates before the next milestone |
| Traceability | `scripts/trace.py` | Section 6.2 rules, gate matrix |
| Design tokens | `design/tokens.json`, `scripts/build_tokens.py`, `scripts/check_contrast.py` | Section 5.1; all 15 contrast pairs pass in both themes |
| Guard hook | `.claude/hooks/guard.py` (PreToolUse) | Read-only spec, plan, requirements, tasks, tokens, ledger; no secrets; no real Flo data; no `--no-verify`, force-push or hard reset |
| Post-edit hook | `.claude/hooks/post_edit.py` (PostToolUse) | Formats and lints each changed file; flags raw colour values |
| Stop hook | `.claude/hooks/stop_check.py` (Stop) | `make verify-fast` green before finishing; stops looping after 3 attempts |
| Session hook | `.claude/hooks/session_context.py` (SessionStart) | Injects status and the current task so no session works from memory |
| Reviewers | `.claude/agents/*` | Spec conformance, design system, security, test strength |
| Gate | `/gate Mx` | Section 8 report; Claude Code stops for sign-off |
| Change requests | `/change-request`, `docs/changes/` | Section 6.4 |
| Drift | `/drift-check` | Weekly whole-codebase review |
| Verification contract | `Makefile` | Section 6.1 target names; T01 makes them all run |

### 9.2 Session protocol

1. Open Claude Code in the repository root. The session hook shows status and the current task.
2. Run `/next-task`. Claude Code completes one task through the loop and reports.
3. Say "continue with the next task" to do another, or stop there.
4. At a milestone's end Claude Code suggests `/gate Mx`; run it, then sign off as in 8.3.

### 9.3 First-session prompt

Paste this once, after copying the kit into the repository and committing it:

```text
You are the engineer building the Life OS MVP. The specification, implementation plan, task list,
requirements, design tokens and progress ledger in this repository are the contract. Your job is to
implement them exactly, one task at a time, proving each step.

Before writing any code:

1. Read CLAUDE.md in full. Then read docs/plan.md in full and docs/spec.md in full. They are long;
   read every section, not a summary. Also read docs/plan/tasks.json, docs/requirements.json,
   design/tokens.json, docs/adr/*.md and docs/changes/*.md.

2. Cross-check the sources and report, in a table, any contradiction or gap between them
   (spec vs plan vs tasks.json vs requirements.json vs tokens). For each real one, run
   /change-request instead of resolving it yourself. If there are none, say so.

3. Confirm the guard rails work: try to make a harmless edit to docs/spec.md (expect the guard hook
   to block it) and run `python3 scripts/ledger.py summary` and `python3 scripts/ledger.py next`.
   Report what happened.

4. Restate, in no more than 12 bullet points, how you will work: the delivery loop (plan section 3),
   the definition of done (plan 6.3), when you must stop (gates, change requests, blocked tasks), and
   the design-system and privacy rules you must never break.

Then stop and wait for me to say "go". After I say go, run /next-task to start T01 and stop when T01
is done and committed, with the evidence report.
```

Every later session needs only `/next-task`. All prompts, including the gate and change-request ones, are in `KICKOFF_PROMPT.md` in the kit.

## 10. Risks to delivery and how the process catches them

The controls above target the ways AI-assisted builds usually go wrong: quiet drift from the spec, tests that prove nothing, and work that looks finished but is not.

| Risk | Early signal | Control |
| --- | --- | --- |
| Claude Code paraphrases the spec and drifts | Reviewer finds field, path or copy mismatches | Re-read rule in `/next-task`; `spec-reviewer` on every task; weekly `/drift-check` |
| Tests written to pass rather than to prove | Tests that only call code, or were never seen failing | Failing-first evidence in the task file; `test-auditor`; acceptance criteria table in `spec-reviewer` output |
| Hidden scope creep | Diff touches files outside the task's plan | `spec-reviewer` scope check; one task per pull request |
| Design inconsistency across screens | Raw values, one-off components | Token-only lint, post-edit hook, `design-system-reviewer`, visual snapshots in both themes |
| Context loss across sessions | Claude Code refers to decisions it cannot point to | Session hook injects status; task files hold decisions; ledger holds evidence |
| Spec stays wrong because work routes around it | Workarounds in code comments | Guard makes the spec read-only; change requests are the only path |
| The spec export in the repo goes stale | Claude Docs and `docs/spec.md` differ | Version line in both; re-export is part of approving a change request |
| Verification too slow, so it gets skipped | Long `make verify` times | `verify-fast` in the Stop hook; full suite at commit and gates; nothing can be marked done without it |
| External dependencies late (Flo export, domain, VPS) | Week-1 checklist open | Section 8.2; T15 and T41 cannot finish without them, which the ledger makes visible |
| Limited time with a new baby | Tasks stay `in_progress` for weeks | Tasks are small; milestone "should" items slip first; gates never skip |
