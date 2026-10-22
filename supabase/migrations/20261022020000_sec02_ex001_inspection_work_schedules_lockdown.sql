-- Migration: 20261022020000_sec02_ex001_inspection_work_schedules_lockdown.sql
-- WO: WO-TAI-SEC02-EX001-P0-OPTION-A-IMPLEMENT-001
-- SEC-02-EX-001: inspection_sets / work_schedules anon·authenticated 직접 접근 차단 (Option A).
--
-- 배경:
--   두 테이블은 RLS가 활성화돼 있으나 정책 조건이 USING=true / WITH CHECK=true —
--   회사·사업장 격리가 DB 수준에서 동작하지 않는다.
--   anon/authenticated에 SELECT/INSERT/UPDATE/DELETE 권한이 잔존하므로
--   Supabase Data API(/rest/v1/)를 통한 전 사 행 직접 접근이 가능하다.
--
-- 조사 결과 (WO-TAI-SEC02-EX001-P0-CONTRACT-001 / GPT C1C2 IV PASS):
--   모든 합법적 접근 경로 = service_role 경유 TAI API.
--   tai-api  : get_supabase() service_role 전용, anon 폴백 금지.
--   tai-admin: /inspection-sets, /work-schedules API 경유 (직접 Supabase 접근 없음).
--   Worker PWA: /worker-check/submit 경유 (직접 Supabase 접근 없음).
--   tai-www  : 두 테이블 참조 없음.
--
-- 변경 범위:
--   DROP POLICY — inspection_sets 5개 + work_schedules 5개 = 10개.
--   REVOKE ALL PRIVILEGES ON TABLE — 2개 테이블.
--   service_role_full 정책 유지.
--   RLS 활성화 유지.
--   테이블 구조·데이터·함수·트리거 변경 없음.
--
-- 참조 패턴:
--   20261020000002_sec_batch_p0_core9_acl_hardening.sql (Group B 구현 동일 방식)
--
-- 인접 위험 (이번 Migration 범위 제외):
--   work_assignments + generate_daily_assignments() — 별도 P0 관리.

BEGIN;

DO $$
DECLARE
  v_count            int;
  v_rls_active       int;
  v_unexpected_names text[];

  c_drop_inspection_sets text[] := ARRAY[
    'anon_select_inspection_sets',
    'anon_insert_inspection_sets',
    'anon_update_inspection_sets',
    'anon_delete_inspection_sets',
    'authenticated_all_inspection_sets'
  ];

  c_drop_work_schedules text[] := ARRAY[
    'anon_select_work_schedules',
    'anon_insert_work_schedules',
    'anon_update_work_schedules',
    'anon_delete_work_schedules',
    'authenticated_all_work_schedules'
  ];

