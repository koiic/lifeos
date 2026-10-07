# CR-011 — How master-key (KEK) versions are configured during rotation

- Raised by: Claude Code during T04
- Date: 2026-10-07
- Status: proposed

## Problem

- Spec 12.2 item 1: "Master key (KEK): 32 random bytes (`openssl rand -base64 32`), mounted as a
  Docker secret at `/run/secrets/lifeos_kek` … `users.kek_version` supports rotation."
- Spec 12.2 item 5: "KEK rotation: add the new key, re-wrap every DEK (seconds), retire the old key."
- Spec 14.3: one secret, `lifeos_kek` ("secret file | Master key (12.2)").

During a rotation the API and worker need the old key (to unwrap DEKs not yet re-wrapped) and the
new key (to wrap new DEKs and re-wrap old ones) at the same time, and they need each key's version
number to match `users.kek_version`. The spec defines one file holding one key and no version
number, so the app cannot know which version the key in `lifeos_kek` is, nor where the second key
lives during rotation. T04 builds the keyring in memory and tests rotation; T06 (first DEK created
at registration) must load it from secrets.

## Options

1. **One file, versioned lines.** `lifeos_kek` holds one line per key: `<version> <base64 key>`,
   e.g. `1 Zm9v…`. The highest version is current (wraps new DEKs); lower versions are kept only
   until every DEK is re-wrapped, then removed. A fresh install has the single line `1 <key>`.
   — impact: spec 12.2 item 1 and 14.3 wording; runbook "rotate the master key" (14.9).
2. **One file per version.** `lifeos_kek_v1`, `lifeos_kek_v2`, …; the highest present is current.
   — impact: 14.3 lists a pattern instead of one secret; Docker secrets must be declared per
   version in Compose (more edits during a rotation).
3. **`lifeos_kek` plus `KEK_VERSION` env and `lifeos_kek_previous`.** — impact: two secrets and an
   env var to keep consistent; easy to get the version wrong.

## Recommendation

Option 1: one secret to mount and back up, the version travels with the key, and a rotation is
"add a line, run the re-wrap job, delete the old line" — with these rules (from the T04 security
review), whichever option is chosen:

1. **Retired keys outlive the backups.** Backups taken before a rotation hold DEKs wrapped under
   the old KEK. Retired versions stay in the offline password manager for at least the backup
   retention period (35 days, spec 12.6), and a restore loads a keyring that includes them.
2. **Remove a version only when nothing uses it:** after the re-wrap job,
   `SELECT count(*) FROM users WHERE kek_version < <current>` must be 0.
3. **Strict parsing at start-up (T06):** lines match `^\d+ [A-Za-z0-9+/=]+$`; versions are unique
   integers ≥ 1; each key decodes to exactly 32 bytes; any error stops the process, and the error
   never echoes the offending line.
4. **Order of a rotation:** the API and worker load the file with the new version before the
   re-wrap job runs (otherwise unwraps of re-wrapped DEKs fail closed).

## Impact if approved

- Spec sections to change: 12.2 item 1 (file format), 14.3 (`lifeos_kek` description), 14.9 runbook
  note.
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T06 (blocked: loads the keyring at start-up), T15 (secret creation), T45
  (rotation rehearsal, spec 15.3).

## Decision (Ibrahim)

<approved / rejected, date, notes>. After approval: update the spec in Claude Docs, re-export it
to docs/spec.md with the version bumped, commit `docs: sync spec vN (CR-011)`.
