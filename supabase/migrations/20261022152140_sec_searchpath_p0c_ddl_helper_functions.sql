-- Migration: 20261022152140_sec_searchpath_p0c_ddl_helper_functions.sql
-- WO: WO-TAI-SEC-SEARCHPATH-P0C-IMPLEMENT-001
-- PARENT: WO-TAI-SEC-SEARCHPATH-P0C-IMPACT-001
-- SEC SEARCHPATH P0C — public DDL 헬퍼 함수 4개 search_path 고정
-- R1: ACL PRE/POST 강화 · Owner POST 추가 · 정확한 인수타입 · 트리거 10건 PRE/POST · proconfig 동일성 검증
--
-- 배경:
--   tai_add_audit_columns(text), tai_comment_column(text,text,text),
--   tai_comment_table(text,text), tai_create_update_trigger(text):
--   모두 SECURITY INVOKER, proconfig=NULL → function_search_path_mutable Advisor 경고.
--   함수 본문 내 객체 참조가 public 범위 내이며 %I는 식별자 인용만 수행.
--   메타데이터 고정만으로 경고 해소 가능 (본문 재작성 불필요).
--
-- 변경 범위:
--   ALTER FUNCTION ... SET search_path TO pg_catalog, public, pg_temp (4건).
--   함수 본문, 트리거, ACL, SECURITY INVOKER 속성 변경 없음.
--
-- 참조:
--   20261022100136_sec_searchpath_p0a_secdef_aggregate_functions.sql
--   20261022131807_sec_searchpath_p0b_set_guest_user_null.sql

BEGIN;

DO $$
DECLARE
  v_count        int;
  v_owner        text;
  v_secdef       bool;
  v_body_md5     text;
  v_proconfig    text[];
  v_trig_count   int;
  v_proacl       text;

  -- ACL 기준선 (4개 함수 동일)
  c_acl_baseline CONSTANT text :=
    '{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}';
  -- proconfig 목표값 (단일 항목)
  c_search_path  CONSTANT text := 'search_path=pg_catalog, public, pg_temp';

