-- Migration: 20261022100136_sec_searchpath_p0a_secdef_aggregate_functions.sql
-- WO: WO-TAI-SEC-SEARCHPATH-P0A-001
-- SECURITY DEFINER 집계 함수 2건 search_path 고정
--
-- 배경:
--   refresh_dashboard_stats(), refresh_engine_equipment_summary():
--   SECURITY DEFINER이나 proconfig에 search_path 미설정 →
--   function_search_path_mutable Security Advisor 경고 대상.
--   함수 본문은 public 스키마의 Materialized View를 비한정 이름으로 참조.
--   anon/authenticated EXECUTE 이미 차단됨 (SEC-04 완료).
--
-- 변경 원칙:
--   함수 본문·ACL·SECURITY DEFINER·소유자 변경 없음.
--   ALTER FUNCTION … SET search_path으로 메타데이터만 고정.
--   목표값: pg_catalog, public, pg_temp
--   (신뢰 스키마 우선, 임시 스키마 마지막)
--
-- 참조 패턴:
--   20261022083010_sec_residual_hnu001_drop_handle_new_user.sql

BEGIN;

DO $$
DECLARE
  v_count       int;
  v_owner       text;
  v_secdef      bool;
  v_def_md5     text;
  v_body_md5    text;
  v_proconfig   text[];
  v_ret         text;

