"""Job queue: Procrastinate's tables in schema `jobs`, grants, and the outbox wake-up trigger
(spec 7.2 note, 7.3, 10.1).

The schema is Procrastinate 3.10.0's own `schema.sql`, vendored as
migrations/procrastinate_3_10_0_schema.sql so this revision never changes when the package is
upgraded (tests/jobs/test_registration.py fails if the installed version stops matching it). Its
SQL uses unqualified names, so it is installed with `search_path = jobs` and every Procrastinate
connection uses `search_path = jobs, public` (app/platform/jobs.py). Upgrading Procrastinate means a
new revision applying its `sql/migrations/*.sql` deltas under the same search_path.

Revision ID: 0002_jobs_schema
Revises: 0001_schema_roles_rls
Create Date: 2026-10-07
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op
from sqlalchemy.util import await_only

revision: str = "0002_jobs_schema"
down_revision: str | None = "0001_schema_roles_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROCRASTINATE_SCHEMA = Path(__file__).parents[1] / "procrastinate_3_10_0_schema.sql"

GRANTS = """
REVOKE ALL ON SCHEMA jobs FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA jobs FROM PUBLIC;

-- The worker (lifeos_jobs) fetches, runs, retries and prunes jobs: full use of the queue.
GRANT USAGE ON SCHEMA jobs TO lifeos_jobs;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA jobs TO lifeos_jobs;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA jobs TO lifeos_jobs;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA jobs TO lifeos_jobs;

-- The API (lifeos_app) may only queue jobs (on-request jobs and the outbox wake-up trigger): it
-- cannot read, fetch, finish, cancel or delete them.
GRANT USAGE ON SCHEMA jobs TO lifeos_app;
GRANT EXECUTE ON FUNCTION jobs.procrastinate_defer_jobs_v1(jobs.procrastinate_job_to_defer_v1[])
  TO lifeos_app;
GRANT INSERT ON jobs.procrastinate_jobs, jobs.procrastinate_events TO lifeos_app;
GRANT SELECT (id) ON jobs.procrastinate_jobs TO lifeos_app;
GRANT USAGE ON SEQUENCE jobs.procrastinate_jobs_id_seq, jobs.procrastinate_events_id_seq
  TO lifeos_app;

-- Spec 7.3 "job tables" for the admin console, narrowed: only aggregate queue health (depth and
-- oldest waiting job), never per-job rows, whose task names, locks and arguments identify a user
-- and when she logged (e.g. a rebuild after a period-flow change).
CREATE VIEW jobs.queue_stats AS
  SELECT j.status::text AS status, count(*) AS jobs, min(e.at) AS oldest_deferred_at
  FROM jobs.procrastinate_jobs j
  LEFT JOIN jobs.procrastinate_events e ON e.job_id = j.id AND e.type = 'deferred'
  GROUP BY j.status;
GRANT USAGE ON SCHEMA jobs TO lifeos_admin_ro;
GRANT SELECT ON jobs.queue_stats TO lifeos_admin_ro;
"""

# Spec 10.1 "outbox.relay … on NOTIFY": queue the relay in the same transaction as the event;
# Procrastinate's own NOTIFY then wakes the worker. The queueing lock keeps one relay waiting; only
# that lock's unique violation is swallowed (so writing an event never fails because a relay is
# already waiting), any other error is raised. pg_temp is last so temp tables cannot shadow.
WAKE_UP = """
CREATE FUNCTION public.outbox_queue_relay() RETURNS trigger
LANGUAGE plpgsql SET search_path = jobs, public, pg_temp AS $$
DECLARE
  violated text;
BEGIN
  PERFORM jobs.procrastinate_defer_jobs_v1(ARRAY[
    ROW('default', 'outbox.relay', 0, NULL, 'outbox.relay', '{}'::jsonb, NULL)
      ::jobs.procrastinate_job_to_defer_v1
  ]);
  RETURN NULL;
EXCEPTION WHEN unique_violation THEN
  GET STACKED DIAGNOSTICS violated = CONSTRAINT_NAME;
  IF violated = 'procrastinate_jobs_queueing_lock_idx_v1' THEN
    RETURN NULL;
  END IF;
  RAISE;
END
$$;
REVOKE ALL ON FUNCTION public.outbox_queue_relay() FROM PUBLIC;

CREATE TRIGGER outbox_queue_relay AFTER INSERT ON public.outbox_events
  FOR EACH STATEMENT EXECUTE FUNCTION public.outbox_queue_relay();
"""


def run_script(sql: str) -> None:
    """Run a multi-statement script on the migration's own connection and transaction."""
    driver = op.get_bind().connection.driver_connection
    await_only(driver.execute(sql))


def upgrade() -> None:
    run_script("CREATE SCHEMA jobs")
    run_script(
        "SET LOCAL search_path TO jobs;\n"
        + PROCRASTINATE_SCHEMA.read_text()
        + "\nSET LOCAL search_path TO public;"
    )
    run_script(GRANTS)
    run_script(WAKE_UP)


def downgrade() -> None:
    run_script("DROP TRIGGER IF EXISTS outbox_queue_relay ON public.outbox_events")
    run_script("DROP FUNCTION IF EXISTS public.outbox_queue_relay()")
    run_script("DROP SCHEMA IF EXISTS jobs CASCADE")
