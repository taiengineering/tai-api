-- WO-TAI-SEC-SEARCHPATH-REM97-ISOLATED-FINAL-R2-006
-- ROLE/RLS verification: B2B-07 + B3B-11 (R2 — GAP-001/002/003 addressed)
-- Run AFTER setup_isolated.sql + setup_rls.sql
-- Covers PHASE1 (pre-ALTER) and PHASE2 (post-ALTER)
--
-- ROLES TESTED:
--   anon          — Supabase anon key role (no grant on runtime tables)
--   authenticated — Supabase JWT-authenticated role (no grant on runtime tables)
--   service_role  — BYPASSRLS + runtime table grants (GAP-002: direct SET ROLE test)
--   postgres      — superuser, secondary evidence only
--
-- B2B-07:
--   R1: anon INSERT runtime_inspection_review → permission denied (no grant)
--   R2: anon INSERT runtime_work_order_review → permission denied (no grant)
--   R3: anon SELECT runtime_inspection_review → permission denied (no grant)
--   R4: postgres INSERT → trigger fires (secondary evidence)
--   R5: service_role INSERT → trigger fires (GAP-002: direct service_role test)
--   R6: authenticated INSERT → permission denied SQLSTATE=42501 (GAP-003)
--
-- B3B-11:
--   R1: anon INSERT construction_workers → trigger fires → registry created
--   R2: anon UPDATE construction_workers → trigger fires → registry updated
--   R3: authenticated INSERT → worker_registry RLS blocks (GAP-001: strict 42501 assertion)

SET search_path = public;

DO $$ BEGIN RAISE NOTICE '========================================'; END $$;
DO $$ BEGIN RAISE NOTICE 'ROLE/RLS VERIFICATION: B2B-07 + B3B-11 (R2)'; END $$;
DO $$ BEGIN RAISE NOTICE '========================================'; END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 1: PRE-ALTER role/RLS verification
-- ─────────────────────────────────────────────────────────────────────────────
DO $$ BEGIN RAISE NOTICE '--- PHASE 1: PRE-ALTER ROLE/RLS ---'; END $$;

-- ── B2B-07-R1: anon INSERT runtime_inspection_review → permission denied ──────
-- anon has no grant on runtime_inspection_review → "permission denied for table"
-- (RLS policy exists for SELECT, but no INSERT policy and no INSERT grant)
DO $$
DECLARE
  v_session_id   uuid;
  v_worker_id    uuid := gen_random_uuid();
  v_obligation   uuid;
  v_blocked      bool := false;
BEGIN
  -- Pre-insert supporting data as postgres (superuser)
  INSERT INTO runtime_obligation_registry (id, label) VALUES (gen_random_uuid(), 'rls-test') RETURNING id INTO v_obligation;
  INSERT INTO runtime_inspection_session
    (id, operational_work_order_id, worker_user_id, session_status, submission_status,
     evidence_status, review_status, offline_sync_status, source_trace)
  VALUES
    (gen_random_uuid(), gen_random_uuid(), v_worker_id,
     'REVIEW_PENDING','SUBMITTED','CONFIRMED','NOT_REVIEWED','ONLINE','RUNTIME_GENERATED')
  RETURNING id INTO v_session_id;

  -- Attempt INSERT as anon
  SET LOCAL ROLE anon;
  BEGIN
    INSERT INTO runtime_inspection_review
      (inspection_session_id, reviewer_id, review_action,
       previous_status, new_status, source_trace)
    VALUES
      (v_session_id, gen_random_uuid(), 'APPROVE',
       'REVIEW_PENDING', 'APPROVED', 'MANUAL_REVIEW');
  EXCEPTION WHEN insufficient_privilege THEN
    v_blocked := true;
  WHEN OTHERS THEN
    RAISE EXCEPTION 'B2B-07-R1 PHASE1 unexpected exception: % (SQLSTATE=%)', SQLERRM, SQLSTATE;
  END;
  RESET ROLE;

  IF NOT v_blocked THEN
    RAISE EXCEPTION 'B2B-07-R1 PHASE1 FAIL: anon INSERT was not blocked by permission denial';
  END IF;

  RAISE NOTICE 'B2B-07-R1 PHASE1 PASS: anon INSERT runtime_inspection_review → permission denied (no grant)';
END;
$$;

-- ── B2B-07-R2: anon INSERT runtime_work_order_review → permission denied ──────
DO $$
DECLARE
  v_wo_id      uuid;
  v_obligation uuid;
  v_blocked    bool := false;
