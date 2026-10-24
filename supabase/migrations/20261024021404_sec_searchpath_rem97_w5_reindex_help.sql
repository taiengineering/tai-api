-- Migration: 20261024021404_sec_searchpath_rem97_w5_reindex_help.sql
-- WO: WO-TAI-SEC-SEARCHPATH-REM97-C3-W5-SOURCE-001
-- SEC SEARCHPATH REM97 W5 — 검색 인덱스 갱신 함수 search_path 고정
--
-- 배경:
--   A-그룹 W5 대상 1개 함수: SECURITY INVOKER, proconfig=NULL
--   → function_search_path_mutable Advisor 경고 83건 중 W5 1건 해소 (83→82).
--   함수 본문:
--     UPDATE safe_help_content
--        SET search_tsv = to_tsvector('simple', COALESCE(p_txt, '')),
--            updated_at = now()
--      WHERE id = p_id;
--   search_path 고정 후 safe_help_content → public.safe_help_content 로 해석
--   (METADATA_ONLY, 기존 동작 변경 없음).
--
-- 변경 범위:
--   ALTER FUNCTION public.reindex_help(uuid, text)
--     SET search_path = pg_catalog, public, pg_temp (1건).
--   함수 본문·ACL·SECURITY INVOKER·Volatility·Parallel 속성 변경 없음.
--
-- 참조:
--   20261023124050_sec_searchpath_rem97_w3_cycle_guard_functions.sql
--   C2 설계: WO-TAI-SEC-SEARCHPATH-REM97-C2-DESIGN-001 / CLOSED_WITH_W4_HOLD
--   C1 기준: WO-TAI-SEC-SEARCHPATH-REM97-C1 CLOSED_FINAL (97건 / A=20 / W5=1)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1: PRE 조건 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_acl_baseline CONSTANT text :=
    '{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}';
  c_fn_sig       CONSTANT text := 'public.reindex_help(uuid, text)';
  c_expected_oid CONSTANT oid  := 243820;
  c_expected_md5 CONSTANT text := '5e69750107f8361914662d0609233d7a';

  v_oid       oid;
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
  v_proacl    text;
  v_volat     char;
  v_parallel  char;

