-- WO-TAI-SEC-SEARCHPATH-REM97-ISOLATED-R1-GATE-CLOSE-004
-- RLS environment setup — production-accurate role/policy reproduction
-- Run AFTER setup_isolated.sql
--
-- Source: production vwlahtguyggrhvslabax (queried read-only 2026-10-24)
-- Production policy snapshot:
--   runtime_inspection_review:      anon=SELECT policy only  / no anon grant
--   runtime_inspection_session:     anon=SELECT policy only  / no anon grant
--   runtime_operational_work_order: anon=SELECT policy only  / no anon grant
--   runtime_work_order_review:      anon=SELECT policy only  / no anon grant
--   construction_workers:           anon=ALL grant+policy / authenticated=ALL grant+policy
--   construction_sites:             anon=ALL grant+policy / authenticated=ALL grant+policy
--   factories:                      anon=ALL grant+policy / authenticated=ALL grant+policy
--   worker_registry:                anon=ALL grant+policy / authenticated=grant ONLY (no policy = RLS blocks)
--   subcontractors:                 anon=SELECT policy / authenticated=ALL policy
--   companies:                      service_role only (no anon/authenticated grant or policy)

SET search_path = public;

-- ─── ROLES ───────────────────────────────────────────────────────────────────

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
END;
$$;

GRANT USAGE ON SCHEMA public TO anon, authenticated;

-- ─── SERVICE_ROLE (GAP-002: direct role reproduction) ─────────────────────────
-- service_role in Supabase has BYPASSRLS privilege + runtime table grants.
-- Isolated reproduction: CREATE ROLE service_role BYPASSRLS to mirror production.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role BYPASSRLS NOLOGIN;
  END IF;
END;
$$;

GRANT USAGE ON SCHEMA public TO service_role;
-- service_role needs direct access to runtime tables (bypasses RLS)
GRANT SELECT, INSERT, UPDATE, DELETE ON runtime_inspection_review      TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON runtime_inspection_session     TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON runtime_operational_work_order TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON runtime_work_order_review      TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON runtime_obligation_registry    TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- ─── TABLE GRANTS ─────────────────────────────────────────────────────────────

-- B2B runtime tables: NO grant to anon/authenticated (matches production)

-- B3B tables: anon and authenticated get SELECT/INSERT/UPDATE/DELETE
GRANT SELECT, INSERT, UPDATE, DELETE ON construction_workers  TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON construction_sites    TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON factories             TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON worker_registry       TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON subcontractors        TO anon, authenticated;
-- companies: no anon/authenticated grant (matches production: service_role only)

-- sequence grants for tables with serial/default PKs
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;

-- ─── RLS ENABLE ───────────────────────────────────────────────────────────────

ALTER TABLE runtime_inspection_review         ENABLE ROW LEVEL SECURITY;
ALTER TABLE runtime_inspection_session        ENABLE ROW LEVEL SECURITY;
ALTER TABLE runtime_operational_work_order    ENABLE ROW LEVEL SECURITY;
ALTER TABLE runtime_work_order_review         ENABLE ROW LEVEL SECURITY;
ALTER TABLE construction_workers              ENABLE ROW LEVEL SECURITY;
ALTER TABLE construction_sites               ENABLE ROW LEVEL SECURITY;
ALTER TABLE factories                        ENABLE ROW LEVEL SECURITY;
ALTER TABLE worker_registry                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE subcontractors                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE companies                        ENABLE ROW LEVEL SECURITY;
ALTER TABLE runtime_obligation_registry      ENABLE ROW LEVEL SECURITY;

-- ─── RLS POLICIES — B2B runtime ───────────────────────────────────────────────
-- anon: SELECT only on all runtime tables (no INSERT/UPDATE/DELETE policy)
-- service_role equivalent: postgres superuser bypasses RLS

CREATE POLICY anon_select_runtime_inspection_review
  ON runtime_inspection_review FOR SELECT TO anon USING (true);

CREATE POLICY anon_select_runtime_inspection_session
  ON runtime_inspection_session FOR SELECT TO anon USING (true);

CREATE POLICY anon_select_runtime_operational_work_order
  ON runtime_operational_work_order FOR SELECT TO anon USING (true);

CREATE POLICY anon_select_runtime_work_order_review
  ON runtime_work_order_review FOR SELECT TO anon USING (true);

-- runtime_obligation_registry: postgres-only (no anon access, matches companies pattern)

-- ─── RLS POLICIES — B3B tables ────────────────────────────────────────────────

