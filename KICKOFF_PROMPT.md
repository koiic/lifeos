# Claude Code prompts for Life OS

## 1. First session (paste once, in the repository root)

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

## 2. Every later session

```text
/next-task
```

The SessionStart hook injects the current status. If you want more than one task in a sitting, say
"continue with the next task" after each report; Claude Code still finishes, verifies and records one
task before starting another, and stops at every gate.

## 3. Milestone gate

```text
/gate M1
```

Then read `docs/plan/gates/M1.md`, do the human checks in its section 4 on your phone (and Zee's when
listed), write the decision in section 6, and set `GATE-M1` to `done` in `docs/plan/PROGRESS.md`
yourself (the guard stops Claude Code from doing it). Commit `docs(plan): sign off gate M1`.

## 4. When something looks wrong

```text
/verify
```

```text
/change-request <short title>
```

```text
/drift-check
```

Run `/drift-check` weekly. After approving a change request: update the spec (or plan) in Claude
Docs, export it to Markdown over `docs/spec.md` (or `docs/plan.md`) with the version line bumped,
update `tasks.json`/`requirements.json`/`tokens.json` yourself if the CR says so, and commit
`docs: sync spec vN (CR-xxx)`. Then tell Claude Code to resume the blocked task.
