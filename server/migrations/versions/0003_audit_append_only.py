"""Audit tables append-only for the API; auth-event retention by the job role (CR-010).

`lifeos_app` keeps INSERT and SELECT on `audit_log` and `auth_events` but loses UPDATE and DELETE,
so a compromised API process cannot rewrite or erase its own trail (spec 12.1). `lifeos_jobs` may
delete auth events (10.1 `account.purge`: older than 1 year) and read `at` for that WHERE clause.
`auth_events.user_id ON DELETE SET NULL` still works: referential actions run as the table owner.

Revision ID: 0003_audit_append_only
Revises: 0002_jobs_schema
Create Date: 2026-10-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_audit_append_only"
down_revision: str | None = "0002_jobs_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("REVOKE UPDATE, DELETE ON audit_log, auth_events FROM lifeos_app")
    op.execute("GRANT SELECT (at), DELETE ON auth_events TO lifeos_jobs")


def downgrade() -> None:
    op.execute("REVOKE SELECT (at), DELETE ON auth_events FROM lifeos_jobs")
    op.execute("GRANT UPDATE, DELETE ON audit_log, auth_events TO lifeos_app")
