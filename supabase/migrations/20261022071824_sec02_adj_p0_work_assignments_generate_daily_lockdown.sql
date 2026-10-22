-- Migration: 20261022071824_sec02_adj_p0_work_assignments_generate_daily_lockdown.sql
-- WO: WO-TAI-SEC02-ADJ-P0-OPTION-A-IMPLEMENT-001
-- SEC-02 인접 P0: work_assignments / generate_daily_assignments() anon·authenticated 접근 차단 (Option A)
--
-- 배경:
--   work_assignments: RLS 활성이나 정책 조건 USING=true — 회사·사업장 격리 없음.
--   anon/authenticated에 CRUD 권한 잔존 → Supabase Data API(/rest/v1/) 직접 접근 가능.
--   generate_daily_assignments(): SECURITY INVOKER, PUBLIC EXECUTE 허용 →
--   anon/authenticated가 작업자 배정 로직을 직접 호출 가능.
--
-- 테이블 유형 (운영 DB 확인):
--   public.work_assignments: relkind = 'r' (일반 테이블, 파티션 없음)
--
-- 소비자 계약 (C1/C2 재사용 — SEC-02-EX-001):
--   모든 합법적 접근 = service_role 경유 TAI API (get_supabase() 필수, anon 폴백 금지).
--   scheduler/handlers.py: _rpc("generate_daily_assignments") = service_role.
--   pg_cron.daily_assignments: postgres 소유, active=false (변경 없음).
--
-- 변경 범위:
--   DROP POLICY — work_assignments 5개.
--   REVOKE ALL PRIVILEGES ON TABLE public.work_assignments FROM PUBLIC, anon, authenticated.
--   REVOKE EXECUTE ON FUNCTION public.generate_daily_assignments() FROM PUBLIC, anon, authenticated.
--   service_role_full 정책 유지, RLS 활성 유지.
--   함수 본문·실행 방식(SECURITY INVOKER) 불변.
--   pg_cron 스케줄 변경 없음.
--
-- 참조 패턴:
--   20261022020000_sec02_ex001_inspection_work_schedules_lockdown.sql

BEGIN;

DO $$
DECLARE
  v_count            int;
  v_rls_active       int;
  v_sec_def          bool;
  v_unexpected_names text[];

  c_drop_work_assignments text[] := ARRAY[
    'anon_select_work_assignments',
    'anon_insert_work_assignments',
    'anon_update_work_assignments',
    'anon_delete_work_assignments',
    'authenticated_all_work_assignments'
  ];

