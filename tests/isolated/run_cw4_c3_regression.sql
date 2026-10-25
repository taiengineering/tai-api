-- WO-TAI-SEC-SEARCHPATH-REM97-CW4-C3-SOURCE-001
-- C-W4 C3 격리 회귀 테스트: collect_auto_qa_results / daily_health_check / send_auto_qa_requests
-- Run AFTER setup_cw4.sql in cw4_c3_test database
--
-- 기존 D-02 증거 (run_cw4_regression.sql, 14/14 PASS) 는 별도 보존
-- 이 파일은 C3 Migration 소스 검증 전용
--
-- NOTE: pg_net HTTP 실제 전달은 격리 DB에서 UNVERIFIED (D-02 OWNER 수용)
--   net.http_get() 호출 → non-null bigint req_id 반환: VERIFIED
--   HTTP 응답 수신: 격리 환경에서 CANNOT_VERIFY_IN_ISOLATION

SET search_path = public;

TRUNCATE monitoring_config, auto_qa_checks, auto_qa_pending, auto_qa_log, fix_chat_sessions;

INSERT INTO monitoring_config (key, value) VALUES
  ('api_url',      'http://kong:8000'),
  ('alert_email',  'test@cw4-isolated.local'),
  ('alert_phone',  '+82-000-0000-0000');

INSERT INTO auto_qa_checks (id, is_active, method, priority, name, endpoint) VALUES
  ('a0000001-0000-0000-0000-000000000001'::uuid, true,  'GET',  'P0', 'P0 health check',   '/'),
  ('a0000001-0000-0000-0000-000000000002'::uuid, true,  'GET',  'P1', 'P1 check alpha',    '/'),
  ('a0000001-0000-0000-0000-000000000003'::uuid, true,  'GET',  'P1', 'P1 check beta',     '/'),
  ('a0000001-0000-0000-0000-000000000004'::uuid, false, 'GET',  'P1', 'Inactive check',    '/'),
  ('a0000001-0000-0000-0000-000000000005'::uuid, true,  'POST', 'P1', 'POST (skip check)', '/');

-- ─────────────────────────────────────────────────────────────────────────────
-- BASELINE: PRE 상태 캡처 (proconfig=NULL, MD5 동적 저장)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sigs  CONSTANT text[] := ARRAY[
    'public.collect_auto_qa_results()',
    'public.daily_health_check()',
    'public.send_auto_qa_requests()'
  ];
  c_names CONSTANT text[] := ARRAY[
    'collect_auto_qa_results',
    'daily_health_check',
    'send_auto_qa_requests'
  ];
  v_md5       text;
  v_secdef    bool;
  v_owner     text;
  v_proconfig text[];
  v_volat     char;
  v_parallel  char;
  i           int;
BEGIN
  FOR i IN 1..3 LOOP
    SELECT md5(p.prosrc), p.prosecdef, pg_get_userbyid(p.proowner),
           p.proconfig, p.provolatile, p.proparallel
    INTO v_md5, v_secdef, v_owner, v_proconfig, v_volat, v_parallel
    FROM pg_proc p WHERE p.proname = c_names[i];

    IF v_md5 IS NULL THEN
      RAISE EXCEPTION 'BASELINE FAILED: % not found', c_names[i];
    END IF;
    IF v_proconfig IS NOT NULL THEN
      RAISE EXCEPTION 'BASELINE FAILED: % proconfig already set: %', c_names[i], v_proconfig;
    END IF;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'BASELINE FAILED: % not SECURITY INVOKER', c_names[i];
    END IF;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'BASELINE FAILED: % volatility is %, expected v', c_names[i], v_volat;
    END IF;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'BASELINE FAILED: % proparallel is %, expected u', c_names[i], v_parallel;
    END IF;

    PERFORM set_config('app.cw4c3_md5_' || c_names[i], v_md5, false);
    RAISE NOTICE 'BASELINE OK [%/3]: % proconfig=NULL MD5=% owner=% volat=v parallel=u',
      i, c_names[i], v_md5, v_owner;
  END LOOP;
