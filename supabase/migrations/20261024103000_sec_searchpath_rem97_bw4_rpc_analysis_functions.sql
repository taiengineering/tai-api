-- Migration: 20261024103000_sec_searchpath_rem97_bw4_rpc_analysis_functions.sql
-- WO: WO-TAI-SEC-SEARCHPATH-REM97-BW4-SOURCE-001 / R1: WO-TAI-SEC-SEARCHPATH-REM97-BW4-SOURCE-R1-001
-- SEC SEARCHPATH REM97 B-W4A — RPC·분석 함수 7개 search_path 고정
--
-- 배경:
--   B-W1/B-W2A CLOSED_FINAL. B-W2B PROD=BLOCKED_ISOLATED_TEST.
--   B-W3A PROD=HOLD. B-W3B PROD=BLOCKED_ISOLATED_TEST.
--   B-W4A 대상 7개 함수: 모두 SECURITY INVOKER, proconfig=NULL.
--   전원 SELECT 전용 RPC 함수 — 외부 DML 없음, 격리 기능검증 불필요.
--   → function_search_path_mutable Advisor 75건 중 B-W4A 7건 해소 (75→68) 예정.
--   7개 함수 모두 비한정 참조 테이블이 public 스키마에 존재하여
--   search_path = pg_catalog, public, pg_temp 고정 후 동작 동등 확인
--   (METADATA_ONLY, 기존 동작 변경 없음).
--
-- 변경 범위:
--   ALTER FUNCTION public.get_diagrams_for_diagnosis(text, text[])
--     SET search_path = pg_catalog, public, pg_temp  (B17)
--   ALTER FUNCTION public.get_equip_count_by_process(text[])
--     SET search_path = pg_catalog, public, pg_temp  (B18)
--   ALTER FUNCTION public.search_help(text, text[], text, text, integer, text[], text, integer, integer)
--     SET search_path = pg_catalog, public, pg_temp  (B20)
--   ALTER FUNCTION public.search_help_count(text, text[], text, integer, text[], text)
--     SET search_path = pg_catalog, public, pg_temp  (B21)
--   ALTER FUNCTION public.search_safety_materials(text, text, text, integer, integer)
--     SET search_path = pg_catalog, public, pg_temp  (B22)
--   ALTER FUNCTION public.stats_customer_sites(date, date, text)
--     SET search_path = pg_catalog, public, pg_temp  (B23)
--   ALTER FUNCTION public.stats_diagnosis_funnel(date, date, text)
--     SET search_path = pg_catalog, public, pg_temp  (B24)
--   함수 본문·ACL·SECURITY INVOKER·Volatility·Parallel 변경 없음.
--   트리거 없음 (7개 함수 모두 RPC 전용).
--
-- B19 HOLD (GPT_BW4_SOURCE_IV 지적):
--   public.get_precompiled_factory_ids() (OID=70200)
--   본문이 참조하는 facility_applicability는 engine_isolated 스키마에만 존재.
--   public.facility_applicability 없음 — search_path=pg_catalog,public,pg_temp 고정 시
--   기존 오류 해소 불가. B19 전용 스키마 해석 및 Source·기능검증 Gate 별도 필요.
--   B19_STATUS = HOLD_SCHEMA_RESOLUTION
--
-- 참조:
--   20261024101500_sec_searchpath_rem97_bw3b_sync_triggers.sql
--   C2 설계: WO-TAI-SEC-SEARCHPATH-REM97-BW4-SOURCE-001
--   C1 기준: WO-TAI-SEC-SEARCHPATH-REM97-C1 CLOSED_FINAL (97건 / B=24 / B-W4=8)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1: PRE 함수 기준선 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_fn_sigs   text[]  := ARRAY[
    'public.get_diagrams_for_diagnosis(text, text[])',
    'public.get_equip_count_by_process(text[])',
    'public.search_help(text, text[], text, text, integer, text[], text, integer, integer)',
    'public.search_help_count(text, text[], text, integer, text[], text)',
    'public.search_safety_materials(text, text, text, integer, integer)',
    'public.stats_customer_sites(date, date, text)',
    'public.stats_diagnosis_funnel(date, date, text)'
  ];
  v_oids      oid[]   := ARRAY[18566, 18567, 243821, 243822, 223735, 242472, 242471];
  v_md5s      text[]  := ARRAY[
    '5e66840f274e21e02ee20c5ed4d9db0d',
    'a22fb0bc8c91cbd82eeb65a059a982d4',
    '736962e539ec4be659ef6712f57d05a0',
    'b5f39c3c761e54f88c4d451d8454c1ab',
    '349e30be44996f011cea340aecbeb093',
    '4ee2731ed5cf2b66d6757ed41bff6fc9',
    '49351eb5a856c2e0c19485dd03e9d629'
  ];
  v_volatiles char[]  := ARRAY['v', 's', 's', 's', 's', 's', 's'];

  i            int;
  v_fn_sig     text;
  v_oid        oid;
  v_secdef     bool;
  v_owner      text;
  v_body_md5   text;
  v_proconfig  text[];
  v_volat      char;
  v_parallel   char;

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

    -- 1-g. Volatility 기준선 (B17=VOLATILE, B18/B20-B24=STABLE)
    SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = v_oid;
    IF v_volat IS DISTINCT FROM v_volatiles[i] THEN
      RAISE EXCEPTION 'PRE FAILED: % volatility mismatch (expected %, got %).', v_fn_sig, v_volatiles[i], v_volat;
    END IF;

    -- 1-h. Parallel 기준선 (u = UNSAFE)
    SELECT p.proparallel INTO v_parallel FROM pg_proc p WHERE p.oid = v_oid;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'PRE FAILED: % proparallel is %, expected u.', v_fn_sig, v_parallel;
    END IF;

  END LOOP;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1B: PRE ACL 기준선 스냅샷 (동적 캡처)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _bw4_fn_acl_baseline (
  fn_oid  oid  PRIMARY KEY,
  proacl  text
) ON COMMIT DROP;

