"""Recent auth per session and recovery invites (CR-017, CR-018).

- `sessions.reauth_at`: when this session last verified a passkey or password (sign-in or
  `/auth/reauth/verify`); recent auth = within 5 minutes (spec 9.2, 12.3).
- `invites.recover_user_id`: null for registration invites; the account a recovery invite
  recovers (AUTH-8).
The admin console reads both like the other columns of those tables (7.3).

Revision ID: 0006_reauth_and_recovery_invites
Revises: 0005_auth_event_indexes
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_reauth_and_recovery_invites"
down_revision: str | None = "0005_auth_event_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN reauth_at timestamptz")
    op.execute(
        "ALTER TABLE invites ADD COLUMN recover_user_id uuid REFERENCES users(id) ON DELETE CASCADE"
    )
    op.execute("GRANT SELECT (reauth_at) ON sessions TO lifeos_admin_ro")
    op.execute("GRANT SELECT (recover_user_id) ON invites TO lifeos_admin_ro")


def downgrade() -> None:
    op.execute("ALTER TABLE invites DROP COLUMN recover_user_id")
    op.execute("ALTER TABLE sessions DROP COLUMN reauth_at")