END;
$$;

-- ACL 스냅샷
CREATE TEMP TABLE _cw4c3_acl (
  fn_oid  oid  PRIMARY KEY,
  proacl  text
);
INSERT INTO _cw4c3_acl (fn_oid, proacl)
SELECT p.oid, p.proacl::text
FROM pg_proc p
WHERE p.proname IN ('collect_auto_qa_results','daily_health_check','send_auto_qa_requests');

DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM _cw4c3_acl;
  IF v_count IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'BASELINE FAILED: ACL snapshot % rows, expected 3', v_count;
  END IF;
  RAISE NOTICE 'BASELINE ACL SNAPSHOT OK: 3 rows';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 1 — ALTER 이전 동작 검증
-- ─────────────────────────────────────────────────────────────────────────────

-- CW4C3-P1-01: send_auto_qa_requests — 활성 GET 3건 → count=3, pending=3
DO $$
DECLARE
  v_cnt  int;
  v_pend int;
  v_null int;
BEGIN
  SELECT public.send_auto_qa_requests() INTO v_cnt;
  IF v_cnt IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'CW4C3-P1-01 FAIL: send returned %, expected 3', v_cnt;
  END IF;
  SELECT COUNT(*) INTO v_pend FROM auto_qa_pending;
  IF v_pend IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'CW4C3-P1-01 FAIL: pending rows=%, expected 3', v_pend;
  END IF;
  SELECT COUNT(*) FILTER (WHERE req_id IS NULL) INTO v_null FROM auto_qa_pending;
  IF v_null > 0 THEN
    RAISE EXCEPTION 'CW4C3-P1-01 FAIL: % NULL req_id (net.http_get call failed)', v_null;
  END IF;
  RAISE NOTICE 'CW4C3-P1-01 PASS: send=3, pending=3, net.http_get req_ids non-null';
END;
$$;

-- CW4C3-P1-02: collect_auto_qa_results — pending 처리 → log 기록, pending 정리
DO $$
DECLARE
  v_pend int;
  v_log  int;
BEGIN
  PERFORM public.collect_auto_qa_results();
  SELECT COUNT(*) INTO v_pend FROM auto_qa_pending;
  SELECT COUNT(*) INTO v_log  FROM auto_qa_log;
  IF v_pend IS DISTINCT FROM 0 THEN
    RAISE EXCEPTION 'CW4C3-P1-02 FAIL: pending not cleared (rows=%)', v_pend;
  END IF;
  IF v_log < 3 THEN
    RAISE EXCEPTION 'CW4C3-P1-02 FAIL: log rows=% expected ≥3', v_log;
  END IF;
  RAISE NOTICE 'CW4C3-P1-02 PASS: collect OK — pending=0, log=%', v_log;
END;
$$;

TRUNCATE auto_qa_pending, auto_qa_log;

-- CW4C3-P1-03: daily_health_check — all_clear (세션 없음)
DO $$
DECLARE v_result jsonb;
BEGIN
  TRUNCATE fix_chat_sessions;
  SELECT public.daily_health_check() INTO v_result;
  IF (v_result->>'status') IS DISTINCT FROM 'all_clear' THEN
    RAISE EXCEPTION 'CW4C3-P1-03 FAIL: expected all_clear, got %', v_result->>'status';
  END IF;
  IF (v_result->>'checked_at') IS NULL THEN
    RAISE EXCEPTION 'CW4C3-P1-03 FAIL: checked_at missing';
  END IF;
  RAISE NOTICE 'CW4C3-P1-03 PASS: daily_health_check → all_clear';
END;
$$;

