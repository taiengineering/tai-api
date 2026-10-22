-- Migration: 20261022131807_sec_searchpath_p0b_set_guest_user_null.sql
-- WO: WO-TAI-SEC-SEARCHPATH-P0B-IMPLEMENT-001
-- PARENT: WO-TAI-SEC-SEARCHPATH-P0B-IMPACT-001
-- SEC SEARCHPATH P0B — public.set_guest_user_null() search_path 고정
--
-- 배경:
--   set_guest_user_null(): SECURITY DEFINER, BEFORE INSERT 트리거 (payments).
--   현재 proconfig=NULL → function_search_path_mutable Advisor 경고.
--   함수 본문 내 모든 참조 schema-qualified (auth.users) 또는 pg_catalog 내장.
--   메타데이터 고정만으로 경고 해소 가능 (본문 재작성 불필요).
--
-- 변경 범위:
--   ALTER FUNCTION public.set_guest_user_null() SET search_path TO pg_catalog, public, pg_temp — 1건.
--   함수 본문, 트리거, payments 테이블, ACL 변경 없음.
--
-- 참조:
--   20261022100136_sec_searchpath_p0a_secdef_aggregate_functions.sql

BEGIN;

DO $$
DECLARE
  v_count        int;
  v_owner        text;
  v_secdef       bool;
  v_def_md5      text;
  v_body_md5     text;
  v_proconfig    text[];
  v_trig_count   int;
  v_trig_md5     text;
  v_rls          bool;