BEGIN
  INSERT INTO runtime_obligation_registry (id, label) VALUES (gen_random_uuid(), 'rls-test') RETURNING id INTO v_obligation;
  INSERT INTO runtime_operational_work_order
    (id, obligation_registry_id, execution_type, assigned_user_id, work_status, source_trace)
  VALUES
    (gen_random_uuid(), v_obligation, 'SCHEDULED', gen_random_uuid(), 'SUBMITTED', 'RUNTIME_GENERATED')
  RETURNING id INTO v_wo_id;

  SET LOCAL ROLE anon;
  BEGIN
    INSERT INTO runtime_work_order_review
      (work_order_id, reviewer_id, review_action, review_comment,
       previous_status, new_status, source_trace)
    VALUES
      (v_wo_id, gen_random_uuid(), 'APPROVE', NULL,
       'SUBMITTED', 'APPROVED', 'MANUAL_REVIEW');
  EXCEPTION WHEN insufficient_privilege THEN
    v_blocked := true;
  WHEN OTHERS THEN
    RAISE EXCEPTION 'B2B-07-R2 PHASE1 unexpected exception: % (SQLSTATE=%)', SQLERRM, SQLSTATE;
  END;
  RESET ROLE;

  IF NOT v_blocked THEN
    RAISE EXCEPTION 'B2B-07-R2 PHASE1 FAIL: anon INSERT runtime_work_order_review was not blocked';
  END IF;

  RAISE NOTICE 'B2B-07-R2 PHASE1 PASS: anon INSERT runtime_work_order_review → permission denied (no grant)';
END;
$$;

-- ── B2B-07-R3: anon SELECT runtime_inspection_review → also denied (no grant) ──
-- Production: no anon GRANT on runtime tables at all (grant was revoked in SEC02/SEC03 hardening).
-- SELECT RLS policy exists in pg_policies but is unreachable without a grant.
-- Permission denied fires before RLS is checked.
DO $$
DECLARE
  v_count int;
  v_denied bool := false;
BEGIN
  SET LOCAL ROLE anon;
  BEGIN
    SELECT COUNT(*) INTO v_count FROM runtime_inspection_review;
  EXCEPTION WHEN insufficient_privilege THEN
    v_denied := true;
  WHEN OTHERS THEN
    RAISE EXCEPTION 'B2B-07-R3 PHASE1 unexpected: % (SQLSTATE=%)', SQLERRM, SQLSTATE;
  END;
  RESET ROLE;

  IF NOT v_denied THEN
    RAISE EXCEPTION 'B2B-07-R3 PHASE1 FAIL: anon SELECT succeeded — expected permission denied (no grant)';
  END IF;

  RAISE NOTICE 'B2B-07-R3 PHASE1 PASS: anon SELECT runtime_inspection_review → permission denied (no grant; SELECT RLS policy unreachable without grant)';
END;
$$;

-- ── B2B-07-R4: postgres (superuser) INSERT → trigger fires [secondary evidence] ─
-- postgres bypasses RLS. Kept as secondary evidence; service_role direct test is R5.
DO $$
DECLARE
  v_session_id   uuid;
  v_worker_id    uuid := gen_random_uuid();
  v_reviewer_id  uuid := gen_random_uuid();
  v_obligation   uuid;
  v_sess_status  text;
  v_rev_status   text;
BEGIN
  -- postgres already has superuser = bypasses RLS
  INSERT INTO runtime_obligation_registry (id, label) VALUES (gen_random_uuid(), 'rls-test') RETURNING id INTO v_obligation;
  INSERT INTO runtime_inspection_session
    (id, operational_work_order_id, worker_user_id, session_status, submission_status,
     evidence_status, review_status, offline_sync_status, source_trace)
  VALUES
    (gen_random_uuid(), gen_random_uuid(), v_worker_id,
     'REVIEW_PENDING','SUBMITTED','CONFIRMED','NOT_REVIEWED','ONLINE','RUNTIME_GENERATED')
  RETURNING id INTO v_session_id;

  INSERT INTO runtime_inspection_review
    (inspection_session_id, reviewer_id, review_action,
     previous_status, new_status, source_trace)
  VALUES
    (v_session_id, v_reviewer_id, 'APPROVE',
     'REVIEW_PENDING', 'APPROVED', 'MANUAL_REVIEW');

  SELECT session_status, review_status INTO v_sess_status, v_rev_status
  FROM runtime_inspection_session WHERE id = v_session_id;

  IF v_sess_status <> 'APPROVED' OR v_rev_status <> 'APPROVED' THEN
    RAISE EXCEPTION 'B2B-07-R4 PHASE1 FAIL: postgres INSERT trigger did not fire correctly (%, %)',
      v_sess_status, v_rev_status;
  END IF;

  RAISE NOTICE 'B2B-07-R4 PHASE1 PASS: postgres (superuser, secondary evidence) INSERT → trigger fires → session APPROVED';
END;
$$;

-- ── B2B-07-R5: service_role INSERT runtime_inspection_review → trigger fires ────
-- GAP-002: direct SET LOCAL ROLE service_role test.
-- service_role has BYPASSRLS + runtime table grants → trigger should fire correctly.
DO $$
DECLARE
  v_session_id   uuid;
  v_worker_id    uuid := gen_random_uuid();
  v_reviewer_id  uuid := gen_random_uuid();
  v_obligation   uuid;
  v_sess_status  text;
  v_rev_status   text;