BEGIN

  -- ── STEP 1: 사전조건 검증 ──────────────────────────────────────────

  -- 1-a. work_assignments 존재 및 relkind='r' (일반 테이블)
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = 'work_assignments' AND c.relkind = 'r';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: work_assignments not found or not relkind=r.';
  END IF;

  -- 1-b. RLS 활성화
  SELECT count(*) INTO v_rls_active
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = 'work_assignments'
    AND c.relkind = 'r' AND c.relrowsecurity = true;
  IF v_rls_active != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: work_assignments RLS not enabled.';
  END IF;

  -- 1-c. 제거 대상 정책 정확히 5개 존재
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'work_assignments'
    AND policyname = ANY(c_drop_work_assignments);
  IF v_count != 5 THEN
    RAISE EXCEPTION 'PRE FAILED: work_assignments — expected 5 policies to drop, found %.', v_count;
  END IF;

  -- 1-d. service_role_full 정책 존재
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'work_assignments'
    AND policyname = 'service_role_full';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: work_assignments — service_role_full policy not found.';
  END IF;

  -- 1-e. 예상 외 정책 차단
  SELECT array_agg(policyname ORDER BY policyname) INTO v_unexpected_names
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'work_assignments'
    AND policyname != 'service_role_full'
    AND NOT (policyname = ANY(c_drop_work_assignments));
  IF v_unexpected_names IS NOT NULL AND array_length(v_unexpected_names, 1) > 0 THEN
    RAISE EXCEPTION 'PRE FAILED: Unexpected policies on work_assignments: %.', v_unexpected_names;
  END IF;

  -- 1-f. service_role 기존 CRUD 유효 권한 확인 (적용 전 보존 조건)
  IF NOT has_table_privilege('service_role', 'public.work_assignments', 'SELECT') THEN
    RAISE EXCEPTION 'PRE FAILED: service_role lacks SELECT on work_assignments.';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.work_assignments', 'INSERT') THEN
    RAISE EXCEPTION 'PRE FAILED: service_role lacks INSERT on work_assignments.';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.work_assignments', 'UPDATE') THEN
    RAISE EXCEPTION 'PRE FAILED: service_role lacks UPDATE on work_assignments.';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.work_assignments', 'DELETE') THEN
    RAISE EXCEPTION 'PRE FAILED: service_role lacks DELETE on work_assignments.';
  END IF;

  -- 1-g. generate_daily_assignments() 함수 존재 (인수 0개)
  SELECT count(*) INTO v_count
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'generate_daily_assignments' AND p.pronargs = 0;
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: generate_daily_assignments() not found or signature mismatch.';
  END IF;

  -- 1-h. SECURITY INVOKER 확인 (prosecdef = false)
  SELECT p.prosecdef INTO v_sec_def
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'generate_daily_assignments' AND p.pronargs = 0;
  IF v_sec_def = true THEN
    RAISE EXCEPTION 'PRE FAILED: generate_daily_assignments() is SECURITY DEFINER — expected INVOKER.';
  END IF;

  -- 1-i. service_role EXECUTE 기존 권한 확인
  IF NOT has_function_privilege('service_role', 'public.generate_daily_assignments()', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: service_role lacks EXECUTE on generate_daily_assignments().';
  END IF;

  -- 1-j. postgres EXECUTE 기존 권한 확인
  IF NOT has_function_privilege('postgres', 'public.generate_daily_assignments()', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: postgres lacks EXECUTE on generate_daily_assignments().';
  END IF;

  RAISE NOTICE 'PRE: Pre-conditions PASS.';

  -- ── STEP 2: 변경 실행 ──────────────────────────────────────────────

  -- 2-a. work_assignments 정책 5개 제거 + 테이블 권한 회수
  DROP POLICY anon_select_work_assignments       ON public.work_assignments;
  DROP POLICY anon_insert_work_assignments       ON public.work_assignments;
  DROP POLICY anon_update_work_assignments       ON public.work_assignments;
  DROP POLICY anon_delete_work_assignments       ON public.work_assignments;
  DROP POLICY authenticated_all_work_assignments ON public.work_assignments;

  REVOKE ALL PRIVILEGES ON TABLE public.work_assignments FROM PUBLIC, anon, authenticated;

  RAISE NOTICE 'STEP 2-a: work_assignments — 5 policies dropped + table privileges revoked.';

  -- 2-b. generate_daily_assignments() 실행권한 회수
  REVOKE EXECUTE ON FUNCTION public.generate_daily_assignments() FROM PUBLIC, anon, authenticated;

  RAISE NOTICE 'STEP 2-b: generate_daily_assignments() — EXECUTE revoked from PUBLIC, anon, authenticated.';

  -- ── STEP 3: 사후조건 검증 ──────────────────────────────────────────

  -- 3-a. 제거 대상 정책 잔존 없음
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'work_assignments'
    AND policyname = ANY(c_drop_work_assignments);
  IF v_count != 0 THEN
    RAISE EXCEPTION 'POST FAILED: % work_assignments user policies remain.', v_count;
  END IF;

  -- 3-b. service_role_full 유지
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'work_assignments'
    AND policyname = 'service_role_full';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'POST FAILED: work_assignments service_role_full policy missing.';
  END IF;

  -- 3-c. RLS 여전히 활성
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = 'work_assignments'
    AND c.relkind = 'r' AND c.relrowsecurity = true;
  IF v_count != 1 THEN
    RAISE EXCEPTION 'POST FAILED: work_assignments RLS deactivated.';
  END IF;

  -- 3-d. anon CRUD = FALSE (4종)
  IF has_table_privilege('anon', 'public.work_assignments', 'SELECT') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains SELECT on work_assignments.';
  END IF;
  IF has_table_privilege('anon', 'public.work_assignments', 'INSERT') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains INSERT on work_assignments.';
  END IF;
  IF has_table_privilege('anon', 'public.work_assignments', 'UPDATE') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains UPDATE on work_assignments.';
  END IF;
  IF has_table_privilege('anon', 'public.work_assignments', 'DELETE') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains DELETE on work_assignments.';
  END IF;

  -- 3-e. authenticated CRUD = FALSE (4종)
  IF has_table_privilege('authenticated', 'public.work_assignments', 'SELECT') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains SELECT on work_assignments.';
  END IF;
  IF has_table_privilege('authenticated', 'public.work_assignments', 'INSERT') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains INSERT on work_assignments.';
  END IF;
  IF has_table_privilege('authenticated', 'public.work_assignments', 'UPDATE') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains UPDATE on work_assignments.';
  END IF;
  IF has_table_privilege('authenticated', 'public.work_assignments', 'DELETE') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains DELETE on work_assignments.';
  END IF;

  -- 3-f. service_role CRUD = TRUE (4종)
  IF NOT has_table_privilege('service_role', 'public.work_assignments', 'SELECT') THEN
    RAISE EXCEPTION 'POST FAILED: service_role lost SELECT on work_assignments.';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.work_assignments', 'INSERT') THEN
    RAISE EXCEPTION 'POST FAILED: service_role lost INSERT on work_assignments.';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.work_assignments', 'UPDATE') THEN
    RAISE EXCEPTION 'POST FAILED: service_role lost UPDATE on work_assignments.';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.work_assignments', 'DELETE') THEN
    RAISE EXCEPTION 'POST FAILED: service_role lost DELETE on work_assignments.';
  END IF;

  -- 3-g. anon EXECUTE = FALSE
  IF has_function_privilege('anon', 'public.generate_daily_assignments()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains EXECUTE on generate_daily_assignments().';
  END IF;

  -- 3-h. authenticated EXECUTE = FALSE
  IF has_function_privilege('authenticated', 'public.generate_daily_assignments()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains EXECUTE on generate_daily_assignments().';
  END IF;

  -- 3-i. service_role EXECUTE = TRUE
  IF NOT has_function_privilege('service_role', 'public.generate_daily_assignments()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: service_role lost EXECUTE on generate_daily_assignments().';
  END IF;

  -- 3-j. postgres EXECUTE = TRUE
  IF NOT has_function_privilege('postgres', 'public.generate_daily_assignments()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: postgres lost EXECUTE on generate_daily_assignments().';
  END IF;

  -- 3-k. SECURITY INVOKER 유지
  SELECT p.prosecdef INTO v_sec_def
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'generate_daily_assignments' AND p.pronargs = 0;
  IF v_sec_def = true THEN
    RAISE EXCEPTION 'POST FAILED: generate_daily_assignments() changed to SECURITY DEFINER.';
  END IF;

  RAISE NOTICE 'POST-COMPLETE: work_assignments(5 policies dropped, anon/auth CRUD=FALSE, service_role CRUD=TRUE, RLS 유지). generate_daily_assignments(anon/auth EXECUTE=FALSE, service_role/postgres EXECUTE=TRUE, SECURITY INVOKER 유지).';

END;
$$;

COMMIT;
