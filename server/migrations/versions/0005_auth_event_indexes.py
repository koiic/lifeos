"""Indexes for the AUTH-7 lockout and TOTP replay queries on `auth_events` (T07).

Every attempt reads recent failures by IP hash and by account, and the last TOTP success by
account, while it holds its lockout locks; refused attempts are logged too, so the table can grow
quickly under attack. Partial indexes keep those reads short. No table or column changes.

Revision ID: 0005_auth_event_indexes
Revises: 0004_session_request_counts
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_auth_event_indexes"
down_revision: str | None = "0004_session_request_counts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX auth_events_failures_by_ip ON auth_events (ip_hash, at) WHERE NOT success"
    )
    op.execute(
        "CREATE INDEX auth_events_failures_by_user ON auth_events (user_id, at) WHERE NOT success"
    )
    op.execute(
        "CREATE INDEX auth_events_totp_successes ON auth_events (user_id, at)"
        " WHERE success AND kind IN ('totp', 'signin_password')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX auth_events_totp_successes")
    op.execute("DROP INDEX auth_events_failures_by_user")
    op.execute("DROP INDEX auth_events_failures_by_ip")