BEGIN
  INSERT INTO runtime_obligation_registry (id, label) VALUES (gen_random_uuid(), 'rls-test') RETURNING id INTO v_obligation;
  INSERT INTO runtime_inspection_session
    (id, operational_work_order_id, worker_user_id, session_status, submission_status,
     evidence_status, review_status, offline_sync_status, source_trace)
  VALUES
    (gen_random_uuid(), gen_random_uuid(), v_worker_id,
     'REVIEW_PENDING','SUBMITTED','CONFIRMED','NOT_REVIEWED','ONLINE','RUNTIME_GENERATED')
  RETURNING id INTO v_session_id;

  SET LOCAL ROLE service_role;
  BEGIN
    INSERT INTO runtime_inspection_review
      (inspection_session_id, reviewer_id, review_action,
       previous_status, new_status, source_trace)
    VALUES
      (v_session_id, v_reviewer_id, 'APPROVE',
       'REVIEW_PENDING', 'APPROVED', 'MANUAL_REVIEW');
  EXCEPTION WHEN OTHERS THEN
    RESET ROLE;
    RAISE EXCEPTION 'B2B-07-R5 PHASE1 FAIL: service_role INSERT failed: % (SQLSTATE=%)', SQLERRM, SQLSTATE;
  END;
  RESET ROLE;

  SELECT session_status, review_status INTO v_sess_status, v_rev_status
  FROM runtime_inspection_session WHERE id = v_session_id;

  IF v_sess_status <> 'APPROVED' OR v_rev_status <> 'APPROVED' THEN
    RAISE EXCEPTION 'B2B-07-R5 PHASE1 FAIL: service_role INSERT trigger did not fire correctly (%, %)',
      v_sess_status, v_rev_status;
  END IF;

  RAISE NOTICE 'B2B-07-R5 PHASE1 PASS: service_role INSERT runtime_inspection_review → trigger fires → session APPROVED';
END;
$$;

-- ── B2B-07-R6: authenticated INSERT runtime_inspection_review → permission denied
-- GAP-003: authenticated also has no grant on runtime tables → SQLSTATE=42501
DO $$
DECLARE
  v_session_id uuid;
  v_worker_id  uuid := gen_random_uuid();
  v_obligation uuid;
  v_blocked    bool := false;
  v_sqlstate   text;
BEGIN
  INSERT INTO runtime_obligation_registry (id, label) VALUES (gen_random_uuid(), 'rls-test') RETURNING id INTO v_obligation;
  INSERT INTO runtime_inspection_session
    (id, operational_work_order_id, worker_user_id, session_status, submission_status,
     evidence_status, review_status, offline_sync_status, source_trace)
  VALUES
    (gen_random_uuid(), gen_random_uuid(), v_worker_id,
     'REVIEW_PENDING','SUBMITTED','CONFIRMED','NOT_REVIEWED','ONLINE','RUNTIME_GENERATED')
  RETURNING id INTO v_session_id;

  SET LOCAL ROLE authenticated;
  BEGIN
    INSERT INTO runtime_inspection_review
      (inspection_session_id, reviewer_id, review_action,
       previous_status, new_status, source_trace)
    VALUES
      (v_session_id, gen_random_uuid(), 'APPROVE',
       'REVIEW_PENDING', 'APPROVED', 'MANUAL_REVIEW');
  EXCEPTION WHEN insufficient_privilege THEN
    v_blocked  := true;
    v_sqlstate := SQLSTATE;
  WHEN OTHERS THEN
    RESET ROLE;
    RAISE EXCEPTION 'B2B-07-R6 PHASE1 unexpected SQLSTATE=% MSG=%', SQLSTATE, SQLERRM;
  END;
  RESET ROLE;

  IF NOT v_blocked THEN
    RAISE EXCEPTION 'B2B-07-R6 PHASE1 FAIL: authenticated INSERT runtime_inspection_review was not blocked';
  END IF;
  IF v_sqlstate <> '42501' THEN
    RAISE EXCEPTION 'B2B-07-R6 PHASE1 FAIL: expected SQLSTATE=42501, got %', v_sqlstate;
  END IF;

  RAISE NOTICE 'B2B-07-R6 PHASE1 PASS: authenticated INSERT runtime_inspection_review → permission denied (SQLSTATE=42501, no grant on runtime tables)';
END;
$$;

-- ── B3B-11-R1: anon INSERT construction_workers → trigger fires → registry created
DO $$
DECLARE
  v_co_id      uuid := gen_random_uuid();
  v_site_id    uuid;
  v_worker_id  uuid;
  v_reg_id     uuid;
BEGIN
  -- Pre-insert company + site as postgres (companies has no anon grant)
  INSERT INTO companies (id, name, company_code) VALUES (v_co_id, 'RLSTestCo1', 'RLS001');
  INSERT INTO construction_sites (id, company_id, site_name)
  VALUES (gen_random_uuid(), v_co_id, 'RLSSite1') RETURNING id INTO v_site_id;

  -- INSERT construction_worker as anon
  SET LOCAL ROLE anon;
  BEGIN
    INSERT INTO construction_workers
      (id, site_id, worker_name, worker_phone, worker_type)
    VALUES
      (gen_random_uuid(), v_site_id, 'RLSWorker1', '010-0000-0101', 'WORKER')
    RETURNING id INTO v_worker_id;
  EXCEPTION WHEN OTHERS THEN
    RESET ROLE;
    RAISE EXCEPTION 'B3B-11-R1 PHASE1 FAIL: anon INSERT construction_workers failed: % (SQLSTATE=%)',
      SQLERRM, SQLSTATE;
  END;
  RESET ROLE;

  -- Verify trigger fired: worker_registry_id backfilled
  SELECT worker_registry_id INTO v_reg_id FROM construction_workers WHERE id = v_worker_id;
  IF v_reg_id IS NULL THEN
    RAISE EXCEPTION 'B3B-11-R1 PHASE1 FAIL: trigger did not fire for anon INSERT (worker_registry_id=NULL)';
  END IF;

  -- Verify registry row exists
  IF NOT EXISTS (SELECT 1 FROM worker_registry WHERE id = v_reg_id) THEN
    RAISE EXCEPTION 'B3B-11-R1 PHASE1 FAIL: worker_registry row not found after anon INSERT';
  END IF;

  RAISE NOTICE 'B3B-11-R1 PHASE1 PASS: anon INSERT construction_workers → trigger fires → registry created (reg_id=%)', v_reg_id;
