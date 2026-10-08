"""Shared per-session request counts for the 300 requests/min limit (spec 9.1, CR-016).

UNLOGGED: the counts are disposable one-minute windows, so they are not WAL-logged, are emptied
after a crash and never reach backups. A system table (no RLS, like `auth_challenges`): it holds
only a count per session id, and only the API's session check uses it.

Revision ID: 0004_session_request_counts
Revises: 0003_audit_append_only
Create Date: 2026-10-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_session_request_counts"
down_revision: str | None = "0003_audit_append_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNLOGGED TABLE session_request_counts (
          session_id uuid PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
          window_start timestamptz NOT NULL,
          count int NOT NULL
        )
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON session_request_counts TO lifeos_app")


def downgrade() -> None:
    op.execute("DROP TABLE session_request_counts")
