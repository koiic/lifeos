"""Schema, roles and row-level security (spec 7.1-7.5, CR-003).

The DDL below is the spec's 7.2 and 7.5 SQL, unchanged. Roles are created by migrations/roles.sql
(cluster-wide, run as superuser); this migration grants to them and creates the policies.

Revision ID: 0001_schema_roles_rls
Revises:
Create Date: 2026-10-07
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.util import await_only

revision: str = "0001_schema_roles_rls"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------------------------
# Spec 7.2 and 7.5, verbatim.
# ---------------------------------------------------------------------------------------------
SCHEMA = """
CREATE EXTENSION IF NOT EXISTS citext;

-- ---------- auth ----------
CREATE TABLE users (
  id               uuid PRIMARY KEY,
  email            citext NOT NULL UNIQUE,
  display_name     text   NOT NULL,
  role             text   NOT NULL DEFAULT 'user' CHECK (role IN ('user','admin')),
  timezone         text   NOT NULL DEFAULT 'Europe/London',
  locale           text   NOT NULL DEFAULT 'en-GB',
  dek_wrapped      bytea  NOT NULL,            -- user data key wrapped by the master key
  kek_version      int    NOT NULL DEFAULT 1,
  deletion_requested_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE user_settings (
  user_id          uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  theme            text NOT NULL DEFAULT 'system' CHECK (theme IN ('system','light','dark')),
  week_start       smallint NOT NULL DEFAULT 1,      -- 1 = Monday
  time_format      text NOT NULL DEFAULT '24h',
  temp_unit        text NOT NULL DEFAULT 'C',
  checkin_time     time NOT NULL DEFAULT '20:00',
  quiet_start      time NOT NULL DEFAULT '22:00',
  quiet_end        time NOT NULL DEFAULT '07:00',
  notif_prefs      jsonb NOT NULL DEFAULT '{"checkin":true,"period_due":true,"late_period":true,"medication":true,"appointment":true,"task":true}',
  discreet_notifications boolean NOT NULL DEFAULT false,
  optional_fields  jsonb NOT NULL DEFAULT '{"bbt":false,"discharge":false,"intimacy":false}',
  app_lock_pin_hash text,                           -- argon2id
  app_lock_timeout_s int NOT NULL DEFAULT 300,
  appointment_reminder_defaults jsonb NOT NULL DEFAULT '[{"type":"day_before_at","time":"19:00"},{"type":"minutes_before","minutes":60}]',
  onboarding_completed_at timestamptz,
  health_consent_at timestamptz,                    -- explicit consent screen (12.6)
  health_consent_version text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE invites (
  id uuid PRIMARY KEY,
  token_hash bytea NOT NULL UNIQUE,                 -- sha256 of a 32-byte random token
  email citext,
  created_by uuid NOT NULL REFERENCES users(id),
  expires_at timestamptz NOT NULL,
  used_at timestamptz, used_by uuid REFERENCES users(id),
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE webauthn_credentials (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  credential_id bytea NOT NULL UNIQUE,
  public_key bytea NOT NULL,
  sign_count bigint NOT NULL DEFAULT 0,
  transports text[] NOT NULL DEFAULT '{}',
  aaguid uuid,
  backup_eligible boolean NOT NULL DEFAULT false,
  backed_up boolean NOT NULL DEFAULT false,
  nickname text NOT NULL DEFAULT 'Passkey',
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz
);

CREATE TABLE password_credentials (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  password_hash text NOT NULL,                      -- argon2id, m=64MiB t=3 p=4
  totp_secret_enc bytea,
  totp_enabled boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recovery_codes (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash text NOT NULL,                          -- argon2id
  used_at timestamptz
);

CREATE TABLE sessions (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash bytea NOT NULL UNIQUE,                 -- sha256 of the cookie token
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  device_label text,                                -- parsed from user agent, e.g. 'iPhone Safari'
  ip_hash bytea                                     -- HMAC of IP, for rate limiting and audit
);
CREATE INDEX ON sessions (user_id) WHERE revoked_at IS NULL;

CREATE TABLE auth_events (
  id bigserial PRIMARY KEY,
  user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  kind text NOT NULL,          -- signin_passkey, signin_password, totp, recovery, register, revoke, pin_unlock
  success boolean NOT NULL,
  ip_hash bytea,
  at timestamptz NOT NULL DEFAULT now()
);

-- ---------- core ----------
CREATE TABLE people (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  payload_enc bytea NOT NULL,  -- {name, relationship, phone, email, address, birthday, notes}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);

CREATE TABLE events (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  module text NOT NULL DEFAULT 'health',
  kind text NOT NULL DEFAULT 'appointment',
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  all_day boolean NOT NULL DEFAULT false,
  timezone text NOT NULL,                           -- wall-clock zone for recurrence
  rrule text,                                       -- RFC 5545 RRULE, NULL = single
  rrule_until timestamptz,
  series_id uuid REFERENCES events(id),             -- set on an edited occurrence
  original_start timestamptz,                       -- which occurrence it overrides
  is_cancelled_occurrence boolean NOT NULL DEFAULT false,
  person_id uuid REFERENCES people(id),
  reminder_rules jsonb NOT NULL,                    -- copied from user defaults, e.g. [{"type":"day_before_at","time":"19:00"},{"type":"minutes_before","minutes":60}]
  payload_enc bytea NOT NULL,                       -- {title, location, notes}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz,
  CHECK (ends_at >= starts_at)
);
CREATE INDEX ON events (user_id, starts_at) WHERE deleted_at IS NULL;

CREATE TABLE tasks (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  due_at timestamptz,
  due_all_day boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','done')),
  completed_at timestamptz,
  rrule text,
  timezone text NOT NULL,
  remind_at timestamptz,
  payload_enc bytea NOT NULL,                       -- {title, notes}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);
CREATE INDEX ON tasks (user_id, status, due_at) WHERE deleted_at IS NULL;

CREATE TABLE notes (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  linked_type text CHECK (linked_type IN ('person','event')),
  linked_id uuid,
  payload_enc bytea NOT NULL,                       -- {title, body, tags[]}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);

-- ---------- health ----------
CREATE TABLE health_profile (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  payload_enc bytea NOT NULL,
  -- {mode: standard|postpartum|ttc|avoid, mode_started_on, usual_cycle_length, usual_period_length,
  --  last_period_hint, excluded_cycle_starts: [date], exclusion_reasons: {date: text}, forced_period_starts: [date]}
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE symptoms (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  system_key text,                                  -- e.g. 'cramps' for seeded ones, NULL for custom
  category text NOT NULL CHECK (category IN ('pain','digestion','skin','emotional','energy','other')),
  sort_order int NOT NULL DEFAULT 0,
  payload_enc bytea NOT NULL,                       -- {name}
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, system_key)
);

CREATE TABLE daily_logs (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date date NOT NULL,
  payload_enc bytea NOT NULL,
  -- {v:1, mood:1-5|null, energy:1-5|null, sleep_hours:number|null, symptom_ids:[uuid],
  --  flow: none|spotting|light|medium|heavy, discharge:str|null, bbt_c:number|null,
  --  intimacy:{logged:bool, protected:bool|null}|null, note:str|null, checkin_ms:int|null}
  import_id uuid,                                   -- set when created by an import (undo)
  client_updated_at timestamptz NOT NULL,           -- last-writer-wins for offline sync
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, date)
);

CREATE TABLE cycles (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  seq int NOT NULL,                                 -- 1 = oldest
  payload_enc bytea NOT NULL,
  -- {start_date, end_date|null, length_days|null, period_length_days, is_complete, excluded, exclusion_reason, postpartum}
  computed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, seq)
);

CREATE TABLE cycle_predictions (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  algorithm_version text NOT NULL,                  -- e.g. 'calendar-1.0'
  payload_enc bytea NOT NULL,
  -- {for_cycle_start, predicted_start, range_low, range_high, ovulation_est, fertile_start, fertile_end,
  --  confidence: high|medium|low|none, n_cycles, mean_len, sd_len, mean_period_len, suppressed_reason|null}
  created_at timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz
);
CREATE INDEX ON cycle_predictions (user_id, created_at DESC);

CREATE TABLE medications (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','archived')),
  as_needed boolean NOT NULL DEFAULT false,
  times_local time[] NOT NULL DEFAULT '{}',         -- e.g. {08:00,20:00}
  days_of_week smallint[] NOT NULL DEFAULT '{1,2,3,4,5,6,7}',
  start_date date NOT NULL,
  end_date date,
  timezone text NOT NULL,
  payload_enc bytea NOT NULL,                       -- {name, dose, notes}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);

CREATE TABLE medication_doses (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  medication_id uuid NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
  scheduled_at timestamptz,                         -- NULL for as-needed doses
  status text NOT NULL DEFAULT 'due' CHECK (status IN ('due','taken','skipped','missed')),
  taken_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (medication_id, scheduled_at)
);
CREATE INDEX ON medication_doses (user_id, scheduled_at);

-- ---------- notify ----------
CREATE TABLE reminders (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN ('checkin','period_due','late_period','medication','appointment','task','test')),
  source_type text,                                 -- event, task, medication_dose, prediction
  source_id uuid,
  fire_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','sending','sent','snoozed','done','cancelled','failed')),
  attempts smallint NOT NULL DEFAULT 0,
  sent_at timestamptz,
  dedupe_key text NOT NULL,                         -- e.g. 'dose:<id>', 'event:<id>:<occurrence>:<rule>'
  payload_enc bytea NOT NULL,                       -- {title, body, url, actions[]}
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, dedupe_key)
);
CREATE INDEX reminders_due_idx ON reminders (fire_at) WHERE status IN ('scheduled','snoozed');

