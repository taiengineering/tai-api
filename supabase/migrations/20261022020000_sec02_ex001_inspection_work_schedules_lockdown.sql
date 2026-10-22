-- Migration: 20261022020000_sec02_ex001_inspection_work_schedules_lockdown.sql
-- WO: WO-TAI-SEC02-EX001-P0-OPTION-A-IMPLEMENT-001 / R1
-- SEC-02-EX-001: inspection_sets / work_schedules anon·authenticated 직접 접근 차단 (Option A).
--
-- 배경:
--   두 테이블은 RLS가 활성화돼 있으나 정책 조건이 USING=true / WITH CHECK=true —
--   회사·사업장 격리가 DB 수준에서 동작하지 않는다.
--   anon/authenticated에 SELECT/INSERT/UPDATE/DELETE 권한이 잔존하므로
--   Supabase Data API(/rest/v1/)를 통한 전 사 행 직접 접근이 가능하다.
--
-- 테이블 유형 (운영 DB 실측, GPT IV 확인):
--   public.inspection_sets: relkind = 'r' (일반 테이블)
--   public.work_schedules:  relkind = 'p' (HASH(factory_id) 파티션 부모, 하위 16개)
--   ※ work_schedules 하위 파티션 16개: anon/authenticated 직접 권한 없음 (GPT 확인).
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
--   하위 파티션 16개 변경 없음.
--
-- 참조 패턴:
--   20261020000002_sec_batch_p0_core9_acl_hardening.sql (Group B 구현 동일 방식)
--
-- R1 수정 (PR #676 Source Gate BLOCKED):
--   - STEP 1-a/1-b/4-f: relkind='r' → 테이블별 정확한 유형 구분
--   - STEP 1-i: service_role 기존 SELECT 유효 권한 확인 (적용 전)
--   - STEP 4-g: 유효 권한 사후 검증 (anon/auth=FALSE, service_role=TRUE)
--   - STEP 4-h: work_schedules 하위 파티션 anon/auth ACL 없음 읽기 검증
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

  -- 1-a. 대상 테이블 존재 확인 (각 테이블의 정확한 relkind 구분)
  --       inspection_sets = 'r' (일반), work_schedules = 'p' (파티션 부모)
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND (
      (c.relname = 'inspection_sets' AND c.relkind = 'r')
      OR
      (c.relname = 'work_schedules'  AND c.relkind = 'p')
    );
  IF v_count != 2 THEN
    RAISE EXCEPTION 'PRE FAILED: expected 2 target tables (inspection_sets r, work_schedules p), found %. Check relkind.', v_count;
  END IF;

  -- 1-b. 두 테이블 RLS 활성화 확인 (테이블별 relkind 구분)
  SELECT count(*) INTO v_rls_active
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND (
      (c.relname = 'inspection_sets' AND c.relkind = 'r')
      OR
      (c.relname = 'work_schedules'  AND c.relkind = 'p')
    )
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

  -- 1-i. service_role 기존 SELECT 유효 권한 확인 (적용 전 보존 조건)
  IF NOT has_table_privilege('service_role', 'public.inspection_sets', 'SELECT') THEN
    RAISE EXCEPTION 'PRE FAILED: service_role lacks SELECT on inspection_sets — unexpected state.';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.work_schedules', 'SELECT') THEN
    RAISE EXCEPTION 'PRE FAILED: service_role lacks SELECT on work_schedules — unexpected state.';
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

  -- 4-f. 두 테이블 RLS 여전히 활성화 (테이블별 relkind 구분)
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND (
      (c.relname = 'inspection_sets' AND c.relkind = 'r')
      OR
      (c.relname = 'work_schedules'  AND c.relkind = 'p')
    )
    AND c.relrowsecurity = true;
  IF v_count != 2 THEN
    RAISE EXCEPTION 'POST FAILED: RLS deactivated — must stay enabled on both tables. Found % with RLS.', v_count;
  END IF;

  -- 4-g. 유효 권한 검증: anon/authenticated = FALSE, service_role = TRUE
  --       inspection_sets
  IF has_table_privilege('anon', 'public.inspection_sets', 'SELECT') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains SELECT on inspection_sets.';
  END IF;
  IF has_table_privilege('anon', 'public.inspection_sets', 'INSERT') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains INSERT on inspection_sets.';
  END IF;
  IF has_table_privilege('anon', 'public.inspection_sets', 'UPDATE') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains UPDATE on inspection_sets.';
  END IF;
  IF has_table_privilege('anon', 'public.inspection_sets', 'DELETE') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains DELETE on inspection_sets.';
  END IF;
  IF has_table_privilege('authenticated', 'public.inspection_sets', 'SELECT') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains SELECT on inspection_sets.';
  END IF;
  IF has_table_privilege('authenticated', 'public.inspection_sets', 'INSERT') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains INSERT on inspection_sets.';
  END IF;
  IF has_table_privilege('authenticated', 'public.inspection_sets', 'UPDATE') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains UPDATE on inspection_sets.';
  END IF;
  IF has_table_privilege('authenticated', 'public.inspection_sets', 'DELETE') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains DELETE on inspection_sets.';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.inspection_sets', 'SELECT') THEN
    RAISE EXCEPTION 'POST FAILED: service_role lost SELECT on inspection_sets.';
  END IF;
  --       work_schedules
  IF has_table_privilege('anon', 'public.work_schedules', 'SELECT') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains SELECT on work_schedules.';
  END IF;
  IF has_table_privilege('anon', 'public.work_schedules', 'INSERT') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains INSERT on work_schedules.';
  END IF;
  IF has_table_privilege('anon', 'public.work_schedules', 'UPDATE') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains UPDATE on work_schedules.';
  END IF;
  IF has_table_privilege('anon', 'public.work_schedules', 'DELETE') THEN
    RAISE EXCEPTION 'POST FAILED: anon retains DELETE on work_schedules.';
  END IF;
  IF has_table_privilege('authenticated', 'public.work_schedules', 'SELECT') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains SELECT on work_schedules.';
  END IF;
  IF has_table_privilege('authenticated', 'public.work_schedules', 'INSERT') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains INSERT on work_schedules.';
  END IF;
  IF has_table_privilege('authenticated', 'public.work_schedules', 'UPDATE') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains UPDATE on work_schedules.';
  END IF;
  IF has_table_privilege('authenticated', 'public.work_schedules', 'DELETE') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated retains DELETE on work_schedules.';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.work_schedules', 'SELECT') THEN
    RAISE EXCEPTION 'POST FAILED: service_role lost SELECT on work_schedules.';
  END IF;

  -- 4-h. work_schedules 하위 파티션 — anon/authenticated ACL 없음 (읽기 전용 검증, 변경 없음)
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_inherits i ON i.inhrelid = c.oid
  JOIN pg_class p ON p.oid = i.inhparent
  JOIN pg_namespace pn ON pn.oid = p.relnamespace
  WHERE pn.nspname = 'public' AND p.relname = 'work_schedules'
    AND n.nspname = 'public'
    AND EXISTS (
      SELECT 1 FROM unnest(c.relacl) AS acl(entry)
      WHERE acl.entry::text ~ '^(anon|authenticated)='
    );
  IF v_count != 0 THEN
    RAISE EXCEPTION 'POST FAILED: % work_schedules partition(s) have unexpected anon/authenticated ACL.', v_count;
  END IF;

  RAISE NOTICE 'POST-COMPLETE: 2 tables locked. inspection_sets(5)+work_schedules(5) policies dropped. anon/auth=FALSE, service_role=TRUE. 파티션 ACL 이상 없음.';

END;
$$;

COMMIT;