BEGIN
  -- 1-a. 함수 존재 확인
  IF to_regprocedure(c_fn_sig) IS NULL THEN
    RAISE EXCEPTION 'PRE FAILED: % not found.', c_fn_sig;
  END IF;

  v_oid := to_regprocedure(c_fn_sig)::oid;

  -- 1-b. OID 기준선 확인
  IF v_oid IS DISTINCT FROM c_expected_oid THEN
    RAISE EXCEPTION 'PRE FAILED: % OID mismatch (expected %, got %).', c_fn_sig, c_expected_oid, v_oid;
  END IF;

  -- 1-c. SECURITY INVOKER 확인
  SELECT p.prosecdef INTO v_secdef FROM pg_proc p WHERE p.oid = v_oid;
  IF v_secdef IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'PRE FAILED: % is not SECURITY INVOKER.', c_fn_sig;
  END IF;

  -- 1-d. 소유자 = postgres
  SELECT pg_get_userbyid(p.proowner) INTO v_owner FROM pg_proc p WHERE p.oid = v_oid;
  IF v_owner IS DISTINCT FROM 'postgres' THEN
    RAISE EXCEPTION 'PRE FAILED: % owner is %, expected postgres.', c_fn_sig, v_owner;
  END IF;

  -- 1-e. 함수 본문 MD5 기준선
  SELECT md5(p.prosrc) INTO v_body_md5 FROM pg_proc p WHERE p.oid = v_oid;
  IF v_body_md5 IS DISTINCT FROM c_expected_md5 THEN
    RAISE EXCEPTION 'PRE FAILED: % prosrc_md5 mismatch (expected %, got %).', c_fn_sig, c_expected_md5, v_body_md5;
  END IF;

  -- 1-f. proconfig = NULL (아직 미적용)
  SELECT p.proconfig INTO v_proconfig FROM pg_proc p WHERE p.oid = v_oid;
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'PRE FAILED: % proconfig already set: %.', c_fn_sig, v_proconfig;
  END IF;

  -- 1-g. anon EXECUTE = TRUE
  IF NOT has_function_privilege('anon', c_fn_sig, 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon does not have EXECUTE on %.', c_fn_sig;
  END IF;

  -- 1-h. authenticated EXECUTE = TRUE
  IF NOT has_function_privilege('authenticated', c_fn_sig, 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated does not have EXECUTE on %.', c_fn_sig;
  END IF;

  -- 1-i. 전체 ACL 기준선
  SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = v_oid;
  IF v_proacl IS DISTINCT FROM c_acl_baseline THEN
    RAISE EXCEPTION 'PRE FAILED: % ACL mismatch (got %).', c_fn_sig, v_proacl;
  END IF;

  -- 1-j. Volatility 기준선 (v = VOLATILE)
  SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = v_oid;
  IF v_volat IS DISTINCT FROM 'v' THEN
    RAISE EXCEPTION 'PRE FAILED: % volatility mismatch (expected v, got %).', c_fn_sig, v_volat;
  END IF;

  -- 1-k. Parallel 기준선 (u = UNSAFE)
  SELECT p.proparallel INTO v_parallel FROM pg_proc p WHERE p.oid = v_oid;
  IF v_parallel IS DISTINCT FROM 'u' THEN
    RAISE EXCEPTION 'PRE FAILED: % proparallel is %, expected u.', c_fn_sig, v_parallel;
  END IF;

END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1B: PRE 대상 테이블·컬럼 존재 확인
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_count int;
BEGIN
  -- safe_help_content 테이블 존재 확인
  SELECT COUNT(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = 'safe_help_content' AND c.relkind = 'r';
  IF v_count IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'PRE FAILED: public.safe_help_content table not found.';
  END IF;

  -- 필수 컬럼 확인: id (uuid), search_tsv (tsvector), updated_at (timestamptz)
  SELECT COUNT(*) INTO v_count
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name = 'safe_help_content'
    AND column_name IN ('id', 'search_tsv', 'updated_at');
  IF v_count IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'PRE FAILED: safe_help_content missing required columns (id/search_tsv/updated_at). found=%', v_count;
  END IF;

  -- search_tsv 컬럼 타입 확인 (tsvector)
  SELECT COUNT(*) INTO v_count
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name = 'safe_help_content'
    AND column_name = 'search_tsv'
    AND udt_name = 'tsvector';
  IF v_count IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'PRE FAILED: safe_help_content.search_tsv is not tsvector type.';
  END IF;

  -- text search config 'simple' 접근 가능 확인
  SELECT COUNT(*) INTO v_count
  FROM pg_ts_config
  WHERE cfgname = 'simple';
  IF v_count IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'PRE FAILED: text search config ''simple'' not found.';
  END IF;

END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2: search_path 고정 (METADATA_ONLY — 함수 본문·ACL 변경 없음)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.reindex_help(uuid, text)
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3: POST 조건 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_acl_baseline  CONSTANT text :=
    '{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}';
  c_search_path   CONSTANT text := 'search_path=pg_catalog, public, pg_temp';
  c_expected_oid  CONSTANT oid  := 243820;
  c_expected_md5  CONSTANT text := '5e69750107f8361914662d0609233d7a';
  c_fn_sig        CONSTANT text := 'public.reindex_help(uuid, text)';

  v_oid       oid;
  v_secdef    bool;
  v_owner     text;
  v_body_md5  text;
  v_proconfig text[];
  v_proacl    text;
  v_volat     char;
  v_parallel  char;

BEGIN
  v_oid := c_expected_oid;

  -- 3-a. OID 불변 확인
  IF to_regprocedure(c_fn_sig)::oid IS DISTINCT FROM v_oid THEN
    RAISE EXCEPTION 'POST FAILED: % OID changed unexpectedly.', c_fn_sig;
  END IF;

  -- 3-b. proconfig 정확 일치 확인 (NULL-safe, 추가 설정 불허)
  SELECT p.proconfig INTO v_proconfig FROM pg_proc p WHERE p.oid = v_oid;
  IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
    RAISE EXCEPTION 'POST FAILED: % unexpected proconfig: %.', c_fn_sig, v_proconfig;
  END IF;

  -- 3-c. 함수 본문 MD5 불변 확인
  SELECT md5(p.prosrc) INTO v_body_md5 FROM pg_proc p WHERE p.oid = v_oid;
  IF v_body_md5 IS DISTINCT FROM c_expected_md5 THEN
    RAISE EXCEPTION 'POST FAILED: % prosrc_md5 changed (expected %, got %).', c_fn_sig, c_expected_md5, v_body_md5;
  END IF;

  -- 3-d. SECURITY INVOKER 불변
  SELECT p.prosecdef INTO v_secdef FROM pg_proc p WHERE p.oid = v_oid;
  IF v_secdef IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'POST FAILED: % prosecdef changed.', c_fn_sig;
  END IF;

  -- 3-e. 소유자 불변
  SELECT pg_get_userbyid(p.proowner) INTO v_owner FROM pg_proc p WHERE p.oid = v_oid;
  IF v_owner IS DISTINCT FROM 'postgres' THEN
    RAISE EXCEPTION 'POST FAILED: % owner changed (got %).', c_fn_sig, v_owner;
  END IF;

  -- 3-f. ACL 불변
  SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = v_oid;
  IF v_proacl IS DISTINCT FROM c_acl_baseline THEN
    RAISE EXCEPTION 'POST FAILED: % ACL changed (got %).', c_fn_sig, v_proacl;
  END IF;

  -- 3-g. Volatility 불변
  SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = v_oid;
  IF v_volat IS DISTINCT FROM 'v' THEN
    RAISE EXCEPTION 'POST FAILED: % volatility changed (got %).', c_fn_sig, v_volat;
  END IF;

  -- 3-h. Parallel 불변
  SELECT p.proparallel INTO v_parallel FROM pg_proc p WHERE p.oid = v_oid;
  IF v_parallel IS DISTINCT FROM 'u' THEN
    RAISE EXCEPTION 'POST FAILED: % proparallel changed (got %).', c_fn_sig, v_parallel;
  END IF;

END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3B: POST 대상 테이블·검색 설정 불변 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_count int;
BEGIN
  -- safe_help_content 테이블 불변
  SELECT COUNT(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = 'safe_help_content' AND c.relkind = 'r';
  IF v_count IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'POST FAILED: public.safe_help_content table missing after migration.';
  END IF;

  -- 필수 컬럼 불변
  SELECT COUNT(*) INTO v_count
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name = 'safe_help_content'
    AND column_name IN ('id', 'search_tsv', 'updated_at');
  IF v_count IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'POST FAILED: safe_help_content required columns changed. found=%', v_count;
  END IF;

  -- text search config 'simple' 불변
  SELECT COUNT(*) INTO v_count
  FROM pg_ts_config
  WHERE cfgname = 'simple';
  IF v_count IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'POST FAILED: text search config ''simple'' missing after migration.';
  END IF;

END;
$$;

COMMIT;
