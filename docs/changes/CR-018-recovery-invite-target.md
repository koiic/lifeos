# CR-018 — How a recovery invite names the account it recovers

- Raised by: Claude Code during T08
- Date: 2026-10-08
- Status: proposed

## Problem

- Spec 4.1 AUTH-8: "The admin issues a recovery invite (single-use, 24 h) that lets her register
  a new passkey on her existing account. Issuing it revokes all sessions, pushes a notice to her
  registered devices, and is audited."
- Spec 9.2: `POST /admin/users/{id}/recovery-invite` → link to `/recover?token=`;
  `POST /auth/recover/options` and `/auth/recover/verify` "register a new passkey on the existing
  account and return fresh recovery codes."
- Spec 7.2 `invites (id, token_hash, email, created_by, expires_at, used_at, used_by,
  revoked_at, created_at)`: nothing marks an invite as a recovery invite or names its account.

A registration invite and a recovery invite would look the same. Using the email to infer the
account would let an ordinary 7-day invite that carries her email act as account recovery, and
would make `/register` and `/recover` accept each other's tokens.

## Options

1. **`invites.recover_user_id uuid REFERENCES users(id) ON DELETE CASCADE`.** Null for
   registration invites; set for recovery invites (expiry 24 h). `/register` refuses invites with
   it set; `/recover` accepts only those, for that account; `used_by` = that account. — impact:
   7.2 column; a migration; admin read grant unchanged (column added to `lifeos_admin_ro`'s
   invite columns).
2. **A separate `recovery_invites` table** (id, token_hash, user_id, created_by, expires_at,
   used_at, revoked_at). — impact: 7.2/7.5 new table, RLS decision, admin grants; duplicates most
   of `invites`.
3. **Infer from email + expiry** (an invite whose email belongs to an existing account is a
   recovery invite). — impact: none to the schema; ambiguous and unsafe as described above.

## Recommendation

Option 1: one column makes the purpose explicit and keeps one invite lifecycle (list, revoke,
expire) for the admin console.

## Impact if approved

- Spec sections to change: 7.2 (`invites.recover_user_id`), 9.2 (recover endpoints use only such
  invites; register refuses them), 7.3 (admin read grant includes the column).
- Plan / tasks.json / requirements.json / tokens: none.
- Tasks affected: T08 (blocked until decided), T44 (admin console lists invites by kind).

## Decision (Ibrahim)

Pending.