CREATE TABLE push_subscriptions (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id uuid REFERENCES sessions(id) ON DELETE SET NULL,
  endpoint text NOT NULL UNIQUE,
  p256dh text NOT NULL,
  auth text NOT NULL,
  device_label text,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_success_at timestamptz,
  failure_count smallint NOT NULL DEFAULT 0,
  disabled_at timestamptz
);

-- ---------- data / platform ----------
CREATE TABLE imports (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source text NOT NULL CHECK (source IN ('flo_json','csv')),
  status text NOT NULL CHECK (status IN ('uploaded','parsed','failed','committed','undone')),
  file_enc bytea,                                   -- uploaded file, deleted 30 days after commit
  preview_enc bytea,                                -- parsed rows awaiting confirmation
  summary jsonb,                                    -- counts only: {days, periods, symptoms, skipped, conflicts, unmapped_keys}
  error text,
  created_at timestamptz NOT NULL DEFAULT now(), committed_at timestamptz, undone_at timestamptz
);

CREATE TABLE exports (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status text NOT NULL CHECK (status IN ('queued','building','ready','expired','failed')),
  storage_key text,                                 -- encrypted ZIP on the data volume
  created_at timestamptz NOT NULL DEFAULT now(), ready_at timestamptz, expires_at timestamptz, downloaded_at timestamptz
);