BEGIN

  -- ── STEP 1: 사전조건 검증 ────────────────────────────────────────────

  -- 1-a. 함수 존재 (인수 0개, RETURNS trigger)
  SELECT count(*) INTO v_count
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'set_guest_user_null' AND p.pronargs = 0
    AND p.prorettype = 'trigger'::regtype::oid;
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: public.set_guest_user_null() not found or signature mismatch.';
  END IF;

  -- 1-b. SECURITY DEFINER 확인
  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'set_guest_user_null' AND p.pronargs = 0;
  IF v_secdef != true THEN
    RAISE EXCEPTION 'PRE FAILED: set_guest_user_null() is not SECURITY DEFINER — baseline mismatch.';
  END IF;

  -- 1-c. 소유자 = postgres
  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'set_guest_user_null' AND p.pronargs = 0;
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'PRE FAILED: set_guest_user_null() owner is %, expected postgres.', v_owner;
  END IF;

  -- 1-d. 함수 정의 MD5 기준선
  SELECT md5(pg_get_functiondef(p.oid)) INTO v_def_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'set_guest_user_null' AND p.pronargs = 0;
  IF v_def_md5 != 'ce566e4848a8ca47c794cbf3b48a826c' THEN
    RAISE EXCEPTION 'PRE FAILED: set_guest_user_null() definition MD5 mismatch: got %.', v_def_md5;
  END IF;

  -- 1-e. 함수 본문 MD5 기준선
  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'set_guest_user_null' AND p.pronargs = 0;
  IF v_body_md5 != 'a879552fd1b918e717c633e7ace65a72' THEN
    RAISE EXCEPTION 'PRE FAILED: set_guest_user_null() body MD5 mismatch: got %.', v_body_md5;
  END IF;

  -- 1-f. proconfig = NULL (search_path 미설정 확인)
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'set_guest_user_null' AND p.pronargs = 0;
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'PRE FAILED: set_guest_user_null() proconfig already set: %.', v_proconfig;
  END IF;

  -- 1-g. anon EXECUTE = FALSE
  IF has_function_privilege('anon', 'public.set_guest_user_null()', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon has EXECUTE on set_guest_user_null().';
  END IF;

  -- 1-h. authenticated EXECUTE = FALSE
  IF has_function_privilege('authenticated', 'public.set_guest_user_null()', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated has EXECUTE on set_guest_user_null().';
  END IF;

  -- 1-i. service_role EXECUTE = TRUE
  IF NOT has_function_privilege('service_role', 'public.set_guest_user_null()', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: service_role does not have EXECUTE on set_guest_user_null().';
  END IF;

  -- 1-j. 활성 트리거 정확히 1건
  SELECT count(*) INTO v_trig_count
  FROM pg_trigger t
  JOIN pg_proc p ON p.oid = t.tgfoid
  JOIN pg_namespace pn ON pn.oid = p.pronamespace
  WHERE pn.nspname = 'public' AND p.proname = 'set_guest_user_null'
    AND NOT t.tgisinternal AND t.tgenabled = 'O';
  IF v_trig_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: expected 1 active trigger, found %.', v_trig_count;
  END IF;

  -- 1-k. 트리거 정의 MD5 기준선
  SELECT md5(pg_get_triggerdef(t.oid)) INTO v_trig_md5
  FROM pg_trigger t
  JOIN pg_proc p ON p.oid = t.tgfoid
  JOIN pg_namespace pn ON pn.oid = p.pronamespace
  WHERE pn.nspname = 'public' AND p.proname = 'set_guest_user_null'
    AND NOT t.tgisinternal;
  IF v_trig_md5 != '5a22f8575250d9a458d39a93c90abbf2' THEN
    RAISE EXCEPTION 'PRE FAILED: trigger definition MD5 mismatch: got %.', v_trig_md5;
  END IF;

  -- 1-l. payments RLS 활성
  SELECT relrowsecurity INTO v_rls
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = 'payments';
  IF v_rls != true THEN
    RAISE EXCEPTION 'PRE FAILED: payments RLS is not enabled.';
  END IF;

  -- 1-m. anon의 public 스키마 CREATE 권한 없음
  IF has_schema_privilege('anon', 'public', 'CREATE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon has CREATE on public schema — search_path injection risk.';
  END IF;

  -- 1-n. authenticated의 public 스키마 CREATE 권한 없음
  IF has_schema_privilege('authenticated', 'public', 'CREATE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated has CREATE on public schema — search_path injection risk.';
  END IF;

  RAISE NOTICE 'PRE: Pre-conditions PASS (함수·트리거·ACL·RLS·스키마권한).';

  -- ── STEP 2: 변경 실행 ──────────────────────────────────────────────

  ALTER FUNCTION public.set_guest_user_null()
    SET search_path TO pg_catalog, public, pg_temp;

  RAISE NOTICE 'STEP 2: search_path 고정 완료 (set_guest_user_null).';

  -- ── STEP 3: 사후조건 검증 ──────────────────────────────────────────

  -- 3-a. proconfig 설정 확인
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'set_guest_user_null' AND p.pronargs = 0;
  IF v_proconfig IS NULL OR NOT (v_proconfig @> ARRAY['search_path=pg_catalog, public, pg_temp']) THEN
    RAISE EXCEPTION 'POST FAILED: proconfig search_path not set correctly: %.', v_proconfig;
  END IF;

  -- 3-b. 함수 본문 MD5 불변
  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'set_guest_user_null' AND p.pronargs = 0;
  IF v_body_md5 != 'a879552fd1b918e717c633e7ace65a72' THEN
    RAISE EXCEPTION 'POST FAILED: body MD5 changed after ALTER: got %.', v_body_md5;
  END IF;

  -- 3-c. SECURITY DEFINER 불변
  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'set_guest_user_null' AND p.pronargs = 0;
  IF v_secdef != true THEN
    RAISE EXCEPTION 'POST FAILED: SECURITY DEFINER changed after ALTER.';
  END IF;

  -- 3-d. 소유자 불변
  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'set_guest_user_null' AND p.pronargs = 0;
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'POST FAILED: owner changed to % after ALTER.', v_owner;
  END IF;

  -- 3-e. anon EXECUTE 불변 (= FALSE)
  IF has_function_privilege('anon', 'public.set_guest_user_null()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: anon gained EXECUTE after ALTER.';
  END IF;

  -- 3-f. authenticated EXECUTE 불변 (= FALSE)
  IF has_function_privilege('authenticated', 'public.set_guest_user_null()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: authenticated gained EXECUTE after ALTER.';
  END IF;

  -- 3-g. service_role EXECUTE 불변 (= TRUE)
  IF NOT has_function_privilege('service_role', 'public.set_guest_user_null()', 'EXECUTE') THEN
    RAISE EXCEPTION 'POST FAILED: service_role lost EXECUTE after ALTER.';
  END IF;

  -- 3-h. 활성 트리거 수 불변
  SELECT count(*) INTO v_trig_count
  FROM pg_trigger t
  JOIN pg_proc p ON p.oid = t.tgfoid
  JOIN pg_namespace pn ON pn.oid = p.pronamespace
  WHERE pn.nspname = 'public' AND p.proname = 'set_guest_user_null'
    AND NOT t.tgisinternal AND t.tgenabled = 'O';
  IF v_trig_count != 1 THEN
    RAISE EXCEPTION 'POST FAILED: active trigger count changed to %.', v_trig_count;
  END IF;

  -- 3-i. 트리거 정의 MD5 불변
  SELECT md5(pg_get_triggerdef(t.oid)) INTO v_trig_md5
  FROM pg_trigger t
  JOIN pg_proc p ON p.oid = t.tgfoid
  JOIN pg_namespace pn ON pn.oid = p.pronamespace
  WHERE pn.nspname = 'public' AND p.proname = 'set_guest_user_null'
    AND NOT t.tgisinternal;
  IF v_trig_md5 != '5a22f8575250d9a458d39a93c90abbf2' THEN
    RAISE EXCEPTION 'POST FAILED: trigger MD5 changed after ALTER: got %.', v_trig_md5;
  END IF;

  -- 3-j. payments RLS 불변
  SELECT relrowsecurity INTO v_rls
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = 'payments';
  IF v_rls != true THEN
    RAISE EXCEPTION 'POST FAILED: payments RLS changed after ALTER.';
  END IF;

  RAISE NOTICE 'POST-COMPLETE: set_guest_user_null() search_path=pg_catalog,public,pg_temp 고정. 본문·SECDEF·ACL·트리거·RLS 불변.';

END;
$$;

COMMIT;
