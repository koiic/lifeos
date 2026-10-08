# Progress ledger

Single record of where the build is. Claude Code updates only the row of the task it is working on,
and only with evidence (plan section 6.3). Statuses: `todo`, `in_progress`, `blocked`, `done`.
Gate rows are signed off by Ibrahim only.

Spec version: 1 · Plan version: 1

## M1 Foundation (weeks 1–2)

| ID | Task | Owns requirements | Depends on | Status | Commit | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | Repository scaffold, tooling and verify pipeline | — | — | done | e9edd37 | make verify green (exit 0, Postgres 16 via Docker): 124 server tests, coverage 100% + per-module gates, migrations up/down/up clean, api-contract, tokens 30/30, trace 0 errors, gitleaks history+tree clean; pre-commit (ruff, prettier, eslint, gitleaks, commitlint) installed and proven; 4 reviewers CHANGES REQUIRED -> all findings fixed or answered (T01.md) |
| T02 | Server skeleton: config, logging, errors, middleware | — | T01 | done | d0e224f | make verify green (exit 0, Postgres 16): 245 server tests (121 new), coverage 100%, migrations clean, api-contract regenerated (problem+json), trace 0 errors, gitleaks clean; reviewers: design PASS, spec/security/test CHANGES REQUIRED -> all findings fixed or answered (T02.md); migrations-role gap recorded pending CR-003 |
| T03 | Database schema, roles and row-level security | — | T02 | done | e0e9e75 | make verify green (exit 0, Postgres 16): 582 server tests incl. 254 catalog-driven DB tests (RLS on 23 tables, exact grants and policies, owner-owned SECURITY DEFINER lookups), migrations up/down/up clean as lifeos_owner, mutation check caught; 3 reviewers CHANGES REQUIRED -> fixed or answered; CR-003 addendum, CR-010 raised (blocks T07) |
| T04 | Encryption module and encrypted payload types | — | T03 | done | b967778 | make verify green (exit 0, Postgres 16): 652 server tests (70 new), crypto.py 100% lines and branches, format checked independently with AESGCM, tamper/AAD/version/re-wrap tests, 2 mutation checks caught; 3 reviewers CHANGES REQUIRED -> all fixed; CR-011 raised (blocks T06) |
| T05 | Job queue, worker and outbox relay | — | T03 | done | 971e504 | make verify green (exit 0, Postgres 16): 687 server tests (33 new), migrations 0001+0002 up/down/up clean; outbox event -> trigger -> relay (lifeos_jobs) -> per-user job (lifeos_app, app.user_id set); five mutants caught; 3 reviewers CHANGES REQUIRED -> all fixed (admin sees only queue_stats, API queue-only, 7-day pruning, vendored Procrastinate schema) |
| T06 | Invites, passkey registration and sign-in, sessions, recovery codes | — | T04 | done | acfa992 | make verify green (831 server, 31 web); 120 tests added; 4 reviewers fixed/answered; CR-012, CR-013 approved |
| T07 | Password + TOTP fallback, rate limits, auth events | AUTH-7 | T06 | done | ac85653 | make verify green (972 server, 31 web); ~110 tests, AUTH-7 tagged; 25 mutations caught; 4 reviewers fixed/answered; CR-014/015/016 approved |
| T08 | App-lock PIN, re-auth, session management, passkey management, recovery invite | AUTH-8 | T07 | todo | | |
| T09 | Profile, settings, consent and per-user seeding | — | T06 | blocked |  | blocked: CR-004: optimistic concurrency version vs updated_at |
| T10 | Web scaffold: router, query client, generated API client, error boundary | — | T01 | done | d655afd | make verify green (exit 0, Postgres 16): 322 server tests (78 new), web 31 tests (lib/api 100% lines), initial JS 73.4 kB/250 kB, ESLint boundaries tested at any depth, api-contract regenerated, trace 0 errors, gitleaks clean; 4 reviewers CHANGES REQUIRED -> all findings fixed or answered (T10.md); T07 follow-up: key client-error limit on client IP |
| T11 | Design system foundation: tokens, fonts, themes, base components | — | T10 | blocked |  | blocked: CR-005: tokens.css location and typography tokens |
| T12 | Web auth flows: register, sign-in, fallback, recovery, lock screen, sessions | AUTH-1, AUTH-2, AUTH-3, AUTH-4, AUTH-5, AUTH-6 | T08, T11 | todo | | |
| T13 | PWA: manifest, service worker, update prompt, install guide | ONB-1 | T11 | todo | | |
| T14 | Web Push end to end: VAPID, subscriptions, test push, permission card | ONB-3 | T05, T13 | todo | | |
| T15 | Infrastructure: VPS, Docker Compose, Cloudflare Pages, Pages Function proxy, Tunnel, Access, secrets | — | T02, T13 | blocked |  | blocked: CR-006: stale Caddy and infra layout in spec |
| T16 | CI/CD: pipelines, staging deploy, production approval, scans, external-origin check | NFR-6 | T15 | todo | | |
| T17 | App shell: bottom navigation, Today greeting, profile and theme settings | SET-1, SET-2, TOD-1 | T12 | todo | | |
| GATE-M1 | Milestone gate review (plan section 8) | — | all M1 tasks | todo | | |