CREATE TABLE outbox_events (
  id bigserial PRIMARY KEY,
  topic text NOT NULL,          -- daily_log.flow_changed, health_profile.changed, event.changed, task.changed, medication.changed, settings.changed
  user_id uuid NOT NULL,
  body jsonb NOT NULL,          -- ids only, never health values
  created_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz
);
CREATE INDEX ON outbox_events (created_at) WHERE processed_at IS NULL;

CREATE TABLE audit_log (
  id bigserial PRIMARY KEY,
  actor_user_id uuid, actor_role text NOT NULL,
  action text NOT NULL,         -- admin.revoke_sessions, admin.invite_create, user.export, user.delete_request, user.import_commit
  target_user_id uuid,
  at timestamptz NOT NULL DEFAULT now(),
  ip_hash bytea
);

-- 7.5 Supporting tables
CREATE TABLE auth_challenges (               -- WebAuthn challenges, single use
  id uuid PRIMARY KEY,
  purpose text NOT NULL CHECK (purpose IN ('register','signin','add_passkey','reauth','unlock')),
  challenge bytea NOT NULL,
  user_id uuid REFERENCES users(id) ON DELETE CASCADE,
  invite_id uuid REFERENCES invites(id),
  expires_at timestamptz NOT NULL,            -- now() + 5 min
  used_at timestamptz
);

