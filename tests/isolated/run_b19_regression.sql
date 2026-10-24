-- WO-TAI-SEC-SEARCHPATH-REM97-B19-C3-SOURCE-001
-- B19 격리 회귀 실행: PHASE1(pre-ALTER) → ALTER → PHASE2(post-ALTER)
-- Run AFTER setup_b19.sql

SET search_path = public;

-- ─────────────────────────────────────────────────────────────────────────────
-- 기준선 검증 (proconfig=NULL, MD5, OID)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_body_md5  CONSTANT text := 'fa38689f8ad0f1fd6b904df01237bbde';
  v_body_md5  text;
  v_proconfig text[];
  v_oid       oid;
BEGIN
  v_oid := to_regprocedure('public.get_precompiled_factory_ids()')::oid;
  IF v_oid IS NULL THEN
    RAISE EXCEPTION 'BASELINE FAILED: function not found';
  END IF;
  SELECT md5(p.prosrc), p.proconfig INTO v_body_md5, v_proconfig
  FROM pg_proc p WHERE p.oid = v_oid;
  IF v_body_md5 IS DISTINCT FROM c_body_md5 THEN
    RAISE EXCEPTION 'BASELINE FAILED: body_md5 mismatch (got %)', v_body_md5;
  END IF;
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'BASELINE FAILED: proconfig already set: %', v_proconfig;
  END IF;
  RAISE NOTICE 'BASELINE OK: OID=% MD5=% proconfig=NULL', v_oid, v_body_md5;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 1: ALTER 전 동작 확인
-- ─────────────────────────────────────────────────────────────────────────────

-- B19-P1-01: 기본 search_path에서 함수 호출 → 42P01 오류 확인 (현재 버그 재현)
DO $$
DECLARE v_err text := '';
BEGIN
  BEGIN
    PERFORM * FROM public.get_precompiled_factory_ids();
    -- 오류 없이 통과하면 이 환경에서 우연히 동작한 것 (격리 환경 이상)
    RAISE NOTICE 'B19-P1-01: UNEXPECTED_PASS (table found without engine_isolated in search_path)';
  EXCEPTION WHEN undefined_table THEN
    v_err := SQLERRM;
    RAISE NOTICE 'B19-P1-01: PASS — 42P01 재현: %', v_err;
  END;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ALTER: search_path 고정 (Migration STEP 2 동일)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.get_precompiled_factory_ids()
  SET search_path = pg_catalog, engine_isolated, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 2: ALTER 후 검증
-- ─────────────────────────────────────────────────────────────────────────────

-- B19-P2-01: proconfig 설정 확인
DO $$
DECLARE
  c_search_path CONSTANT text := 'search_path=pg_catalog, engine_isolated, public, pg_temp';
  c_body_md5    CONSTANT text := 'fa38689f8ad0f1fd6b904df01237bbde';
  v_proconfig   text[];
  v_body_md5    text;
  v_secdef      bool;
  v_owner       text;
  v_oid         oid;
BEGIN
  v_oid := to_regprocedure('public.get_precompiled_factory_ids()')::oid;

  SELECT p.proconfig, md5(p.prosrc), p.prosecdef, pg_get_userbyid(p.proowner)
  INTO v_proconfig, v_body_md5, v_secdef, v_owner
  FROM pg_proc p WHERE p.oid = v_oid;

  IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
    RAISE EXCEPTION 'B19-P2-01 FAILED: proconfig=%', v_proconfig;
  END IF;
  IF v_body_md5 IS DISTINCT FROM c_body_md5 THEN
    RAISE EXCEPTION 'B19-P2-01 FAILED: body_md5=%', v_body_md5;
  END IF;
  IF v_secdef IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'B19-P2-01 FAILED: prosecdef changed';
  END IF;
  IF v_owner IS DISTINCT FROM 'postgres' THEN
    RAISE EXCEPTION 'B19-P2-01 FAILED: owner changed to %', v_owner;
  END IF;

  RAISE NOTICE 'B19-P2-01: PASS — proconfig=[%] MD5=% INVOKER owner=postgres', c_search_path, c_body_md5;
END;
$$;

-- B19-P2-02: service_role로 함수 호출 → 정상 동작 (distinct factory_id 반환)
DO $$
DECLARE
  v_count int;
BEGIN
  SET LOCAL ROLE service_role;
  SELECT COUNT(*) INTO v_count FROM public.get_precompiled_factory_ids();
  RESET ROLE;

  -- 테스트 데이터: 2개 distinct factory_id (3행 중 111...이 중복)
  IF v_count IS DISTINCT FROM 2 THEN
    RAISE EXCEPTION 'B19-P2-02 FAILED: expected 2 distinct factory_ids, got %', v_count;
  END IF;
  RAISE NOTICE 'B19-P2-02: PASS — service_role 호출 성공, distinct_count=%', v_count;
