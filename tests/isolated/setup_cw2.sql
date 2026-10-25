-- WO-TAI-SEC-SEARCHPATH-REM97-CW2-C3-SOURCE-001
-- C-W2 격리 환경 설정: work_schedules + work_assignments + generate_daily_assignments
-- Run BEFORE run_cw2_regression.sql

SET search_path = public;

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

-- ─── work_schedules ──────────────────────────────────────────────────────────
CREATE TABLE public.work_schedules (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  active_yn        BOOLEAN     NOT NULL DEFAULT FALSE,
  factory_id       UUID,
  asset_id         UUID,
  assigned_user_id UUID
);

-- ─── work_assignments ────────────────────────────────────────────────────────
CREATE TABLE public.work_assignments (
  id               UUID        PRIMARY KEY,
  schedule_id      UUID        NOT NULL,
  asset_id         UUID,
  assigned_user_id UUID,
  scheduled_date   DATE        NOT NULL,
  status_code      TEXT        NOT NULL,
  factory_id       UUID
);

-- ─── generate_daily_assignments (proconfig=NULL — 운영 기준선 재현) ─────────
-- prosrc는 운영 DB dump에서 직접 추출한 값과 동일하게 유지
CREATE OR REPLACE FUNCTION public.generate_daily_assignments()
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
begin

if exists (
    select 1 from work_schedules
    where active_yn = true and factory_id is null
) then
    raise exception 'generate_daily_assignments: active schedule factory_id NULL';
end if;

insert into work_assignments (
    id, schedule_id, asset_id, assigned_user_id,
    scheduled_date, status_code, factory_id
)
select
    gen_random_uuid(),
    ws.id, ws.asset_id, ws.assigned_user_id,
    current_date, 'READY', ws.factory_id
from work_schedules ws
where ws.active_yn = true;

end;
$$;

-- ─── 권한 부여 (service_role 전용 — sec02 계약 준수) ────────────────────────
-- anon, authenticated 는 EXECUTE 권한 없음
-- PostgreSQL 기본: 함수 생성 시 PUBLIC에 EXECUTE 부여 → PUBLIC revoke 후 service_role만 GRANT
GRANT SELECT, INSERT, UPDATE, DELETE ON public.work_schedules TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.work_assignments TO service_role;
REVOKE EXECUTE ON FUNCTION public.generate_daily_assignments() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.generate_daily_assignments() TO service_role;

-- ─── 설정 검증 ────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_fn_count  int;
  v_bad_count int;
BEGIN
  SELECT COUNT(*) INTO v_fn_count
  FROM pg_proc
  WHERE proname = 'generate_daily_assignments';
  IF v_fn_count IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'SETUP FAILED: expected 1 function, found %', v_fn_count;
  END IF;

  SELECT COUNT(*) INTO v_bad_count
  FROM pg_proc
  WHERE proname = 'generate_daily_assignments'
    AND proconfig IS NOT NULL;
  IF v_bad_count > 0 THEN
    RAISE EXCEPTION 'SETUP FAILED: generate_daily_assignments already has proconfig set';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'work_schedules' AND relkind = 'r') THEN
    RAISE EXCEPTION 'SETUP FAILED: work_schedules table missing';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'work_assignments' AND relkind = 'r') THEN
    RAISE EXCEPTION 'SETUP FAILED: work_assignments table missing';
  END IF;

  -- service_role EXECUTE 확인
  IF NOT has_function_privilege('service_role', 'public.generate_daily_assignments()', 'EXECUTE') THEN
    RAISE EXCEPTION 'SETUP FAILED: service_role does not have EXECUTE on generate_daily_assignments';
  END IF;

  RAISE NOTICE 'SETUP OK: 1 function (proconfig=NULL) + tables + roles + service_role EXECUTE granted';
END;
$$;
