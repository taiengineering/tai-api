-- WO-TAI-SEC-SEARCHPATH-REM97-CW2-C3-SOURCE-001
-- C-W2 격리 회귀 테스트: generate_daily_assignments search_path 고정 검증
-- Run AFTER setup_cw2.sql

SET search_path = public;
TRUNCATE work_schedules, work_assignments;

-- ─────────────────────────────────────────────────────────────────────────────
-- BASELINE: PRE 상태 캡처 (proconfig=NULL, MD5 동적 저장)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_md5       text;
  v_secdef    bool;
  v_owner     text;
  v_proconfig text[];
  v_volat     char;
  v_parallel  char;
BEGIN
  SELECT md5(p.prosrc), p.prosecdef, pg_get_userbyid(p.proowner),
         p.proconfig, p.provolatile, p.proparallel
  INTO v_md5, v_secdef, v_owner, v_proconfig, v_volat, v_parallel
  FROM pg_proc p
  WHERE p.proname = 'generate_daily_assignments';

  IF v_md5 IS NULL THEN
    RAISE EXCEPTION 'BASELINE FAILED: generate_daily_assignments not found';
  END IF;
  IF v_proconfig IS NOT NULL THEN
    RAISE EXCEPTION 'BASELINE FAILED: proconfig already set: %', v_proconfig;
  END IF;
  IF v_secdef IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'BASELINE FAILED: not SECURITY INVOKER';
  END IF;
  IF v_volat IS DISTINCT FROM 'v' THEN
    RAISE EXCEPTION 'BASELINE FAILED: volatility is %, expected v', v_volat;
  END IF;
  IF v_parallel IS DISTINCT FROM 'u' THEN
    RAISE EXCEPTION 'BASELINE FAILED: proparallel is %, expected u', v_parallel;
  END IF;

  -- MD5를 세션 설정으로 저장하여 PHASE 2에서 불변 검증에 사용
  PERFORM set_config('app.cw2_baseline_md5', v_md5, false);

  RAISE NOTICE 'BASELINE OK: proconfig=NULL MD5=% INVOKER owner=% volat=% parallel=%',
    v_md5, v_owner, v_volat, v_parallel;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ACL 스냅샷 (PHASE 2 불변 검증용)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TEMP TABLE _cw2_reg_acl (
  fn_oid  oid  PRIMARY KEY,
  proacl  text
);

INSERT INTO _cw2_reg_acl (fn_oid, proacl)
SELECT p.oid, p.proacl::text
FROM pg_proc p
WHERE p.proname = 'generate_daily_assignments';

DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM _cw2_reg_acl;
  IF v_count IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'BASELINE FAILED: ACL snapshot captured % rows, expected 1', v_count;
  END IF;
  RAISE NOTICE 'BASELINE ACL SNAPSHOT OK';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 1 — ALTER 이전 동작 검증
-- ─────────────────────────────────────────────────────────────────────────────

-- CW2-P1-01: 정상 배정 INSERT
-- active_yn=true + factory_id IS NOT NULL → RAISE 없음, work_assignments 삽입
DO $$
DECLARE
  v_ws_id     uuid := gen_random_uuid();
  v_asset_id  uuid := gen_random_uuid();
  v_user_id   uuid := gen_random_uuid();
  v_factory   uuid := gen_random_uuid();
  v_count     int;
BEGIN
  INSERT INTO work_schedules (id, active_yn, factory_id, asset_id, assigned_user_id)
  VALUES (v_ws_id, true, v_factory, v_asset_id, v_user_id);

  PERFORM public.generate_daily_assignments();

  SELECT COUNT(*) INTO v_count
  FROM work_assignments
  WHERE schedule_id = v_ws_id
    AND asset_id    = v_asset_id
    AND factory_id  = v_factory
    AND status_code = 'READY'
    AND scheduled_date = current_date;

  IF v_count IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'CW2-P1-01 FAIL: expected 1 assignment, got %', v_count;
  END IF;
  RAISE NOTICE 'CW2-P1-01 PASS: normal assignment inserted (1 row)';
END;
$$;

TRUNCATE work_schedules, work_assignments;

-- CW2-P1-02: inactive 스케줄 → INSERT 없음 (예외 없음)
DO $$
DECLARE
  v_count int;
BEGIN
  INSERT INTO work_schedules (id, active_yn, factory_id, asset_id, assigned_user_id)
  VALUES (gen_random_uuid(), false, gen_random_uuid(), gen_random_uuid(), gen_random_uuid());

  PERFORM public.generate_daily_assignments();

  SELECT COUNT(*) INTO v_count FROM work_assignments;
  IF v_count IS DISTINCT FROM 0 THEN
    RAISE EXCEPTION 'CW2-P1-02 FAIL: expected 0 assignments, got %', v_count;
  END IF;
  RAISE NOTICE 'CW2-P1-02 PASS: inactive schedule → 0 assignments, no exception';
