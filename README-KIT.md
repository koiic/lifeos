# Life OS — Claude Code operating kit

This kit turns an empty repository into one where Claude Code builds the Life OS MVP by following
the specification and implementation plan to the letter, with every step verified.

## What is inside

| Path | Purpose |
| --- | --- |
| `CLAUDE.md` | Standing instructions Claude Code reads every session |
| `KICKOFF_PROMPT.md` | The prompts to paste: first session, every session, gates, problems |
| `docs/spec.md` | Specification (exported from Claude Docs) |
| `docs/plan.md` | Implementation plan (exported from Claude Docs) |
| `docs/requirements.json` | 90 requirement IDs with priority, milestone and owning task |
| `docs/plan/tasks.json` | 52 tasks with spec references, dependencies and "done when" |
| `docs/plan/PROGRESS.md` | Progress ledger (Claude Code changes it only via `scripts/ledger.py`) |
| `docs/plan/tasks/_TEMPLATE.md` | Per-task plan and evidence file |
| `docs/plan/gates/_TEMPLATE.md` | Milestone gate report |
| `docs/changes/` | Change requests (CR-001 already applied: Night outline contrast) |
| `docs/adr/` | ADR-0001 hybrid hosting, ADR-0002 Postgres job queue, ADR-0003 encrypted payloads |
| `design/tokens.json` | Every design value for Sorbet and Night Garden |
| `web/src/ui/tokens.css`, `tokens.ts` | Generated from tokens.json (do not edit) |
| `scripts/ledger.py` | Ledger tool: next, start, block, done (with evidence checks), gate-ready |
| `scripts/trace.py` | Requirement → test traceability and gate checks |
| `scripts/build_tokens.py`, `check_contrast.py` | Token generation and WCAG contrast checks |
| `Makefile` | The verification contract; T01 makes every target work |
| `.claude/settings.json` | Permissions and hooks |
| `.claude/hooks/` | Guard (protects sources of truth and secrets), post-edit lint, stop check, session context |
| `.claude/skills/` | `/next-task`, `/verify`, `/gate`, `/change-request`, `/drift-check` |
| `.claude/agents/` | `spec-reviewer`, `design-system-reviewer`, `security-reviewer`, `test-auditor` |

## Setup (once)

1. Install: git, Python 3.12+, `uv`, Node 20+, Docker, `gitleaks`, `pre-commit`, Claude Code.
2. Create an empty private GitHub repository `life-os` and clone it.
3. Copy the contents of this kit into the repository root (including the hidden `.claude/` folder).
4. Check the spec and plan exports are current: if either doc changed in Claude Docs after this kit
   was made, export it again to Markdown over `docs/spec.md` / `docs/plan.md`.
5. `git add -A && git commit -m "chore: add Life OS operating kit"` and push.
6. Open Claude Code in the repository root and paste the first-session prompt from
   `KICKOFF_PROMPT.md`.

## Your role (Ibrahim)

- Say "go" after reviewing Claude Code's cross-check and restatement.
- Answer change requests; update the spec in Claude Docs and re-export when you approve one.
- At each gate: read the report, do the human checks on your phone (and Zee's where listed), and
  sign off by setting the `GATE-Mx` row to `done` yourself.
- Weekly: run `/drift-check`.
- Week 1 jobs only you can do: request Zee's Flo export; buy the domain and add it to Cloudflare;
  create the VPS, Cloudflare Pages project, tunnel and object storage; generate the master key,
  VAPID keys and backup cipher and store them in your password manager.
