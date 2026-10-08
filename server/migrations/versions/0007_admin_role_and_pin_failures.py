"""The admin write role (CR-022) and per-session PIN tries (CR-021).

`lifeos_admin` is what admin endpoints that write connect as. It can create and revoke invites,
revoke sessions, spend pending sign-in challenges, append to the audit log and queue the
`auth.security_notice` outbox event — and nothing else: no health table, no credential, no key.
Admin reads keep `lifeos_admin_ro`.

`sessions.pin_failures` counts wrong app-lock PINs on that session (spec 9.2: "5 tries then full
sign-in required"); a good PIN or a passkey unlock resets it.

Revision ID: 0007_admin_role_and_pin_failures
Revises: 0006_reauth_and_recovery_invites
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.util import await_only

revision: str = "0007_admin_role_and_pin_failures"
down_revision: str | None = "0006_reauth_and_recovery_invites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS = """
GRANT SELECT (id, email, display_name, deleted_at) ON users TO lifeos_admin;
CREATE POLICY admin_write ON users FOR SELECT TO lifeos_admin USING (true);

GRANT SELECT (id, email, created_by, expires_at, used_at, used_by, revoked_at, created_at,
  recover_user_id), INSERT ON invites TO lifeos_admin;
GRANT UPDATE (revoked_at) ON invites TO lifeos_admin;

GRANT SELECT (id, user_id, revoked_at), UPDATE (revoked_at) ON sessions TO lifeos_admin;
CREATE POLICY admin_write_read ON sessions FOR SELECT TO lifeos_admin USING (true);
-- Revoke only: a revoked session can never be revived.
CREATE POLICY admin_write_revoke ON sessions FOR UPDATE TO lifeos_admin
  USING (true) WITH CHECK (revoked_at IS NOT NULL);

GRANT SELECT (user_id, purpose, invite_id, used_at), UPDATE (used_at) ON auth_challenges
  TO lifeos_admin;

GRANT INSERT ON audit_log TO lifeos_admin;
GRANT USAGE ON SEQUENCE audit_log_id_seq TO lifeos_admin;

GRANT INSERT (user_id, topic, body) ON outbox_events TO lifeos_admin;
GRANT USAGE ON SEQUENCE outbox_events_id_seq TO lifeos_admin;
CREATE POLICY admin_notice ON outbox_events FOR INSERT TO lifeos_admin
  WITH CHECK (topic = 'auth.security_notice');

-- invites and auth_challenges have no RLS (CR-003): a trigger stops lifeos_admin clearing
-- `revoked_at` / `used_at` (reviving an invite or un-spending a challenge).
CREATE FUNCTION public.admin_cannot_undo() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
BEGIN
  -- One branch per table: a row only has its own table's columns.
  IF current_user <> 'lifeos_admin' THEN
    RETURN NEW;
  END IF;
  IF TG_TABLE_NAME = 'invites' THEN
    IF OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS NULL THEN
      RAISE EXCEPTION 'admin cannot undo a revocation' USING ERRCODE = 'insufficient_privilege';
    END IF;
  ELSIF TG_TABLE_NAME = 'auth_challenges' THEN
    IF OLD.used_at IS NOT NULL AND NEW.used_at IS NULL THEN
      RAISE EXCEPTION 'admin cannot undo a revocation' USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  RETURN NEW;
END
$$;
-- Runs as whichever role updates the row, so it stays executable by all; it only refuses.
CREATE TRIGGER admin_cannot_undo BEFORE UPDATE ON invites
  FOR EACH ROW EXECUTE FUNCTION public.admin_cannot_undo();
CREATE TRIGGER admin_cannot_undo BEFORE UPDATE ON auth_challenges
  FOR EACH ROW EXECUTE FUNCTION public.admin_cannot_undo();

-- The outbox wake-up trigger queues the relay as the inserting role: queue-only, like lifeos_app.
GRANT USAGE ON SCHEMA jobs TO lifeos_admin;
GRANT EXECUTE ON FUNCTION jobs.procrastinate_defer_jobs_v1(jobs.procrastinate_job_to_defer_v1[])
  TO lifeos_admin;
GRANT INSERT ON jobs.procrastinate_jobs, jobs.procrastinate_events TO lifeos_admin;
GRANT SELECT (id) ON jobs.procrastinate_jobs TO lifeos_admin;
GRANT USAGE ON SEQUENCE jobs.procrastinate_jobs_id_seq, jobs.procrastinate_events_id_seq
  TO lifeos_admin;
"""

REVOKE = """
DROP TRIGGER admin_cannot_undo ON auth_challenges;
DROP TRIGGER admin_cannot_undo ON invites;
DROP FUNCTION public.admin_cannot_undo();
DROP POLICY admin_notice ON outbox_events;
DROP POLICY admin_write_revoke ON sessions;
DROP POLICY admin_write_read ON sessions;
DROP POLICY admin_write ON users;
REVOKE ALL ON users, invites, sessions, auth_challenges, audit_log, outbox_events FROM lifeos_admin;
REVOKE ALL ON SEQUENCE audit_log_id_seq, outbox_events_id_seq FROM lifeos_admin;
REVOKE ALL ON jobs.procrastinate_jobs, jobs.procrastinate_events FROM lifeos_admin;
REVOKE ALL ON SEQUENCE jobs.procrastinate_jobs_id_seq, jobs.procrastinate_events_id_seq
  FROM lifeos_admin;
REVOKE EXECUTE ON FUNCTION jobs.procrastinate_defer_jobs_v1(jobs.procrastinate_job_to_defer_v1[])
  FROM lifeos_admin;
REVOKE USAGE ON SCHEMA jobs FROM lifeos_admin;
"""


def run_script(sql: str) -> None:
    """Run a multi-statement script (with a function body) on the migration's connection."""
    driver = op.get_bind().connection.driver_connection
    await_only(driver.execute(sql))


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN pin_failures smallint NOT NULL DEFAULT 0")
    op.execute("GRANT SELECT (pin_failures) ON sessions TO lifeos_admin_ro")
    run_script(GRANTS)


def downgrade() -> None:
    run_script(REVOKE)
    op.execute("ALTER TABLE sessions DROP COLUMN pin_failures")