END;
$$;

-- ── B3B-11-R2: anon UPDATE construction_workers → trigger fires → registry updated
DO $$
DECLARE
  v_co_id      uuid := gen_random_uuid();
  v_site_id    uuid;
  v_worker_id  uuid;
  v_reg_name   text;
BEGIN
  INSERT INTO companies (id, name, company_code) VALUES (v_co_id, 'RLSTestCo2', 'RLS002');
  INSERT INTO construction_sites (id, company_id, site_name)
  VALUES (gen_random_uuid(), v_co_id, 'RLSSite2') RETURNING id INTO v_site_id;

  -- INSERT as anon first
  SET LOCAL ROLE anon;
  INSERT INTO construction_workers
    (id, site_id, worker_name, worker_phone, worker_type)
  VALUES
    (gen_random_uuid(), v_site_id, 'RLSWorker2_Old', '010-0000-0102', 'WORKER')
  RETURNING id INTO v_worker_id;
  RESET ROLE;

  -- UPDATE worker_name as anon
  SET LOCAL ROLE anon;
  BEGIN
    UPDATE construction_workers SET worker_name = 'RLSWorker2_New' WHERE id = v_worker_id;
  EXCEPTION WHEN OTHERS THEN
    RESET ROLE;
    RAISE EXCEPTION 'B3B-11-R2 PHASE1 FAIL: anon UPDATE construction_workers failed: %', SQLERRM;
  END;
  RESET ROLE;

  -- Verify registry updated
  SELECT w.name INTO v_reg_name
  FROM worker_registry w
  JOIN construction_workers c ON c.worker_registry_id = w.id
  WHERE c.id = v_worker_id;

  IF v_reg_name <> 'RLSWorker2_New' THEN
    RAISE EXCEPTION 'B3B-11-R2 PHASE1 FAIL: registry name not updated by anon UPDATE (got %)', v_reg_name;
  END IF;

  RAISE NOTICE 'B3B-11-R2 PHASE1 PASS: anon UPDATE construction_workers → trigger fires → registry name updated';
END;
$$;

-- ── B3B-11-R3: authenticated INSERT construction_workers → worker_registry RLS gap
-- authenticated has no RLS policy on worker_registry → trigger INSERT worker_registry blocked
-- This is PRODUCTION_RLS_OBSERVATION — not a test defect
-- GAP-001: tightened to require SQLSTATE=42501 and error from worker_registry specifically
DO $$
DECLARE
  v_co_id      uuid := gen_random_uuid();
  v_site_id    uuid;
  v_worker_id  uuid;
  v_blocked    bool := false;
  v_sqlstate   text;
  v_errmsg     text;
BEGIN
  INSERT INTO companies (id, name, company_code) VALUES (v_co_id, 'RLSTestCo3', 'RLS003');
  INSERT INTO construction_sites (id, company_id, site_name)
  VALUES (gen_random_uuid(), v_co_id, 'RLSSite3') RETURNING id INTO v_site_id;

  SET LOCAL ROLE authenticated;
  BEGIN
    INSERT INTO construction_workers
      (id, site_id, worker_name, worker_phone, worker_type)
    VALUES
      (gen_random_uuid(), v_site_id, 'RLSWorker3', '010-0000-0103', 'WORKER')
    RETURNING id INTO v_worker_id;
  EXCEPTION WHEN insufficient_privilege THEN
    v_blocked  := true;
    v_sqlstate := SQLSTATE;
    v_errmsg   := SQLERRM;
  WHEN OTHERS THEN
    RESET ROLE;
    RAISE EXCEPTION 'B3B-11-R3 PHASE1 unexpected SQLSTATE=% MSG=%', SQLSTATE, SQLERRM;
  END;
  RESET ROLE;

  IF NOT v_blocked THEN
    RAISE EXCEPTION 'B3B-11-R3 PHASE1 UNEXPECTED: authenticated INSERT succeeded — worker_registry policy gap expected to block trigger';
  END IF;
  IF v_sqlstate <> '42501' THEN
    RAISE EXCEPTION 'B3B-11-R3 PHASE1 FAIL: expected SQLSTATE=42501, got %', v_sqlstate;
  END IF;
  IF v_errmsg NOT LIKE '%worker_registry%' THEN
    RAISE EXCEPTION 'B3B-11-R3 PHASE1 FAIL: expected error from worker_registry, got: %', v_errmsg;
  END IF;

  RAISE NOTICE 'B3B-11-R3 PHASE1 PRODUCTION_RLS_OBSERVATION: authenticated INSERT construction_workers → trigger INSERT worker_registry blocked (SQLSTATE=42501, MSG=%) — no authenticated RLS policy on worker_registry = production behavior', v_errmsg;