-- CW4C3-P1-04: daily_health_check — alerts (90% abandon rate → alerts=[chat_abandon_90_pct])
DO $$
DECLARE v_result jsonb;
BEGIN
  TRUNCATE fix_chat_sessions;
  INSERT INTO fix_chat_sessions (current_turn)
  SELECT CASE WHEN i = 1 THEN 3 ELSE 0 END FROM generate_series(1,10) i;
  SELECT public.daily_health_check() INTO v_result;
  IF (v_result->>'status') IS DISTINCT FROM 'alerts' THEN
    RAISE EXCEPTION 'CW4C3-P1-04 FAIL: expected alerts, got %', v_result->>'status';
  END IF;
  IF NOT (v_result->'alerts')::text LIKE '%chat_abandon%' THEN
    RAISE EXCEPTION 'CW4C3-P1-04 FAIL: chat_abandon alert missing, got %', v_result->'alerts';
  END IF;
  RAISE NOTICE 'CW4C3-P1-04 PASS: daily_health_check → alerts=[%]', v_result->'alerts';
END;
$$;

-- CW4C3-P1-05: EXECUTE 권한 확인 (격리 환경 기준 — 운영 ACL과 다름, 별도 기록)
-- 격리: service_role=T, anon=F, auth=F (intentionally strict)
-- 운영: PUBLIC=T, sr=T, anon=T, auth=T (기존 설정)
DO $$
DECLARE
  v_sr   bool;
  v_anon bool;
  v_auth bool;
  v_fn   text;
BEGIN
  FOR v_fn IN VALUES
    ('public.collect_auto_qa_results()'),
    ('public.daily_health_check()'),
    ('public.send_auto_qa_requests()')
  LOOP
    v_sr   := has_function_privilege('service_role',  v_fn, 'EXECUTE');
    v_anon := has_function_privilege('anon',          v_fn, 'EXECUTE');
    v_auth := has_function_privilege('authenticated', v_fn, 'EXECUTE');
    IF NOT v_sr THEN
      RAISE EXCEPTION 'CW4C3-P1-05 FAIL: service_role lacks EXECUTE on %', v_fn;
    END IF;
    IF v_anon THEN
      RAISE EXCEPTION 'CW4C3-P1-05 FAIL: anon has EXECUTE on % (isolated ACL violation)', v_fn;
    END IF;
    IF v_auth THEN
      RAISE EXCEPTION 'CW4C3-P1-05 FAIL: authenticated has EXECUTE on % (isolated ACL violation)', v_fn;
    END IF;
  END LOOP;
  RAISE NOTICE 'CW4C3-P1-05 PASS: service_role=T, anon=F, auth=F (isolated ACL — differs from production PUBLIC=T)';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ALTER: search_path 고정 (마이그레이션과 동일)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER FUNCTION public.collect_auto_qa_results()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.daily_health_check()
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.send_auto_qa_requests()
  SET search_path = pg_catalog, public, pg_temp;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 2 — ALTER 이후 메타데이터 및 동작 검증
-- ─────────────────────────────────────────────────────────────────────────────

-- CW4C3-P2-01: proconfig 목표값 + MD5/SECURITY/Volatility/Parallel 불변 (Fail-Closed)
DO $$
DECLARE
  c_search_path CONSTANT text := 'search_path=pg_catalog, public, pg_temp';
  c_names CONSTANT text[] := ARRAY[
    'collect_auto_qa_results',
    'daily_health_check',
    'send_auto_qa_requests'
  ];
  v_baseline_md5 text;
  v_md5          text;
  v_secdef       bool;
  v_owner        text;
  v_proconfig    text[];
  v_volat        char;
  v_parallel     char;
  v_fn_key       text;
  i              int;
