# Life OS MVP — Product & Technical Specification

Oct 6, 2026 · @ibrahim

## 1. Summary

The Life OS MVP is a private, installable web app (PWA) that replaces Flo for Zee within 12 weeks. It covers cycle tracking with honest predictions, a daily check-in, health appointments, medication reminders and a Today screen, with the shared core that later life areas will reuse.

**The MVP is done when** Zee has installed the app on her phone, imported her Flo history, logged on at least 5 days a week for 4 weeks, received reminders reliably, and deleted her Flo account.

| Item | Decision |
| --- | --- |
| Users | One primary user (Zee); one admin/maintainer (Ibrahim) with no access to her health data |
| Platform | PWA installed to the home screen; mobile first, works on desktop browsers |
| Visual design | Sorbet (light) and Night Garden (dark), one component set; Sticker Book accents for delight moments |
| Backend | Python 3.12, FastAPI modular monolith, PostgreSQL 16 (also the job queue, via Procrastinate) |
| Frontend | React 18 + TypeScript, Vite, vite-plugin-pwa (Workbox), TanStack Query |
| Hosting | Cloudflare Pages for the PWA; one UK/EU VPS (Docker Compose) for API, worker and database, reached only through a Cloudflare Tunnel (ADR-001) |
| Privacy stance | No third-party SDKs; field-level encryption of health data; full export and delete |

This document is the single source of truth for building the MVP. Spec version 1 (6 Oct 2026; includes ADR-001 hybrid hosting and CR-001). Sections 4 and 17 define what must work; sections 6–15 define how.

## 2. Goals, non-goals and success metrics

The MVP succeeds if Zee prefers it to Flo for daily use; everything else is secondary.

**Goals**

1. G1 — Replace Flo: period logging, cycle predictions and symptom tracking at least as easy as Flo.
2. G2 — Own the data: no third parties see her health data; she can export or delete everything at any time.
3. G3 — Reliable reminders: medications, appointments, check-ins and "period due" arrive on her phone on time.
4. G4 — One place for today: a Today screen showing cycle status, check-in and the day's events and tasks.
5. G5 — Foundation: core entities (Person, Event, Task, Reminder, LogEntry, Note) ready for later modules.

**Non-goals for the MVP** (explicitly out of scope; see section 4.18)

- Career, home, finance, socials and entertainment modules.
- AI assistant, chat or generated insights.
- Native iOS/Android apps, wearables, Apple Health or Google Fit sync.
- Two-way Google/Apple calendar sync.
- Multi-user households or sharing her data with anyone, including Ibrahim.
- Contraception or fertility advice of any kind.