END;
$$;

DO $$ BEGIN RAISE NOTICE '--- PHASE 1 ROLE/RLS COMPLETE ---'; END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ALTER FUNCTION (same as run_regression.sql — applying search_path)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$ BEGIN RAISE NOTICE '--- APPLYING ALTER FUNCTION (search_path fix) ---'; END $$;

ALTER FUNCTION public.fn_validate_inspection_reviewer()
  SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.fn_validate_reviewer_not_assignee()
  SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.sync_construction_notification_time()
  SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.sync_construction_worker_to_registry()
  SET search_path = pg_catalog, public, pg_temp;
ALTER FUNCTION public.sync_factory_notification_time_to_cs()
  SET search_path = pg_catalog, public, pg_temp;

DO $$ BEGIN RAISE NOTICE '--- ALTER FUNCTION COMPLETE ---'; END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 2: POST-ALTER role/RLS verification — same assertions
-- ─────────────────────────────────────────────────────────────────────────────
DO $$ BEGIN RAISE NOTICE '--- PHASE 2: POST-ALTER ROLE/RLS ---'; END $$;

-- ── B2B-07-R1 POST ────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_session_id   uuid;
  v_worker_id    uuid := gen_random_uuid();
  v_obligation   uuid;
  v_blocked      bool := false;
BEGIN
  INSERT INTO runtime_obligation_registry (id, label) VALUES (gen_random_uuid(), 'rls-test') RETURNING id INTO v_obligation;
  INSERT INTO runtime_inspection_session
    (id, operational_work_order_id, worker_user_id, session_status, submission_status,
     evidence_status, review_status, offline_sync_status, source_trace)
  VALUES
    (gen_random_uuid(), gen_random_uuid(), v_worker_id,
     'REVIEW_PENDING','SUBMITTED','CONFIRMED','NOT_REVIEWED','ONLINE','RUNTIME_GENERATED')
  RETURNING id INTO v_session_id;

  SET LOCAL ROLE anon;
  BEGIN
    INSERT INTO runtime_inspection_review
      (inspection_session_id, reviewer_id, review_action,
       previous_status, new_status, source_trace)
    VALUES
      (v_session_id, gen_random_uuid(), 'APPROVE',
       'REVIEW_PENDING', 'APPROVED', 'MANUAL_REVIEW');
  EXCEPTION WHEN insufficient_privilege THEN
    v_blocked := true;
  WHEN OTHERS THEN
    RAISE EXCEPTION 'B2B-07-R1 PHASE2 unexpected exception: % (SQLSTATE=%)', SQLERRM, SQLSTATE;
  END;
  RESET ROLE;

  IF NOT v_blocked THEN
    RAISE EXCEPTION 'B2B-07-R1 PHASE2 FAIL: anon INSERT was not blocked after ALTER';
  END IF;

  RAISE NOTICE 'B2B-07-R1 PHASE2 PASS: anon INSERT runtime_inspection_review → still permission denied after ALTER';
END;
$$;

-- ── B2B-07-R2 POST ────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_wo_id      uuid;
  v_obligation uuid;
  v_blocked    bool := false;
BEGIN
  INSERT INTO runtime_obligation_registry (id, label) VALUES (gen_random_uuid(), 'rls-test') RETURNING id INTO v_obligation;
  INSERT INTO runtime_operational_work_order
    (id, obligation_registry_id, execution_type, assigned_user_id, work_status, source_trace)
  VALUES
    (gen_random_uuid(), v_obligation, 'SCHEDULED', gen_random_uuid(), 'SUBMITTED', 'RUNTIME_GENERATED')
  RETURNING id INTO v_wo_id;

  SET LOCAL ROLE anon;
  BEGIN
    INSERT INTO runtime_work_order_review
      (work_order_id, reviewer_id, review_action, review_comment,
       previous_status, new_status, source_trace)
    VALUES
      (v_wo_id, gen_random_uuid(), 'APPROVE', NULL,
       'SUBMITTED', 'APPROVED', 'MANUAL_REVIEW');
  EXCEPTION WHEN insufficient_privilege THEN
    v_blocked := true;
  WHEN OTHERS THEN
    RAISE EXCEPTION 'B2B-07-R2 PHASE2 unexpected exception: % (SQLSTATE=%)', SQLERRM, SQLSTATE;
  END;
  RESET ROLE;

  IF NOT v_blocked THEN
    RAISE EXCEPTION 'B2B-07-R2 PHASE2 FAIL: anon INSERT runtime_work_order_review was not blocked after ALTER';
  END IF;

  RAISE NOTICE 'B2B-07-R2 PHASE2 PASS: anon INSERT runtime_work_order_review → still permission denied after ALTER';
END;
$$;

-- ── B2B-07-R3 POST ────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_count int;
  v_denied bool := false;