BEGIN

  -- ── STEP 1: 사전조건 검증 ────────────────────────────────────────────

  -- ── F1: tai_add_audit_columns(text) ─────────────────────────────────

  -- 1-a. 함수 존재 및 정확한 인수 타입 확인
  SELECT count(*) INTO v_count
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_add_audit_columns'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: public.tai_add_audit_columns(text) not found or signature mismatch.';
  END IF;

  -- 1-b. SECURITY INVOKER 확인
  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_add_audit_columns'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_secdef != false THEN
    RAISE EXCEPTION 'PRE FAILED: tai_add_audit_columns() is not SECURITY INVOKER — baseline mismatch.';
  END IF;

  -- 1-c. 소유자 = postgres
  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_add_audit_columns'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'PRE FAILED: tai_add_audit_columns() owner is %, expected postgres.', v_owner;
  END IF;

  -- 1-d. 함수 본문 MD5 기준선
  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_add_audit_columns'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_body_md5 != '363bbf0a50ac376c841225d564ad7809' THEN
    RAISE EXCEPTION 'PRE FAILED: tai_add_audit_columns() body MD5 mismatch: got %.', v_body_md5;
  END IF;

  -- 1-e. proconfig = NULL
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_add_audit_columns'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'PRE FAILED: tai_add_audit_columns() proconfig already set: %.', v_proconfig;
  END IF;

  -- 1-f. anon EXECUTE = TRUE
  IF NOT has_function_privilege('anon', 'public.tai_add_audit_columns(text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon does not have EXECUTE on tai_add_audit_columns().';
  END IF;

  -- 1-g. authenticated EXECUTE = TRUE
  IF NOT has_function_privilege('authenticated', 'public.tai_add_audit_columns(text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated does not have EXECUTE on tai_add_audit_columns().';
  END IF;

  -- 1-h. 전체 ACL 기준선 확인
  SELECT p.proacl::text INTO v_proacl
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_add_audit_columns'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_proacl != c_acl_baseline THEN
    RAISE EXCEPTION 'PRE FAILED: tai_add_audit_columns() ACL mismatch: got %.', v_proacl;
  END IF;

  -- ── F2: tai_comment_column(text,text,text) ───────────────────────────

  -- 2-a. 함수 존재 및 정확한 인수 타입 확인
  SELECT count(*) INTO v_count
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_column'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text, text';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: public.tai_comment_column(text,text,text) not found or signature mismatch.';
  END IF;

  -- 2-b. SECURITY INVOKER 확인
  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_column'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text, text';
  IF v_secdef != false THEN
    RAISE EXCEPTION 'PRE FAILED: tai_comment_column() is not SECURITY INVOKER — baseline mismatch.';
  END IF;

  -- 2-c. 소유자 = postgres
  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_column'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text, text';
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'PRE FAILED: tai_comment_column() owner is %, expected postgres.', v_owner;
  END IF;

  -- 2-d. 함수 본문 MD5 기준선
  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_column'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text, text';
  IF v_body_md5 != '418c8af3362682dff269df17872e4aa9' THEN
    RAISE EXCEPTION 'PRE FAILED: tai_comment_column() body MD5 mismatch: got %.', v_body_md5;
  END IF;

  -- 2-e. proconfig = NULL
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_column'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text, text';
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'PRE FAILED: tai_comment_column() proconfig already set: %.', v_proconfig;
  END IF;

  -- 2-f. anon EXECUTE = TRUE
  IF NOT has_function_privilege('anon', 'public.tai_comment_column(text,text,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon does not have EXECUTE on tai_comment_column().';
  END IF;

  -- 2-g. authenticated EXECUTE = TRUE
  IF NOT has_function_privilege('authenticated', 'public.tai_comment_column(text,text,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated does not have EXECUTE on tai_comment_column().';
  END IF;

  -- 2-h. 전체 ACL 기준선 확인
  SELECT p.proacl::text INTO v_proacl
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_column'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text, text';
  IF v_proacl != c_acl_baseline THEN
    RAISE EXCEPTION 'PRE FAILED: tai_comment_column() ACL mismatch: got %.', v_proacl;
  END IF;

  -- ── F3: tai_comment_table(text,text) ────────────────────────────────

  -- 3-a. 함수 존재 및 정확한 인수 타입 확인
  SELECT count(*) INTO v_count
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_table'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: public.tai_comment_table(text,text) not found or signature mismatch.';
  END IF;

  -- 3-b. SECURITY INVOKER 확인
  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_table'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text';
  IF v_secdef != false THEN
    RAISE EXCEPTION 'PRE FAILED: tai_comment_table() is not SECURITY INVOKER — baseline mismatch.';
  END IF;

  -- 3-c. 소유자 = postgres
  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_table'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text';
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'PRE FAILED: tai_comment_table() owner is %, expected postgres.', v_owner;
  END IF;

  -- 3-d. 함수 본문 MD5 기준선
  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_table'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text';
  IF v_body_md5 != '7da885c26c03a436a209b7eb12070feb' THEN
    RAISE EXCEPTION 'PRE FAILED: tai_comment_table() body MD5 mismatch: got %.', v_body_md5;
  END IF;

  -- 3-e. proconfig = NULL
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_table'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text';
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'PRE FAILED: tai_comment_table() proconfig already set: %.', v_proconfig;
  END IF;

  -- 3-f. anon EXECUTE = TRUE
  IF NOT has_function_privilege('anon', 'public.tai_comment_table(text,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon does not have EXECUTE on tai_comment_table().';
  END IF;

  -- 3-g. authenticated EXECUTE = TRUE
  IF NOT has_function_privilege('authenticated', 'public.tai_comment_table(text,text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated does not have EXECUTE on tai_comment_table().';
  END IF;

  -- 3-h. 전체 ACL 기준선 확인
  SELECT p.proacl::text INTO v_proacl
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_table'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text';
  IF v_proacl != c_acl_baseline THEN
    RAISE EXCEPTION 'PRE FAILED: tai_comment_table() ACL mismatch: got %.', v_proacl;
  END IF;

  -- ── F4: tai_create_update_trigger(text) ─────────────────────────────

  -- 4-a. 함수 존재 및 정확한 인수 타입 확인
  SELECT count(*) INTO v_count
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_create_update_trigger'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: public.tai_create_update_trigger(text) not found or signature mismatch.';
  END IF;

  -- 4-b. SECURITY INVOKER 확인
  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_create_update_trigger'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_secdef != false THEN
    RAISE EXCEPTION 'PRE FAILED: tai_create_update_trigger() is not SECURITY INVOKER — baseline mismatch.';
  END IF;

  -- 4-c. 소유자 = postgres
  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_create_update_trigger'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'PRE FAILED: tai_create_update_trigger() owner is %, expected postgres.', v_owner;
  END IF;

  -- 4-d. 함수 본문 MD5 기준선
  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_create_update_trigger'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_body_md5 != 'df68333c1155353f9c0395a59ad7bdf2' THEN
    RAISE EXCEPTION 'PRE FAILED: tai_create_update_trigger() body MD5 mismatch: got %.', v_body_md5;
  END IF;

  -- 4-e. proconfig = NULL
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_create_update_trigger'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'PRE FAILED: tai_create_update_trigger() proconfig already set: %.', v_proconfig;
  END IF;

  -- 4-f. anon EXECUTE = TRUE
  IF NOT has_function_privilege('anon', 'public.tai_create_update_trigger(text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon does not have EXECUTE on tai_create_update_trigger().';
  END IF;

  -- 4-g. authenticated EXECUTE = TRUE
  IF NOT has_function_privilege('authenticated', 'public.tai_create_update_trigger(text)', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated does not have EXECUTE on tai_create_update_trigger().';
  END IF;

  -- 4-h. 전체 ACL 기준선 확인
  SELECT p.proacl::text INTO v_proacl
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_create_update_trigger'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_proacl != c_acl_baseline THEN
    RAISE EXCEPTION 'PRE FAILED: tai_create_update_trigger() ACL mismatch: got %.', v_proacl;
  END IF;

  -- ── tai_set_updated_at() 존재 및 활성 트리거 10개 확인 ──────────────
  SELECT count(*) INTO v_count
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_set_updated_at';
  IF v_count < 1 THEN
    RAISE EXCEPTION 'PRE FAILED: public.tai_set_updated_at() not found — dependency missing.';
  END IF;

  SELECT count(*) INTO v_trig_count
  FROM pg_trigger t
  JOIN pg_proc p ON p.oid = t.tgfoid
  JOIN pg_namespace pn ON pn.oid = p.pronamespace
  WHERE pn.nspname = 'public' AND p.proname = 'tai_set_updated_at'
    AND NOT t.tgisinternal AND t.tgenabled = 'O';
  IF v_trig_count != 10 THEN
    RAISE EXCEPTION 'PRE FAILED: expected 10 active triggers for tai_set_updated_at(), found %.', v_trig_count;
  END IF;

  -- ── 스키마 CREATE 권한 없음 ──────────────────────────────────────────
  IF has_schema_privilege('anon', 'public', 'CREATE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon has CREATE on public schema — search_path injection risk.';
  END IF;
  IF has_schema_privilege('authenticated', 'public', 'CREATE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated has CREATE on public schema — search_path injection risk.';
  END IF;

  RAISE NOTICE 'PRE: Pre-conditions PASS (함수 4개·MD5·ACL·의존함수·트리거10·스키마권한).';

  -- ── STEP 2: 변경 실행 ──────────────────────────────────────────────

  ALTER FUNCTION public.tai_add_audit_columns(text)
    SET search_path TO pg_catalog, public, pg_temp;

  ALTER FUNCTION public.tai_comment_column(text, text, text)
    SET search_path TO pg_catalog, public, pg_temp;

  ALTER FUNCTION public.tai_comment_table(text, text)
    SET search_path TO pg_catalog, public, pg_temp;

  ALTER FUNCTION public.tai_create_update_trigger(text)
    SET search_path TO pg_catalog, public, pg_temp;

  RAISE NOTICE 'STEP 2: search_path 고정 완료 (4개 함수).';

  -- ── STEP 3: 사후조건 검증 ──────────────────────────────────────────

  -- ── POST F1 ──
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_add_audit_columns'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_proconfig IS NULL
     OR array_length(v_proconfig, 1) != 1
     OR v_proconfig[1] != c_search_path THEN
    RAISE EXCEPTION 'POST FAILED: tai_add_audit_columns() proconfig not set correctly: %.', v_proconfig;
  END IF;

  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_add_audit_columns'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_body_md5 != '363bbf0a50ac376c841225d564ad7809' THEN
    RAISE EXCEPTION 'POST FAILED: tai_add_audit_columns() body MD5 changed: got %.', v_body_md5;
  END IF;

  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_add_audit_columns'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_secdef != false THEN
    RAISE EXCEPTION 'POST FAILED: tai_add_audit_columns() SECURITY INVOKER changed after ALTER.';
  END IF;

  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_add_audit_columns'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'POST FAILED: tai_add_audit_columns() owner changed to % after ALTER.', v_owner;
  END IF;

  SELECT p.proacl::text INTO v_proacl
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_add_audit_columns'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_proacl != c_acl_baseline THEN
    RAISE EXCEPTION 'POST FAILED: tai_add_audit_columns() ACL changed: got %.', v_proacl;
  END IF;

  -- ── POST F2 ──
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_column'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text, text';
  IF v_proconfig IS NULL
     OR array_length(v_proconfig, 1) != 1
     OR v_proconfig[1] != c_search_path THEN
    RAISE EXCEPTION 'POST FAILED: tai_comment_column() proconfig not set correctly: %.', v_proconfig;
  END IF;

  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_column'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text, text';
  IF v_body_md5 != '418c8af3362682dff269df17872e4aa9' THEN
    RAISE EXCEPTION 'POST FAILED: tai_comment_column() body MD5 changed: got %.', v_body_md5;
  END IF;

  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_column'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text, text';
  IF v_secdef != false THEN
    RAISE EXCEPTION 'POST FAILED: tai_comment_column() SECURITY INVOKER changed after ALTER.';
  END IF;

  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_column'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text, text';
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'POST FAILED: tai_comment_column() owner changed to % after ALTER.', v_owner;
  END IF;

  SELECT p.proacl::text INTO v_proacl
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_column'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text, text';
  IF v_proacl != c_acl_baseline THEN
    RAISE EXCEPTION 'POST FAILED: tai_comment_column() ACL changed: got %.', v_proacl;
  END IF;

  -- ── POST F3 ──
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_table'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text';
  IF v_proconfig IS NULL
     OR array_length(v_proconfig, 1) != 1
     OR v_proconfig[1] != c_search_path THEN
    RAISE EXCEPTION 'POST FAILED: tai_comment_table() proconfig not set correctly: %.', v_proconfig;
  END IF;

  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_table'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text';
  IF v_body_md5 != '7da885c26c03a436a209b7eb12070feb' THEN
    RAISE EXCEPTION 'POST FAILED: tai_comment_table() body MD5 changed: got %.', v_body_md5;
  END IF;

  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_table'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text';
  IF v_secdef != false THEN
    RAISE EXCEPTION 'POST FAILED: tai_comment_table() SECURITY INVOKER changed after ALTER.';
  END IF;

  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_table'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text';
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'POST FAILED: tai_comment_table() owner changed to % after ALTER.', v_owner;
  END IF;

  SELECT p.proacl::text INTO v_proacl
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_comment_table'
    AND pg_get_function_identity_arguments(p.oid) = 'text, text';
  IF v_proacl != c_acl_baseline THEN
    RAISE EXCEPTION 'POST FAILED: tai_comment_table() ACL changed: got %.', v_proacl;
  END IF;

  -- ── POST F4 ──
  SELECT p.proconfig INTO v_proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_create_update_trigger'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_proconfig IS NULL
     OR array_length(v_proconfig, 1) != 1
     OR v_proconfig[1] != c_search_path THEN
    RAISE EXCEPTION 'POST FAILED: tai_create_update_trigger() proconfig not set correctly: %.', v_proconfig;
  END IF;

  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_create_update_trigger'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_body_md5 != 'df68333c1155353f9c0395a59ad7bdf2' THEN
    RAISE EXCEPTION 'POST FAILED: tai_create_update_trigger() body MD5 changed: got %.', v_body_md5;
  END IF;

  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_create_update_trigger'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_secdef != false THEN
    RAISE EXCEPTION 'POST FAILED: tai_create_update_trigger() SECURITY INVOKER changed after ALTER.';
  END IF;

  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_create_update_trigger'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'POST FAILED: tai_create_update_trigger() owner changed to % after ALTER.', v_owner;
  END IF;

  SELECT p.proacl::text INTO v_proacl
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'tai_create_update_trigger'
    AND pg_get_function_identity_arguments(p.oid) = 'text';
  IF v_proacl != c_acl_baseline THEN
    RAISE EXCEPTION 'POST FAILED: tai_create_update_trigger() ACL changed: got %.', v_proacl;
  END IF;

  -- ── POST 트리거 보존 ───────────────────────────────────────────────
  SELECT count(*) INTO v_trig_count
  FROM pg_trigger t
  JOIN pg_proc p ON p.oid = t.tgfoid
  JOIN pg_namespace pn ON pn.oid = p.pronamespace
  WHERE pn.nspname = 'public' AND p.proname = 'tai_set_updated_at'
    AND NOT t.tgisinternal AND t.tgenabled = 'O';
  IF v_trig_count != 10 THEN
    RAISE EXCEPTION 'POST FAILED: active trigger count for tai_set_updated_at() changed to %.', v_trig_count;
  END IF;

  RAISE NOTICE 'POST-COMPLETE: 4개 함수 search_path=pg_catalog,public,pg_temp 고정. 본문·SECDEF·Owner·ACL·트리거 불변.';

END;
$$;

COMMIT;