END;
$$;

TRUNCATE work_schedules, work_assignments;

-- CW2-P1-03: Fail-Closed — active_yn=true + factory_id IS NULL → RAISE EXCEPTION
DO $$
DECLARE
  v_raised bool := false;
BEGIN
  INSERT INTO work_schedules (id, active_yn, factory_id, asset_id, assigned_user_id)
  VALUES (gen_random_uuid(), true, NULL, gen_random_uuid(), gen_random_uuid());

  BEGIN
    PERFORM public.generate_daily_assignments();
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM LIKE '%generate_daily_assignments: active schedule factory_id NULL%' THEN
        v_raised := true;
      ELSE
        RAISE EXCEPTION 'CW2-P1-03 FAIL: unexpected exception: %', SQLERRM;
      END IF;
  END;

  IF NOT v_raised THEN
    RAISE EXCEPTION 'CW2-P1-03 FAIL: expected RAISE EXCEPTION but none was raised';
  END IF;
  RAISE NOTICE 'CW2-P1-03 PASS: Fail-Closed triggered (factory_id NULL → exception)';
END;
$$;

TRUNCATE work_schedules, work_assignments;

-- CW2-P1-04: 복수 active 스케줄 → 복수 INSERT
DO $$
DECLARE
  v_factory uuid := gen_random_uuid();
  v_count   int;
BEGIN
  INSERT INTO work_schedules (id, active_yn, factory_id, asset_id, assigned_user_id)
  VALUES
    (gen_random_uuid(), true, v_factory, gen_random_uuid(), gen_random_uuid()),
    (gen_random_uuid(), true, v_factory, gen_random_uuid(), gen_random_uuid()),
    (gen_random_uuid(), true, v_factory, gen_random_uuid(), gen_random_uuid());

  PERFORM public.generate_daily_assignments();

  SELECT COUNT(*) INTO v_count FROM work_assignments WHERE status_code = 'READY';
  IF v_count IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'CW2-P1-04 FAIL: expected 3 assignments, got %', v_count;
  END IF;
  RAISE NOTICE 'CW2-P1-04 PASS: 3 active schedules → 3 assignments';
END;
$$;

TRUNCATE work_schedules, work_assignments;

-- CW2-P1-05: EXECUTE 권한 확인 — service_role=true, anon/authenticated=false
DO $$
DECLARE
  v_sr    bool;
  v_anon  bool;
  v_auth  bool;
BEGIN
  v_sr   := has_function_privilege('service_role',  'public.generate_daily_assignments()', 'EXECUTE');
  v_anon := has_function_privilege('anon',          'public.generate_daily_assignments()', 'EXECUTE');
  v_auth := has_function_privilege('authenticated', 'public.generate_daily_assignments()', 'EXECUTE');

  IF NOT v_sr THEN
    RAISE EXCEPTION 'CW2-P1-05 FAIL: service_role does not have EXECUTE';
  END IF;
  IF v_anon THEN
    RAISE EXCEPTION 'CW2-P1-05 FAIL: anon should NOT have EXECUTE (sec02 contract)';
  END IF;
  IF v_auth THEN
    RAISE EXCEPTION 'CW2-P1-05 FAIL: authenticated should NOT have EXECUTE (sec02 contract)';
  END IF;
  RAISE NOTICE 'CW2-P1-05 PASS: service_role=EXECUTE, anon/authenticated=blocked';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ALTER: search_path 고정 (마이그레이션과 동일)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.generate_daily_assignments()
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 2 — ALTER 이후 메타데이터 및 동작 검증
-- ─────────────────────────────────────────────────────────────────────────────

-- CW2-P2-01: proconfig 고정 + 기타 메타데이터 불변
DO $$
DECLARE
  c_search_path CONSTANT text := 'search_path=pg_catalog, public, pg_temp';
  v_baseline_md5  text;
  v_md5           text;
  v_secdef        bool;
  v_owner         text;
  v_proconfig     text[];
  v_volat         char;
  v_parallel      char;
BEGIN
  v_baseline_md5 := current_setting('app.cw2_baseline_md5');

  SELECT md5(p.prosrc), p.prosecdef, pg_get_userbyid(p.proowner),
         p.proconfig, p.provolatile, p.proparallel
  INTO v_md5, v_secdef, v_owner, v_proconfig, v_volat, v_parallel
  FROM pg_proc p
  WHERE p.proname = 'generate_daily_assignments';

  IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
    RAISE EXCEPTION 'CW2-P2-01 FAIL: proconfig mismatch: %', v_proconfig;
  END IF;
  IF v_md5 IS DISTINCT FROM v_baseline_md5 THEN
    RAISE EXCEPTION 'CW2-P2-01 FAIL: prosrc_md5 changed (before=%, after=%)', v_baseline_md5, v_md5;
  END IF;
  IF v_secdef IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'CW2-P2-01 FAIL: prosecdef changed';
  END IF;
  IF v_volat IS DISTINCT FROM 'v' THEN
    RAISE EXCEPTION 'CW2-P2-01 FAIL: volatility changed';
  END IF;
  IF v_parallel IS DISTINCT FROM 'u' THEN
    RAISE EXCEPTION 'CW2-P2-01 FAIL: proparallel changed';
  END IF;

  RAISE NOTICE 'CW2-P2-01 PASS: proconfig=[%] MD5=% (unchanged) INVOKER volat=v parallel=u',
    c_search_path, v_md5;