BEGIN
  SET LOCAL ROLE anon;
  BEGIN
    SELECT COUNT(*) INTO v_count FROM runtime_inspection_review;
  EXCEPTION WHEN insufficient_privilege THEN
    v_denied := true;
  WHEN OTHERS THEN
    RAISE EXCEPTION 'B2B-07-R3 PHASE2 unexpected: % (SQLSTATE=%)', SQLERRM, SQLSTATE;
  END;
  RESET ROLE;

  IF NOT v_denied THEN
    RAISE EXCEPTION 'B2B-07-R3 PHASE2 FAIL: anon SELECT succeeded after ALTER — expected permission denied (no grant)';
  END IF;

  RAISE NOTICE 'B2B-07-R3 PHASE2 PASS: anon SELECT runtime_inspection_review → still permission denied after ALTER (no grant)';
END;
$$;

-- ── B2B-07-R4 POST ────────────────────────────────────────────────────────────
-- postgres superuser, secondary evidence
DO $$
DECLARE
  v_session_id   uuid;
  v_worker_id    uuid := gen_random_uuid();
  v_reviewer_id  uuid := gen_random_uuid();
  v_obligation   uuid;
  v_sess_status  text;
  v_rev_status   text;
BEGIN
  INSERT INTO runtime_obligation_registry (id, label) VALUES (gen_random_uuid(), 'rls-test') RETURNING id INTO v_obligation;
  INSERT INTO runtime_inspection_session
    (id, operational_work_order_id, worker_user_id, session_status, submission_status,
     evidence_status, review_status, offline_sync_status, source_trace)
  VALUES
    (gen_random_uuid(), gen_random_uuid(), v_worker_id,
     'REVIEW_PENDING','SUBMITTED','CONFIRMED','NOT_REVIEWED','ONLINE','RUNTIME_GENERATED')
  RETURNING id INTO v_session_id;

  INSERT INTO runtime_inspection_review
    (inspection_session_id, reviewer_id, review_action,
     previous_status, new_status, source_trace)
  VALUES
    (v_session_id, v_reviewer_id, 'APPROVE',
     'REVIEW_PENDING', 'APPROVED', 'MANUAL_REVIEW');

  SELECT session_status, review_status INTO v_sess_status, v_rev_status
  FROM runtime_inspection_session WHERE id = v_session_id;

  IF v_sess_status <> 'APPROVED' OR v_rev_status <> 'APPROVED' THEN
    RAISE EXCEPTION 'B2B-07-R4 PHASE2 FAIL: postgres INSERT trigger did not fire correctly after ALTER (%, %)',
      v_sess_status, v_rev_status;
  END IF;

  RAISE NOTICE 'B2B-07-R4 PHASE2 PASS: postgres (superuser, secondary evidence) INSERT → trigger still fires after ALTER → session APPROVED';
END;
$$;

-- ── B2B-07-R5 POST ────────────────────────────────────────────────────────────
-- GAP-002: service_role direct test (post-ALTER)
DO $$
DECLARE
  v_session_id   uuid;
  v_worker_id    uuid := gen_random_uuid();
  v_reviewer_id  uuid := gen_random_uuid();
  v_obligation   uuid;
  v_sess_status  text;
  v_rev_status   text;
BEGIN
  INSERT INTO runtime_obligation_registry (id, label) VALUES (gen_random_uuid(), 'rls-test') RETURNING id INTO v_obligation;
  INSERT INTO runtime_inspection_session
    (id, operational_work_order_id, worker_user_id, session_status, submission_status,
     evidence_status, review_status, offline_sync_status, source_trace)
  VALUES
    (gen_random_uuid(), gen_random_uuid(), v_worker_id,
     'REVIEW_PENDING','SUBMITTED','CONFIRMED','NOT_REVIEWED','ONLINE','RUNTIME_GENERATED')
  RETURNING id INTO v_session_id;

  SET LOCAL ROLE service_role;
  BEGIN
    INSERT INTO runtime_inspection_review
      (inspection_session_id, reviewer_id, review_action,
       previous_status, new_status, source_trace)
    VALUES
      (v_session_id, v_reviewer_id, 'APPROVE',
       'REVIEW_PENDING', 'APPROVED', 'MANUAL_REVIEW');
  EXCEPTION WHEN OTHERS THEN
    RESET ROLE;
    RAISE EXCEPTION 'B2B-07-R5 PHASE2 FAIL: service_role INSERT failed after ALTER: % (SQLSTATE=%)', SQLERRM, SQLSTATE;
  END;
  RESET ROLE;

  SELECT session_status, review_status INTO v_sess_status, v_rev_status
  FROM runtime_inspection_session WHERE id = v_session_id;

  IF v_sess_status <> 'APPROVED' OR v_rev_status <> 'APPROVED' THEN
    RAISE EXCEPTION 'B2B-07-R5 PHASE2 FAIL: service_role INSERT trigger did not fire after ALTER (%, %)',
      v_sess_status, v_rev_status;
  END IF;

  RAISE NOTICE 'B2B-07-R5 PHASE2 PASS: service_role INSERT runtime_inspection_review → trigger still fires after ALTER → session APPROVED';
END;
$$;

-- ── B2B-07-R6 POST ────────────────────────────────────────────────────────────
-- GAP-003: authenticated blocked post-ALTER
DO $$
DECLARE
  v_session_id uuid;
  v_worker_id  uuid := gen_random_uuid();
  v_obligation uuid;
  v_blocked    bool := false;
  v_sqlstate   text;
