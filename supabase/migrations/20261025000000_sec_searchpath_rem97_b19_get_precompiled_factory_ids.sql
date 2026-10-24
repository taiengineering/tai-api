-- Migration: 20261025000000_sec_searchpath_rem97_b19_get_precompiled_factory_ids.sql
-- WO: WO-TAI-SEC-SEARCHPATH-REM97-B19-C3-SOURCE-001
-- SEC SEARCHPATH REM97 B19 — get_precompiled_factory_ids() search_path 고정
--
-- 배경:
--   B19 get_precompiled_factory_ids()는 engine_isolated.facility_applicability를
--   비한정 참조하며, 기본 search_path("$user", public, extensions)에 engine_isolated가
--   없어 현재 42P01 오류 재현 (GPT_B19_C1_SOURCE_IV = CONFIRMED).
--   C2 계약(GPT_B19_C2_CONTRACT_IV=CONDITIONAL_PASS): service_role 전용 복구.
--   함수 본문 변경 없이 search_path에 engine_isolated 추가.
--   anon/authenticated 권한 확대 없음 (SECURITY INVOKER 유지).
--
-- 변경 범위:
--   ALTER FUNCTION public.get_precompiled_factory_ids()
--     SET search_path = pg_catalog, engine_isolated, public, pg_temp  (B19)
--   함수 본문·ACL·SECURITY INVOKER·Volatility·Parallel 변경 없음.
--   트리거 없음. 스키마 권한 변경 없음.
--
-- 지원 호출자: service_role (engine_isolated USAGE + facility_applicability SELECT 보유)
-- anon/authenticated: 기존 권한 미변경 (engine_isolated 접근 불가 유지)
--
-- 승인:
--   B19_C3_OWNER_SCOPE_APPROVAL = 2026-10-25
--
-- 참조:
--   C1: WO-TAI-SEC-SEARCHPATH-REM97-C1 CLOSED_FINAL (97건 / B=24 / B19=1)
--   C2: WO-TAI-SEC-SEARCHPATH-REM97-B19-C2-CALLER-CONTRACT-001 CONDITIONAL_PASS
--   20261024103000_sec_searchpath_rem97_bw4_rpc_analysis_functions.sql

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1: PRE 함수 기준선 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_fn_sig    CONSTANT text := 'public.get_precompiled_factory_ids()';
  c_oid       CONSTANT oid  := 70200;
  c_body_md5  CONSTANT text := 'fa38689f8ad0f1fd6b904df01237bbde';

  v_oid        oid;
  v_secdef     bool;
  v_owner      text;
  v_body_md5   text;
  v_proconfig  text[];
  v_volat      char;
  v_parallel   char;
BEGIN
  -- 1-a. 함수 존재 확인
  IF to_regprocedure(c_fn_sig) IS NULL THEN
    RAISE EXCEPTION 'PRE FAILED: % not found.', c_fn_sig;
  END IF;

  v_oid := to_regprocedure(c_fn_sig)::oid;

  -- 1-b. OID 기준선 확인
  IF v_oid IS DISTINCT FROM c_oid THEN
    RAISE EXCEPTION 'PRE FAILED: % OID mismatch (expected %, got %).', c_fn_sig, c_oid, v_oid;
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
  IF v_body_md5 IS DISTINCT FROM c_body_md5 THEN
    RAISE EXCEPTION 'PRE FAILED: % prosrc_md5 mismatch (expected %, got %).', c_fn_sig, c_body_md5, v_body_md5;
  END IF;

  -- 1-f. proconfig = NULL (아직 미적용)
  SELECT p.proconfig INTO v_proconfig FROM pg_proc p WHERE p.oid = v_oid;
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'PRE FAILED: % proconfig already set: %.', c_fn_sig, v_proconfig;
  END IF;

  -- 1-g. Volatility 기준선 (s = STABLE)
  SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = v_oid;
  IF v_volat IS DISTINCT FROM 's' THEN
    RAISE EXCEPTION 'PRE FAILED: % volatility mismatch (expected s, got %).', c_fn_sig, v_volat;
  END IF;

  -- 1-h. Parallel 기준선 (u = UNSAFE)
  SELECT p.proparallel INTO v_parallel FROM pg_proc p WHERE p.oid = v_oid;
  IF v_parallel IS DISTINCT FROM 'u' THEN
    RAISE EXCEPTION 'PRE FAILED: % proparallel is %, expected u.', c_fn_sig, v_parallel;
  END IF;

  RAISE NOTICE 'PRE OK: % OID=% MD5=% INVOKER owner=postgres proconfig=NULL',
    c_fn_sig, c_oid, c_body_md5;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1B: PRE ACL 기준선 스냅샷
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _b19_fn_acl_baseline (
  fn_oid  oid  PRIMARY KEY,
  proacl  text
) ON COMMIT DROP;

INSERT INTO _b19_fn_acl_baseline (fn_oid, proacl)
SELECT p.oid, p.proacl::text
FROM pg_proc p
WHERE p.oid = 70200;

DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM _b19_fn_acl_baseline;
  IF v_count IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'PRE FAILED: ACL baseline captured % rows, expected 1.', v_count;
  END IF;
  RAISE NOTICE 'PRE ACL SNAPSHOT OK: 1 row captured for OID 70200';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2: search_path 고정 (METADATA_ONLY — 함수 본문·ACL·권한 변경 없음)