END;
$$;

-- CW2-P2-02: ACL 불변 검증
DO $$
DECLARE
  r        record;
  v_proacl text;
BEGIN
  FOR r IN SELECT fn_oid, proacl FROM _cw2_reg_acl LOOP
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = r.fn_oid;
    IF v_proacl IS DISTINCT FROM r.proacl THEN
      RAISE EXCEPTION 'CW2-P2-02 FAIL: ACL changed (before=%, after=%)', r.proacl, v_proacl;
    END IF;
  END LOOP;
  RAISE NOTICE 'CW2-P2-02 PASS: ACL unchanged';
END;
$$;

-- CW2-P2-03: ALTER 후 동작 불변 — 정상 배정 INSERT
DO $$
DECLARE
  v_ws_id    uuid := gen_random_uuid();
  v_factory  uuid := gen_random_uuid();
  v_count    int;
BEGIN
  INSERT INTO work_schedules (id, active_yn, factory_id, asset_id, assigned_user_id)
  VALUES (v_ws_id, true, v_factory, gen_random_uuid(), gen_random_uuid());

  PERFORM public.generate_daily_assignments();

  SELECT COUNT(*) INTO v_count
  FROM work_assignments
  WHERE schedule_id = v_ws_id AND factory_id = v_factory AND status_code = 'READY';

  IF v_count IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'CW2-P2-03 FAIL: expected 1 assignment, got %', v_count;
  END IF;
  RAISE NOTICE 'CW2-P2-03 PASS: normal assignment after ALTER (behavioral invariance)';
END;
$$;

TRUNCATE work_schedules, work_assignments;

-- CW2-P2-04: ALTER 후 Fail-Closed 불변 — factory_id IS NULL → 예외
DO $$
DECLARE
  v_raised bool := false;
BEGIN
  INSERT INTO work_schedules (id, active_yn, factory_id, asset_id, assigned_user_id)
  VALUES (gen_random_uuid(), true, NULL, gen_random_uuid(), gen_random_uuid());

  BEGIN
    PERFORM public.generate_daily_assignments();
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM LIKE '%generate_daily_assignments: active schedule factory_id NULL%' THEN
        v_raised := true;
      ELSE
        RAISE EXCEPTION 'CW2-P2-04 FAIL: unexpected exception: %', SQLERRM;
      END IF;
  END;

  IF NOT v_raised THEN
    RAISE EXCEPTION 'CW2-P2-04 FAIL: Fail-Closed not triggered after ALTER';
  END IF;
  RAISE NOTICE 'CW2-P2-04 PASS: Fail-Closed unchanged after ALTER';
END;
$$;

TRUNCATE work_schedules, work_assignments;

-- CW2-P2-05: ALTER 후 EXECUTE 권한 불변
DO $$
DECLARE
  v_sr    bool;
  v_anon  bool;
  v_auth  bool;
BEGIN
  v_sr   := has_function_privilege('service_role',  'public.generate_daily_assignments()', 'EXECUTE');
  v_anon := has_function_privilege('anon',          'public.generate_daily_assignments()', 'EXECUTE');
  v_auth := has_function_privilege('authenticated', 'public.generate_daily_assignments()', 'EXECUTE');

  IF NOT v_sr THEN
    RAISE EXCEPTION 'CW2-P2-05 FAIL: service_role lost EXECUTE after ALTER';
  END IF;
  IF v_anon THEN
    RAISE EXCEPTION 'CW2-P2-05 FAIL: anon gained EXECUTE after ALTER';
  END IF;
  IF v_auth THEN
    RAISE EXCEPTION 'CW2-P2-05 FAIL: authenticated gained EXECUTE after ALTER';
  END IF;
  RAISE NOTICE 'CW2-P2-05 PASS: EXECUTE ACL unchanged after ALTER';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 최종 요약
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
  RAISE NOTICE '=== C-W2 REGRESSION COMPLETE: 10/10 PASS ===';
  RAISE NOTICE 'P1: 01-normal INSERT, 02-inactive skip, 03-fail-closed, 04-multi INSERT, 05-ACL pre';
  RAISE NOTICE 'P2: 01-proconfig+MD5+meta, 02-ACL invariant, 03-normal INSERT, 04-fail-closed, 05-ACL post';
END;
$$;