BEGIN
  FOR i IN 1..3 LOOP
    v_fn_key := 'app.cw4c3_md5_' || c_names[i];
    v_baseline_md5 := current_setting(v_fn_key, true);

    -- Fail-Closed: 기준선 누락 시 즉시 예외
    IF v_baseline_md5 IS NULL THEN
      RAISE EXCEPTION 'CW4C3-P2-01 FAIL: MD5 baseline missing for %', c_names[i];
    END IF;

    SELECT md5(p.prosrc), p.prosecdef, pg_get_userbyid(p.proowner),
           p.proconfig, p.provolatile, p.proparallel
    INTO v_md5, v_secdef, v_owner, v_proconfig, v_volat, v_parallel
    FROM pg_proc p WHERE p.proname = c_names[i];

    IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
      RAISE EXCEPTION 'CW4C3-P2-01 FAIL: % proconfig mismatch: %', c_names[i], v_proconfig;
    END IF;
    IF v_md5 IS DISTINCT FROM v_baseline_md5 THEN
      RAISE EXCEPTION 'CW4C3-P2-01 FAIL: % prosrc_md5 changed (baseline=%, now=%)',
        c_names[i], v_baseline_md5, v_md5;
    END IF;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'CW4C3-P2-01 FAIL: % prosecdef changed', c_names[i];
    END IF;
    IF v_owner IS DISTINCT FROM 'postgres' THEN
      RAISE EXCEPTION 'CW4C3-P2-01 FAIL: % owner changed', c_names[i];
    END IF;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'CW4C3-P2-01 FAIL: % volatility changed', c_names[i];
    END IF;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'CW4C3-P2-01 FAIL: % proparallel changed', c_names[i];
    END IF;

    RAISE NOTICE 'CW4C3-P2-01 PASS [%/3]: % proconfig=[%] MD5=% (unchanged)',
      i, c_names[i], c_search_path, v_md5;
  END LOOP;
END;
$$;

-- CW4C3-P2-02: ACL 불변
DO $$
DECLARE
  r        record;
  v_proacl text;
BEGIN
  FOR r IN SELECT fn_oid, proacl FROM _cw4c3_acl ORDER BY fn_oid LOOP
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = r.fn_oid;
    IF v_proacl IS DISTINCT FROM r.proacl THEN
      RAISE EXCEPTION 'CW4C3-P2-02 FAIL: ACL changed for OID % (before=%, after=%)',
        r.fn_oid, r.proacl, v_proacl;
    END IF;
  END LOOP;
  RAISE NOTICE 'CW4C3-P2-02 PASS: ACL unchanged (3/3)';
END;
$$;

-- CW4C3-P2-03: ALTER 후 send_auto_qa_requests 동작 불변
DO $$
DECLARE
  v_cnt  int;
  v_pend int;
  v_null int;
BEGIN
  TRUNCATE auto_qa_pending, auto_qa_log;
  SELECT public.send_auto_qa_requests() INTO v_cnt;
  IF v_cnt IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'CW4C3-P2-03 FAIL: send returned %, expected 3', v_cnt;
  END IF;
  SELECT COUNT(*) INTO v_pend FROM auto_qa_pending;
  IF v_pend IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'CW4C3-P2-03 FAIL: pending rows=%, expected 3', v_pend;
  END IF;
  SELECT COUNT(*) FILTER (WHERE req_id IS NULL) INTO v_null FROM auto_qa_pending;
  IF v_null > 0 THEN
    RAISE EXCEPTION 'CW4C3-P2-03 FAIL: % NULL req_id after ALTER', v_null;
  END IF;
  RAISE NOTICE 'CW4C3-P2-03 PASS: send behavioral invariance after ALTER (count=3, pending=3, net.http_get non-null)';
END;
$$;

-- CW4C3-P2-04: ALTER 후 collect_auto_qa_results 동작 불변
DO $$
DECLARE
  v_pend int;
  v_log  int;
BEGIN
  PERFORM public.collect_auto_qa_results();
  SELECT COUNT(*) INTO v_pend FROM auto_qa_pending;
  SELECT COUNT(*) INTO v_log  FROM auto_qa_log;
  IF v_pend IS DISTINCT FROM 0 THEN
    RAISE EXCEPTION 'CW4C3-P2-04 FAIL: pending not cleared after ALTER (rows=%)', v_pend;
  END IF;
  IF v_log < 3 THEN
    RAISE EXCEPTION 'CW4C3-P2-04 FAIL: log rows=% after ALTER, expected ≥3', v_log;
  END IF;
  RAISE NOTICE 'CW4C3-P2-04 PASS: collect behavioral invariance after ALTER (pending=0, log=%)', v_log;
