---
name: verify
description: Run the full verification suite (plan section 6.1) and summarise failures with their causes.
allowed-tools: Bash(make verify*) Bash(python3 scripts/trace.py *) Bash(python3 scripts/check_contrast.py) Bash(python3 scripts/build_tokens.py *)
---

Run, in order, and stop at nothing — collect every result:

1. `make verify`
2. `python3 scripts/trace.py`
3. If `web/` changed on this branch: `make verify-e2e`

Report a table: check, result, first failing line. For each failure, give the likely cause and the
fix you propose. Do not change spec, plan, tokens, requirements or the ledger to make a check pass;
fix the code, or raise `/change-request` if the check itself contradicts the spec.
