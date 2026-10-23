-- Migration: 20261023082048_sec_searchpath_rem97_w2_utility_functions.sql
-- WO: WO-TAI-SEC-SEARCHPATH-REM97-C3-W2-SOURCE-001
-- SEC SEARCHPATH REM97 W2 — 유틸리티 함수 4개 search_path 고정
--
-- 배경:
--   A-그룹 W2 대상 4개 함수: 모두 SECURITY INVOKER, proconfig=NULL
--   → function_search_path_mutable Advisor 경고 89건 중 W2 4건 해소 (89→85).
--   함수 본문은 search_path에 의존하지 않는 순수 연산 또는 text 반환 패턴으로
--   search_path 고정이 동작에 영향 없음 (METADATA_ONLY).
--
-- 변경 범위:
--   ALTER FUNCTION ... SET search_path = pg_catalog, public, pg_temp (4건).
--   함수 본문·ACL·SECURITY INVOKER·Volatility·Parallel 속성 변경 없음.
--   help_doc_blocks_chk 제약조건 변경 없음.
--
-- 참조:
--   20261023012950_sec_searchpath_rem97_w1_timestamp_triggers.sql
--   C2 설계: WO-TAI-SEC-SEARCHPATH-REM97-C2-DESIGN-001
--   C1 기준: WO-TAI-SEC-SEARCHPATH-REM97-C1 CLOSED_FINAL (97건 / A=20 / W2=4)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1: PRE 조건 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  -- ACL 기준선 (4개 함수 동일)
  c_acl_baseline CONSTANT text :=
    '{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}';

  -- 함수별 기대값 (fn_sig, expected_oid, expected_prosrc_md5, expected_volatility)
  v_fn_sigs  text[]  := ARRAY[
    'public.generate_request_no()',
    'public.help_blocks_valid(jsonb)',
    'public.help_doc_include_refs(jsonb)',
    'public.jsonb_to_text_array(jsonb)'
  ];
  v_oids     oid[]   := ARRAY[18565, 246342, 246455, 18569];
  v_md5s     text[]  := ARRAY[
    'bc68b45992c6ae6918b7b7897968eb59',
    'f8ab771e143a1f4bae50d8f4e834956c',
    'f59b1a9e351738a420a554dbd3bf005e',
    '8ffd61ed1e5f379f96de29d745138596'
  ];
  v_volats   char[]  := ARRAY['v', 'i', 'i', 'i'];

  i           int;
  v_fn_sig    text;
  v_oid       oid;
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
  v_proacl    text;
  v_volat     char;

BEGIN
  FOR i IN 1..array_length(v_fn_sigs, 1) LOOP
    v_fn_sig := v_fn_sigs[i];

    -- 1-a. 함수 존재 확인
    IF to_regprocedure(v_fn_sig) IS NULL THEN
      RAISE EXCEPTION 'PRE FAILED: % not found.', v_fn_sig;
    END IF;

    v_oid := to_regprocedure(v_fn_sig)::oid;

    -- 1-b. OID 기준선 확인
    IF v_oid IS DISTINCT FROM v_oids[i] THEN
      RAISE EXCEPTION 'PRE FAILED: % OID mismatch (expected %, got %).', v_fn_sig, v_oids[i], v_oid;
    END IF;

    -- 1-c. SECURITY INVOKER 확인
    SELECT p.prosecdef INTO v_secdef FROM pg_proc p WHERE p.oid = v_oid;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'PRE FAILED: % is not SECURITY INVOKER.', v_fn_sig;
    END IF;

    -- 1-d. 소유자 = postgres
    SELECT pg_get_userbyid(p.proowner) INTO v_owner FROM pg_proc p WHERE p.oid = v_oid;
    IF v_owner IS DISTINCT FROM 'postgres' THEN
      RAISE EXCEPTION 'PRE FAILED: % owner is %, expected postgres.', v_fn_sig, v_owner;
    END IF;

    -- 1-e. 함수 본문 MD5 기준선
    SELECT md5(p.prosrc) INTO v_body_md5 FROM pg_proc p WHERE p.oid = v_oid;
    IF v_body_md5 IS DISTINCT FROM v_md5s[i] THEN
      RAISE EXCEPTION 'PRE FAILED: % prosrc_md5 mismatch (expected %, got %).', v_fn_sig, v_md5s[i], v_body_md5;
    END IF;

    -- 1-f. proconfig = NULL (아직 미적용)
    SELECT p.proconfig INTO v_proconfig FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proconfig IS NOT NULL THEN
      RAISE EXCEPTION 'PRE FAILED: % proconfig already set: %.', v_fn_sig, v_proconfig;
    END IF;

    -- 1-g. anon EXECUTE = TRUE
    IF NOT has_function_privilege('anon', v_fn_sig, 'EXECUTE') THEN
      RAISE EXCEPTION 'PRE FAILED: anon does not have EXECUTE on %.', v_fn_sig;
    END IF;

    -- 1-h. authenticated EXECUTE = TRUE
    IF NOT has_function_privilege('authenticated', v_fn_sig, 'EXECUTE') THEN
      RAISE EXCEPTION 'PRE FAILED: authenticated does not have EXECUTE on %.', v_fn_sig;
    END IF;

    -- 1-i. 전체 ACL 기준선
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proacl IS DISTINCT FROM c_acl_baseline THEN
      RAISE EXCEPTION 'PRE FAILED: % ACL mismatch (got %).', v_fn_sig, v_proacl;
    END IF;

    -- 1-j. Volatility 기준선
    SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = v_oid;
    IF v_volat IS DISTINCT FROM v_volats[i] THEN
      RAISE EXCEPTION 'PRE FAILED: % volatility mismatch (expected %, got %).', v_fn_sig, v_volats[i], v_volat;
    END IF;

  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1B: PRE 제약조건 기준선 검증 (help_doc_blocks_chk)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_con_def text;