BEGIN

  -- ── STEP 1: 사전조건 검증 ──────────────────────────────────────────

  -- 1-a. refresh_dashboard_stats() 존재 (인수 0개, RETURNS void)
  SELECT count(*) INTO v_count
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_dashboard_stats'
    AND p.pronargs = 0 AND pg_get_function_result(p.oid) = 'void';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_dashboard_stats() not found or signature mismatch.';
  END IF;

  -- 1-b. refresh_dashboard_stats() — SECURITY DEFINER
  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_dashboard_stats' AND p.pronargs = 0;
  IF v_secdef != true THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_dashboard_stats() is not SECURITY DEFINER.';
  END IF;

  -- 1-c. refresh_dashboard_stats() — owner = postgres
  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_dashboard_stats' AND p.pronargs = 0;
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_dashboard_stats() owner is %, expected postgres.', v_owner;
  END IF;

  -- 1-d. refresh_dashboard_stats() — 정의 MD5 기준선
  SELECT md5(pg_get_functiondef(p.oid)) INTO v_def_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_dashboard_stats' AND p.pronargs = 0;
  IF v_def_md5 != 'f51bb1e3a717d44e91b97a2c1bd1232f' THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_dashboard_stats() definition MD5 mismatch: got %.', v_def_md5;
  END IF;

  -- 1-e. refresh_dashboard_stats() — 본문 MD5 기준선
  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_dashboard_stats' AND p.pronargs = 0;
  IF v_body_md5 != '8f9e939d25ceb118ea44ae97aa16f9f1' THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_dashboard_stats() body MD5 mismatch: got %.', v_body_md5;
  END IF;

  -- 1-f. refresh_dashboard_stats() — proconfig = NULL
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_dashboard_stats' AND p.pronargs = 0;
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_dashboard_stats() proconfig is %, expected NULL.', v_proconfig;
  END IF;

  -- 1-g. refresh_dashboard_stats() — anon/authenticated EXECUTE = FALSE
  IF has_function_privilege('anon', 'public.refresh_dashboard_stats()', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon has EXECUTE on refresh_dashboard_stats().';
  END IF;
  IF has_function_privilege('authenticated', 'public.refresh_dashboard_stats()', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated has EXECUTE on refresh_dashboard_stats().';
  END IF;

  -- 1-h. refresh_engine_equipment_summary() 존재 (인수 0개, RETURNS void)
  SELECT count(*) INTO v_count
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_engine_equipment_summary'
    AND p.pronargs = 0 AND pg_get_function_result(p.oid) = 'void';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_engine_equipment_summary() not found or signature mismatch.';
  END IF;

  -- 1-i. refresh_engine_equipment_summary() — SECURITY DEFINER
  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_engine_equipment_summary' AND p.pronargs = 0;
  IF v_secdef != true THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_engine_equipment_summary() is not SECURITY DEFINER.';
  END IF;

  -- 1-j. refresh_engine_equipment_summary() — owner = postgres
  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_engine_equipment_summary' AND p.pronargs = 0;
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_engine_equipment_summary() owner is %, expected postgres.', v_owner;
  END IF;

  -- 1-k. refresh_engine_equipment_summary() — 정의 MD5 기준선
  SELECT md5(pg_get_functiondef(p.oid)) INTO v_def_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_engine_equipment_summary' AND p.pronargs = 0;
  IF v_def_md5 != '0b38f2bc5ed06d1cbadd60617525a8f2' THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_engine_equipment_summary() definition MD5 mismatch: got %.', v_def_md5;
  END IF;

  -- 1-l. refresh_engine_equipment_summary() — 본문 MD5 기준선
  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_engine_equipment_summary' AND p.pronargs = 0;
  IF v_body_md5 != '9035dcba996c27b14c53c5483ae78e61' THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_engine_equipment_summary() body MD5 mismatch: got %.', v_body_md5;
  END IF;

  -- 1-m. refresh_engine_equipment_summary() — proconfig = NULL
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_engine_equipment_summary' AND p.pronargs = 0;
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'PRE FAILED: refresh_engine_equipment_summary() proconfig is %, expected NULL.', v_proconfig;
  END IF;

  -- 1-n. refresh_engine_equipment_summary() — anon/authenticated EXECUTE = FALSE
  IF has_function_privilege('anon', 'public.refresh_engine_equipment_summary()', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon has EXECUTE on refresh_engine_equipment_summary().';
  END IF;
  IF has_function_privilege('authenticated', 'public.refresh_engine_equipment_summary()', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated has EXECUTE on refresh_engine_equipment_summary().';
  END IF;

  -- 1-o. Materialized View 2개 존재 (public 스키마)
  SELECT count(*) INTO v_count
  FROM pg_matviews
  WHERE schemaname = 'public' AND matviewname = 'dashboard_stats';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: public.dashboard_stats matview not found.';
  END IF;

  SELECT count(*) INTO v_count
  FROM pg_matviews
  WHERE schemaname = 'public' AND matviewname = 'engine_equipment_summary';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: public.engine_equipment_summary matview not found.';
  END IF;

  -- 1-p. public 스키마 CREATE 권한 기준선 (anon/authenticated = FALSE)
  IF has_schema_privilege('anon', 'public', 'CREATE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon has CREATE on public schema — baseline mismatch.';
  END IF;
  IF has_schema_privilege('authenticated', 'public', 'CREATE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated has CREATE on public schema — baseline mismatch.';
  END IF;

  RAISE NOTICE 'PRE: Pre-conditions PASS (F1·F2 서명·MD5·proconfig·ACL·MatView·스키마권한).';

  -- ── STEP 2: 변경 실행 ──────────────────────────────────────────────

  ALTER FUNCTION public.refresh_dashboard_stats()
    SET search_path TO pg_catalog, public, pg_temp;

  ALTER FUNCTION public.refresh_engine_equipment_summary()
    SET search_path TO pg_catalog, public, pg_temp;

  RAISE NOTICE 'STEP 2: search_path 고정 완료 (refresh_dashboard_stats, refresh_engine_equipment_summary).';

  -- ── STEP 3: 사후조건 검증 ──────────────────────────────────────────

  -- 3-a. refresh_dashboard_stats() — proconfig에 search_path 존재
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_dashboard_stats' AND p.pronargs = 0;
  IF v_proconfig IS NULL OR NOT ('search_path=pg_catalog, public, pg_temp' = ANY(v_proconfig)) THEN
    RAISE EXCEPTION 'POST FAILED: refresh_dashboard_stats() search_path not set correctly: %.', v_proconfig;
  END IF;

  -- 3-b. refresh_dashboard_stats() — 본문 MD5 불변
  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_dashboard_stats' AND p.pronargs = 0;
  IF v_body_md5 != '8f9e939d25ceb118ea44ae97aa16f9f1' THEN
    RAISE EXCEPTION 'POST FAILED: refresh_dashboard_stats() body MD5 changed: %.', v_body_md5;
  END IF;

  -- 3-c. refresh_dashboard_stats() — SECURITY DEFINER 불변
  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_dashboard_stats' AND p.pronargs = 0;
  IF v_secdef != true THEN
    RAISE EXCEPTION 'POST FAILED: refresh_dashboard_stats() SECURITY DEFINER changed.';
  END IF;

  -- 3-d. refresh_dashboard_stats() — ACL 불변 (anon/authenticated = FALSE)
  IF has_function_privilege('anon', 'public.refresh_dashboard_stats()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: anon gained EXECUTE on refresh_dashboard_stats().';
  END IF;
  IF has_function_privilege('authenticated', 'public.refresh_dashboard_stats()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated gained EXECUTE on refresh_dashboard_stats().';
  END IF;
  IF NOT has_function_privilege('service_role', 'public.refresh_dashboard_stats()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: service_role lost EXECUTE on refresh_dashboard_stats().';
  END IF;
  IF NOT has_function_privilege('postgres', 'public.refresh_dashboard_stats()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: postgres lost EXECUTE on refresh_dashboard_stats().';
  END IF;

  -- 3-e. refresh_engine_equipment_summary() — proconfig에 search_path 존재
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_engine_equipment_summary' AND p.pronargs = 0;
  IF v_proconfig IS NULL OR NOT ('search_path=pg_catalog, public, pg_temp' = ANY(v_proconfig)) THEN
    RAISE EXCEPTION 'POST FAILED: refresh_engine_equipment_summary() search_path not set correctly: %.', v_proconfig;
  END IF;

  -- 3-f. refresh_engine_equipment_summary() — 본문 MD5 불변
  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_engine_equipment_summary' AND p.pronargs = 0;
  IF v_body_md5 != '9035dcba996c27b14c53c5483ae78e61' THEN
    RAISE EXCEPTION 'POST FAILED: refresh_engine_equipment_summary() body MD5 changed: %.', v_body_md5;
  END IF;

  -- 3-g. refresh_engine_equipment_summary() — SECURITY DEFINER 불변
  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'refresh_engine_equipment_summary' AND p.pronargs = 0;
  IF v_secdef != true THEN
    RAISE EXCEPTION 'POST FAILED: refresh_engine_equipment_summary() SECURITY DEFINER changed.';
  END IF;

  -- 3-h. refresh_engine_equipment_summary() — ACL 불변
  IF has_function_privilege('anon', 'public.refresh_engine_equipment_summary()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: anon gained EXECUTE on refresh_engine_equipment_summary().';
  END IF;
  IF has_function_privilege('authenticated', 'public.refresh_engine_equipment_summary()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated gained EXECUTE on refresh_engine_equipment_summary().';
  END IF;
  IF NOT has_function_privilege('service_role', 'public.refresh_engine_equipment_summary()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: service_role lost EXECUTE on refresh_engine_equipment_summary().';
  END IF;
  IF NOT has_function_privilege('postgres', 'public.refresh_engine_equipment_summary()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: postgres lost EXECUTE on refresh_engine_equipment_summary().';
  END IF;

  -- 3-i. MatView 불변
  SELECT count(*) INTO v_count
  FROM pg_matviews WHERE schemaname = 'public' AND matviewname = 'dashboard_stats';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'POST FAILED: public.dashboard_stats matview missing after ALTER.';
  END IF;

  SELECT count(*) INTO v_count
  FROM pg_matviews WHERE schemaname = 'public' AND matviewname = 'engine_equipment_summary';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'POST FAILED: public.engine_equipment_summary matview missing after ALTER.';
  END IF;

  -- 3-j. 승인된 2개 함수 이외 proconfig 변경 없음 확인 (다른 함수 proconfig 기준선)
  -- 동일 트랜잭션 내 변경이므로 ALTER 2건 외 변경 불가 — 구조적으로 보장됨.

  RAISE NOTICE 'POST-COMPLETE: refresh_dashboard_stats() search_path=pg_catalog,public,pg_temp 고정. refresh_engine_equipment_summary() search_path=pg_catalog,public,pg_temp 고정. 본문·SECDEF·ACL·MatView 불변.';

END;
$$;

COMMIT;
