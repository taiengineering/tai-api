-- Migration: 20261022083010_sec_residual_hnu001_drop_handle_new_user.sql
-- WO: WO-TAI-SEC-RESIDUAL-HNU-001
-- SEC 잔여 — public.handle_new_user() 미사용 레거시 함수 제거
--
-- 배경:
--   handle_new_user(): SECURITY DEFINER, 연결된 트리거 없음 (pg_trigger = 0건).
--   현재 회원가입 경로는 routers/auth.py가 public.users에 직접 INSERT.
--   auth.users 트리거 미연결, Auth Hook 미설정, 코드 직접 호출 없음.
--   SEC-04에서 anon/authenticated EXECUTE 이미 차단됨.
--   소비자 없는 미사용 SECURITY DEFINER 함수 — function_search_path_mutable 경고 포함.
--
-- 변경 범위:
--   DROP FUNCTION public.handle_new_user() 1건.
--   트리거·RLS·다른 함수·public.users 구조·auth.users 구조 변경 없음.
--
-- 참조 패턴:
--   20261022020000_sec02_ex001_inspection_work_schedules_lockdown.sql
--   20261022071824_sec02_adj_p0_work_assignments_generate_daily_lockdown.sql

BEGIN;

DO $$
DECLARE
  v_count        int;
  v_owner        text;
  v_secdef       bool;
  v_def_md5      text;
  v_body_md5     text;
  v_trig_count   int;
  v_dep_count    int;

BEGIN

  -- ── STEP 1: 사전조건 검증 ──────────────────────────────────────────

  -- 1-a. 함수 존재 (인수 0개, RETURNS trigger)
  SELECT count(*) INTO v_count
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'handle_new_user' AND p.pronargs = 0
    AND p.prorettype = 'trigger'::regtype::oid;
  IF v_count != 1 THEN
    RAISE EXCEPTION 'PRE FAILED: public.handle_new_user() not found or signature mismatch.';
  END IF;

  -- 1-b. SECURITY DEFINER 확인
  SELECT p.prosecdef INTO v_secdef
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'handle_new_user' AND p.pronargs = 0;
  IF v_secdef != true THEN
    RAISE EXCEPTION 'PRE FAILED: handle_new_user() is not SECURITY DEFINER — baseline mismatch.';
  END IF;

  -- 1-c. 소유자 = postgres
  SELECT pg_get_userbyid(p.proowner) INTO v_owner
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'handle_new_user' AND p.pronargs = 0;
  IF v_owner != 'postgres' THEN
    RAISE EXCEPTION 'PRE FAILED: handle_new_user() owner is %, expected postgres.', v_owner;
  END IF;

  -- 1-d. 함수 정의 MD5 기준선
  SELECT md5(pg_get_functiondef(p.oid)) INTO v_def_md5
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'handle_new_user' AND p.pronargs = 0;
  IF v_def_md5 != '8e04ca79820d6f495fe808c9eef98756' THEN
    RAISE EXCEPTION 'PRE FAILED: handle_new_user() definition MD5 mismatch: got %.', v_def_md5;
  END IF;

  -- 1-e. 함수 본문 MD5 기준선
  SELECT md5(p.prosrc) INTO v_body_md5
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'handle_new_user' AND p.pronargs = 0;
  IF v_body_md5 != 'f9ac19e4af493e7cba768d9ee76d5542' THEN
    RAISE EXCEPTION 'PRE FAILED: handle_new_user() body MD5 mismatch: got %.', v_body_md5;
  END IF;

  -- 1-f. 연결 트리거 0건
  SELECT count(*) INTO v_trig_count
  FROM pg_trigger t
  JOIN pg_proc p ON p.oid = t.tgfoid
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'handle_new_user' AND p.pronargs = 0;
  IF v_trig_count != 0 THEN
    RAISE EXCEPTION 'PRE FAILED: handle_new_user() has % connected trigger(s).', v_trig_count;
  END IF;

  -- 1-g. DB 종속 객체 0건 (implicit dependency 제외)
  SELECT count(*) INTO v_dep_count
  FROM pg_depend dep
  JOIN pg_proc p ON p.oid = dep.refobjid
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'handle_new_user' AND p.pronargs = 0
    AND dep.deptype != 'i';
  IF v_dep_count != 0 THEN
    RAISE EXCEPTION 'PRE FAILED: handle_new_user() has % non-implicit dependency(ies).', v_dep_count;
  END IF;

  -- 1-h. anon EXECUTE = FALSE (SEC-04 기준선 유지 확인)
  IF has_function_privilege('anon', 'public.handle_new_user()', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: anon retains EXECUTE on handle_new_user() — SEC-04 baseline violated.';
  END IF;

  -- 1-i. authenticated EXECUTE = FALSE
  IF has_function_privilege('authenticated', 'public.handle_new_user()', 'EXECUTE') THEN
    RAISE EXCEPTION 'PRE FAILED: authenticated retains EXECUTE on handle_new_user() — SEC-04 baseline violated.';
  END IF;

  RAISE NOTICE 'PRE: Pre-conditions PASS.';

  -- ── STEP 2: 변경 실행 ──────────────────────────────────────────────

  DROP FUNCTION public.handle_new_user();

  RAISE NOTICE 'STEP 2: public.handle_new_user() dropped.';

  -- ── STEP 3: 사후조건 검증 ──────────────────────────────────────────

  -- 3-a. 함수 부재 확인
  SELECT count(*) INTO v_count
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'handle_new_user' AND p.pronargs = 0;
  IF v_count != 0 THEN
    RAISE EXCEPTION 'POST FAILED: handle_new_user() still exists after DROP.';
  END IF;

  RAISE NOTICE 'POST-COMPLETE: public.handle_new_user() removed. trigger=0, dependency=0.';

END;
$$;

COMMIT;