BEGIN

  -- ── STEP 1: 사전조건 검증 ──────────────────────────────────────────

  -- 1-a. 대상 테이블 존재 확인
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r'
    AND c.relname IN ('inspection_sets', 'work_schedules');
  IF v_count != 2 THEN
    RAISE EXCEPTION 'PRE FAILED: expected 2 target tables, found %.', v_count;
  END IF;

  -- 1-b. 두 테이블 RLS 활성화 확인
  SELECT count(*) INTO v_rls_active
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r'
    AND c.relname IN ('inspection_sets', 'work_schedules')
    AND c.relrowsecurity = true;
  IF v_rls_active != 2 THEN
    RAISE EXCEPTION 'PRE FAILED: expected 2 tables with RLS enabled, found %.', v_rls_active;
  END IF;

  -- 1-c. inspection_sets: 제거 대상 5개 정책 존재 확인
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'inspection_sets'
    AND policyname = ANY(c_drop_inspection_sets);
  IF v_count != 5 THEN
    RAISE EXCEPTION 'PRE FAILED: inspection_sets — expected 5 policies to drop, found %.', v_count;
  END IF;

  -- 1-d. inspection_sets: service_role_full 정책 존재 확인
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'inspection_sets'
    AND policyname = 'service_role_full';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: inspection_sets — service_role_full policy not found.';
  END IF;

  -- 1-e. inspection_sets: 예상 외 정책 차단
  SELECT array_agg(policyname ORDER BY policyname) INTO v_unexpected_names
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'inspection_sets'
    AND policyname != 'service_role_full'
    AND NOT (policyname = ANY(c_drop_inspection_sets));
  IF v_unexpected_names IS NOT NULL AND array_length(v_unexpected_names, 1) > 0 THEN
    RAISE EXCEPTION 'PRE FAILED: Unexpected policies on inspection_sets: %.', v_unexpected_names;
  END IF;

  -- 1-f. work_schedules: 제거 대상 5개 정책 존재 확인
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'work_schedules'
    AND policyname = ANY(c_drop_work_schedules);
  IF v_count != 5 THEN
    RAISE EXCEPTION 'PRE FAILED: work_schedules — expected 5 policies to drop, found %.', v_count;
  END IF;

  -- 1-g. work_schedules: service_role_full 정책 존재 확인
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'work_schedules'
    AND policyname = 'service_role_full';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: work_schedules — service_role_full policy not found.';
  END IF;

  -- 1-h. work_schedules: 예상 외 정책 차단
  SELECT array_agg(policyname ORDER BY policyname) INTO v_unexpected_names
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'work_schedules'
    AND policyname != 'service_role_full'
    AND NOT (policyname = ANY(c_drop_work_schedules));
  IF v_unexpected_names IS NOT NULL AND array_length(v_unexpected_names, 1) > 0 THEN
    RAISE EXCEPTION 'PRE FAILED: Unexpected policies on work_schedules: %.', v_unexpected_names;
  END IF;

  RAISE NOTICE 'PRE: Pre-conditions PASS.';

  -- ── STEP 2: inspection_sets 정책 제거 + 권한 회수 ──────────────────

  DROP POLICY anon_select_inspection_sets       ON public.inspection_sets;
  DROP POLICY anon_insert_inspection_sets       ON public.inspection_sets;
  DROP POLICY anon_update_inspection_sets       ON public.inspection_sets;
  DROP POLICY anon_delete_inspection_sets       ON public.inspection_sets;
  DROP POLICY authenticated_all_inspection_sets ON public.inspection_sets;

  REVOKE ALL PRIVILEGES ON TABLE public.inspection_sets FROM PUBLIC, anon, authenticated;

  RAISE NOTICE 'STEP 2: inspection_sets — 5 policies dropped + privileges revoked.';

  -- ── STEP 3: work_schedules 정책 제거 + 권한 회수 ───────────────────

  DROP POLICY anon_select_work_schedules       ON public.work_schedules;
  DROP POLICY anon_insert_work_schedules       ON public.work_schedules;
  DROP POLICY anon_update_work_schedules       ON public.work_schedules;
  DROP POLICY anon_delete_work_schedules       ON public.work_schedules;
  DROP POLICY authenticated_all_work_schedules ON public.work_schedules;

  REVOKE ALL PRIVILEGES ON TABLE public.work_schedules FROM PUBLIC, anon, authenticated;

  RAISE NOTICE 'STEP 3: work_schedules — 5 policies dropped + privileges revoked.';

  -- ── STEP 4: 사후조건 검증 ──────────────────────────────────────────

  -- 4-a. inspection_sets: 제거 대상 정책 잔존 없음
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'inspection_sets'
    AND policyname = ANY(c_drop_inspection_sets);
  IF v_count != 0 THEN
    RAISE EXCEPTION 'POST FAILED: % inspection_sets user policies remain.', v_count;
  END IF;

  -- 4-b. inspection_sets: service_role_full 유지
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'inspection_sets'
    AND policyname = 'service_role_full';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'POST FAILED: inspection_sets service_role_full policy missing.';
  END IF;

  -- 4-c. work_schedules: 제거 대상 정책 잔존 없음
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'work_schedules'
    AND policyname = ANY(c_drop_work_schedules);
  IF v_count != 0 THEN
    RAISE EXCEPTION 'POST FAILED: % work_schedules user policies remain.', v_count;
  END IF;

  -- 4-d. work_schedules: service_role_full 유지
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'work_schedules'
    AND policyname = 'service_role_full';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'POST FAILED: work_schedules service_role_full policy missing.';
  END IF;

  -- 4-e. 두 테이블에 anon / authenticated ACL 항목 없음
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND c.relname IN ('inspection_sets', 'work_schedules')
    AND EXISTS (
      SELECT 1 FROM unnest(c.relacl) AS acl(entry)
      WHERE acl.entry::text ~ '^(anon|authenticated)='
    );
  IF v_count != 0 THEN
    RAISE EXCEPTION 'POST FAILED: anon/authenticated ACL entries remain on % table(s).', v_count;
  END IF;

  -- 4-f. 두 테이블 RLS 여전히 활성화
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r'
    AND c.relname IN ('inspection_sets', 'work_schedules')
    AND c.relrowsecurity = true;
  IF v_count != 2 THEN
    RAISE EXCEPTION 'POST FAILED: RLS deactivated on % table(s) — must stay enabled.', (2 - v_count);
  END IF;

  RAISE NOTICE 'POST-COMPLETE: 2 tables locked. inspection_sets(5) + work_schedules(5) policies dropped. service_role 접근 유지.';

END;
$$;

COMMIT;