**Success metrics** (measured from the app's own database, no analytics SDK)

| Metric | Target | How measured |
| --- | --- | --- |
| Logging adherence | ≥ 5 days/week for 4 consecutive weeks | Distinct `daily_log.date` per ISO week |
| Check-in speed | Median < 30 s from opening to save | Client timestamps sent with the save request (open → save) |
| Reminder reliability | ≥ 98% of reminders delivered within 2 min of `fire_at` | `reminder.sent_at − fire_at` from the worker log |
| Prediction accuracy | Actual start inside the shown range for ≥ 70% of predictions once she has ≥ 3 regular cycles | Compare `cycle_prediction` to the next logged period start |
| Flo exit | History imported and Flo account deleted | Zee confirms |
| Stability | Zero data-loss incidents; ≤ 1 h downtime per month | Uptime monitor and restore drills |

## 3. User journeys

Eleven journeys cover everything Zee does in the MVP; each must work end to end on her phone before launch (section 17).

**J1 — First run and install**

1. Ibrahim sends her an invite link (single-use, expires in 7 days).
2. She opens it in Safari/Chrome, enters her name and email, and creates a passkey (Face ID / fingerprint). Fallback: password + TOTP if passkeys fail.
3. She is shown a 3-step install guide for her platform (iOS: Share → Add to Home Screen) and opens the app from the home screen.
4. Setup wizard (4 screens, each skippable): health mode (standard / postpartum / trying to conceive / avoiding pregnancy); last period start date (or "not yet since birth"); usual cycle and period length (or "not sure"); reminder preferences (check-in time, period-due alert on/off).
5. Enable notifications: one tap on a button (required for iOS), test notification sent immediately.
6. She lands on Today.

**J2 — Import from Flo**

1. She requests her data from Flo (in Flo: Menu → Help → Contact us → request export; choose JSON).
2. In Life OS: Settings → Import → Flo → upload the JSON file.
3. The app shows a preview: number of periods, date range, symptoms found, anything it could not map.
4. She confirms; data is imported, cycles rebuilt, predictions refreshed. Import is reversible for 30 days ("Undo import").

**J3 — Daily check-in (target < 30 s)**

1. Notification at her chosen time: "How are you today?" Tapping opens the check-in sheet directly.
2. She taps a mood, energy level, optionally sleep hours and symptoms, and flow if relevant.
3. Save. The Today card shows a completed state and the streak count.

**J4 — Period starts and ends**

1. From Today or the Cycle screen she taps "Period started" (defaults to today; she can pick another date).
2. Each following day the check-in pre-selects flow; she adjusts or taps "Period ended".
3. If she forgets to tap "Period ended", the period counts as ended at the last flow day once 3 days pass with no flow; if flow runs past 10 days she is asked to confirm (PER-4).
4. Cycles and predictions update within seconds.

**J5 — Knowing what's coming**

1. Cycle screen shows day of cycle, phase, next period range, fertile window (labelled informational) and confidence.
2. Two days before the predicted range starts she gets "Your period may start in about 2 days".
3. If she is more than 7 days past the range end with no period logged, she gets one gentle "Late? Log it when it starts" note; no medical claims.

**J6 — Appointments**

1. She taps + → Appointment: title, date/time, location, linked person (e.g. GP, health visitor), notes.
2. Default reminders: day before at 19:00 and 1 hour before; she can change them.
3. Appointment appears on Today and in the Calendar.

**J7 — Medications and supplements**

1. - → Medication: name, dose, schedule (times per day, days of week, start and optional end date).
2. At each scheduled time she gets a reminder with a "Taken" action; tapping marks it taken.
3. Today shows each dose with a tick; missed doses are shown quietly, without nagging.

**J8 — Night use**

At 03:00 she opens the app to log something: the Night Garden theme is active (follows the system setting, or her manual choice), text is large, nothing flashes.

**J9 — Offline**

On a train with no signal she logs a check-in. It saves locally, Today shows "Will sync", and it syncs automatically when back online.

**J10 — Export and delete**

Settings → Your data → Export: a ZIP with JSON and CSV of everything, built in the background and downloaded in the app (link valid for 24 hours). Delete account: confirm with passkey, typed confirmation, 7-day grace period, then permanent deletion including backups after their retention window.

**J11 — New phone or lost phone**

She signs in on the new device with her synced passkey (iCloud Keychain / Google Password Manager) or a recovery code from setup. Lost phone: Ibrahim can revoke all sessions from the admin console without seeing her data.

## 4. Functional requirements

Every requirement has an ID used in tickets, tests and the acceptance checklist; "must" items block launch, "should" items can slip to weeks 9–12.

### 4.1 Accounts and sign-in

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| AUTH-1 | Must: registration by invite only | Invite tokens are single-use, expire after 7 days, stored hashed; `/register` without a valid token returns 403 |
| AUTH-2 | Must: passkey (WebAuthn) registration and sign-in | Works in iOS Safari 16.4+ and Chrome Android; user verification required |
| AUTH-3 | Must: fallback password + TOTP | Argon2id password hash; TOTP RFC 6238, 30 s, ±1 step |
| AUTH-4 | Must: 10 single-use recovery codes shown once at setup | Stored hashed; each works once; regenerating invalidates old codes |
| AUTH-5 | Must: sessions | HttpOnly, Secure, SameSite=Lax cookie; 30-day sliding expiry for installed PWA; list and revoke sessions in Settings |
| AUTH-6 | Must: app lock | After 5 min in background the app shows a lock screen; unlock with passkey (user verification) or a 6-digit PIN |
| AUTH-7 | Must: rate limiting | 5 failed sign-ins per 15 min per account and per IP, then 15-min lockout; all attempts logged |

**AUTH-8 — Must: account recovery when every sign-in method is lost.** The admin issues a recovery invite (single-use, 24 h) that lets her register a new passkey on her existing account. Issuing it revokes all sessions, pushes a notice to her registered devices, and is audited. This is the operator access described in section 12.1, made visible to her.

### 4.2 Onboarding and settings

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| ONB-1 | Must: install guide | Detects `display-mode: standalone`; if not installed shows platform-specific steps; dismissible |
| ONB-2 | Must: setup wizard (J1 step 4) | Each step skippable; values saved to `user_settings` and `health_mode`; wizard can be rerun from Settings |
| ONB-3 | Must: notification opt-in from a button | Permission requested only on tap; test push delivered; denied state explained with steps to re-enable |
| SET-1 | Must: profile | Display name, timezone (auto-detected, editable), week start (Mon default), units for temperature (°C default) |
| SET-2 | Must: theme | Light (Sorbet), Dark (Night Garden), System (default) |
| SET-3 | Must: notification preferences | Toggle per type: check-in, period due, late period, medication, appointment; quiet hours (default 22:00–07:00, appointment and medication reminders still fire) |
| SET-4 | Must: health mode switch | Changing mode records `started_on`; postpartum excludes earlier cycles (section 8) |
| SET-5 | Should: discreet notifications | Option to replace cycle wording with neutral text ("Time to check in") on the lock screen |

### 4.3 Today screen

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| TOD-1 | Must: greeting with date and time-aware salutation | Morning/afternoon/evening/night by local time |
| TOD-2 | Must: cycle card | Shows cycle day, phase, next-period text ("Period in about 5 days" / "Period may start today" / "Day 2 of your period" / postpartum text) and range; tapping opens Cycle |
| TOD-3 | Must: check-in card | Shows mood buttons if not done today; completed state with summary and edit link if done |
| TOD-4 | Must: today list | Events, medication doses and tasks due today sorted by time; untimed items last; tap to open; tick to complete |
| TOD-5 | Must: streak | Consecutive days with a `daily_log`; shown as a Sticker Book badge from 3 days |
| TOD-6 | Must: quick add | + button opens sheet: Period started/ended, Check-in, Appointment, Medication, Task, Note |
| TOD-7 | Must: sync status | Pending offline changes shown as "Will sync" chip |
| TOD-8 | Must: loads in < 1.5 s on a mid-range phone on 4G (cached shell < 0.5 s) | Lighthouse mobile run and real-device check |

### 4.4 Daily check-in

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| CHK-1 | Must: one sheet, max one scroll | Mood (5-point: Bright, Good, Okay, Tired, Low), energy (1–5), sleep hours (0–14 in 0.5 steps, optional), symptoms (multi-select chips), flow (None/Spotting/Light/Medium/Heavy), note (optional, 2,000 chars) |
| CHK-2 | Must: one log per day, editable | Upsert on (user, date); editing any past day allowed; future dates rejected |
| CHK-3 | Must: custom symptoms | Add, rename, archive; archived symptoms remain on historical logs |
| CHK-4 | Must: optional fields hidden by default | Basal temperature, discharge, sex/intimacy (with protected flag) appear only if enabled in Settings |
| CHK-5 | Must: works offline | Saved to IndexedDB queue; synced on reconnect (section 11) |

### 4.5 Period logging

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| PER-1 | Must: start and end a period in one tap each | "Period started" `sets flow Medium (editable) on that date's daily log, creating the log if needed` |
| PER-2 | Must: log flow per day | Flow `is a field of the daily log; setting None clears it; every change emits daily_log.flow_changed` |
| PER-3 | Must: edit history | Calendar month view: tap any day to add/edit/remove flow; changes trigger cycle rebuild |
| PER-4 | Must: auto-close | Open period with no flow for 3 consecutive days is treated as ended at the last flow day; if > 10 days of flow, prompt to confirm |
| PER-5 | Must: spotting does not start a cycle | Spotting-only days are stored but never begin a new cycle (section 8) |

### 4.6 Cycle engine and predictions

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| CYC-1 | Must: cycles derived from period days | Rebuild after every period-day change completes in < 2 s; idempotent |
| CYC-2 | Must: next period prediction as a range | Mean ± max(1, SD) days, using up to 6 included cycles; never a single day only |
| CYC-3 | Must: ovulation estimate and fertile window | Labelled "estimate, not contraception" wherever shown |
| CYC-4 | Must: confidence level | High / Medium / Low per section 8 rules; Low shows "Predictions get better as you log" |
| CYC-5 | Must: exclusions | She can exclude a cycle (illness, travel, medication); excluded cycles are shown but not used |
| CYC-6 | Must: irregularity note | If included cycle lengths vary by > 7 days, show a neutral note; if 3 cycles in a row are missed (> 90 days), show the NHS guidance link |
| CYC-7 | Must: prediction history | Each prediction stored with `algorithm_version` for accuracy measurement |

### 4.7 Health modes

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| MOD-1 | Must: standard mode | All predictions shown |
| MOD-2 | Must: postpartum mode | Predictions hidden until 2 complete cycles after mode start; Today shows "Waiting for your cycle to return"; logging works normally |
| MOD-3 | Should: trying-to-conceive mode | Fertile window emphasised on Cycle screen; still labelled as estimate |
| MOD-4 | Should: avoiding-pregnancy mode | Fertile window shown with an explicit banner that the app is not a contraceptive and to use a method she trusts |

### 4.8 Cycle screen and history

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| CSC-1 | Must: ring view | Period arc, fertile window arc, today marker, cycle day and phase (as in the Sorbet mock-up) |
| CSC-2 | Must: prediction card | Next period range, confidence, "based on N cycles" |
| CSC-3 | Must: month calendar | Period days, predicted days (dashed), fertile window (tint), logged-check-in dots; swipe between months |
| CSC-4 | Must: cycle history list | Each cycle: start date, length, period length, included/excluded toggle |
| CSC-5 | Should: averages | Average cycle and period length with range, from included cycles |

### 4.9 Appointments and people

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| APT-1 | Must: create, edit, delete appointments | Title (required), start, end (default +1 h), all-day flag, location, notes, linked person, module = health |
| APT-2 | Must: default reminders | Day before at 19:00 and 1 h before; editable per appointment; global defaults in Settings |
| APT-3 | Must: recurring appointments | RRULE: daily, weekly, monthly, custom interval; edit "this one" or "all future" |
| APT-4 | Must: people | Name (required), relationship, phone, email, address, notes; tap phone to call |
| APT-5 | Should: add to device calendar | Download `.ics` for a single appointment |

### 4.10 Medications and supplements

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| MED-1 | Must: create medication | Name, dose text (e.g. "1 tablet, 10 µg"), times of day (1–6), days of week, start date, optional end date, notes |
| MED-2 | Must: scheduled doses | Dose instances generated 14 days ahead by the worker; editing a schedule regenerates future untaken doses only |
| MED-3 | Must: reminder with Taken action | Notification action "Taken" marks the dose without opening the app (Android); on iOS tapping opens a one-tap confirm screen |
| MED-4 | Must: dose states | Due, Taken (with time), Skipped, Missed (auto after 6 h); she can correct any state |
| MED-5 | Must: pause and archive | Paused medications generate no doses; archived ones keep history |
| MED-6 | Should: as-needed medication | No schedule; "Log a dose" button records time taken |

### 4.11 Tasks and notes (core, minimal)

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| TSK-1 | Must: tasks | Title, optional due date/time, optional reminder, status (open/done), recurrence (same options as APT-3) |
| TSK-2 | Must: tasks on Today | Due today or overdue; overdue shown once in a quiet "Earlier" group |
| NOTE-1 | Must: notes | Title optional, body (encrypted, 20,000 chars), tags, optional link to a person or appointment |

### 4.12 Reminders and notifications

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| REM-1 | Must: single reminder model | Every nudge is a `reminder` row linked to its source; fire times stored in UTC, computed from her timezone |
| REM-2 | Must: delivery within 2 min of fire time | Dispatcher runs every minute; push sent with TTL 6 h and urgency high for medication/appointment |
| REM-3 | Must: snooze | 15 min, 1 h, tonight (19:00), tomorrow morning (08:00) |
| REM-4 | Must: multiple devices | Push to every active subscription; expired subscriptions (HTTP 404/410) removed |
| REM-5 | Must: in-app inbox | Last 30 days of sent reminders listed, so nothing is lost if a push is missed |
| REM-6 | Must: quiet hours and discreet mode respected | See SET-3, SET-5 |
| REM-7 | Must: DST and timezone changes | Recurring reminders keep local wall-clock time across BST/GMT changes and travel |

### 4.13 Calendar view

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| CAL-1 | Must: month and agenda views | Month grid with dots (period, appointment, medication); agenda list for the selected day |
| CAL-2 | Must: unified timeline | Events, doses, tasks and period days from the `timeline` endpoint |

### 4.14 Insights (minimal)

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| INS-1 | Should: symptoms by phase | For each symptom logged ≥ 5 times over ≥ 2 cycles: % of occurrences per phase; shown only when ≥ 2 complete cycles exist |
| INS-2 | Should: mood and energy by cycle day | Average per cycle day over included cycles, as a simple line chart |
| INS-3 | Must: no medical interpretation | Insights describe her data only; no diagnoses or advice |

### 4.15 Data ownership

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| DATA-1 | Must: Flo import | Section 13; preview before commit; undo within 30 days |
| DATA-2 | Must: CSV import fallback | Template with `date,flow,symptoms,mood,note`, for other apps or hand-kept records |
| DATA-3 | Must: full export | ZIP of JSON (complete) and CSV (per table), decrypted, generated within 2 min |
| DATA-4 | Must: account deletion | Section 13: passkey confirmation, 7-day grace, hard delete, backups expire within 35 days |

### 4.16 Admin console (Ibrahim)

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| ADM-1 | Must: separate admin role | Admin cannot read any user's health tables, notes or documents; enforced in the API layer and by database roles |
| ADM-2 | Must: invites | Create and revoke invite links |
| ADM-3 | Must: operations | View system health, job queue depth, failed pushes (counts only), backup status; revoke all sessions for a user |

### 4.17 Non-functional requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-1 | Browser support | iOS Safari 16.4+ (installed PWA), Chrome/Edge Android last 2 versions, desktop Chrome, Safari, Firefox last 2 versions |
| NFR-2 | Performance | API p95 < 300 ms; Today first render from cache < 0.5 s; JS bundle < 250 KB gzipped initial |
| NFR-3 | Availability | 99.5% monthly; offline logging covers outages |
| NFR-4 | Accessibility | WCAG 2.2 AA: contrast, 44 px targets, screen-reader labels, reduced-motion support, text scales to 200% |
| NFR-5 | Durability | RPO 24 h (nightly backup) plus WAL archiving to reach RPO 5 min; RTO 4 h |
| NFR-6 | Privacy | No third-party scripts, fonts self-hosted, no analytics SDKs; CSP blocks external origins |
| NFR-7 | Localisation | English (UK) copy; dates as "6 Oct", 24-hour time by default, configurable |

### 4.18 Out of scope for the MVP

Career, home, finance, socials and entertainment modules; AI assistant; documents and file storage; goals; partner or family access; two-way calendar sync; wearables and health-platform sync; native apps; multi-language support.

## 5. UX and UI

One layout and one component library, themed two ways: Sorbet by day, Night Garden by night, with Sticker Book touches reserved for small celebrations. The canvas *Life OS UI Directions* is the visual reference.

### 5.1 Navigation

Bottom bar, five slots, always visible except in sheets and the lock screen:

1. **Today** — home.
2. **Health** — hub with tabs: Cycle (ring), Calendar (month), History, Insights, Medications.
3. **+** — quick-add sheet (TOD-6).
4. **Calendar** — month and agenda of everything.
5. **More** — Tasks, Notes, People, Reminder inbox, Settings.

Deep links: `/today`, `/checkin?date=`, `/health/cycle`, `/health/calendar`, `/health/history`, `/health/insights`, `/health/meds`, `/meds/doses/:id`, `/calendar`, `/appointments/:id`, `/people/:id`, `/tasks`, `/notes/:id`, `/inbox`, `/settings/*`, `/import/flo`. Every notification opens a deep link.

### 5.2 Screen inventory

| Screen | Route | Key contents | Requirements |
| --- | --- | --- | --- |
| Register (invite) | `/register?token=` | Name, email, create passkey; fallback password + TOTP | AUTH-1–4 |
| Sign in | `/signin` | Passkey button; "Use password"; "Use recovery code" | AUTH-2–4 |
| Lock screen | overlay | Unlock with passkey or PIN | AUTH-6 |
| Install guide | `/install` | iOS/Android steps with illustrations | ONB-1 |
| Setup wizard | `/setup/1–4` | Mode, last period, cycle length, reminders | ONB-2 |
| Notifications opt-in | `/setup/notifications` | Enable button, test push | ONB-3 |
| Today | `/today` | Greeting, cycle card, check-in card, today list, streak | TOD-1–7 |
| Check-in sheet | `/checkin` | Mood, energy, sleep, symptoms, flow, note | CHK-1–5 |
| Quick add sheet | overlay | Six actions | TOD-6 |
| Cycle | `/health/cycle` | Ring, legend, prediction card, flow and symptom quick log | CSC-1–2 |
| Cycle calendar | `/health/calendar` | Month grid, tap a day to edit | CSC-3, PER-3 |
| Cycle history | `/health/history` | Cycles list, include/exclude, averages | CSC-4–5, CYC-5 |
| Insights | `/health/insights` | Symptoms by phase, mood by cycle day | INS-1–3 |
| Medications | `/health/meds` | Active list, today's doses, add/edit/pause | MED-1–6 |
| Dose confirm | `/meds/doses/:id` | Taken / Skip / Snooze | MED-3–4 |
| Calendar | `/calendar` | Month + agenda | CAL-1–2 |
| Appointment form/detail | `/appointments/new`, `/:id` | Fields, reminders, recurrence, .ics | APT-1–5 |
| People | `/people`, `/:id` | List, detail, linked appointments | APT-4 |
| Tasks | `/tasks` | Open/done lists, form | TSK-1–2 |
| Notes | `/notes`, `/:id` | List, editor, tags | NOTE-1 |
| Reminder inbox | `/inbox` | Last 30 days | REM-5 |
| Settings | `/settings/*` | Profile, theme, notifications, health mode, symptoms, optional fields, security and sessions, your data, about | SET-1–5 |
| Import / export / delete | `/settings/data/*` | Flo import preview, CSV import, export, delete | DATA-1–4 |
| Admin console | `/admin` (admin role only) | Invites, health, queues, sessions | ADM-1–3 |

Every list screen has an empty state with one clear action; every form has inline validation; every network action has loading, success and error states with a retry.

### 5.3 Design tokens

Tokens live in `tokens.css` as CSS custom properties; theme is set by `data-theme` on `<html>`.

| Token | Sorbet (light) | Night Garden (dark) | Use |
| --- | --- | --- | --- |
| `--bg` | #FFF4F1 | #14122B | Page background |
| `--surface` | #FFFFFF | #221F45 | Cards, sheets |
| `--surface-tint` | #FFD9CF | #2E2A57 | Tracks, dividers, decorative blobs |
| `--ink` | #2B1B2E | #F3EEFF | Primary text, icons |
| `--ink-muted` | #6E5468 | #B7AFD9 | Secondary text |
| `--accent` | #FF6B5A | #FFB4A2 | Period, primary card, active nav |
| `--accent-ink` | #2B1B2E | #14122B | Text on accent |
| `--fertile` | #9EE6C8 | #7DE3C8 | Fertile window, positive states |
| `--sun` | #FFC94D | #FFD97A | Add button, highlights, streak |
| `--lilac` | #D9CCFF | #9D8CFF | Appointments, selected chips |
| `--butter` | #FFE08A | #4A4578 | Medications, info badges |
| `--danger` | #B3261E | #FF8A80 | Destructive actions, errors |
| `--border-strong` | #2B1B2E | #7A72B4 | Sticker outlines, chip borders (≥ 3:1 non-text contrast; Night value changed by CR-001) |

Spacing scale 4, 8, 12, 16, 20, 24, 32, 40. Radii: chip 999, button 20, card 24–32, sheet 32 top corners. Shadow: none, except Sticker accents (`3px 3px 0 var(--border-strong)`).

All text/background pairs must pass 4.5:1 (3:1 at ≥ 24 px); this is checked in CI (section 15). Ink on coral and ink on every pastel already pass; white text on coral does not and is not allowed.

### 5.4 Typography

| Role | Sorbet | Night Garden | Size / weight |
| --- | --- | --- | --- |
| Display (H1) | Bricolage Grotesque | Fraunces (SOFT 100) | 34–36 / 800 (Fraunces 600) |
| H2 | Bricolage Grotesque | Fraunces | 20 / 800 (600) |
| Body | DM Sans | DM Sans | 16 / 400–500 |
| Label, chips | DM Sans | DM Sans | 13–14 / 700 |
| Numerals (cycle day) | Bricolage Grotesque | Fraunces | 64 / 800 |

Fonts are self-hosted (WOFF2 via Fontsource packages, OFL licence), subset to Latin, `font-display: swap`. Text sizes use `rem` so the iOS text-size setting scales them.

### 5.5 Components

Build these once in `src/ui/`, each with a Storybook-style preview page (or Ladle) and both themes:

Button (primary, secondary, ghost, danger, icon), Chip (toggle, choice), MoodPicker, FlowPicker, SymptomChips, Slider (energy), Stepper (sleep), CycleRing (SVG, props: cycleLength, periodDays, fertileStart, fertileEnd, today), MiniRing (Today card), MonthCalendar, AgendaList, TimelineItem (event/dose/task variants), Card, Sheet (bottom sheet with drag handle and focus trap), Dialog, Toast, BottomNav, FAB, TextField, TextArea, DateTimePicker (native inputs styled), Select, Switch, EmptyState, ErrorState, Skeleton, StreakBadge (Sticker style), SyncChip, LockScreen, InstallGuide, NotificationPermissionCard.

### 5.6 Motion and delight

- Ring fills with a 600 ms ease-out when a log is saved; the cycle-day number counts up.
- Saving a check-in drops a Sticker Book "sticker" (scale 0.6 → 1.05 → 1, slight rotation) on the card.
- Streak badge wiggles on day 3, 7, 14, 30.
- All motion is disabled under `prefers-reduced-motion`; nothing autoplays or loops.

### 5.7 Copy and tone

Warm, short, never medical. Use "about" and ranges for predictions ("Period in about 5 days"). Never "you are fertile"; use "estimated fertile window". Never blame ("You missed 3 days"); invite instead ("Want to catch up on this week?"). All copy lives in `src/copy/en-GB.ts`.

### 5.8 Accessibility

Real buttons and links only; visible focus ring (2 px `--ink` outline, 2 px offset); every icon-only control has `aria-label`; the ring has an `aria-label` sentence ("Day 23 of about 29, luteal phase, next period expected 11 to 13 October"); colour is never the only signal (period days also carry a droplet icon, predicted days a dashed outline); sheets trap focus and return it on close; minimum target 44 × 44 px.

## 6. System architecture

Cloudflare serves the app and forwards /api to one server running four processes: cloudflared, the FastAPI app, a worker and PostgreSQL (ADR-001). PostgreSQL also holds the job queue, so there is one stateful thing to back up.

_[Diagram, as text] Zee's phone (React PWA, service worker, IndexedDB offline queue) → Cloudflare (Pages serves the app files; /api forwarded via Pages Function and Tunnel to the VPS) → FastAPI app (auth, core, health, notify, data, admin) → PostgreSQL 16 (data + job queue, health fields encrypted) → encrypted off-site backups (nightly + WAL). The worker (reminders every minute; rebuild, import, export) reads and writes PostgreSQL and sends Web Push through the push services (Apple, Google, Mozilla), which deliver to the phone._

The phone talks only to Cloudflare over HTTPS; the server has no open web ports. The worker sends reminders through the browser push services, which wake the phone even when the app is closed.

### 6.1 Technology choices

| Layer | Choice | Why |
| --- | --- | --- |
| Language (server) | Python 3.12 | His strongest language |
| Web framework | FastAPI + Pydantic v2 | Typed request/response models, OpenAPI generated for free |
| ORM and migrations | SQLAlchemy 2.0 (async) + asyncpg, Alembic | Mature, explicit, works with typed tables and JSONB |
| Database | PostgreSQL 16 | JSONB, `tstzrange`, row-level security, `SKIP LOCKED` |
| Jobs and schedules | Procrastinate (Postgres task queue with periodic tasks) | No Redis to run or back up; transactional enqueue |
| Auth | `webauthn` (py\_webauthn), `argon2-cffi`, `pyotp` | Passkeys plus password/TOTP fallback |
| Crypto | `cryptography` (AES-256-GCM, HKDF) | Field-level envelope encryption (section 12) |
| Push | `pywebpush` with VAPID keys | Standard Web Push for iOS, Android, desktop |
| Recurrence | `python-dateutil` rrule + `zoneinfo` | RFC 5545 recurrence and DST-correct local times |
| Logging | `structlog` JSON logs, no health payloads | Self-hosted, privacy-safe |
| Client | React 18 + TypeScript, Vite | Fast builds, large ecosystem |
| PWA | `vite-plugin-pwa` (Workbox, injectManifest) | Precaching, offline shell, custom push handler |
| Server state | TanStack Query v5 | Caching, retries, optimistic updates |
| Local state | Zustand | Small UI state (theme, lock, sheets) |
| Offline store | `idb` (IndexedDB) | Mutation queue and cached reads |
| Forms and validation | React Hook Form + Zod | Same schemas validate forms and API payloads |
| Dates | `date-fns` + `date-fns-tz` | Local-time display, UTC storage |
| Passkeys (client) | `@simplewebauthn/browser` | Handles WebAuthn ceremonies |
| Routing | React Router 6 | Deep links from notifications |
| Proxy | Cloudflare Pages + Pages Function proxy + Cloudflare Tunnel | TLS and static hosting at the edge; no open ports on the VPS (ADR-001) |

### 6.2 Server modules

One codebase, one deployable, strict module boundaries enforced by import-linter in CI:

- `auth` — invites, passkeys, passwords, TOTP, recovery codes, sessions, app-lock PIN.
- `core` — people, events, tasks, notes, tags, reminders, timeline.
- `health` — period days, daily logs, symptoms, cycles, predictions, health modes, medications, doses, insights.
- `notify` — push subscriptions, reminder dispatch, inbox.
- `data` — Flo/CSV import, export, account deletion.
- `admin` — invites, operational status, session revocation.
- `platform` — config, database, crypto, logging, outbox, job registration.

Modules communicate through service interfaces and an `outbox_event` table (e.g. `period_day.changed` → health rebuild job → `prediction.updated` → notify reschedules period reminders), never by importing each other's repositories.

## 7. Data model

Twenty-eight tables in PostgreSQL 16 (25 in 7.2, 3 in 7.5). Every health value, including period flow, lives inside an encrypted `payload_enc` column; only the columns the server must sort or schedule by (dates, fire times, statuses) are plaintext.

### 7.1 Conventions

- Primary keys: UUID v7 generated in Python (`uuid6` package), time-ordered for index locality.
- Every user-owned table has `user_id`, `created_at`, `updated_at` (trigger-maintained) and, where users can delete, `deleted_at` (soft delete; purged after 30 days by a job).
- `payload_enc` is `bytea` holding `version(1 byte) ‖ nonce(12) ‖ ciphertext ‖ tag(16)` of a UTF-8 JSON object, encrypted with AES-256-GCM under the user's data key; AAD = `table:column:row_id:user_id` (section 12). Each payload has a Pydantic schema with a `v` field for evolution.
- Row-level security on every user table: `USING (user_id = current_setting('app.user_id')::uuid)`; the app runs `SET LOCAL app.user_id` per transaction.
- Times are `timestamptz` in UTC; wall-clock schedules store a local time plus the IANA timezone.
- Period days are not a separate table: a day is a period day when its daily log's `flow` is light, medium or heavy. This keeps period dates out of plaintext.

### 7.2 Schema (DDL)

```sql
CREATE EXTENSION IF NOT EXISTS citext;

-- ---------- auth ----------
CREATE TABLE users (
  id               uuid PRIMARY KEY,
  email            citext NOT NULL UNIQUE,
  display_name     text   NOT NULL,
  role             text   NOT NULL DEFAULT 'user' CHECK (role IN ('user','admin')),
  timezone         text   NOT NULL DEFAULT 'Europe/London',
  locale           text   NOT NULL DEFAULT 'en-GB',
  dek_wrapped      bytea  NOT NULL,            -- user data key wrapped by the master key
  kek_version      int    NOT NULL DEFAULT 1,
  deletion_requested_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE user_settings (
  user_id          uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  theme            text NOT NULL DEFAULT 'system' CHECK (theme IN ('system','light','dark')),
  week_start       smallint NOT NULL DEFAULT 1,      -- 1 = Monday
  time_format      text NOT NULL DEFAULT '24h',
  temp_unit        text NOT NULL DEFAULT 'C',
  checkin_time     time NOT NULL DEFAULT '20:00',
  quiet_start      time NOT NULL DEFAULT '22:00',
  quiet_end        time NOT NULL DEFAULT '07:00',
  notif_prefs      jsonb NOT NULL DEFAULT '{"checkin":true,"period_due":true,"late_period":true,"medication":true,"appointment":true,"task":true}',
  discreet_notifications boolean NOT NULL DEFAULT false,
  optional_fields  jsonb NOT NULL DEFAULT '{"bbt":false,"discharge":false,"intimacy":false}',
  app_lock_pin_hash text,                           -- argon2id
  app_lock_timeout_s int NOT NULL DEFAULT 300,
  appointment_reminder_defaults jsonb NOT NULL DEFAULT '[{"type":"day_before_at","time":"19:00"},{"type":"minutes_before","minutes":60}]',
  onboarding_completed_at timestamptz,
  health_consent_at timestamptz,                    -- explicit consent screen (12.6)
  health_consent_version text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE invites (
  id uuid PRIMARY KEY,
  token_hash bytea NOT NULL UNIQUE,                 -- sha256 of a 32-byte random token
  email citext,
  created_by uuid NOT NULL REFERENCES users(id),
  expires_at timestamptz NOT NULL,
  used_at timestamptz, used_by uuid REFERENCES users(id),
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE webauthn_credentials (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  credential_id bytea NOT NULL UNIQUE,
  public_key bytea NOT NULL,
  sign_count bigint NOT NULL DEFAULT 0,
  transports text[] NOT NULL DEFAULT '{}',
  aaguid uuid,
  backup_eligible boolean NOT NULL DEFAULT false,
  backed_up boolean NOT NULL DEFAULT false,
  nickname text NOT NULL DEFAULT 'Passkey',
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz
);

CREATE TABLE password_credentials (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  password_hash text NOT NULL,                      -- argon2id, m=64MiB t=3 p=4
  totp_secret_enc bytea,
  totp_enabled boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recovery_codes (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash text NOT NULL,                          -- argon2id
  used_at timestamptz
);

CREATE TABLE sessions (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash bytea NOT NULL UNIQUE,                 -- sha256 of the cookie token
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  device_label text,                                -- parsed from user agent, e.g. 'iPhone Safari'
  ip_hash bytea                                     -- HMAC of IP, for rate limiting and audit
);
CREATE INDEX ON sessions (user_id) WHERE revoked_at IS NULL;

CREATE TABLE auth_events (
  id bigserial PRIMARY KEY,
  user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  kind text NOT NULL,          -- signin_passkey, signin_password, totp, recovery, register, revoke, pin_unlock
  success boolean NOT NULL,
  ip_hash bytea,
  at timestamptz NOT NULL DEFAULT now()
);

-- ---------- core ----------
CREATE TABLE people (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  payload_enc bytea NOT NULL,  -- {name, relationship, phone, email, address, birthday, notes}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);

CREATE TABLE events (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  module text NOT NULL DEFAULT 'health',
  kind text NOT NULL DEFAULT 'appointment',
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  all_day boolean NOT NULL DEFAULT false,
  timezone text NOT NULL,                           -- wall-clock zone for recurrence
  rrule text,                                       -- RFC 5545 RRULE, NULL = single
  rrule_until timestamptz,
  series_id uuid REFERENCES events(id),             -- set on an edited occurrence
  original_start timestamptz,                       -- which occurrence it overrides
  is_cancelled_occurrence boolean NOT NULL DEFAULT false,
  person_id uuid REFERENCES people(id),
  reminder_rules jsonb NOT NULL,                    -- copied from user defaults, e.g. [{"type":"day_before_at","time":"19:00"},{"type":"minutes_before","minutes":60}]
  payload_enc bytea NOT NULL,                       -- {title, location, notes}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz,
  CHECK (ends_at >= starts_at)
);
CREATE INDEX ON events (user_id, starts_at) WHERE deleted_at IS NULL;

CREATE TABLE tasks (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  due_at timestamptz,
  due_all_day boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','done')),
  completed_at timestamptz,
  rrule text,
  timezone text NOT NULL,
  remind_at timestamptz,
  payload_enc bytea NOT NULL,                       -- {title, notes}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);
CREATE INDEX ON tasks (user_id, status, due_at) WHERE deleted_at IS NULL;

CREATE TABLE notes (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  linked_type text CHECK (linked_type IN ('person','event')),
  linked_id uuid,
  payload_enc bytea NOT NULL,                       -- {title, body, tags[]}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);

-- ---------- health ----------
CREATE TABLE health_profile (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  payload_enc bytea NOT NULL,
  -- {mode: standard|postpartum|ttc|avoid, mode_started_on, usual_cycle_length, usual_period_length,
  --  last_period_hint, excluded_cycle_starts: [date], exclusion_reasons: {date: text}, forced_period_starts: [date]}
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE symptoms (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  system_key text,                                  -- e.g. 'cramps' for seeded ones, NULL for custom
  category text NOT NULL CHECK (category IN ('pain','digestion','skin','emotional','energy','other')),
  sort_order int NOT NULL DEFAULT 0,
  payload_enc bytea NOT NULL,                       -- {name}
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, system_key)
);

CREATE TABLE daily_logs (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date date NOT NULL,
  payload_enc bytea NOT NULL,
  -- {v:1, mood:1-5|null, energy:1-5|null, sleep_hours:number|null, symptom_ids:[uuid],
  --  flow: none|spotting|light|medium|heavy, discharge:str|null, bbt_c:number|null,
  --  intimacy:{logged:bool, protected:bool|null}|null, note:str|null, checkin_ms:int|null}
  import_id uuid,                                   -- set when created by an import (undo)
  client_updated_at timestamptz NOT NULL,           -- last-writer-wins for offline sync
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, date)
);

CREATE TABLE cycles (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  seq int NOT NULL,                                 -- 1 = oldest
  payload_enc bytea NOT NULL,
  -- {start_date, end_date|null, length_days|null, period_length_days, is_complete, excluded, exclusion_reason, postpartum}
  computed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, seq)
);

CREATE TABLE cycle_predictions (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  algorithm_version text NOT NULL,                  -- e.g. 'calendar-1.0'
  payload_enc bytea NOT NULL,
  -- {for_cycle_start, predicted_start, range_low, range_high, ovulation_est, fertile_start, fertile_end,
  --  confidence: high|medium|low|none, n_cycles, mean_len, sd_len, mean_period_len, suppressed_reason|null}
  created_at timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz
);
CREATE INDEX ON cycle_predictions (user_id, created_at DESC);

CREATE TABLE medications (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','archived')),
  as_needed boolean NOT NULL DEFAULT false,
  times_local time[] NOT NULL DEFAULT '{}',         -- e.g. {08:00,20:00}
  days_of_week smallint[] NOT NULL DEFAULT '{1,2,3,4,5,6,7}',
  start_date date NOT NULL,
  end_date date,
  timezone text NOT NULL,
  payload_enc bytea NOT NULL,                       -- {name, dose, notes}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);

CREATE TABLE medication_doses (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  medication_id uuid NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
  scheduled_at timestamptz,                         -- NULL for as-needed doses
  status text NOT NULL DEFAULT 'due' CHECK (status IN ('due','taken','skipped','missed')),
  taken_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (medication_id, scheduled_at)
);
CREATE INDEX ON medication_doses (user_id, scheduled_at);

-- ---------- notify ----------
CREATE TABLE reminders (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN ('checkin','period_due','late_period','medication','appointment','task','test')),
  source_type text,                                 -- event, task, medication_dose, prediction
  source_id uuid,
  fire_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','sending','sent','snoozed','done','cancelled','failed')),
  attempts smallint NOT NULL DEFAULT 0,
  sent_at timestamptz,
  dedupe_key text NOT NULL,                         -- e.g. 'dose:<id>', 'event:<id>:<occurrence>:<rule>'
  payload_enc bytea NOT NULL,                       -- {title, body, url, actions[]}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, dedupe_key)
);
CREATE INDEX reminders_due_idx ON reminders (fire_at) WHERE status IN ('scheduled','snoozed');

CREATE TABLE push_subscriptions (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id uuid REFERENCES sessions(id) ON DELETE SET NULL,
  endpoint text NOT NULL UNIQUE,
  p256dh text NOT NULL,
  auth text NOT NULL,
  device_label text,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_success_at timestamptz,
  failure_count smallint NOT NULL DEFAULT 0,
  disabled_at timestamptz
);

-- ---------- data / platform ----------
CREATE TABLE imports (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source text NOT NULL CHECK (source IN ('flo_json','csv')),
  status text NOT NULL CHECK (status IN ('uploaded','parsed','failed','committed','undone')),
  file_enc bytea,                                   -- uploaded file, deleted 30 days after commit
  preview_enc bytea,                                -- parsed rows awaiting confirmation
  summary jsonb,                                    -- counts only: {days, periods, symptoms, skipped, conflicts, unmapped_keys}
  error text,
  created_at timestamptz NOT NULL DEFAULT now(), committed_at timestamptz, undone_at timestamptz
);

CREATE TABLE exports (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status text NOT NULL CHECK (status IN ('queued','building','ready','expired','failed')),
  storage_key text,                                 -- encrypted ZIP on the data volume
  created_at timestamptz NOT NULL DEFAULT now(), ready_at timestamptz, expires_at timestamptz, downloaded_at timestamptz
);

CREATE TABLE outbox_events (
  id bigserial PRIMARY KEY,
  topic text NOT NULL,          -- daily_log.flow_changed, health_profile.changed, event.changed, task.changed, medication.changed, settings.changed
  user_id uuid NOT NULL,
  body jsonb NOT NULL,          -- ids only, never health values
  created_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz
);
CREATE INDEX ON outbox_events (created_at) WHERE processed_at IS NULL;

CREATE TABLE audit_log (
  id bigserial PRIMARY KEY,
  actor_user_id uuid, actor_role text NOT NULL,
  action text NOT NULL,         -- admin.revoke_sessions, admin.invite_create, user.export, user.delete_request, user.import_commit
  target_user_id uuid,
  at timestamptz NOT NULL DEFAULT now(),
  ip_hash bytea
);
```

Procrastinate creates its job tables through its own migration, in a separate `jobs` schema.

### 7.3 Database roles

| Role | Grants | Used by |
| --- | --- | --- |
| `lifeos_owner` | Owns schema; runs migrations | Alembic only, at deploy |
| `lifeos_app` | CRUD on all tables; RLS enforced (`FORCE ROW LEVEL SECURITY`) | API and worker |
| `lifeos_admin_ro` | SELECT on `users(id, email, display_name, role, created_at)`, `sessions`, `invites`, `auth_events`, `audit_log`, job tables; nothing else | Admin console endpoints |
| `lifeos_backup` | `pg_read_all_data` | Backup job |

The worker processes many users' jobs, so each job opens its own transaction and sets `app.user_id` for the user it serves before touching user tables.

### 7.4 Seed data

On registration the app seeds 18 symptoms for the user: cramps, back pain, headache, tender breasts (pain); bloating, nausea, constipation, diarrhoea, cravings (digestion); spots, oily skin (skin); low energy, insomnia (energy); anxious, irritable, sad, calm, happy (emotional). Flo symptom names map onto these keys during import (section 13).

### 7.5 Supporting tables

```sql
CREATE TABLE auth_challenges (               -- WebAuthn challenges, single use
  id uuid PRIMARY KEY,
  purpose text NOT NULL CHECK (purpose IN ('register','signin','add_passkey','reauth','unlock')),
  challenge bytea NOT NULL,
  user_id uuid REFERENCES users(id) ON DELETE CASCADE,
  invite_id uuid REFERENCES invites(id),
  expires_at timestamptz NOT NULL,            -- now() + 5 min
  used_at timestamptz
);

CREATE TABLE idempotency_keys (
  key uuid NOT NULL,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  method text NOT NULL, path text NOT NULL,
  request_hash bytea NOT NULL,                -- same key with a different body → 422
  response_status smallint NOT NULL,
  response_body_enc bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),   -- purged after 7 days
  PRIMARY KEY (user_id, key)
);

CREATE TABLE pending_deletions (             -- survives restores; no personal data
  user_id uuid PRIMARY KEY,
  delete_after timestamptz NOT NULL,
  completed_at timestamptz
);
```

Optimistic concurrency uses `updated_at` as the resource version: responses carry it as `ETag`, PATCH sends it in `If-Match`.

## 8. Cycle engine

Version `calendar-1.0` is a pure, deterministic function from her flow history and health profile to cycles and one prediction; it is easy to explain, unit-test and replace later.

### 8.1 Definitions

- **Flow day**: a daily log with flow light, medium or heavy. Spotting is stored but never counts as a flow day.
- **Bleed episode**: a run of flow days where gaps between consecutive flow days are at most 2 days.
- **Period start**: the first day of a bleed episode that begins at least 15 days after the previous period start, or any date in `health_profile.forced_period_starts` (she confirmed it). An episode starting sooner is an **intra-cycle bleed**: stored, shown, and the Cycle screen asks "Is this a new period?"; answering yes adds the date to `forced_period_starts`.
- **Cycle**: from one period start to the day before the next. Length = next start − this start (days). The latest cycle is incomplete.
- **Period length**: last flow day of the starting episode − start + 1.
- **Cycle day**: today − latest start + 1.

NHS guidance gives 21–35 days as the common range for cycles and 2–7 days for periods; the engine does not judge her against these ranges, it only uses them to set defaults and outlier bounds below.

### 8.2 Inclusion rules

A complete cycle is **included** in statistics unless one of these applies; excluded cycles are still shown, with the reason.

| Rule | Reason code |
| --- | --- |
| She excluded it (illness, travel, medication) | `user_excluded` |
| Length < 15 or > 60 days | `outlier` |
| Mode is postpartum and the cycle started before `mode_started_on` | `postpartum` |
| The cycle started before a gap of > 60 days with no logs at all (data missing, not a long cycle) | `data_gap` |

### 8.3 Prediction algorithm

```python
ALGO = "calendar-1.0"
DEFAULT_SD = 3.0          # assumed spread when fewer than 2 cycles
MAX_HALF_WIDTH = 7

def predict(today, cycles, profile):
    latest = cycles[-1] if cycles else None
    if latest is None and profile.last_period_hint is None:
        return Prediction(confidence="none", suppressed_reason="no_data")

    last_start = latest.start_date if latest else profile.last_period_hint
    used = [c for c in cycles if c.is_complete and not c.excluded][-6:]
    n = len(used)

    if profile.mode == "postpartum":
        after = [c for c in used if c.start_date >= profile.mode_started_on]
        if len(after) < 2:
            return Prediction(confidence="none", suppressed_reason="postpartum_waiting")

    if n == 0:
        if profile.usual_cycle_length is None:
            return Prediction(confidence="none", suppressed_reason="need_one_cycle")
        mean, sd = profile.usual_cycle_length, DEFAULT_SD
    elif n == 1:
        mean, sd = used[0].length_days, DEFAULT_SD
    else:
        lengths = [c.length_days for c in used]
        mean, sd = statistics.mean(lengths), statistics.stdev(lengths)

    half = min(MAX_HALF_WIDTH, max(1, round_half_up(sd)))
    predicted = last_start + days(round_half_up(mean))
    mean_period = mean_or_default([c.period_length_days for c in used], profile.usual_period_length or 5)

    ovulation = predicted - days(14)
    fertile = (ovulation - days(5), ovulation + days(1))
    if ovulation <= last_start + days(round_half_up(mean_period)):
        fertile = None                     # cycle too short to place it sensibly

    return Prediction(
        predicted_start=predicted,
        range_low=predicted - days(half), range_high=predicted + days(half),
        ovulation_est=ovulation if fertile else None, fertile=fertile,
        confidence=confidence(n, sd), n_cycles=n, mean_len=mean, sd_len=sd,
        mean_period_len=mean_period, algorithm_version=ALGO)

def confidence(n, sd):
    if n >= 6 and sd <= 2: return "high"
    if n >= 3 and sd <= 4: return "medium"
    return "low"
```

### 8.4 Derived states shown in the UI

| State | Rule | Today card copy |
| --- | --- | --- |
| On period | Today is within the latest episode or flow logged today | "Day 2 of your period" |
| Upcoming | today < range\_low | "Period in about N days" (N = predicted − today) |
| Window | range\_low ≤ today ≤ range\_high | "Period may start any day now" |
| Late | today > range\_high, no new start | "Your period is N days later than expected" (once, gentle) |
| Long gap | > 90 days since last start | Adds link to NHS periods guidance |
| Irregular | max − min of used lengths > 7 | "Your cycles vary quite a bit, so ranges are wider" |
| Waiting | postpartum suppression | "Waiting for your cycle to return" |
| No data | suppressed `no_data` / `need_one_cycle` | "Log your period to start predictions" |

Phase (shown only when a prediction exists): Menstrual (cycle day 1 to mean period length), Follicular (until fertile window), Fertile window (estimate), Luteal (after the window until next start).

### 8.5 When it runs

1. Any daily-log save that changes flow, or any change to `health_profile`, writes an outbox event in the same transaction.
2. The outbox relay enqueues `health.rebuild_cycles(user_id)`; jobs for the same user are serialised (Procrastinate `queueing_lock`).
3. The job decrypts all flow values (a few thousand rows at most), rebuilds cycles in memory, replaces the user's `cycles` rows in one transaction, supersedes the previous prediction, inserts the new one and emits `prediction.updated`.
4. `notify` reschedules `period_due` (2 days before `range_low`, at 09:00 local) and `late_period` (3 days after `range_high`, 09:00) reminders.
5. The client invalidates its cycle queries; the API also runs the rebuild synchronously if the client calls `GET /health/cycle` while a rebuild is pending, so the screen is never stale. Target: < 2 s end to end.

A nightly job also recomputes every user's prediction, so day-dependent states (late, long gap) update without new logs.

### 8.6 Test vectors (must pass in CI)

| ID | Input | Expected |
| --- | --- | --- |
| TV1 | Starts 2026-06-01, 06-29, 07-28, 08-26, 09-24 (lengths 28, 29, 29, 29); period 5 days each | n=4, mean 28.75, sd 0.5 → half-width 1; predicted 2026-10-23; range 10-22 to 10-24; ovulation 10-09; fertile 10-04 to 10-10; confidence medium |
| TV2 | One complete cycle of 30 days, latest start 2026-09-20 | sd 3 → predicted 2026-10-20; range 10-17 to 10-23; confidence low |
| TV3 | No cycles; usual length 28; last period hint 2026-09-15 | predicted 2026-10-13; range 10-10 to 10-16; confidence low |
| TV4 | Postpartum mode from 2026-08-01; one complete cycle after it | Suppressed: `postpartum_waiting` |
| TV5 | Lengths 25, 35, 28, 40, 26 | mean 30.8, sd 6.46 → half-width 6; irregular note shown; confidence low |
| TV6 | Only spotting logged on 2026-10-01 | No new cycle; latest start unchanged |
| TV7 | Flow begins 10 days after the latest start | Intra-cycle bleed; no new cycle; prompt shown; after "yes", a new cycle of 10 days exists and is excluded as `outlier` |
| TV8 | One cycle of 70 days among 28-day cycles | That cycle excluded as `outlier`; stats from the rest |
| TV9 | Flow on days 1, 2, 4, 5 (gap of 1 day) | One episode; period length 5 |
| TV10 | Flow on days 1, 2, then 6, 7 (gap of 3 days), 5 days apart | Second run is an intra-cycle bleed, not a new period |
| TV11 | Prediction run on 2026-10-26 with TV1 data and no new period | State Late, 2 days; `late_period` reminder scheduled for 10-27 09:00 |
| TV12 | Edit a past flow day that changes a start date | Cycles rebuilt; prediction superseded; reminders rescheduled; no duplicate reminders (dedupe keys) |

Property-based tests (Hypothesis): for random flow histories, rebuild is idempotent, cycle lengths sum to the span between first and latest start, and every prediction satisfies range\_low ≤ predicted ≤ range\_high.

## 9. API specification

A JSON REST API under `/api/v1`, described by the OpenAPI document FastAPI generates; the client's TypeScript types are generated from it (`openapi-typescript`) so client and server cannot drift.

### 9.1 Conventions

- **Auth**: session cookie `lo_session` (HttpOnly, Secure, SameSite=Lax, Path=/). Every mutating request must send `X-LifeOS-Client: web` and an `Origin` matching the app origin (CSRF defence).
- **Idempotency**: every POST/PUT/PATCH/DELETE accepts `Idempotency-Key` (UUID). The server stores key → response for 7 days; a replay returns the stored response. The offline queue always sends one.
- **Dates**: `date` as `YYYY-MM-DD` (her local calendar date); instants as RFC 3339 UTC; local times as `HH:MM`.
- **Errors**: RFC 9457 `application/problem+json` with `type`, `title`, `status`, `detail`, and `errors[]` (field, code, message) for 422.
- **Pagination**: `?limit=` (default 50, max 200) and opaque `cursor`; response `{items, next_cursor}`.
- **Concurrency**: mutable resources return `version` (integer); PATCH sends `If-Match: <version>`; mismatch → 409 with the current resource. Daily logs use `client_updated_at` last-writer-wins instead (section 11).
- **Rate limits**: auth endpoints per section 4.1; all others 300 requests/min per session → 429 with `Retry-After`.

### 9.2 Endpoints

| Method and path | Purpose | Notes |
| --- | --- | --- |
| `POST /auth/invites/verify` | Check an invite token | `{token}` → `{valid, email?}` |
| `POST /auth/register/options` | Start passkey registration | `{token, name, email}` → WebAuthn creation options; challenge stored server-side for 5 min |
| `POST /auth/register/verify` | Finish passkey registration | Creates user, settings, DEK, seeded symptoms, session; returns recovery codes once |
| `POST /auth/register/password` | Fallback registration | `{token, name, email, password}` → TOTP provisioning URI; account active after `/auth/totp/confirm` |
| `POST /auth/totp/confirm` | Confirm TOTP | `{code}` |
| `POST /auth/signin/options` | Start passkey sign-in | Discoverable credentials (no username needed) |
| `POST /auth/signin/verify` | Finish passkey sign-in | Sets cookie |
| `POST /auth/signin/password` | Password + TOTP sign-in | `{email, password, totp}` |
| `POST /auth/signin/recovery` | Recovery-code sign-in | `{email, code}`; forces new passkey setup |
| `POST /auth/signout` | End session |  |
| `GET /auth/sessions` | List sessions | Device label, last seen, current flag |
| `DELETE /auth/sessions/{id}` | Revoke a session |  |
| `POST /auth/passkeys/options`, `/verify` | Add another passkey |  |
| `DELETE /auth/passkeys/{id}` | Remove a passkey | Not the last sign-in method |
| `POST /auth/recovery-codes` | Regenerate codes | Requires recent auth (< 5 min) |
| `PUT /auth/app-lock` | Set or clear PIN, timeout |  |
| `POST /auth/app-lock/unlock` | Verify PIN | 5 tries then full sign-in required |
| `GET /me` | Profile, settings, health mode, feature flags | Bootstraps the client |
| `PATCH /me`, `PATCH /me/settings` | Update profile and settings |  |
| `GET /today?date=` | Aggregated Today payload | Cycle card, check-in state, items, streak, pending counts |
| `GET /daily-logs?from=&to=` | Logs in a date range | Max 400 days per call |
| `GET /daily-logs/{date}` | One day | 404 if none |
| `PUT /daily-logs/{date}` | Upsert a day | Body below; future dates → 422; triggers rebuild if flow changed |
| `DELETE /daily-logs/{date}` | Clear a day |  |
| `POST /health/period/start` | "Period started" | `{date}`; sets flow medium if empty |
| `POST /health/period/end` | "Period ended" | `{date}`: last flow day |
| `GET /health/cycle` | Current cycle, prediction, states | Body below |
| `GET /health/cycles` | Cycle history | Includes exclusion reasons |
| `POST /health/cycles/exclusions` | Exclude/include a cycle | `{start_date, excluded, reason?}` |
| `POST /health/period-starts/confirm` | Answer "Is this a new period?" | `{date, is_new_period}` |
| `GET /health/calendar?month=YYYY-MM` | Month view data | Per day: flow, predicted, fertile, has\_log, events, doses |
| `GET /health/profile`, `PUT /health/profile` | Mode, usual lengths, hints | Mode change records `mode_started_on` |
| `GET /health/insights` | Symptoms by phase, mood by cycle day | Only when data thresholds met (INS-1) |
| `GET/POST /symptoms`, `PATCH/DELETE /symptoms/{id}` | Catalogue | DELETE archives |
| `GET/POST /medications`, `GET/PATCH/DELETE /medications/{id}` | Medications | PATCH schedule regenerates future doses |
| `GET /medication-doses?from=&to=` | Doses in range |  |
| `POST /medication-doses/{id}/taken`, `/skip`, `/undo` | Dose actions | `{at?}` |
| `POST /medications/{id}/doses` | Log an as-needed dose | `{at}` |
| `GET/POST /events`, `GET/PATCH/DELETE /events/{id}` | Appointments | Recurring: \`?scope=this |
| `GET /events/{id}/ics` | Download `.ics` |  |
| `GET/POST /people`, `GET/PATCH/DELETE /people/{id}` | People |  |
| `GET/POST /tasks`, `GET/PATCH/DELETE /tasks/{id}` | Tasks | `POST /tasks/{id}/complete`, `/reopen` |
| `GET/POST /notes`, `GET/PATCH/DELETE /notes/{id}` | Notes |  |
| `GET /timeline?from=&to=` | Unified items for Calendar | Events (expanded occurrences), doses, tasks, flow days |
| `GET /reminders/inbox` | Last 30 days of sent reminders |  |
| `POST /reminders/{id}/snooze` | Snooze | \`{preset: 15m |
| `POST /reminders/{id}/done` | Dismiss |  |
| `GET /push/vapid-public-key` | VAPID key |  |
| `POST /push/subscriptions` | Save subscription | `{endpoint, keys:{p256dh, auth}, device_label}` |
| `DELETE /push/subscriptions` | Remove by endpoint | `{endpoint}` |
| `POST /push/test` | Send a test push now |  |
| `POST /imports` | Upload Flo JSON or CSV | multipart, max 20 MB → `{id, status}` |
| `GET /imports/{id}` | Parse status and preview summary |  |
| `POST /imports/{id}/commit` | Apply import |  |
| `POST /imports/{id}/undo` | Undo within 30 days |  |
| `POST /exports` | Start export | → `{id}` |
| `GET /exports/{id}` | Status |  |
| `GET /exports/{id}/download` | Download ZIP | Requires recent auth; one download, then expires |
| `POST /account/deletion` | Request deletion | Requires recent auth and `{confirm: "DELETE"}` |
| `DELETE /account/deletion` | Cancel during grace period |  |
| `GET /admin/status` | Health, queue depth, backup age, push failure counts | Admin only |
| `GET/POST /admin/invites`, `DELETE /admin/invites/{id}` | Invites | Admin only |
| `POST /admin/users/{id}/revoke-sessions` | Revoke sessions | Admin only; audited |
| `GET /healthz`, `GET /readyz` | Liveness and readiness | No auth; no data |

"Recent auth" means a passkey or password verification within the last 5 minutes (`POST /auth/reauth/options`, `/verify`).

Account recovery (AUTH-8): `POST /admin/users/{id}/recovery-invite` (admin, audited, revokes sessions, notifies her devices) → link to `/recover?token=`; `POST /auth/recover/options` and `/auth/recover/verify` register a new passkey on the existing account and return fresh recovery codes.

### 9.3 Key payloads

```json
// PUT /api/v1/daily-logs/2026-10-06
{
  "mood": 4, "energy": 3, "sleep_hours": 6.5,
  "symptom_ids": ["0192f1c4-..."],
  "flow": "none",
  "discharge": null, "bbt_c": null, "intimacy": null,
  "note": null,
  "checkin_ms": 18400,
  "client_updated_at": "2026-10-06T19:02:11.412Z"
}
// 200 → the stored log plus {"rebuild": "queued" | "not_needed"}
```

```json
// GET /api/v1/health/cycle
{
  "cycle_day": 23,
  "latest_start": "2026-09-14",
  "phase": "luteal",
  "state": "upcoming",
  "prediction": {
    "predicted_start": "2026-10-12", "range_low": "2026-10-11", "range_high": "2026-10-13",
    "ovulation_est": "2026-09-28", "fertile_start": "2026-09-23", "fertile_end": "2026-09-29",
    "confidence": "medium", "n_cycles": 4, "mean_len": 28.5, "sd_len": 0.6,
    "mean_period_len": 5, "algorithm_version": "calendar-1.0", "suppressed_reason": null
  },
  "notes": [{"kind": "irregular", "text": null}],
  "pending_prompt": null,
  "mode": "standard"
}
```

```json
// GET /api/v1/today?date=2026-10-06
{
  "date": "2026-10-06",
  "greeting": "morning",
  "cycle_card": { "cycle_day": 23, "state": "upcoming", "days_until": 6, "range_low": "2026-10-11", "range_high": "2026-10-13", "suppressed_reason": null },
  "checkin": { "done": false, "log": null },
  "streak": 5,
  "items": [
    { "type": "event", "id": "...", "title": "Health visitor", "starts_at": "2026-10-06T09:30:00Z", "all_day": false },
    { "type": "dose", "id": "...", "medication": "Vitamin D", "dose": "1 tablet", "scheduled_at": "2026-10-06T07:00:00Z", "status": "due" },
    { "type": "task", "id": "...", "title": "Call Mum", "due_at": null, "status": "open" }
  ],
  "unread_inbox": 1
}
```

### 9.4 Server-side validation rules

| Field | Rule |
| --- | --- |
| `mood`, `energy` | Integer 1–5 or null |
| `sleep_hours` | 0–14 in 0.5 steps or null |
| `flow` | One of none, spotting, light, medium, heavy |
| `bbt_c` | 34.0–40.0, 2 decimals, only if enabled |
| `note` | ≤ 2,000 chars; notes body ≤ 20,000 |
| Daily-log `date` | Not after her local today; not before 1990-01-01 |
| Event | `ends_at ≥ starts_at`; RRULE parsed by dateutil; max 1,000 occurrences generated |
| Medication | 1–6 times; days of week 1–7; `end_date ≥ start_date` |
| Strings | Trimmed; control characters stripped; Unicode NFC |

## 10. Reminders, scheduling and Web Push

Every nudge is a `reminders` row created ahead of time and sent by a once-a-minute dispatcher, so reminders survive restarts and are easy to audit.

### 10.1 Background jobs (Procrastinate)

| Job | Schedule | What it does |
| --- | --- | --- |
| `outbox.relay` | Every minute, and on `NOTIFY` | Reads unprocessed `outbox_events`, enqueues the matching jobs, marks processed |
| `notify.dispatch` | Every minute | Sends due reminders (10.3) |
| `notify.extend_horizon` | Daily 02:10 UTC, and per user on relevant events | Generates reminders and medication doses for the next 14 days; idempotent via `dedupe_key` |
| `health.rebuild_cycles` | On `daily_log.flow_changed`, `health_profile.changed` | Section 8.5 |
| `health.nightly_predict` | Daily 03:05 UTC | Recomputes predictions and day-dependent states |
| `meds.mark_missed` | Every 15 min | Due doses older than 6 h → missed |
| `data.import_parse`, `data.import_commit`, `data.import_undo` | On request | Section 13 |
| `data.export_build`, `data.export_expire` | On request; hourly | Section 13 |
| `account.purge` | Daily 04:00 UTC | Hard-deletes accounts past the 7-day grace period; purges soft-deleted rows > 30 days, idempotency keys > 7 days, used challenges, old auth events > 1 year |
| `ops.backup_check` | Hourly | Alerts if the newest backup is older than 26 h |

### 10.2 How each reminder is created

| Kind | Created by | Fire time (her local time) | Skipped when |
| --- | --- | --- | --- |
| `checkin` | Horizon job | Every day at `checkin_time` | A daily log for that date exists at send time |
| `period_due` | Prediction update | 09:00, 2 days before `range_low` | Prediction suppressed or period already logged |
| `late_period` | Prediction update | 09:00, 3 days after `range_high` | A new period started; sent at most once per cycle |
| `medication` | Dose generation | Each dose's `scheduled_at` | Dose already taken or skipped |
| `appointment` | Event create/update + horizon | Each rule: `day_before_at HH:MM` (previous local day at that time) or `minutes_before N` | Occurrence cancelled; fire time already past when created |
| `task` | Task create/update | `remind_at` | Task done |
| `test` | `/push/test` | Now | — |

Quiet hours: `checkin`, `period_due`, `late_period` and `task` reminders falling inside quiet hours move to `quiet_end`; medication and appointment reminders always fire. A change of timezone, check-in time, quiet hours or notification preferences regenerates all future reminders for that user.

DST: local fire times are computed with `zoneinfo` for each date, so a 08:00 dose stays at 08:00 across the GMT/BST change. A local time that does not exist (spring forward) fires at the next valid minute; a repeated time (autumn back) fires once, at the first occurrence.

### 10.3 Dispatcher

```sql
-- inside one transaction, as lifeos_app with RLS bypass for the dispatcher role only
SELECT id, user_id FROM reminders
WHERE status IN ('scheduled','snoozed') AND fire_at <= now()
ORDER BY fire_at
FOR UPDATE SKIP LOCKED
LIMIT 200;
-- mark 'sending', commit, then send each one
```

For each reminder: re-check the skip condition; decrypt payload; apply discreet mode; send to every active push subscription; on any success mark `sent`, set `sent_at`, add to the inbox; on 404/410 disable that subscription; on 429/5xx retry in 1, 2 and 5 minutes (`attempts`), then mark `failed`. Reminders stuck in `sending` for more than 5 minutes return to `scheduled` (crash recovery). The dispatcher is the only component allowed to read across users; it uses a dedicated database role whose RLS policy permits it and is limited to `reminders`, `push_subscriptions`, `user_settings`, `users(id, timezone, dek_wrapped)` and the status columns it needs.

### 10.4 Push message

Sent with `pywebpush` using VAPID (keys generated once, stored as secrets, subject `mailto:` the admin address). The payload is end-to-end encrypted to the browser (Web Push message encryption), so the push service cannot read it.

```json
{
  "reminder_id": "0192f2...",
  "kind": "medication",
  "title": "Vitamin D",
  "body": "1 tablet — tap when taken",
  "url": "/meds/doses/0192f2...",
  "tag": "dose:0192f2...",
  "actions": [{"action": "taken", "title": "Taken"}, {"action": "snooze", "title": "In 15 min"}],
  "badge_count": 2
}
```

Headers: `TTL` 21,600 s for medication and appointment, 86,400 s otherwise; `Urgency: high` for medication and appointment, `normal` otherwise; `Topic` = a hash of `tag` so a newer message replaces an undelivered older one. Discreet mode replaces `title` with "Life OS" and `body` with "You have a reminder" and drops `actions`.

### 10.5 Service worker behaviour

- `push`: always calls `showNotification(title, {body, tag, data: {url, reminder_id, kind}, actions, icon, badge})`; iOS requires a visible notification for every push. Then `navigator.setAppBadge(badge_count)` where supported.
- `notificationclick`: if `action === 'taken'`, `fetch('/api/v1/medication-doses/{id}/taken', {method: 'POST', credentials: 'include', headers: {'X-LifeOS-Client': 'web', 'Idempotency-Key': reminder_id}})`; if that fails, open the dose screen instead. If `action === 'snooze'`, call the snooze endpoint. Otherwise focus an existing app window and navigate to `url`, or open a new one.
- `pushsubscriptionchange`: resubscribe with the VAPID key and POST the new subscription.
- On every app start the client compares `pushManager.getSubscription()` with the server list and re-registers if missing.

### 10.6 Platform requirements and limits

| Platform | Requirement | What the app does |
| --- | --- | --- |
| iPhone (iOS/iPadOS 16.4+) | Push works only when the PWA is added to the Home Screen and opened from there; never in a Safari tab | Install guide first (ONB-1); the Enable button is shown only in standalone mode |
| iPhone | Permission must be requested from a user tap | Request only in the button's click handler (ONB-3) |
| iPhone | No notification action buttons | Tap opens the one-tap dose screen (MED-3) |
| iPhone | Browser tab and installed app keep separate storage and subscriptions | All state is server-side; the install guide tells her to use the Home Screen icon only |
| Android Chrome | Works in browser and installed | Actions "Taken" and "In 15 min" supported |
| All | A user can revoke permission at any time | Settings shows current permission state and how to re-enable; inbox (REM-5) keeps every reminder |

### 10.7 Notification copy

| Kind | Title | Body | Opens |
| --- | --- | --- | --- |
| `checkin` | How are you today? | Takes 20 seconds | `/checkin` |
| `period_due` | Heads up | Your period may start in about 2 days | `/health/cycle` |
| `late_period` | Just checking in | Your period hasn't been logged yet. Log it when it starts | `/health/cycle` |
| `medication` | {name} | {dose} — tap when taken | `/meds/doses/{id}` |
| `appointment` (day before) | Tomorrow: {title} | {time} · {location} | `/appointments/{id}` |
| `appointment` (minutes before) | {title} at {time} | {location} | `/appointments/{id}` |
| `task` | Reminder | {title} | `/tasks` |
| `test` | Notifications are on | You'll get reminders here | `/today` |
| Account notice | Life OS | Security notice: {event}. Open the app for details | `/settings/security` |

Discreet mode replaces every title with "Life OS" and every body with "You have a reminder".

## 11. Client architecture

A single-page React app, installed as a PWA, that renders from local cache first and queues writes when offline; the server stays the source of truth.

### 11.1 Repository layout (one monorepo)

```text
life-os/
  server/                 FastAPI app, worker, Alembic, tests
    app/
      platform/           config, db, crypto, logging, outbox, jobs, rls
      auth/ core/ health/ notify/ data/ admin/
        api.py  service.py  repo.py  schemas.py  models.py  jobs.py
      main.py             API entrypoint
      worker.py           Procrastinate worker entrypoint
    migrations/
    tests/
  web/
    index.html
    public/               icons, apple-touch-icon, manifest assets
    src/
      app/                router, providers, layout, BottomNav
      features/           today, checkin, health, meds, calendar, appointments,
                          people, tasks, notes, inbox, settings, auth, data, admin
      ui/                 component library (section 5.5)
      lib/api/            generated types (openapi-typescript) + fetch wrapper
      lib/offline/        IndexedDB outbox, cache persister, sync engine
      lib/push/           subscribe, permission, badge
      lib/lock/           app lock timer and overlay
      lib/theme/          tokens.css, theme switcher, theme-color meta
      copy/en-GB.ts
      sw.ts               service worker (injectManifest)
    tests/                Vitest unit, Playwright e2e
  infra/                  docker-compose.yml, Caddyfile, backup scripts, runbooks
  docs/                   this spec, ADRs
```

### 11.2 Web app manifest

```json
{
  "name": "Life OS",
  "short_name": "Life OS",
  "id": "/",
  "start_url": "/today?source=pwa",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#FFF4F1",
  "theme_color": "#FFF4F1",
  "icons": [
    {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ]
}
```

Also in `index.html`: `<link rel="apple-touch-icon" href="/icons/apple-touch-icon-180.png">`, `<meta name="theme-color">` updated by the theme switcher, `viewport-fit=cover` with safe-area padding for the bottom bar. The app name can change once Zee picks one (section 18).

### 11.3 Service worker

- Built with `vite-plugin-pwa` in `injectManifest` mode so `sw.ts` holds custom push code.
- Precache: app shell, route chunks, fonts, icons (Workbox precache manifest, revisioned).
- Navigation requests: network-first with 3 s timeout, falling back to cached `index.html`.
- API requests are **not** cached by the service worker; offline data comes from the query cache (11.4).
- Updates: `registerType: 'prompt'`; when a new version is waiting, show a toast "New version ready — Refresh"; it also activates on the next cold start.
- Push and notification handlers: section 10.5.

### 11.4 Data fetching and local cache

- TanStack Query for all server state. Query keys: `['me']`, `['today', date]`, `['dailyLog', date]`, `['dailyLogs', from, to]`, `['cycle']`, `['cycles']`, `['calendar', month]`, `['meds']`, `['doses', from, to]`, `['events', from, to]`, `['people']`, `['tasks', status]`, `['notes']`, `['inbox']`, `['insights']`.
- `staleTime` 30 s for Today and cycle, 5 min for lists; refetch on window focus and on reconnect.
- Persist the query cache to IndexedDB (`@tanstack/query-async-storage-persister` with an `idb` adapter), max age 14 days, so Today, Cycle and the last two months of calendar open offline.
- The persisted cache is encrypted with AES-GCM using a non-extractable WebCrypto key stored in IndexedDB. This does not stop someone with her unlocked phone; it stops casual reading of browser files and backups. The phone's own lock and the app lock (11.6) are the main device protections.
- Sign-out and remote session revocation clear the cache, the outbox, and the key.
- Mutations that change cycle data invalidate `['cycle']`, `['today', *]`, `['calendar', *]` after the server confirms.

### 11.5 Offline writes and sync

| Works offline | Requires connection |
| --- | --- |
| Daily check-in and edits, period start/end, dose taken/skip, task complete/reopen, create and edit notes | Sign-in, settings, appointments, medications setup, people, import, export, deletion |

Outbox design (IndexedDB store `outbox`):

1. Each offline-capable mutation is written as `{id: uuid, method, path, body, created_at, attempts}` and applied optimistically to the query cache.
2. The sync engine flushes the outbox in order on `online`, on app focus, after each enqueue, and every 30 s while open (Background Sync where supported; iOS does not support it, so flushing on open covers iPhone).
3. Each request sends `Idempotency-Key: id`, so a retry after a lost response is safe.
4. Responses: 2xx → remove; 401 → pause and ask her to sign in; 409/422 → remove, roll back the optimistic change, and list it under "Couldn't sync" in the inbox with a Retry/Discard choice; 429/5xx/network → keep, backoff 5 s → 5 min.
5. Daily logs carry `client_updated_at`; the server keeps whichever write has the later timestamp, so editing the same day on two devices resolves predictably.
6. A "Will sync" chip shows on Today while the outbox is non-empty (TOD-7).

### 11.6 App lock

On `visibilitychange` to hidden, store the time. On visible, if more than `app_lock_timeout_s` passed (default 300), show the LockScreen overlay over a blurred app. Unlock with a passkey (`/auth/reauth`, purpose `unlock`) or her PIN (`/auth/app-lock/unlock`). The overlay is rendered before any data, and screens hide content when the app is backgrounded so the iOS app switcher snapshot shows the lock state.

### 11.7 Other client rules

- Theme: `system` follows `prefers-color-scheme`; the chosen theme sets `data-theme` on `<html>` and updates `theme-color`.
- Timezone: dates display in the profile timezone; the client sends `X-Timezone` so the server can warn if the device and profile differ ("You seem to be in Lagos — switch timezone?").
- Routes are code-split; initial JS budget 250 KB gzipped (NFR-2), enforced in CI with `size-limit`.
- TypeScript `strict`, ESLint, Prettier; no `any` in `lib/api`.
- Forms: React Hook Form with Zod schemas mirroring section 9.4.
- Errors: a top-level error boundary with "Something went wrong — Reload" and no stack traces shown; client errors are POSTed to `/api/v1/client-errors` (message, route, version; no user data) and logged server-side.

Add to the API (section 9): `POST /client-errors` → 204, rate-limited to 20 per minute.

## 12. Security and privacy

The design protects her data against database leaks, stolen backups, phishing and third-party tracking; it does not fully protect against the person who runs the server, and Zee should be told that plainly.

### 12.1 Threat model

| Threat | Mitigation | Residual risk |
| --- | --- | --- |
| Database dump or disk stolen | Health values, notes, names and messages encrypted per field; keys not in the database | Plaintext dates show which days have logs, not what was logged |
| Backup stolen | Backups encrypted (age/restic) with a key separate from the data key; field encryption still applies inside | Low |
| Phishing for her sign-in | Passkeys are bound to the site origin and cannot be phished; password fallback requires TOTP | Low |
| Password guessing | Argon2id, rate limits, lockout, TOTP | Low |
| XSS stealing data | Strict CSP (no inline script, no third-party origins), React escaping, no `dangerouslySetInnerHTML`, HttpOnly cookie | Low |
| CSRF | SameSite=Lax cookie, `Origin` check, custom header on mutations | Low |
| Third-party SDKs leaking data (the Flo problem) | None installed; CSP blocks all external origins; fonts self-hosted; CI fails if a new external origin appears in the built app | Very low |
| Push service reading messages | Web Push payloads are end-to-end encrypted; discreet mode for lock-screen text | Push service sees timing only |
| Lost or stolen phone | Phone lock, app lock, remote session revocation, encrypted local cache | Unlocked phone in someone's hands |
| Server compromise | Patched host, firewall with no inbound web ports (traffic arrives only through the Cloudflare Tunnel; SSH by key), non-root containers, secrets as files, audit log | An attacker on the running server can use the keys |
| The operator (Ibrahim) | Admin role cannot reach health tables; no admin endpoint returns health data; every admin action audited | He controls the server and the master key, so a determined operator could decrypt. Removing this needs client-held keys (local-first), proposed for after the MVP |

### 12.2 Key hierarchy and encryption

1. **Master key (KEK)**: 32 random bytes (`openssl rand -base64 32`), mounted as a Docker secret at `/run/secrets/lifeos_kek`. A copy lives in an offline password manager; without it backups cannot be restored. `users.kek_version` supports rotation.
2. **User data key (DEK)**: 32 random bytes created at registration, stored only wrapped: AES-256-GCM under the KEK with AAD = `dek:<user_id>`.
3. **Field encryption**: AES-256-GCM, random 96-bit nonce per write, AAD = `table:column:row_id:user_id` so ciphertext cannot be moved between rows. Format: `0x01 ‖ nonce ‖ ciphertext ‖ tag`.
4. **In memory**: DEKs are unwrapped per request or job, cached for at most 5 minutes in process memory, never logged or written to disk.
5. **KEK rotation**: add the new key, re-wrap every DEK (seconds), retire the old key. **DEK rotation**: a re-encryption job; not needed for the MVP but the format allows it.
6. All crypto goes through `platform/crypto.py`, the only module importing `cryptography`; it has its own test suite including tamper tests (changed AAD or byte → decryption fails).

### 12.3 Authentication details

- WebAuthn relying party ID = the app's domain; `userVerification: required`; `residentKey: required` (discoverable passkeys, so no username needed); attestation `none`; accepted algorithms ES256 and RS256; sign-count checked when non-zero.
- Passwords: Argon2id (memory 64 MiB, iterations 3, parallelism 4), minimum 12 characters, checked against a local list of common passwords.
- TOTP: RFC 6238, SHA-1, 6 digits, 30 s, ±1 step, secret encrypted; codes cannot be reused within their window.
- Session tokens: 32 random bytes, only the SHA-256 stored; cookie expiry 30 days sliding; idle 30 days; absolute 180 days.
- Sensitive actions (export download, deletion, recovery-code regeneration, removing a passkey) need recent authentication within 5 minutes.

### 12.4 HTTP security headers (Pages \_headers file for the app; FastAPI middleware for /api)

```text
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:;
  font-src 'self'; connect-src 'self'; worker-src 'self'; manifest-src 'self'; frame-ancestors 'none';
  base-uri 'none'; form-action 'self'; upgrade-insecure-requests
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=(), interest-cohort=()
Cross-Origin-Opener-Policy: same-origin
```

Inline `style` attributes from React are allowed by CSP only through CSS custom properties set in stylesheets; components use classes (CSS Modules), not inline styles.

### 12.5 Logging and monitoring privacy

Logs contain request ids, routes, status codes, timings, user ids and job names only. Request and response bodies, decrypted values, push payloads and IP addresses are never logged (IPs are HMACed with a rotating key). Error reports scrub any field ending in `_enc`, `note`, `body`, `title`, `name`.

### 12.6 UK GDPR and consent

Health data is special category data under UK GDPR. A private app used by one family member may fall under the household exemption, but this spec follows the principles anyway (this is not legal advice):

- **Explicit consent** at registration: a plain-language screen explaining what is stored, where, who can access it (including the operator limitation above), and that she can export or delete everything; consent time stored.
- **Minimisation**: optional fields off by default; no analytics; IPs hashed.
- **Rights**: access and portability = export (DATA-3); erasure = deletion (DATA-4); rectification = edit anything.
- **Retention**:

| Data | Retention |
| --- | --- |
| Her records | Until she deletes them or her account |
| Soft-deleted records | 30 days, then purged |
| Uploaded import files | 30 days after commit |
| Export ZIPs | 24 hours or first download |
| Auth events | 1 year |
| Application logs | 14 days |
| Backups | Daily for 14 days, weekly for 5 weeks; deleted accounts disappear from backups within 35 days |

- **Breach plan**: revoke sessions, rotate KEK and VAPID keys, restore from a clean backup if needed, tell Zee within 24 hours what was exposed.

### 12.7 Medical safety rules

The app is a personal record, not a medical device. It never claims to diagnose, never presents the fertile window as contraception, uses ranges rather than single days, and links to NHS guidance where relevant (irregular cycles, long gaps). Apps intended for contraception are regulated as medical devices in the UK, which is why the avoiding-pregnancy mode carries an explicit banner (MOD-4).

### 12.8 Supply chain

Pinned dependencies with lockfiles (`uv.lock`, `package-lock.json`); Renovate weekly; `pip-audit`, `npm audit` and Trivy image scans in CI, failing on high-severity issues; images built from slim official bases, run as non-root, read-only root filesystem where possible.

## 13. Flo import, export and account deletion

She must be able to bring her history in, take everything out, and remove it all; each path is reversible until the last step.

### 13.1 Getting her Flo data

Flo exports on request rather than from a button: in the Flo app, Menu (avatar) → Help → Contact us, then ask for a data export. Flo offers a readable TXT file and a machine-readable JSON file; ask for **JSON**. Anonymous-mode users must register first. ([Flo help](https://help.flo.health/hc/en-us/articles/360054973811-How-do-I-export-my-data))

Flo does not publish the JSON structure, so the importer is built against her real file:

1. Request the export in week 1, so it arrives before the import work in week 7.
2. Inspect the file; record its structure in `server/app/data/flo/FORMAT.md`.
3. Create an anonymised fixture (dates shifted, notes replaced) in `server/tests/fixtures/flo_sample.json`. The real file never enters the repository.
4. Write the mapping in `server/app/data/flo/mapping.py` and tests against the fixture.

### 13.2 Import pipeline

| Step | Behaviour |
| --- | --- |
| Upload | `POST /imports` (multipart, ≤ 20 MB, JSON or CSV). File encrypted and stored in `imports.file_enc`; job `data.import_parse` queued |
| Parse | Tolerant parser: finds period start/end dates, daily flow intensity, symptoms, moods, notes, basal temperature and Flo's cycle settings where present. Unknown keys are counted in `summary.unmapped_keys`, never fatal. Dates are interpreted in her profile timezone |
| Map | Flow intensities → spotting/light/medium/heavy; period ranges without daily intensity → medium on each day; Flo symptom names → seeded symptom keys via a mapping table; unknown symptoms → new custom symptoms (listed in the preview); moods → nearest of the 5 mood values or into the note |
| Preview | `GET /imports/{id}` returns counts: days, periods, date range, symptoms mapped, custom symptoms to create, days that already have a log (conflicts, left untouched), unmapped keys. The client shows this before anything is written |
| Commit | One transaction: insert daily logs only for dates with no existing log, each with `import_id`; create custom symptoms; set `health_profile.usual_*` if empty; emit `daily_log.flow_changed`; audit `user.import_commit` |
| Undo (30 days) | Delete daily logs with that `import_id` that she has not edited since; archive custom symptoms created by the import if unused elsewhere; rebuild cycles |
| Cleanup | `file_enc` and `preview_enc` deleted 30 days after commit |

**CSV fallback** (DATA-2) uses the same pipeline with a template: `date,flow,symptoms,mood,energy,sleep_hours,note` where `symptoms` is a `;`-separated list of names. The template is downloadable from the import screen.

### 13.3 Export

`POST /exports` queues `data.export_build`, which writes a ZIP:

```text
life-os-export-2026-10-06.zip
  README.txt              what each file contains, field meanings, algorithm version
  data.json               everything, decrypted, nested by entity
  csv/daily_logs.csv      date, flow, mood, energy, sleep_hours, symptoms, bbt_c, discharge, note
  csv/cycles.csv          start_date, end_date, length_days, period_length_days, included, exclusion_reason
  csv/predictions.csv     created_at, predicted_start, range_low, range_high, confidence, algorithm_version
  csv/symptoms.csv  csv/medications.csv  csv/medication_doses.csv
  csv/appointments.csv  csv/people.csv  csv/tasks.csv  csv/notes.csv
  settings.json           settings and health profile
```

The ZIP is stored encrypted with a one-off key, decrypted while streaming on download, and deleted after the first successful download or 24 hours. The client polls `GET /exports/{id}` every 2 s and shows a Download button when ready; target under 2 minutes.

### 13.4 Account deletion

1. She chooses Delete account, re-authenticates, types DELETE.
2. `deletion_requested_at` is set; all other sessions are revoked; push subscriptions removed except the current device; a banner and a push tell her the date it will happen and offer Cancel.
3. During 7 days she can sign in and cancel; nothing is lost.
4. On day 7, `account.purge` deletes the user row (cascading to every user table), her export and import files, idempotency keys and job rows, and writes an audit entry with no personal data.
5. Backups containing her data expire within 35 days (section 12.6). Restores within that window must re-run pending deletions before the app starts (the purge list is kept in a small separate table of user ids and deletion dates).

## 14. Infrastructure, deployment and operations

Cloudflare Pages serves the app; one small VPS runs the API, worker and database with Docker Compose behind a Cloudflare Tunnel; backups go off-site, encrypted, every night with continuous WAL archiving in between.

### 14.1 Hosting

| Item | Choice |
| --- | --- |
| Web app | Cloudflare Pages project built from `web/`; production on the custom domain, previews on `*.pages.dev` |
| API path | Pages Function `web/functions/api/[[path]].ts` forwards `/api/*` (method, headers, cookies, body) to `ORIGIN_URL` with the Access service-token headers; it adds no logic |
| Origin access | Cloudflare Tunnel (`cloudflared`) from the VPS to a hostname protected by Cloudflare Access; only the service token is allowed |
| Server | One VPS, 2 vCPU, 4 GB RAM, 40 GB SSD, UK or EU region, Ubuntu 24.04 LTS |
| Domain | Bought and on Cloudflare before Zee registers (plan, section 2.2); `staging` subdomain for staging |
| Off-site storage | S3-compatible object storage in a different provider or region, bucket versioning on, access key limited to that bucket |
| Uptime | External HTTP check of `/api/v1/healthz` every minute plus a dead-man's switch pinged by the backup job; neither receives user data |
| Alerts | ntfy push to Ibrahim's phone and email (both) |

### 14.2 Containers (`infra/docker-compose.yml`)

| Service | Image | Notes |
| --- | --- | --- |
| `cloudflared` | `cloudflare/cloudflared` | Tunnel to `api:8000`; token from a secret; the only path in |
| `api` | built from `server/` | `uvicorn app.main:app --workers 2 --proxy-headers`, non-root, read-only FS, healthcheck `/readyz`; sets the API's security headers |
| `worker` | same image | `procrastinate worker` with periodic tasks; one replica |
| `migrate` | same image | One-off `alembic upgrade head` before `api` and `worker` start |
| `postgres` | `postgres:16` | Data volume; `archive_mode=on`; internal network only |
| `backup` | pgBackRest (or wal-g) | Full backup nightly 02:30 UTC, WAL archiving continuous, encrypted with its own key |

The web app is not a container: Cloudflare Pages builds `web/` on each push (preview) and on `main` (staging), and production is promoted by the same CI approval as the server.

### 14.3 Configuration and secrets

| Name | Kind | Purpose |
| --- | --- | --- |
| `APP_ORIGIN` | env | e.g. `https://app.example.com`; used for CORS-free same-origin checks and WebAuthn origin |
| `WEBAUTHN_RP_ID` | env | Domain, e.g. `app.example.com` |
| `DATABASE_URL`, `DATABASE_ADMIN_URL` | secret | `lifeos_app` and `lifeos_admin_ro` connections |
| `lifeos_kek` | secret file | Master key (12.2) |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | secret | Web Push |
| `IP_HMAC_KEY` | secret | Hashing IPs, rotated monthly |
| `BACKUP_REPO_CIPHER_PASS`, `S3_*` | secret | Backups |
| `ALERT_*` | secret | Alert channel tokens |
| `ENV` | env | `local`, `staging`, `production` |

Cloudflare-side settings: `ORIGIN_URL`, `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` as Pages Function environment secrets; `TUNNEL_TOKEN` as a Docker secret for `cloudflared`. The API trusts the client IP only from the `CF-Connecting-IP` header, and only on requests that carry the valid Access token.

Secrets are Docker secrets read from files; a copy of every secret is kept in his password manager. Losing `lifeos_kek` or the backup cipher means losing the data.

### 14.4 Environments

| Environment | Where | Data |
| --- | --- | --- |
| Local | Docker Compose on his laptop; Vite dev server on `localhost` (a secure context, so passkeys and service workers work) | Seeded fake data (`make seed`) |
| Staging | Same VPS, separate Compose project, separate database and keys, `staging.<domain>` | Fake data; restore drills land here |
| Production | `app.<domain>` | Zee's data |

### 14.5 CI/CD (GitHub Actions)

1. On every push: ruff, mypy (strict on `platform`, `health`), pytest with a Postgres service container, import-linter module rules; ESLint, `tsc --noEmit`, Vitest, `size-limit`; OpenAPI diff check (client types regenerated and committed); dependency and image scans.
2. On merge to `main`: build and push images to GHCR tagged with the commit SHA; deploy to staging; run the Playwright suite against staging.
3. Manual approval: deploy the same SHA to production over SSH (`docker compose pull && docker compose run --rm migrate && docker compose up -d`). Expect a few seconds of API restart; the offline queue covers it.
4. Rollback: redeploy the previous SHA. Migrations follow expand-then-contract, so the previous version still runs against the new schema.

### 14.6 Backups and restore

- Full backup nightly plus continuous WAL archiving: worst case loses about 5 minutes of data (NFR-5).
- Retention: daily 14, weekly 5 (35 days).
- Restore drill monthly into staging using `infra/runbooks/restore.md`; record the time taken (target under 4 hours, NFR-5) and confirm a sample day decrypts.
- After any production restore, run `account.purge` against `pending_deletions` before opening the app.

### 14.7 Server hardening

SSH keys only, root login off, `ufw` denying all inbound except SSH (or SSH also through the tunnel with Cloudflare Access); `unattended-upgrades` for security patches; fail2ban on SSH; Docker daemon not exposed; Postgres reachable only on the Compose network; monthly reboot window.

### 14.8 Observability

- Structured JSON logs (12.5) to local files, rotated after 14 days.
- `/admin/status`: app version, uptime, database size, queue depth and oldest job age, reminders sent and failed in the last 24 h, push subscription failures, last backup time, last restore drill.
- Alerts: `/healthz` down for 3 minutes; queue oldest job > 5 minutes; reminder failures > 5 in an hour; backup older than 26 hours; disk > 80%; certificate renewal failure.

### 14.9 Runbooks (in `infra/runbooks/`)

Deploy; rollback; restore from backup; rotate the master key; rotate VAPID keys (clients resubscribe on next open); revoke all sessions; push delivery failing; disk full; lost master key (what is and is not recoverable).

## 15. Testing strategy and quality gates

The riskiest parts (cycle maths, encryption, reminder timing, data isolation) get the deepest automated tests; the experience is proven on her actual phone before launch.

### 15.1 Test layers

| Layer | Tooling | What it must cover |
| --- | --- | --- |
| Server unit | pytest, Hypothesis | Cycle engine TV1–TV12 and properties (8.6); crypto round-trip and tamper tests; reminder time computation; RRULE expansion; validation rules (9.4); Flo and CSV mappers against fixtures |
| Server integration | pytest + real PostgreSQL 16 (CI service container) | Every endpoint's happy path and main errors; RLS: user A can never read or change user B's rows, even with forged ids; `lifeos_admin_ro` cannot select health tables; idempotency replay returns the same response; outbox → job → rebuild → reminders chain; import commit and undo; export contents; account purge removes every row |
| Time and DST | pytest with `time-machine` | Reminders across 2026-10-25 (BST ends) and 2027-03-28 (BST starts); timezone change regenerates reminders; quiet-hours deferral; late-period scheduling (TV11) |
| Push | pytest with a fake push endpoint | Payload shape, TTL and urgency headers, 404/410 disables subscription, retries on 5xx, discreet mode |
| Client unit | Vitest + Testing Library + `fake-indexeddb` | Components (MoodPicker, FlowPicker, CycleRing aria text), copy rules, outbox ordering, retry and rollback, cache encryption, app-lock timer |
| End to end | Playwright (Chromium with a virtual WebAuthn authenticator; WebKit for layout) | J1–J10 scripted against staging with fake data; offline mode via `context.setOffline`; push permission mocked |
| Accessibility | axe-core in Playwright; token contrast script | Zero serious or critical issues on every screen in both themes; every token pair ≥ 4.5:1 |
| Performance | Lighthouse CI (mobile), `size-limit` | Performance ≥ 85, installable PWA, initial JS ≤ 250 KB gzipped |
| Security | OWASP ZAP baseline against staging; CSP and header check; pip-audit, npm audit, Trivy | No high findings; no external origins in the built app |

### 15.2 Real-device test matrix (manual, before launch)

| Device | Checks |
| --- | --- |
| Zee's iPhone (her iOS version, must be 16.4+) | Install from Safari, passkey registration and sign-in, push permission, check-in reminder arrives with the app closed, tap opens the right screen, dose confirm screen, offline check-in syncs, dark theme at night, app lock after 5 min, app switcher shows lock state |
| An Android phone (if available) | Same, plus notification actions Taken and In 15 min |
| Desktop Chrome and Safari | Sign-in with synced passkey, calendar and history screens, export download |

### 15.3 Quality gates for merging and release

- All CI checks green; cycle-engine test vectors are a required check.
- Line coverage ≥ 90% for `health`, `notify`, `platform/crypto`; ≥ 75% overall.
- No skipped tests on `main` without a linked issue.
- Release to production only after the Playwright suite passes on staging for the same commit.
- Before launch: one successful restore drill and one KEK rotation rehearsal on staging.

### 15.4 Beta

1. Week 9: Ibrahim uses staging daily with fake data for a week.
2. Weeks 10–11: Zee uses production alongside Flo, logging in both; weekly 15-minute feedback chat; bugs triaged within 48 hours.
3. Week 12: she imports her final Flo history, stops using Flo, and the acceptance checklist (section 17) is reviewed with her.

## 16. Delivery plan

Twelve weeks of evening and weekend work in five milestones; push is proven on her iPhone in the first fortnight because it is the riskiest platform dependency.

_[Diagram, as text] M1 Foundation (weeks 1–2), gate: she signs in and gets a test push → M2 Logging (weeks 3–4), gate: she logs daily beside Flo → M3 Predictions (weeks 5–6), gate: TV1–TV12 pass, history checks out → M4 Feature complete (weeks 7–8), gate: all must items done, restore drill passes → M5 Beta and launch (weeks 9–12), gate: section 17 all ticked._

A milestone closes only when its gate is met; if a gate slips, the next milestone's "should" items move to M5 rather than the gate being skipped.

| Milestone | Requirements delivered | Also in this milestone |
| --- | --- | --- |
| M1 Foundation | AUTH-1–8, ONB-1, ONB-3, SET-1–2, TOD-1, NFR-6 | Repo and CI (14.5), VPS and Caddy, crypto module and tests, migrations for all tables, RLS, component library basics, theme tokens, push end to end with a test notification |
| M2 Logging | CHK-1–5, PER-1–5, CSC-3, TOD-3, TOD-5, TOD-7 | Offline outbox and cache persistence, symptom seeding, calendar endpoint |
| M3 Predictions | CYC-1–7, MOD-1–2, CSC-1–2, CSC-4, TOD-2, REM-1–7 (check-in, period due, late), ONB-2, SET-3–4 | Outbox relay, rebuild job, nightly predict, dispatcher, horizon job, inbox |
| M4 Feature complete | APT-1–4, MED-1–5, TSK-1–2, NOTE-1, CAL-1–2, DATA-1–4, ADM-1–3, TOD-4, TOD-6 | Flo importer built on her real export, export ZIP, deletion and purge, backups and first restore drill, admin console |
| M5 Beta and launch | NFR-1–5, NFR-7, TOD-8, SET-5, MOD-3–4, CSC-5, INS-1–3, APT-5, MED-6 | Accessibility and performance passes, ZAP scan, device matrix, beta (15.4), final Flo import, launch |

Week 1 tasks that unblock later work: request her Flo export; buy the domain; create the VPS and object storage; generate the master key, VAPID keys and backup cipher and store them in the password manager; check her iPhone's iOS version is 16.4 or later.

## 17. End-to-end acceptance checklist

Launch happens when every box below is ticked on Zee's own phone with her real data; this is the test of whether the specification is complete.

**Getting in**

- [ ] She opens the invite, creates a passkey, sees and stores recovery codes (J1, AUTH-1–4)
- [ ] She installs the app to her Home Screen and opens it from there (ONB-1)
- [ ] She completes or skips the setup wizard and gives consent for health data (ONB-2, 12.6)
- [ ] She enables notifications and receives the test push within a minute (ONB-3)
- [ ] She signs out and back in with Face ID / fingerprint; the app lock appears after 5 minutes in the background (AUTH-5–6)

**Replacing Flo**

- [ ] Her Flo JSON imports; the preview counts match what she sees in Flo; cycles and averages look right to her (J2, DATA-1)
- [ ] Undo import works on staging with a copy of the file
- [ ] She logs a period start, daily flow and the end; the cycle ring and calendar update within 2 seconds (J4, PER-1–5, CYC-1)
- [ ] The prediction shows a range, confidence and "based on N cycles"; the fertile window is labelled as an estimate (CYC-2–4)
- [ ] Postpartum mode hides predictions when chosen, and the Today card says so (MOD-2)
- [ ] "Period due" arrives two days before the range; "late" arrives once when late (J5)

**Every day**

- [ ] The check-in reminder arrives at her chosen time with the app closed; the check-in takes under 30 seconds (J3, CHK-1)
- [ ] Today shows her cycle, check-in state, appointments, doses and tasks in time order (TOD-1–6)
- [ ] A medication reminder arrives on time; she marks it taken from the notification or the confirm screen (J7, MED-3)
- [ ] An appointment reminder arrives the evening before and an hour before (J6, APT-2)
- [ ] Snooze works and the inbox lists every reminder sent (REM-3, REM-5)
- [ ] Night Garden appears automatically at night and is comfortable to read (J8, SET-2)
- [ ] A check-in logged in flight mode syncs when back online with no duplicate (J9, CHK-5)

**Her data is hers**

- [ ] Export downloads a ZIP she can open, with everything she logged (DATA-3)
- [ ] On staging, deleting an account removes every row after the grace period, and cancelling during grace restores access (DATA-4)
- [ ] The built app makes no request to any origin other than its own (NFR-6), checked with the browser network panel
- [ ] As admin, Ibrahim's console shows no health data (ADM-1)

**Operations**

- [ ] A restore drill into staging succeeded in under 4 hours and a restored record decrypts (NFR-5)
- [ ] Alerts fire when the API is stopped and when a backup is skipped (14.8)
- [ ] Master key, VAPID keys and backup cipher are in the password manager and the restore runbook was followed by reading it, not from memory

**Done**

- [ ] Four consecutive weeks with logs on at least 5 days each (success metric)
- [ ] She deletes her Flo account

### 17.1 Self-review: is the specification complete?

I checked each journey (J1–J11) against the requirements, data model, API, jobs and screens; each step has a screen (5.2), an endpoint (9.2), storage (7) and, where it involves time, a job (10.1). Gaps found during review and closed in this version: account recovery when all sign-in methods are lost (AUTH-8), notification copy (10.7), idempotency and challenge storage (7.5), restore-safe deletion (`pending_deletions`), consent storage, and the intra-cycle bleed prompt (8.1).

Three things this specification cannot settle in advance; each has an owner and a week:

1. **Flo's JSON structure** is not public. The importer is built from her real file (13.1). If the file lacks daily flow intensity, periods import as medium-flow ranges, which is acceptable for predictions.
2. **Her iPhone's behaviour with web push** must be proven early (M1 gate). If her iOS version is below 16.4, she must update before launch; if push proves unreliable for her, the fallback is the in-app inbox plus a native wrapper as a later phase.
3. **Whether she likes it.** The beta (15.4) exists for this; weekly feedback can reorder M5 "should" items.

If the specification is implemented as written, Zee can install the app, bring her history from Flo, log her cycle and day in under 30 seconds, get reliable reminders for her period, medications and appointments, see honest predictions, and leave Flo, which is the MVP's definition of done.

## 18. Risks, open questions and sources

The biggest risks are platform behaviour on her iPhone and the effort a solo builder can sustain; both are tested early and have fallbacks.

### 18.1 Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Web push unreliable on her iPhone | Medium | High | Prove in M1; in-app inbox; check-in reminder also shown as a Today banner; native wrapper later if needed |
| She stops logging | Medium | High | Under-30-second check-in, streaks, weekly feedback, no nagging copy |
| Scope creep into other life areas | High | Medium | Section 4.18 is binding until launch; new ideas go to a "Next" list |
| Solo builder runs out of evenings | Medium | High | Milestone gates; "should" items slip first; new baby means planning for slower weeks |
| Flo export delayed or unusable | Medium | Medium | Request in week 1; CSV fallback; she can enter recent cycles by hand from Flo's calendar |
| Losing the master key or backup cipher | Low | Severe | Password manager copies, restore drill, runbook |
| Prediction errors damage trust | Medium | Medium | Ranges, confidence, plain explanations, never contraception |
| Postpartum cycles very irregular | High | Low | Postpartum mode, exclusions, wider ranges |
| Security incident | Low | Severe | Section 12 controls; breach plan |

### 18.2 Open questions for Zee (answer before M1 ends)

- [ ] What should the app be called, and does she want to choose the icon?
- [ ] Which mode fits now: standard, postpartum, trying to conceive or avoiding pregnancy?
- [ ] Preferred check-in time and quiet hours?
- [ ] Which optional fields does she want (basal temperature, discharge, intimacy)?
- [ ] Does she want discreet lock-screen notifications?
- [ ] Which medications or supplements to set up first?
- [ ] Is she comfortable with the operator limitation in 12.1, or should client-held keys move up the roadmap?

### 18.3 Open questions for Ibrahim

- [ ] Domain name and VPS provider. - we can start with vercel/cloudfare , i'll update with domain name later
- [ ] Her iPhone's iOS version (must be 16.4+). - yes
- [ ] Where alerts should go (ntfy, email, both). - both

### 18.4 After the MVP (not part of this specification)

Client-held keys (local-first) so the operator cannot read her data; AI daily brief and assistant; career, home, family and finance modules; two-way calendar sync; Apple Health import; native wrapper if push needs it.

### 18.5 Sources

- [NHS: Periods](https://www.nhs.uk/conditions/periods/) — typical cycle length 21–35 days, periods 2–7 days, when to see a GP.
- [Flo Help Center: How do I export my data?](https://help.flo.health/hc/en-us/articles/360054973811-How-do-I-export-my-data) — export by request via Help → Contact us; TXT or JSON formats.
- [Pushpad: iOS special requirements for web push](https://pushpad.xyz/blog/ios-special-requirements-for-web-push-notifications) — Home Screen install and user-gesture permission requirements.
- [OneSignal: Web push for iOS](https://documentation.onesignal.com/docs/web-push-for-ios) — iOS 16.4+ web push setup for installed web apps.