BEGIN
  INSERT INTO runtime_obligation_registry (id, label) VALUES (gen_random_uuid(), 'rls-test') RETURNING id INTO v_obligation;
  INSERT INTO runtime_inspection_session
    (id, operational_work_order_id, worker_user_id, session_status, submission_status,
     evidence_status, review_status, offline_sync_status, source_trace)
  VALUES
    (gen_random_uuid(), gen_random_uuid(), v_worker_id,
     'REVIEW_PENDING','SUBMITTED','CONFIRMED','NOT_REVIEWED','ONLINE','RUNTIME_GENERATED')
  RETURNING id INTO v_session_id;

  SET LOCAL ROLE authenticated;
  BEGIN
    INSERT INTO runtime_inspection_review
      (inspection_session_id, reviewer_id, review_action,
       previous_status, new_status, source_trace)
    VALUES
      (v_session_id, gen_random_uuid(), 'APPROVE',
       'REVIEW_PENDING', 'APPROVED', 'MANUAL_REVIEW');
  EXCEPTION WHEN insufficient_privilege THEN
    v_blocked  := true;
    v_sqlstate := SQLSTATE;
  WHEN OTHERS THEN
    RESET ROLE;
    RAISE EXCEPTION 'B2B-07-R6 PHASE2 unexpected SQLSTATE=% MSG=%', SQLSTATE, SQLERRM;
  END;
  RESET ROLE;

  IF NOT v_blocked THEN
    RAISE EXCEPTION 'B2B-07-R6 PHASE2 FAIL: authenticated INSERT runtime_inspection_review was not blocked after ALTER';
  END IF;
  IF v_sqlstate <> '42501' THEN
    RAISE EXCEPTION 'B2B-07-R6 PHASE2 FAIL: expected SQLSTATE=42501, got %', v_sqlstate;
  END IF;

  RAISE NOTICE 'B2B-07-R6 PHASE2 PASS: authenticated INSERT runtime_inspection_review → still permission denied after ALTER (SQLSTATE=42501)';
END;
$$;

-- ── B3B-11-R1 POST ────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_co_id      uuid := gen_random_uuid();
  v_site_id    uuid;
  v_worker_id  uuid;
  v_reg_id     uuid;
BEGIN
  INSERT INTO companies (id, name, company_code) VALUES (v_co_id, 'RLSTestCo4', 'RLS004');
  INSERT INTO construction_sites (id, company_id, site_name)
  VALUES (gen_random_uuid(), v_co_id, 'RLSSite4') RETURNING id INTO v_site_id;

  SET LOCAL ROLE anon;
  BEGIN
    INSERT INTO construction_workers
      (id, site_id, worker_name, worker_phone, worker_type)
    VALUES
      (gen_random_uuid(), v_site_id, 'RLSWorker4', '010-0000-0104', 'WORKER')
    RETURNING id INTO v_worker_id;
  EXCEPTION WHEN OTHERS THEN
    RESET ROLE;
    RAISE EXCEPTION 'B3B-11-R1 PHASE2 FAIL: anon INSERT construction_workers failed after ALTER: %', SQLERRM;
  END;
  RESET ROLE;

  SELECT worker_registry_id INTO v_reg_id FROM construction_workers WHERE id = v_worker_id;
  IF v_reg_id IS NULL THEN
    RAISE EXCEPTION 'B3B-11-R1 PHASE2 FAIL: trigger did not fire for anon INSERT after ALTER';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM worker_registry WHERE id = v_reg_id) THEN
    RAISE EXCEPTION 'B3B-11-R1 PHASE2 FAIL: worker_registry row not found after anon INSERT post-ALTER';
  END IF;

  RAISE NOTICE 'B3B-11-R1 PHASE2 PASS: anon INSERT construction_workers → trigger still fires after ALTER → registry created';
END;
$$;

-- ── B3B-11-R2 POST ────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_co_id      uuid := gen_random_uuid();
  v_site_id    uuid;
  v_worker_id  uuid;
  v_reg_name   text;
BEGIN
  INSERT INTO companies (id, name, company_code) VALUES (v_co_id, 'RLSTestCo5', 'RLS005');
  INSERT INTO construction_sites (id, company_id, site_name)
  VALUES (gen_random_uuid(), v_co_id, 'RLSSite5') RETURNING id INTO v_site_id;

  SET LOCAL ROLE anon;
  INSERT INTO construction_workers
    (id, site_id, worker_name, worker_phone, worker_type)
  VALUES
    (gen_random_uuid(), v_site_id, 'RLSWorker5_Old', '010-0000-0105', 'WORKER')
  RETURNING id INTO v_worker_id;
  RESET ROLE;

  SET LOCAL ROLE anon;
  BEGIN
    UPDATE construction_workers SET worker_name = 'RLSWorker5_New' WHERE id = v_worker_id;
  EXCEPTION WHEN OTHERS THEN
    RESET ROLE;
    RAISE EXCEPTION 'B3B-11-R2 PHASE2 FAIL: anon UPDATE construction_workers failed after ALTER: %', SQLERRM;
  END;
  RESET ROLE;

  SELECT w.name INTO v_reg_name
  FROM worker_registry w
  JOIN construction_workers c ON c.worker_registry_id = w.id
  WHERE c.id = v_worker_id;

  IF v_reg_name <> 'RLSWorker5_New' THEN
    RAISE EXCEPTION 'B3B-11-R2 PHASE2 FAIL: registry name not updated by anon UPDATE after ALTER (got %)', v_reg_name;
  END IF;

  RAISE NOTICE 'B3B-11-R2 PHASE2 PASS: anon UPDATE construction_workers → trigger still fires after ALTER → registry updated';
