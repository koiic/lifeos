---
name: next-task
description: Take the next task from the progress ledger and carry it through the full delivery loop (plan section 3). Use whenever starting or resuming implementation work.
disable-model-invocation: true
argument-hint: "[optional task id to resume, e.g. T07]"
allowed-tools: Bash(python3 scripts/ledger.py *) Bash(python3 scripts/trace.py *) Bash(make verify*) Bash(git status *) Bash(git diff *) Bash(git add *) Bash(git commit *) Bash(git switch *)
---

# Next task: the delivery loop

## Where we are

!`python3 scripts/ledger.py summary`

!`python3 scripts/ledger.py next`

If the output says STOP (a gate awaits sign-off) or shows no eligible task, report that to Ibrahim
and stop. Do not pick a different task. If $ARGUMENTS names a task, it must be the one shown above.

## The loop (follow every step, in order; do not skip or merge steps)

1. **Start.** `python3 scripts/ledger.py start <ID>` (skip if it says RESUME). Create a branch
   `git switch -c tNN-<short-name>` from `main` if not already on it.
2. **Re-read the sources.** Open `docs/spec.md` and read every section in "Spec sections" in full,
   plus the requirement rows (spec section 4) for each owned ID. Read the relevant parts of
   `docs/plan.md` (sections 4 and 5 always; others as cited). Do not rely on memory of earlier sessions.
3. **Write the task file.** Copy `docs/plan/tasks/_TEMPLATE.md` to `docs/plan/tasks/<ID>.md` and fill
   Scope (quote acceptance criteria verbatim), Plan, Tests, Out of scope. Leave Evidence as TODO.
   If anything needed is missing, ambiguous or contradictory in the spec, STOP and run
   `/change-request` instead of guessing.
4. **Tests first.** Write the tests listed in the task file, tagged with requirement IDs
   (`@pytest.mark.req("ID")` or a `[ID]` title prefix). Run them; confirm they fail for the expected
   reason. Paste the failing summary into the task file under Tests.
5. **Implement** the smallest change that makes them pass, following plan section 4 (standards) and
   section 5 (design system: tokens only, `src/ui` components only, both themes). No unrelated changes.
6. **Verify.** Run `make verify`. Fix until fully green. For web tasks also run `make verify-e2e`.
   Run `python3 scripts/trace.py --task <ID>`.
7. **Review.** Delegate to the reviewer agents with the task ID and diff (`git diff main...HEAD`):
   - `spec-reviewer` — always.
   - `design-system-reviewer` — if any file under `web/` changed.
   - `security-reviewer` — if auth, crypto, data export/import/deletion, notify, infra, RLS or migrations changed.
   - `test-auditor` — always.
   Fix every finding or answer it in the task file's Decisions section with a reason. Re-run step 6 after fixes.
8. **Evidence.** Fill the Evidence section of the task file: commit (after step 9, amend if needed),
   `make verify` summary, tests added and coverage of touched modules, trace output, each reviewer's
   verdict, screenshot/snapshot names for UI.
9. **Commit.** `git add -A && git commit -m "<type>(<scope>): <ID> <summary>"` (Conventional Commits).
   Then `python3 scripts/ledger.py done <ID> --commit <sha> --evidence "<one-line summary>"`.
   Commit the ledger update: `git commit -am "chore(plan): <ID> done"`.
10. **Report** to Ibrahim in five lines or fewer: what was built, the evidence, anything deferred.
    If this was the last task of a milestone, say so and suggest `/gate <Mx>`; do not start the next task.

Work on exactly one task per invocation.