-- construction_workers: anon=ALL, authenticated=ALL
CREATE POLICY anon_all_construction_workers
  ON construction_workers TO anon USING (true) WITH CHECK (true);
CREATE POLICY authenticated_all_construction_workers
  ON construction_workers TO authenticated USING (true) WITH CHECK (true);

-- construction_sites: anon=ALL, authenticated=ALL
CREATE POLICY anon_all_construction_sites
  ON construction_sites TO anon USING (true) WITH CHECK (true);
CREATE POLICY authenticated_all_construction_sites
  ON construction_sites TO authenticated USING (true) WITH CHECK (true);

-- factories: anon=ALL, authenticated=ALL
CREATE POLICY anon_all_factories
  ON factories TO anon USING (true) WITH CHECK (true);
CREATE POLICY authenticated_all_factories
  ON factories TO authenticated USING (true) WITH CHECK (true);

-- worker_registry: anon=ALL, NO authenticated policy
-- (authenticated has grant but no RLS policy → blocked by RLS = production behavior)
CREATE POLICY anon_all_worker_registry
  ON worker_registry TO anon USING (true) WITH CHECK (true);
-- Note: authenticated deliberately has no policy here — mirrors production

-- subcontractors: anon=SELECT only, authenticated=ALL
CREATE POLICY anon_select_subcontractors
  ON subcontractors FOR SELECT TO anon USING (true);
CREATE POLICY authenticated_all_subcontractors
  ON subcontractors TO authenticated USING (true) WITH CHECK (true);

-- ─── VERIFY RLS SETUP ─────────────────────────────────────────────────────────
DO $$
DECLARE
  v_count int;
BEGIN
  -- Verify roles exist
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    RAISE EXCEPTION 'RLS SETUP FAILED: role anon not found';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    RAISE EXCEPTION 'RLS SETUP FAILED: role authenticated not found';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    RAISE EXCEPTION 'RLS SETUP FAILED: role service_role not found';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role' AND rolbypassrls = true) THEN
    RAISE EXCEPTION 'RLS SETUP FAILED: service_role does not have BYPASSRLS';
  END IF;

  -- Verify RLS enabled on runtime tables
  SELECT COUNT(*) INTO v_count FROM pg_class c
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public'
      AND c.relname IN (
        'runtime_inspection_review', 'runtime_work_order_review',
        'runtime_inspection_session', 'runtime_operational_work_order'
      )
      AND c.relrowsecurity = true;
  IF v_count <> 4 THEN
    RAISE EXCEPTION 'RLS SETUP FAILED: expected 4 runtime tables with RLS, found %', v_count;
  END IF;

  -- Verify RLS enabled on B3B tables
  SELECT COUNT(*) INTO v_count FROM pg_class c
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public'
      AND c.relname IN (
        'construction_workers', 'construction_sites',
        'factories', 'worker_registry', 'subcontractors'
      )
      AND c.relrowsecurity = true;
  IF v_count <> 5 THEN
    RAISE EXCEPTION 'RLS SETUP FAILED: expected 5 B3B tables with RLS, found %', v_count;
  END IF;

  -- Verify anon has no grant on runtime tables (permission denied expected)
  SELECT COUNT(*) INTO v_count FROM information_schema.role_table_grants
    WHERE table_schema = 'public'
      AND table_name IN (
        'runtime_inspection_review', 'runtime_work_order_review',
        'runtime_inspection_session', 'runtime_operational_work_order'
      )
      AND grantee = 'anon';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'RLS SETUP FAILED: anon has unexpected grants on runtime tables (count=%)', v_count;
  END IF;

  RAISE NOTICE '';
  RAISE NOTICE 'RLS SETUP OK:';
  RAISE NOTICE '  Roles: anon, authenticated, service_role created';
  RAISE NOTICE '  service_role: BYPASSRLS=true + runtime table grants (GAP-002)';
  RAISE NOTICE '  RLS enabled: 4 runtime tables + 5 B3B tables + companies + runtime_obligation_registry';
  RAISE NOTICE '  B2B: anon has NO grant on runtime tables (permission denied = production behavior)';
  RAISE NOTICE '  B2B: service_role has direct grants + BYPASSRLS on runtime tables';
  RAISE NOTICE '  B3B: anon=ALL grant+policy on construction_workers/sites/factories/worker_registry';
  RAISE NOTICE '  B3B: authenticated=ALL grant+policy on construction_workers/sites/factories';
  RAISE NOTICE '  B3B: worker_registry authenticated=grant only (no policy = RLS blocked = production behavior)';
  RAISE NOTICE '  B3B: subcontractors anon=SELECT, authenticated=ALL';
END;
$$;
