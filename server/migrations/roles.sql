-- Life OS database roles (spec 7.3 as amended by CR-003).
-- Roles are cluster-wide, so they are created here, not in a migration. Run as the database
-- superuser; safe to run again. The migrations grant privileges and create policies for them.
-- Staging/production (T15): give lifeos_owner, lifeos_app, lifeos_admin_ro, lifeos_admin (CR-022),
-- lifeos_jobs and lifeos_dispatcher LOGIN and passwords from secrets.
DO $$
DECLARE
  role_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY[
    'lifeos_owner', 'lifeos_app', 'lifeos_admin_ro', 'lifeos_admin', 'lifeos_jobs',
    'lifeos_dispatcher', 'lifeos_backup'
  ] LOOP
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN', role_name);
    END IF;
  END LOOP;
END
$$;

-- The owner runs migrations and owns the SECURITY DEFINER sign-in lookups; FORCE ROW LEVEL
-- SECURITY applies to owners too, so the owner must bypass RLS for those lookups to work. It is
-- not a superuser: it needs CREATE on this database (the trusted citext extension) and on schema
-- public, and nothing else.
ALTER ROLE lifeos_owner BYPASSRLS;
DO $$
BEGIN
  EXECUTE format('GRANT CREATE ON DATABASE %I TO lifeos_owner', current_database());
END
$$;
GRANT USAGE, CREATE ON SCHEMA public TO lifeos_owner;
-- Only the owner creates objects in public (also the PostgreSQL 15+ default; stated explicitly
-- because the SECURITY DEFINER lookups rely on it).
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
-- The roles reach objects in public explicitly, not through PUBLIC's default USAGE.
GRANT USAGE ON SCHEMA public
  TO lifeos_app, lifeos_admin_ro, lifeos_admin, lifeos_jobs, lifeos_dispatcher, lifeos_backup;

-- Spec 7.3: lifeos_backup has pg_read_all_data (see T03 Decisions: logical dumps also need
-- BYPASSRLS; decided in T45).
GRANT pg_read_all_data TO lifeos_backup;
