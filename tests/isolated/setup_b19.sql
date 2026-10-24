-- WO-TAI-SEC-SEARCHPATH-REM97-B19-C3-SOURCE-001
-- B19 격리 환경 설정: engine_isolated 스키마 + facility_applicability + 역할 + 함수
-- Run BEFORE run_b19_regression.sql

SET search_path = public;

-- ─── SCHEMA ──────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS engine_isolated;

-- ─── ROLES ───────────────────────────────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role BYPASSRLS NOLOGIN;
  END IF;
END;
$$;

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

-- ─── engine_isolated 권한 ─────────────────────────────────────────────────────
-- service_role: USAGE + SELECT
-- anon/authenticated: 아무 권한 없음 (운영 동일)
GRANT USAGE ON SCHEMA engine_isolated TO service_role;

-- ─── facility_applicability 테이블 ────────────────────────────────────────────
CREATE TABLE engine_isolated.facility_applicability (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  factory_id           uuid NOT NULL,
  draft_id             uuid,
  part_id              uuid,
  applicability_status text,
  match_details        jsonb,
  created_at           timestamptz DEFAULT now()
);

GRANT SELECT ON engine_isolated.facility_applicability TO service_role;
-- anon/authenticated: 권한 없음 (의도적)

-- ─── 테스트 데이터 ────────────────────────────────────────────────────────────
INSERT INTO engine_isolated.facility_applicability (factory_id, applicability_status)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'APPLICABLE'),
  ('22222222-2222-2222-2222-222222222222', 'NOT_APPLICABLE'),
  ('11111111-1111-1111-1111-111111111111', 'APPLICABLE');

-- ─── B19 함수 생성 (proconfig=NULL, 운영 상태 재현) ───────────────────────────
-- 운영 MD5: fa38689f8ad0f1fd6b904df01237bbde
-- SQL 함수 생성 시 비한정 참조 검증을 통과하도록 세션 search_path에 engine_isolated 추가.
-- 함수 자체의 proconfig는 NULL로 유지 (운영 기준선과 동일).
SET search_path = engine_isolated, public;

CREATE OR REPLACE FUNCTION public.get_precompiled_factory_ids()
RETURNS TABLE (factory_id uuid)
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
  SELECT DISTINCT fa.factory_id FROM facility_applicability fa;
$$;

RESET search_path;

GRANT EXECUTE ON FUNCTION public.get_precompiled_factory_ids() TO anon, authenticated, service_role;

-- ─── 설정 검증 ────────────────────────────────────────────────────────────────
DO $$
DECLARE v_count int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'engine_isolated') THEN
    RAISE EXCEPTION 'SETUP FAILED: engine_isolated schema not found';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid
                  WHERE n.nspname = 'engine_isolated' AND c.relname = 'facility_applicability') THEN
    RAISE EXCEPTION 'SETUP FAILED: engine_isolated.facility_applicability not found';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role' AND rolbypassrls = true) THEN
    RAISE EXCEPTION 'SETUP FAILED: service_role without BYPASSRLS not found';
  END IF;
  SELECT COUNT(*) INTO v_count FROM engine_isolated.facility_applicability;
  IF v_count IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'SETUP FAILED: expected 3 test rows, got %', v_count;
  END IF;

  -- service_role 권한 확인
  IF NOT has_schema_privilege('service_role', 'engine_isolated', 'USAGE') THEN
    RAISE EXCEPTION 'SETUP FAILED: service_role lacks engine_isolated USAGE';
  END IF;
  IF NOT has_table_privilege('service_role', 'engine_isolated.facility_applicability', 'SELECT') THEN
    RAISE EXCEPTION 'SETUP FAILED: service_role lacks facility_applicability SELECT';
  END IF;

  -- anon/authenticated 권한 없음 확인
  IF has_schema_privilege('anon', 'engine_isolated', 'USAGE') THEN
    RAISE EXCEPTION 'SETUP FAILED: anon should not have engine_isolated USAGE';
  END IF;
  IF has_schema_privilege('authenticated', 'engine_isolated', 'USAGE') THEN
    RAISE EXCEPTION 'SETUP FAILED: authenticated should not have engine_isolated USAGE';
  END IF;

  RAISE NOTICE 'SETUP OK: engine_isolated schema + table + roles + data (3 rows)';
  RAISE NOTICE 'SETUP OK: service_role = USAGE + SELECT / anon/authenticated = no access';
END;
$$;