END;
$$;

-- ── B3B-11-R3 POST ────────────────────────────────────────────────────────────
-- GAP-001: tightened to require SQLSTATE=42501 and error from worker_registry
DO $$
DECLARE
  v_co_id      uuid := gen_random_uuid();
  v_site_id    uuid;
  v_worker_id  uuid;
  v_blocked    bool := false;
  v_sqlstate   text;
  v_errmsg     text;
BEGIN
  INSERT INTO companies (id, name, company_code) VALUES (v_co_id, 'RLSTestCo6', 'RLS006');
  INSERT INTO construction_sites (id, company_id, site_name)
  VALUES (gen_random_uuid(), v_co_id, 'RLSSite6') RETURNING id INTO v_site_id;

  SET LOCAL ROLE authenticated;
  BEGIN
    INSERT INTO construction_workers
      (id, site_id, worker_name, worker_phone, worker_type)
    VALUES
      (gen_random_uuid(), v_site_id, 'RLSWorker6', '010-0000-0106', 'WORKER')
    RETURNING id INTO v_worker_id;
  EXCEPTION WHEN insufficient_privilege THEN
    v_blocked  := true;
    v_sqlstate := SQLSTATE;
    v_errmsg   := SQLERRM;
  WHEN OTHERS THEN
    RESET ROLE;
    RAISE EXCEPTION 'B3B-11-R3 PHASE2 unexpected SQLSTATE=% MSG=%', SQLSTATE, SQLERRM;
  END;
  RESET ROLE;

  IF NOT v_blocked THEN
    RAISE EXCEPTION 'B3B-11-R3 PHASE2 UNEXPECTED: authenticated INSERT succeeded after ALTER — worker_registry policy gap expected to block';
  END IF;
  IF v_sqlstate <> '42501' THEN
    RAISE EXCEPTION 'B3B-11-R3 PHASE2 FAIL: expected SQLSTATE=42501, got %', v_sqlstate;
  END IF;
  IF v_errmsg NOT LIKE '%worker_registry%' THEN
    RAISE EXCEPTION 'B3B-11-R3 PHASE2 FAIL: expected error from worker_registry, got: %', v_errmsg;
  END IF;

  RAISE NOTICE 'B3B-11-R3 PHASE2 PRODUCTION_RLS_OBSERVATION: authenticated INSERT still blocked after ALTER (SQLSTATE=42501, MSG=%) — behavior unchanged = PASS', v_errmsg;
END;
$$;

DO $$ BEGIN RAISE NOTICE '--- PHASE 2 ROLE/RLS COMPLETE ---'; END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- FINAL SUMMARY
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
  RAISE NOTICE '========================================';
  RAISE NOTICE 'ROLE/RLS VERIFICATION COMPLETE (R2)';
  RAISE NOTICE '';
  RAISE NOTICE 'B2B-07 PHASE1+PHASE2:';
  RAISE NOTICE '  R1: anon INSERT runtime_inspection_review → permission denied (no grant) [PASS]';
  RAISE NOTICE '  R2: anon INSERT runtime_work_order_review → permission denied (no grant) [PASS]';
  RAISE NOTICE '  R3: anon SELECT runtime_inspection_review → permission denied (no grant; SELECT policy unreachable) [PASS]';
  RAISE NOTICE '  R4: postgres superuser INSERT → trigger fires (secondary evidence) [PASS]';
  RAISE NOTICE '  R5: service_role INSERT → trigger fires (GAP-002: direct SET ROLE service_role) [PASS]';
  RAISE NOTICE '  R6: authenticated INSERT → permission denied SQLSTATE=42501 (GAP-003) [PASS]';
  RAISE NOTICE '';
  RAISE NOTICE 'B3B-11 PHASE1+PHASE2:';
  RAISE NOTICE '  R1: anon INSERT construction_workers → trigger fires → registry created [PASS]';
  RAISE NOTICE '  R2: anon UPDATE construction_workers → trigger fires → registry updated [PASS]';
  RAISE NOTICE '  R3: authenticated INSERT construction_workers → worker_registry RLS SQLSTATE=42501 (GAP-001: strict assertion) [PRODUCTION_RLS_OBSERVATION]';
  RAISE NOTICE '';
  RAISE NOTICE 'GAP-001 RESOLVED: B3B-11-R3 now asserts SQLSTATE=42501 + worker_registry error source';
  RAISE NOTICE 'GAP-002 RESOLVED: B2B-07-R5 uses SET LOCAL ROLE service_role directly';
  RAISE NOTICE 'GAP-003 RESOLVED: B2B-07-R6 authenticated INSERT blocked SQLSTATE=42501 verified';
  RAISE NOTICE '';
  RAISE NOTICE 'ALTER FUNCTION equivalence: CONFIRMED for all roles';
  RAISE NOTICE 'search_path fix does NOT change role/RLS behavior';
  RAISE NOTICE '========================================';
END;
$$;