CREATE TABLE idempotency_keys (
  key uuid NOT NULL,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  method text NOT NULL, path text NOT NULL,
  request_hash bytea NOT NULL,                -- same key with a different body → 422
  response_status smallint NOT NULL,
  response_body_enc bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),   -- purged after 7 days
  PRIMARY KEY (user_id, key)
);

CREATE TABLE pending_deletions (             -- survives restores; no personal data
  user_id uuid PRIMARY KEY,
  delete_after timestamptz NOT NULL,
  completed_at timestamptz
);
"""

# Tables in creation order, for downgrade (dropped in reverse).
TABLES = [
    "users", "user_settings", "invites", "webauthn_credentials", "password_credentials",
    "recovery_codes", "sessions", "auth_events", "people", "events", "tasks", "notes",
    "health_profile", "symptoms", "daily_logs", "cycles", "cycle_predictions", "medications",
    "medication_doses", "reminders", "push_subscriptions", "imports", "exports", "outbox_events",
    "audit_log", "auth_challenges", "idempotency_keys", "pending_deletions",
]  # fmt: skip

# CR-003: system tables without RLS (auth and admin services only; no health data).
SYSTEM_TABLES = ["invites", "auth_challenges", "auth_events", "audit_log", "pending_deletions"]
# Every other table is user-owned: isolated on user_id (users: on id).
USER_TABLES = [t for t in TABLES if t not in SYSTEM_TABLES]

UPDATED_AT_TABLES = [
    "users", "user_settings", "password_credentials", "people", "events", "tasks", "notes",
    "health_profile", "symptoms", "daily_logs", "medications", "medication_doses", "reminders",
]  # fmt: skip

# An unset or reset (empty) app.user_id matches no rows instead of failing the uuid cast.
CURRENT_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"

TRIGGER_FUNCTION = """
CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  -- clock_timestamp(): two updates in one transaction get different versions.
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$$;
"""

# CR-003: pre-auth lookups. SECURITY DEFINER as the owner (who bypasses RLS), fixed search_path,
# executable only by lifeos_app, returning only what authentication needs.
AUTH_LOOKUPS = """
CREATE FUNCTION auth_find_credential(p_credential_id bytea)
RETURNS TABLE (user_id uuid, public_key bytea, sign_count bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT c.user_id, c.public_key, c.sign_count
  FROM public.webauthn_credentials c WHERE c.credential_id = p_credential_id
$$;

CREATE FUNCTION auth_find_session(p_token_hash bytea)
RETURNS TABLE (session_id uuid, user_id uuid, expires_at timestamptz, revoked boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT s.id, s.user_id, s.expires_at, s.revoked_at IS NOT NULL
  FROM public.sessions s WHERE s.token_hash = p_token_hash
$$;

CREATE FUNCTION auth_find_user_by_email(p_email text)
RETURNS TABLE (user_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT u.id FROM public.users u WHERE u.email = p_email::public.citext
$$;
"""
AUTH_FUNCTIONS = [
    "auth_find_credential(bytea)",
    "auth_find_session(bytea)",
    "auth_find_user_by_email(text)",
]

GRANTS = """
-- lifeos_app: CRUD on every table; RLS limits user tables to app.user_id.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO lifeos_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO lifeos_app;
REVOKE ALL ON alembic_version FROM lifeos_app;

-- lifeos_admin_ro (7.3): account columns, sessions, invites, auth events, audit log.
GRANT SELECT (id, email, display_name, role, created_at) ON users TO lifeos_admin_ro;
-- Sessions and invites without token_hash: the console never needs the hashes.
GRANT SELECT (id, user_id, created_at, last_seen_at, expires_at, revoked_at, device_label, ip_hash)
  ON sessions TO lifeos_admin_ro;
GRANT SELECT (id, email, created_by, expires_at, used_at, used_by, revoked_at, created_at)
  ON invites TO lifeos_admin_ro;
GRANT SELECT ON auth_events, audit_log TO lifeos_admin_ro;
CREATE POLICY admin_read ON users FOR SELECT TO lifeos_admin_ro USING (true);
CREATE POLICY admin_read ON sessions FOR SELECT TO lifeos_admin_ro USING (true);

-- lifeos_jobs (CR-003): finds work across users; the work runs as lifeos_app.
GRANT SELECT, UPDATE (processed_at) ON outbox_events TO lifeos_jobs;
GRANT SELECT (id, timezone) ON users TO lifeos_jobs;
GRANT SELECT (id, user_id, status, fire_at) ON reminders TO lifeos_jobs;
GRANT SELECT (id, user_id, status, scheduled_at) ON medication_doses TO lifeos_jobs;
GRANT SELECT ON pending_deletions TO lifeos_jobs;
CREATE POLICY jobs_all ON outbox_events TO lifeos_jobs USING (true) WITH CHECK (true);
CREATE POLICY jobs_read ON users FOR SELECT TO lifeos_jobs USING (true);
CREATE POLICY jobs_read ON reminders FOR SELECT TO lifeos_jobs USING (true);
CREATE POLICY jobs_read ON medication_doses FOR SELECT TO lifeos_jobs USING (true);

-- lifeos_dispatcher (10.3, CR-003): reminders, push subscriptions, settings, keys.
GRANT SELECT, UPDATE (status, attempts, sent_at, fire_at) ON reminders TO lifeos_dispatcher;
GRANT SELECT, UPDATE (last_success_at, failure_count, disabled_at) ON push_subscriptions
  TO lifeos_dispatcher;
-- Only what sending needs (quiet hours, preferences, discreet mode, check-in time): never the
-- app-lock PIN hash or consent columns.
GRANT SELECT (user_id, quiet_start, quiet_end, notif_prefs, discreet_notifications, checkin_time)
  ON user_settings TO lifeos_dispatcher;
GRANT SELECT (id, timezone, dek_wrapped) ON users TO lifeos_dispatcher;
CREATE POLICY dispatcher_all ON reminders TO lifeos_dispatcher USING (true) WITH CHECK (true);
CREATE POLICY dispatcher_all ON push_subscriptions TO lifeos_dispatcher
  USING (true) WITH CHECK (true);
CREATE POLICY dispatcher_read ON user_settings FOR SELECT TO lifeos_dispatcher USING (true);
CREATE POLICY dispatcher_read ON users FOR SELECT TO lifeos_dispatcher USING (true);
"""


def run_script(sql: str) -> None:
    """Run a multi-statement SQL script as written, on the migration's own connection and
    transaction. asyncpg's simple-query protocol allows several statements and does no
    bind-parameter parsing (the spec's JSON defaults contain ':true')."""
    driver = op.get_bind().connection.driver_connection
    await_only(driver.execute(sql))


def upgrade() -> None:
    run_script(SCHEMA)
    run_script(TRIGGER_FUNCTION)
    for table in UPDATED_AT_TABLES:
        op.execute(
            f"CREATE TRIGGER set_updated_at BEFORE UPDATE ON {table}"
            " FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    for table in USER_TABLES:
        key = "id" if table == "users" else "user_id"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY app_isolation ON {table} TO lifeos_app"
            f" USING ({key} = {CURRENT_USER}) WITH CHECK ({key} = {CURRENT_USER})"
        )
    run_script(AUTH_LOOKUPS)
    for function in AUTH_FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {function} TO lifeos_app")
    run_script(GRANTS)


def downgrade() -> None:
    for function in AUTH_FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {function}")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP EXTENSION IF EXISTS citext")