INSERT INTO _bw4_fn_acl_baseline (fn_oid, proacl)
SELECT p.oid, p.proacl::text
FROM pg_proc p
WHERE p.oid IN (18566, 18567, 243821, 243822, 223735, 242472, 242471);

DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM _bw4_fn_acl_baseline;
  IF v_count IS DISTINCT FROM 7 THEN
    RAISE EXCEPTION 'PRE FAILED: ACL baseline captured % rows, expected 7.', v_count;
  END IF;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2: search_path 고정 (METADATA_ONLY — 함수 본문·ACL 변경 없음)
-- B19 get_precompiled_factory_ids() 제외 (HOLD_SCHEMA_RESOLUTION)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.get_diagrams_for_diagnosis(text, text[])
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.get_equip_count_by_process(text[])
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.search_help(text, text[], text, text, integer, text[], text, integer, integer)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.search_help_count(text, text[], text, integer, text[], text)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.search_safety_materials(text, text, text, integer, integer)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.stats_customer_sites(date, date, text)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.stats_diagnosis_funnel(date, date, text)
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3: POST 함수 검증
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_search_path  CONSTANT text := 'search_path=pg_catalog, public, pg_temp';

  v_fn_sigs   text[]  := ARRAY[
    'public.get_diagrams_for_diagnosis(text, text[])',
    'public.get_equip_count_by_process(text[])',
    'public.search_help(text, text[], text, text, integer, text[], text, integer, integer)',
    'public.search_help_count(text, text[], text, integer, text[], text)',
    'public.search_safety_materials(text, text, text, integer, integer)',
    'public.stats_customer_sites(date, date, text)',
    'public.stats_diagnosis_funnel(date, date, text)'
  ];
  v_oids      oid[]   := ARRAY[18566, 18567, 243821, 243822, 223735, 242472, 242471];
  v_md5s      text[]  := ARRAY[
    '5e66840f274e21e02ee20c5ed4d9db0d',
    'a22fb0bc8c91cbd82eeb65a059a982d4',
    '736962e539ec4be659ef6712f57d05a0',
    'b5f39c3c761e54f88c4d451d8454c1ab',
    '349e30be44996f011cea340aecbeb093',
    '4ee2731ed5cf2b66d6757ed41bff6fc9',
    '49351eb5a856c2e0c19485dd03e9d629'
  ];
  v_volatiles char[]  := ARRAY['v', 's', 's', 's', 's', 's', 's'];

  i            int;
  v_fn_sig     text;
  v_oid        oid;
  v_secdef     bool;
  v_owner      text;
  v_body_md5   text;
  v_proconfig  text[];
  v_volat      char;
  v_parallel   char;

BEGIN
  FOR i IN 1..array_length(v_fn_sigs, 1) LOOP
    v_fn_sig := v_fn_sigs[i];
    v_oid    := v_oids[i];

    -- 3-a. OID 불변 확인
    IF to_regprocedure(v_fn_sig)::oid IS DISTINCT FROM v_oid THEN
      RAISE EXCEPTION 'POST FAILED: % OID changed unexpectedly.', v_fn_sig;
    END IF;

    -- 3-b. proconfig 정확 일치 (NULL-safe, 추가 설정 불허)
    SELECT p.proconfig INTO v_proconfig FROM pg_proc p WHERE p.oid = v_oid;
    IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
      RAISE EXCEPTION 'POST FAILED: % unexpected proconfig: %.', v_fn_sig, v_proconfig;
    END IF;

    -- 3-c. 함수 본문 MD5 불변
    SELECT md5(p.prosrc) INTO v_body_md5 FROM pg_proc p WHERE p.oid = v_oid;
    IF v_body_md5 IS DISTINCT FROM v_md5s[i] THEN
      RAISE EXCEPTION 'POST FAILED: % prosrc_md5 changed.', v_fn_sig;
    END IF;

    -- 3-d. SECURITY INVOKER 불변
    SELECT p.prosecdef INTO v_secdef FROM pg_proc p WHERE p.oid = v_oid;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'POST FAILED: % prosecdef changed.', v_fn_sig;
    END IF;

    -- 3-e. 소유자 불변
    SELECT pg_get_userbyid(p.proowner) INTO v_owner FROM pg_proc p WHERE p.oid = v_oid;
    IF v_owner IS DISTINCT FROM 'postgres' THEN
      RAISE EXCEPTION 'POST FAILED: % owner changed.', v_fn_sig;
    END IF;

    -- 3-f. Volatility 불변
    SELECT p.provolatile INTO v_volat FROM pg_proc p WHERE p.oid = v_oid;
    IF v_volat IS DISTINCT FROM v_volatiles[i] THEN
      RAISE EXCEPTION 'POST FAILED: % volatility changed.', v_fn_sig;
    END IF;

    -- 3-g. Parallel 불변
    SELECT p.proparallel INTO v_parallel FROM pg_proc p WHERE p.oid = v_oid;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'POST FAILED: % proparallel changed.', v_fn_sig;
    END IF;

  END LOOP;
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
  FOR r IN SELECT fn_oid, proacl FROM _bw4_fn_acl_baseline LOOP
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = r.fn_oid;
    IF v_proacl IS DISTINCT FROM r.proacl THEN
      RAISE EXCEPTION 'POST FAILED: ACL changed for OID % (before=%, after=%).',
        r.fn_oid, r.proacl, v_proacl;
    END IF;
  END LOOP;
END;
$$;

COMMIT;