## M2 Logging (weeks 3–4)

| ID | Task | Owns requirements | Depends on | Status | Commit | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T18 | Daily logs API with validation and last-writer-wins | CHK-2 | T09, T05 | todo | | |
| T19 | Symptom catalogue API with custom symptoms | — | T09 | todo | | |
| T20 | Period start/end endpoints and bleed-episode logic | PER-4, PER-5 | T18 | todo | | |
| T21 | Calendar month endpoint | — | T20 | todo | | |
| T22 | Check-in sheet UI: mood, energy, sleep, symptoms, flow, note, optional fields | CHK-1, CHK-3, CHK-4, PER-2 | T18, T19, T11 | todo | | |
| T23 | Offline layer: IndexedDB outbox, encrypted query cache, sync engine, sync chip | CHK-5, TOD-7 | T22 | todo | | |
| T24 | Health calendar screen, day editing and period start/end controls | CSC-3, PER-1, PER-3 | T21, T23 | todo | | |
| T25 | Today: check-in card and streak | TOD-3, TOD-5 | T22 | todo | | |
| GATE-M2 | Milestone gate review (plan section 8) | — | all M2 tasks | todo | | |

## M3 Predictions (weeks 5–6)

| ID | Task | Owns requirements | Depends on | Status | Commit | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T26 | Cycle engine calendar-1.0 (pure) | CYC-2 | T20 | todo | | |
| T27 | Rebuild job, predictions storage, nightly predict, health profile, exclusions, new-period confirm | CYC-1, CYC-7 | T26, T05 | todo | | |
| T28 | Cycle screen: ring, prediction card, states, history, exclusions | CSC-1, CSC-2, CSC-4, CYC-3, CYC-4, CYC-5, CYC-6 | T27, T11 | todo | | |
| T29 | Setup wizard and health mode settings | MOD-1, MOD-2, ONB-2, SET-4 | T27 | todo | | |
| T30 | Reminder engine: model, horizon job, dispatcher, quiet hours, DST, retries, inbox API | REM-1, REM-2, REM-4, REM-6, REM-7 | T14, T27 | blocked |  | blocked: CR-007: truncated 9.2 cells (event scope, snooze presets) |
| T31 | Check-in, period-due and late-period reminders | — | T30 | blocked |  | blocked: CR-008: late-period timing and cycle copy |
| T32 | Notification settings, snooze and reminder inbox UI | REM-3, REM-5, SET-3 | T30, T17 | todo | | |
| T33 | Today cycle card and complete /today aggregate for cycle | TOD-2 | T27, T25 | todo | | |
| GATE-M3 | Milestone gate review (plan section 8) | — | all M3 tasks | todo | | |

## M4 Feature complete (weeks 7–8)

| ID | Task | Owns requirements | Depends on | Status | Commit | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T34 | People: API and screens | APT-4 | T17 | todo | | |
| T35 | Events API: CRUD, recurrence, occurrence edits, reminder rules, timeline | CAL-2 | T30 | todo | | |
| T36 | Appointment screens and Calendar (month and agenda) | APT-1, APT-2, APT-3, CAL-1 | T35, T34 | todo | | |
| T37 | Medications and doses API: schedules, generation, actions, missed job | MED-2 | T30 | todo | | |
| T38 | Medication screens, dose confirm, notification Taken and snooze actions | MED-1, MED-3, MED-4, MED-5 | T37, T14 | todo | | |
| T39 | Tasks and notes: API and screens | NOTE-1, TSK-1 | T30, T17 | todo | | |
| T40 | Today list and quick-add sheet | TOD-4, TOD-6, TSK-2 | T36, T38, T39 | todo | | |
| T41 | Flo and CSV import with preview and undo | DATA-1, DATA-2 | T27 | blocked |  | blocked: CR-009: CSV template columns |
| T42 | Data export | DATA-3 | T41 | todo | | |
| T43 | Account deletion, grace period and purge | DATA-4 | T42 | todo | | |
| T44 | Admin console | ADM-1, ADM-2, ADM-3 | T43 | todo | | |
| T45 | Backups, restore drill, alerts and operations status | NFR-3, NFR-5 | T16 | todo | | |
| GATE-M4 | Milestone gate review (plan section 8) | — | all M4 tasks | todo | | |

## M5 Beta and launch (weeks 9–12)

| ID | Task | Owns requirements | Depends on | Status | Commit | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T46 | Should items: discreet notifications, TTC and avoid modes, averages, .ics, as-needed doses | APT-5, CSC-5, MED-6, MOD-3, MOD-4, SET-5 | T40 | todo | | |
| T47 | Insights | INS-1, INS-2, INS-3 | T27 | todo | | |
| T48 | Accessibility pass | NFR-4 | T46, T47 | todo | | |
| T49 | Performance pass | NFR-2, TOD-8 | T46, T47 | todo | | |
| T50 | Security pass | — | T46, T47 | todo | | |
| T51 | Device matrix and beta support | NFR-1, NFR-7 | T48, T49, T50 | todo | | |
| T52 | Launch: final Flo import, readiness review, acceptance checklist | — | T51 | todo | | |
| GATE-M5 | Milestone gate review (plan section 8) | — | all M5 tasks | todo | | |