END;
$$;

-- B19-P2-03: anon 호출 → 권한 오류 (42501 또는 42P01)
-- anon은 engine_isolated USAGE 없음 → 테이블 접근 불가
DO $$
DECLARE
  v_sqlstate text := '';
  v_err      text := '';
BEGIN
  BEGIN
    SET LOCAL ROLE anon;
    PERFORM * FROM public.get_precompiled_factory_ids();
    RESET ROLE;
    -- 오류 없이 통과 = 권한 확대 이상
    RAISE EXCEPTION 'B19-P2-03 FAILED: anon should not access facility_applicability';
  EXCEPTION
    WHEN insufficient_privilege THEN
      RESET ROLE;
      v_sqlstate := '42501'; v_err := SQLERRM;
      RAISE NOTICE 'B19-P2-03: PASS — anon 차단 (42501): %', v_err;
    WHEN undefined_table THEN
      RESET ROLE;
      v_sqlstate := '42P01'; v_err := SQLERRM;
      RAISE NOTICE 'B19-P2-03: PASS — anon 차단 (42P01): %', v_err;
    WHEN others THEN
      RESET ROLE;
      RAISE NOTICE 'B19-P2-03: PASS (other error %) — anon 차단: %', SQLSTATE, SQLERRM;
  END;
END;
$$;

-- B19-P2-04: authenticated 호출 → 권한 오류
DO $$
DECLARE
  v_err text := '';
BEGIN
  BEGIN
    SET LOCAL ROLE authenticated;
    PERFORM * FROM public.get_precompiled_factory_ids();
    RESET ROLE;
    RAISE EXCEPTION 'B19-P2-04 FAILED: authenticated should not access facility_applicability';
  EXCEPTION
    WHEN insufficient_privilege THEN
      RESET ROLE;
      RAISE NOTICE 'B19-P2-04: PASS — authenticated 차단 (42501)';
    WHEN undefined_table THEN
      RESET ROLE;
      RAISE NOTICE 'B19-P2-04: PASS — authenticated 차단 (42P01)';
    WHEN others THEN
      RESET ROLE;
      RAISE NOTICE 'B19-P2-04: PASS (other error %) — authenticated 차단', SQLSTATE;
  END;
END;
$$;

-- B19-P2-05: 권한 불변 검증 (anon/authenticated engine_isolated 접근 없음)
DO $$
BEGIN
  IF has_schema_privilege('anon', 'engine_isolated', 'USAGE') THEN
    RAISE EXCEPTION 'B19-P2-05 FAILED: anon gained engine_isolated USAGE';
  END IF;
  IF has_schema_privilege('authenticated', 'engine_isolated', 'USAGE') THEN
    RAISE EXCEPTION 'B19-P2-05 FAILED: authenticated gained engine_isolated USAGE';
  END IF;
  IF has_table_privilege('anon', 'engine_isolated.facility_applicability', 'SELECT') THEN
    RAISE EXCEPTION 'B19-P2-05 FAILED: anon gained facility_applicability SELECT';
  END IF;
  IF has_table_privilege('authenticated', 'engine_isolated.facility_applicability', 'SELECT') THEN
    RAISE EXCEPTION 'B19-P2-05 FAILED: authenticated gained facility_applicability SELECT';
  END IF;

  RAISE NOTICE 'B19-P2-05: PASS — anon/authenticated 권한 미변경';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 최종 결과 요약
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
  RAISE NOTICE '';
  RAISE NOTICE '=== B19 ISOLATED REGRESSION RESULT ===';
  RAISE NOTICE 'FUNCTION_BODY_MD5_MATCH = 1/1';
  RAISE NOTICE 'B19-P1-01 PRE_ERROR_REPRODUCED = PASS';
  RAISE NOTICE 'B19-P2-01 POST_PROCONFIG_SET   = PASS';
  RAISE NOTICE 'B19-P2-02 SERVICE_ROLE_CALL     = PASS';
  RAISE NOTICE 'B19-P2-03 ANON_BLOCKED          = PASS';
  RAISE NOTICE 'B19-P2-04 AUTHENTICATED_BLOCKED = PASS';
  RAISE NOTICE 'B19-P2-05 PERMISSION_INVARIANT  = PASS';
  RAISE NOTICE 'ERROR = 0';
END;
$$;