-- engine_isolated 추가로 facility_applicability 참조 가능.
-- service_role 전용 복구. anon/authenticated 접근 제한 유지.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.get_precompiled_factory_ids()
  SET search_path = pg_catalog, engine_isolated, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3: POST 함수 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_fn_sig      CONSTANT text := 'public.get_precompiled_factory_ids()';
  c_oid         CONSTANT oid  := 70200;
  c_body_md5    CONSTANT text := 'fa38689f8ad0f1fd6b904df01237bbde';
  c_search_path CONSTANT text := 'search_path=pg_catalog, engine_isolated, public, pg_temp';

  v_secdef     bool;
  v_owner      text;
  v_body_md5   text;
  v_proconfig  text[];
  v_volat      char;
  v_parallel   char;
BEGIN
  -- 3-a. OID 불변 확인
  IF to_regprocedure(c_fn_sig)::oid IS DISTINCT FROM c_oid THEN
    RAISE EXCEPTION 'POST FAILED: % OID changed unexpectedly.', c_fn_sig;
  END IF;

  -- 3-b. proconfig 정확 일치 (NULL-safe, 추가 설정 불허)
  SELECT p.proconfig INTO v_proconfig FROM pg_proc p WHERE p.oid = c_oid;
  IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
    RAISE EXCEPTION 'POST FAILED: % unexpected proconfig: %.', c_fn_sig, v_proconfig;
  END IF;

  -- 3-c. 함수 본문 MD5 불변
  SELECT md5(p.prosrc) INTO v_body_md5 FROM pg_proc p WHERE p.oid = c_oid;
  IF v_body_md5 IS DISTINCT FROM c_body_md5 THEN
    RAISE EXCEPTION 'POST FAILED: % prosrc_md5 changed.', c_fn_sig;
  END IF;

  -- 3-d. SECURITY INVOKER 불변
  SELECT p.prosecdef INTO v_secdef FROM pg_proc p WHERE p.oid = c_oid;
  IF v_secdef IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'POST FAILED: % prosecdef changed.', c_fn_sig;
  END IF;

  -- 3-e. 소유자 불변
  SELECT pg_get_userbyid(p.proowner) INTO v_owner FROM pg_proc p WHERE p.oid = c_oid;
  IF v_owner IS DISTINCT FROM 'postgres' THEN
    RAISE EXCEPTION 'POST FAILED: % owner changed.', c_fn_sig;
  END IF;

  -- 3-f. Volatility 불변
  SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = c_oid;
  IF v_volat IS DISTINCT FROM 's' THEN
    RAISE EXCEPTION 'POST FAILED: % volatility changed.', c_fn_sig;
  END IF;

  -- 3-g. Parallel 불변
  SELECT p.proparallel INTO v_parallel FROM pg_proc p WHERE p.oid = c_oid;
  IF v_parallel IS DISTINCT FROM 'u' THEN
    RAISE EXCEPTION 'POST FAILED: % proparallel changed.', c_fn_sig;
  END IF;

  RAISE NOTICE 'POST OK: % proconfig=[%] MD5=% OID=% INVOKER owner=postgres',
    c_fn_sig, c_search_path, c_body_md5, c_oid;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3B: POST ACL 불변 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  r        record;
  v_proacl text;
BEGIN
  FOR r IN SELECT fn_oid, proacl FROM _b19_fn_acl_baseline LOOP
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = r.fn_oid;
    IF v_proacl IS DISTINCT FROM r.proacl THEN
      RAISE EXCEPTION 'POST FAILED: ACL changed for OID % (before=%, after=%).',
        r.fn_oid, r.proacl, v_proacl;
    END IF;
  END LOOP;
  RAISE NOTICE 'POST ACL OK: ACL unchanged for OID 70200';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3C: 권한 불변 검증 (anon/authenticated에 신규 권한 없음)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_anon_ei_usage  bool;
  v_auth_ei_usage  bool;
  v_anon_fa_sel    bool;
  v_auth_fa_sel    bool;
BEGIN
  SELECT
    has_schema_privilege('anon',          'engine_isolated', 'USAGE'),
    has_schema_privilege('authenticated', 'engine_isolated', 'USAGE'),
    has_table_privilege('anon',          'engine_isolated.facility_applicability', 'SELECT'),
    has_table_privilege('authenticated', 'engine_isolated.facility_applicability', 'SELECT')
  INTO v_anon_ei_usage, v_auth_ei_usage, v_anon_fa_sel, v_auth_fa_sel;

  IF v_anon_ei_usage IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'POST FAILED: anon unexpectedly gained engine_isolated USAGE.';
  END IF;
  IF v_auth_ei_usage IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'POST FAILED: authenticated unexpectedly gained engine_isolated USAGE.';
  END IF;
  IF v_anon_fa_sel IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'POST FAILED: anon unexpectedly gained facility_applicability SELECT.';
  END IF;
  IF v_auth_fa_sel IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'POST FAILED: authenticated unexpectedly gained facility_applicability SELECT.';
  END IF;

  RAISE NOTICE 'POST PERMISSION OK: anon/authenticated engine_isolated 권한 미변경';
END;
$$;

COMMIT;