BEGIN
  SELECT pg_get_constraintdef(c.oid)
    INTO v_con_def
  FROM pg_constraint c
  JOIN pg_class t ON t.oid = c.conrelid
  WHERE c.conname = 'help_doc_blocks_chk'
    AND t.relname = 'help_doc';

  IF v_con_def IS NULL THEN
    RAISE EXCEPTION 'PRE FAILED: help_doc_blocks_chk constraint not found on help_doc.';
  END IF;

  IF v_con_def IS DISTINCT FROM 'CHECK (help_blocks_valid(blocks))' THEN
    RAISE EXCEPTION 'PRE FAILED: help_doc_blocks_chk definition changed (got %).', v_con_def;
  END IF;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2: search_path 고정 (METADATA_ONLY — 함수 본문·제약조건·ACL 변경 없음)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.generate_request_no()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.help_blocks_valid(b jsonb)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.help_doc_include_refs(b jsonb)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.jsonb_to_text_array(j jsonb)
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3: POST 조건 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_acl_baseline  CONSTANT text :=
    '{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}';
  c_search_path   CONSTANT text := 'search_path=pg_catalog, public, pg_temp';

  v_fn_sigs  text[]  := ARRAY[
    'public.generate_request_no()',
    'public.help_blocks_valid(jsonb)',
    'public.help_doc_include_refs(jsonb)',
    'public.jsonb_to_text_array(jsonb)'
  ];
  v_oids     oid[]   := ARRAY[18565, 246342, 246455, 18569];
  v_md5s     text[]  := ARRAY[
    'bc68b45992c6ae6918b7b7897968eb59',
    'f8ab771e143a1f4bae50d8f4e834956c',
    'f59b1a9e351738a420a554dbd3bf005e',
    '8ffd61ed1e5f379f96de29d745138596'
  ];
  v_volats   char[]  := ARRAY['v', 'i', 'i', 'i'];

  i           int;
  v_fn_sig    text;
  v_oid       oid;
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
  v_proacl    text;
  v_volat     char;

BEGIN
  FOR i IN 1..array_length(v_fn_sigs, 1) LOOP
    v_fn_sig := v_fn_sigs[i];
    v_oid    := v_oids[i];

    -- 3-a. OID 불변 확인
    IF to_regprocedure(v_fn_sig)::oid IS DISTINCT FROM v_oid THEN
      RAISE EXCEPTION 'POST FAILED: % OID changed unexpectedly.', v_fn_sig;
    END IF;

    -- 3-b. proconfig 정확 일치 확인 (NULL-safe, 추가 설정 불허)
    SELECT p.proconfig INTO v_proconfig FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
      RAISE EXCEPTION 'POST FAILED: % unexpected proconfig: %.', v_fn_sig, v_proconfig;
    END IF;

    -- 3-c. 함수 본문 MD5 불변 확인
    SELECT md5(p.prosrc) INTO v_body_md5 FROM pg_proc p WHERE p.oid = v_oid;
    IF v_body_md5 IS DISTINCT FROM v_md5s[i] THEN
      RAISE EXCEPTION 'POST FAILED: % prosrc_md5 changed (expected %, got %).', v_fn_sig, v_md5s[i], v_body_md5;
    END IF;

    -- 3-d. SECURITY INVOKER 불변
    SELECT p.prosecdef INTO v_secdef FROM pg_proc p WHERE p.oid = v_oid;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'POST FAILED: % prosecdef changed.', v_fn_sig;
    END IF;

    -- 3-e. 소유자 불변
    SELECT pg_get_userbyid(p.proowner) INTO v_owner FROM pg_proc p WHERE p.oid = v_oid;
    IF v_owner IS DISTINCT FROM 'postgres' THEN
      RAISE EXCEPTION 'POST FAILED: % owner changed (got %).', v_fn_sig, v_owner;
    END IF;

    -- 3-f. ACL 불변
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proacl IS DISTINCT FROM c_acl_baseline THEN
      RAISE EXCEPTION 'POST FAILED: % ACL changed (got %).', v_fn_sig, v_proacl;
    END IF;

    -- 3-g. Volatility 불변
    SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = v_oid;
    IF v_volat IS DISTINCT FROM v_volats[i] THEN
      RAISE EXCEPTION 'POST FAILED: % volatility changed (expected %, got %).', v_fn_sig, v_volats[i], v_volat;
    END IF;

  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3B: POST 제약조건 불변 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_con_def text;
BEGIN
  SELECT pg_get_constraintdef(c.oid)
    INTO v_con_def
  FROM pg_constraint c
  JOIN pg_class t ON t.oid = c.conrelid
  WHERE c.conname = 'help_doc_blocks_chk'
    AND t.relname = 'help_doc';

  IF v_con_def IS NULL THEN
    RAISE EXCEPTION 'POST FAILED: help_doc_blocks_chk constraint missing after migration.';
  END IF;

  IF v_con_def IS DISTINCT FROM 'CHECK (help_blocks_valid(blocks))' THEN
    RAISE EXCEPTION 'POST FAILED: help_doc_blocks_chk definition changed (got %).', v_con_def;
  END IF;
END;
$$;

COMMIT;