END;
$$;

TRUNCATE auto_qa_pending, auto_qa_log;

-- CW4C3-P2-05: ALTER 후 daily_health_check all_clear 불변
DO $$
DECLARE v_result jsonb;
BEGIN
  TRUNCATE fix_chat_sessions;
  SELECT public.daily_health_check() INTO v_result;
  IF (v_result->>'status') IS DISTINCT FROM 'all_clear' THEN
    RAISE EXCEPTION 'CW4C3-P2-05 FAIL: expected all_clear, got %', v_result->>'status';
  END IF;
  RAISE NOTICE 'CW4C3-P2-05 PASS: daily_health_check all_clear after ALTER';
END;
$$;

-- CW4C3-P2-06: ALTER 후 daily_health_check alerts 불변
DO $$
DECLARE v_result jsonb;
BEGIN
  TRUNCATE fix_chat_sessions;
  INSERT INTO fix_chat_sessions (current_turn)
  SELECT CASE WHEN i = 1 THEN 3 ELSE 0 END FROM generate_series(1,10) i;
  SELECT public.daily_health_check() INTO v_result;
  IF (v_result->>'status') IS DISTINCT FROM 'alerts' THEN
    RAISE EXCEPTION 'CW4C3-P2-06 FAIL: expected alerts, got %', v_result->>'status';
  END IF;
  IF NOT (v_result->'alerts')::text LIKE '%chat_abandon%' THEN
    RAISE EXCEPTION 'CW4C3-P2-06 FAIL: chat_abandon alert missing after ALTER';
  END IF;
  RAISE NOTICE 'CW4C3-P2-06 PASS: daily_health_check alerts invariance after ALTER';
END;
$$;

-- CW4C3-P2-07: ALTER 후 EXECUTE 권한 불변
DO $$
DECLARE
  v_sr   bool;
  v_anon bool;
  v_auth bool;
  v_fn   text;
BEGIN
  FOR v_fn IN VALUES
    ('public.collect_auto_qa_results()'),
    ('public.daily_health_check()'),
    ('public.send_auto_qa_requests()')
  LOOP
    v_sr   := has_function_privilege('service_role',  v_fn, 'EXECUTE');
    v_anon := has_function_privilege('anon',          v_fn, 'EXECUTE');
    v_auth := has_function_privilege('authenticated', v_fn, 'EXECUTE');
    IF NOT v_sr THEN
      RAISE EXCEPTION 'CW4C3-P2-07 FAIL: service_role lost EXECUTE on %', v_fn;
    END IF;
    IF v_anon THEN
      RAISE EXCEPTION 'CW4C3-P2-07 FAIL: anon gained EXECUTE on %', v_fn;
    END IF;
    IF v_auth THEN
      RAISE EXCEPTION 'CW4C3-P2-07 FAIL: authenticated gained EXECUTE on %', v_fn;
    END IF;
  END LOOP;
  RAISE NOTICE 'CW4C3-P2-07 PASS: EXECUTE ACL unchanged after ALTER (3/3)';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 최종 요약
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
  RAISE NOTICE '=== C-W4 C3 REGRESSION COMPLETE: 12/12 PASS ===';
  RAISE NOTICE 'P1: 01-send(count+net.http_get) 02-collect(log+pending) 03-health_allclear 04-health_alerts 05-ACL_pre';
  RAISE NOTICE 'P2: 01-proconfig+MD5+meta(Fail-Closed) 02-ACL_invariant 03-send 04-collect 05-health_allclear 06-health_alerts 07-ACL_post';
  RAISE NOTICE 'D02_RUNTIME: net.http_get CALL=VERIFIED, HTTP_DELIVERY=CANNOT_VERIFY_IN_ISOLATION (OWNER_ACCEPTED)';
  RAISE NOTICE 'ACL_NOTE: isolated=service_role_only, production=PUBLIC+all_roles (documented)';
  RAISE NOTICE 'PRODUCTION_DB_WRITE: 0';
END;
$$;
