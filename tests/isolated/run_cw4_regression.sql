-- WO-TAI-SEC-SEARCHPATH-REM97-CW4-D02-RUNTIME-EVIDENCE-001
-- C-W4 격리 회귀 테스트: C16/C17/C18 search_path 고정 검증
-- Run AFTER setup_cw4.sql in cw4_d02_test database
-- HTTP endpoint: http://kong:8000 (local Docker, controlled, no real external calls)

SET search_path = public;

-- ─── 테스트 데이터 설정 ─────────────────────────────────────────────────────────
-- monitoring_config: 통제 엔드포인트(kong:8000)
TRUNCATE monitoring_config, auto_qa_checks, auto_qa_pending, auto_qa_log, fix_chat_sessions;

INSERT INTO monitoring_config (key, value) VALUES
  ('api_url',      'http://kong:8000'),
  ('alert_email',  'test@cw4-isolated.local'),
  ('alert_phone',  '+82-000-0000-0000');

-- auto_qa_checks: 1건 P0 + 2건 P1 (모두 GET, local Kong endpoint)
INSERT INTO auto_qa_checks (id, is_active, method, priority, name, endpoint) VALUES
  ('a0000001-0000-0000-0000-000000000001'::uuid, true,  'GET',  'P0', 'P0 health check',  '/'),
  ('a0000001-0000-0000-0000-000000000002'::uuid, true,  'GET',  'P1', 'P1 check alpha',   '/'),
  ('a0000001-0000-0000-0000-000000000003'::uuid, true,  'GET',  'P1', 'P1 check beta',    '/'),
  ('a0000001-0000-0000-0000-000000000004'::uuid, false, 'GET',  'P1', 'Inactive check',   '/'),
  ('a0000001-0000-0000-0000-000000000005'::uuid, true,  'POST', 'P1', 'POST (skip check)', '/');

-- ─────────────────────────────────────────────────────────────────────────────
-- BASELINE: PRE 상태 캡처 (proconfig=NULL, MD5 동적 저장)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  c_sigs CONSTANT text[] := ARRAY[
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
    FROM pg_proc p
    WHERE p.proname = c_names[i];

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

    PERFORM set_config('app.cw4_md5_' || c_names[i], v_md5, false);
    RAISE NOTICE 'BASELINE OK [%/3]: % proconfig=NULL MD5=% owner=% volat=% parallel=%',
      i, c_names[i], v_md5, v_owner, v_volat, v_parallel;
  END LOOP;
END;
$$;

-- ─── ACL 스냅샷 ───────────────────────────────────────────────────────────────
CREATE TEMP TABLE _cw4_reg_acl (
  fn_oid  oid  PRIMARY KEY,
  proacl  text
);
INSERT INTO _cw4_reg_acl (fn_oid, proacl)
SELECT p.oid, p.proacl::text
FROM pg_proc p
WHERE p.proname IN ('collect_auto_qa_results','daily_health_check','send_auto_qa_requests');

DO $$
DECLARE v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM _cw4_reg_acl;
  IF v_count IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'BASELINE FAILED: ACL snapshot captured % rows, expected 3', v_count;
  END IF;
  RAISE NOTICE 'BASELINE ACL SNAPSHOT OK: 3 rows';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- PHASE 1 — ALTER 이전 동작 검증
-- ─────────────────────────────────────────────────────────────────────────────

-- CW4-P1-01: send_auto_qa_requests — 활성 GET 체크 3건 → 3 반환, auto_qa_pending 3건
DO $$
DECLARE
  v_cnt    int;
  v_pend   int;
BEGIN
  SELECT public.send_auto_qa_requests() INTO v_cnt;

  IF v_cnt IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'CW4-P1-01 FAIL: expected 3 from send, got %', v_cnt;
  END IF;

  SELECT COUNT(*) INTO v_pend FROM auto_qa_pending;
  IF v_pend IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'CW4-P1-01 FAIL: expected 3 pending rows, got %', v_pend;
  END IF;

  RAISE NOTICE 'CW4-P1-01 PASS: send_auto_qa_requests returned %, pending=%', v_cnt, v_pend;
END;
$$;

-- CW4-P1-02: pg_net 실제 호출 검증 — req_id는 non-null bigint (net.http_get 호출 증거)
DO $$
DECLARE
  v_null_cnt  int;
  v_min_id    bigint;
  v_max_id    bigint;
BEGIN
  SELECT COUNT(*) FILTER (WHERE req_id IS NULL),
         MIN(req_id),
         MAX(req_id)
  INTO v_null_cnt, v_min_id, v_max_id
  FROM auto_qa_pending;

  IF v_null_cnt > 0 THEN
    RAISE EXCEPTION 'CW4-P1-02 FAIL: % pending rows have NULL req_id (net.http_get failed)', v_null_cnt;
  END IF;
  IF v_min_id IS NULL OR v_min_id < 1 THEN
    RAISE EXCEPTION 'CW4-P1-02 FAIL: req_id values invalid (min=%)', v_min_id;
  END IF;

  RAISE NOTICE 'CW4-P1-02 PASS: pg_net REAL_CALL verified — 3 non-null req_ids (min=%, max=%)',
    v_min_id, v_max_id;
END;
$$;

-- CW4-P1-03: collect_auto_qa_results — pending 처리 (pg_net 응답 대기 후)
-- pg_net 비동기 처리 대기 (3초)
DO $$
BEGIN
  PERFORM pg_sleep(3);
  RAISE NOTICE 'CW4-P1-03: pg_sleep(3) complete — waiting for pg_net responses';
END;
$$;

DO $$
DECLARE
  v_raised bool := false;
  v_log_cnt int;
  v_pend_cnt int;
BEGIN
  BEGIN
    PERFORM public.collect_auto_qa_results();
  EXCEPTION WHEN OTHERS THEN
    v_raised := true;
    RAISE EXCEPTION 'CW4-P1-03 FAIL: collect_auto_qa_results raised exception: %', SQLERRM;
  END;

  IF v_raised THEN
    RAISE EXCEPTION 'CW4-P1-03 FAIL: unexpected exception';
  END IF;

  -- pending이 정리됐는지 확인
  SELECT COUNT(*) INTO v_pend_cnt FROM auto_qa_pending;
  IF v_pend_cnt IS DISTINCT FROM 0 THEN
    RAISE EXCEPTION 'CW4-P1-03 FAIL: auto_qa_pending not cleared after collect (rows=%)', v_pend_cnt;
  END IF;

  -- log에 3건 기록됐는지 확인 (P0·P1 GET 3건 + POST SKIP 1건 = 4건)
  SELECT COUNT(*) INTO v_log_cnt FROM auto_qa_log;
  IF v_log_cnt < 3 THEN
    RAISE EXCEPTION 'CW4-P1-03 FAIL: expected ≥3 log rows, got %', v_log_cnt;
  END IF;

  RAISE NOTICE 'CW4-P1-03 PASS: collect_auto_qa_results OK — pending=0, log_rows=%', v_log_cnt;
END;
$$;

-- CW4-P1-04: daily_health_check — all_clear (세션 없음 → status='all_clear')
DO $$
DECLARE
  v_result jsonb;
  v_status text;
BEGIN
  TRUNCATE fix_chat_sessions;

  SELECT public.daily_health_check() INTO v_result;

  v_status := v_result->>'status';
  IF v_status IS DISTINCT FROM 'all_clear' THEN
    RAISE EXCEPTION 'CW4-P1-04 FAIL: expected status=all_clear, got %', v_status;
  END IF;
  IF (v_result->>'checked_at') IS NULL THEN
    RAISE EXCEPTION 'CW4-P1-04 FAIL: checked_at missing from result';
  END IF;

  RAISE NOTICE 'CW4-P1-04 PASS: daily_health_check → all_clear (no sessions)';
END;
$$;

-- CW4-P1-05: daily_health_check — alerts case (abandon_rate > 80%)
-- 10세션 중 9건 current_turn=0 → abandon_rate=90% → status='alerts'
-- 통제 엔드포인트(kong:8000)로만 net.http_get 호출 — 실제 SMS 미발송
DO $$
DECLARE
  v_result  jsonb;
  v_status  text;
  v_alerts  jsonb;
BEGIN
  TRUNCATE fix_chat_sessions;

  INSERT INTO fix_chat_sessions (current_turn)
  SELECT CASE WHEN i = 1 THEN 3 ELSE 0 END
  FROM generate_series(1, 10) AS i;

  SELECT public.daily_health_check() INTO v_result;

  v_status := v_result->>'status';
  IF v_status IS DISTINCT FROM 'alerts' THEN
    RAISE EXCEPTION 'CW4-P1-05 FAIL: expected status=alerts, got %', v_status;
  END IF;

  v_alerts := v_result->'alerts';
  IF jsonb_array_length(v_alerts) < 1 THEN
    RAISE EXCEPTION 'CW4-P1-05 FAIL: alerts array empty';
  END IF;
  IF NOT (v_alerts::text LIKE '%chat_abandon%') THEN
    RAISE EXCEPTION 'CW4-P1-05 FAIL: expected chat_abandon alert, got %', v_alerts;
  END IF;

  RAISE NOTICE 'CW4-P1-05 PASS: daily_health_check → alerts (90%% abandon) alerts=%', v_alerts;
END;
$$;

-- CW4-P1-06: EXECUTE 권한 확인 — service_role=true, anon/authenticated=false
DO $$
DECLARE
  v_sr    bool;
  v_anon  bool;
  v_auth  bool;
  v_fn    text;
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
      RAISE EXCEPTION 'CW4-P1-06 FAIL: service_role lacks EXECUTE on %', v_fn;
    END IF;
    IF v_anon THEN
      RAISE EXCEPTION 'CW4-P1-06 FAIL: anon has EXECUTE on % (sec02 violation)', v_fn;
    END IF;
    IF v_auth THEN
      RAISE EXCEPTION 'CW4-P1-06 FAIL: authenticated has EXECUTE on % (sec02 violation)', v_fn;
    END IF;
  END LOOP;
  RAISE NOTICE 'CW4-P1-06 PASS: service_role=EXECUTE, anon/authenticated=blocked (3/3)';
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

-- CW4-P2-01: proconfig 고정 + MD5/SECURITY/Volatility/Parallel 불변 (Fail-Closed)
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
    v_fn_key := 'app.cw4_md5_' || c_names[i];
    v_baseline_md5 := current_setting(v_fn_key, true);

    IF v_baseline_md5 IS NULL THEN
      RAISE EXCEPTION 'CW4-P2-01 FAIL: MD5 baseline missing for %', c_names[i];
    END IF;

    SELECT md5(p.prosrc), p.prosecdef, pg_get_userbyid(p.proowner),
           p.proconfig, p.provolatile, p.proparallel
    INTO v_md5, v_secdef, v_owner, v_proconfig, v_volat, v_parallel
    FROM pg_proc p
    WHERE p.proname = c_names[i];

    IF v_proconfig IS DISTINCT FROM ARRAY[c_search_path]::text[] THEN
      RAISE EXCEPTION 'CW4-P2-01 FAIL: % proconfig mismatch: %', c_names[i], v_proconfig;
    END IF;
    IF v_md5 IS DISTINCT FROM v_baseline_md5 THEN
      RAISE EXCEPTION 'CW4-P2-01 FAIL: % prosrc_md5 changed (baseline=%, now=%)',
        c_names[i], v_baseline_md5, v_md5;
    END IF;
    IF v_secdef IS DISTINCT FROM false THEN
      RAISE EXCEPTION 'CW4-P2-01 FAIL: % prosecdef changed', c_names[i];
    END IF;
    IF v_volat IS DISTINCT FROM 'v' THEN
      RAISE EXCEPTION 'CW4-P2-01 FAIL: % volatility changed', c_names[i];
    END IF;
    IF v_parallel IS DISTINCT FROM 'u' THEN
      RAISE EXCEPTION 'CW4-P2-01 FAIL: % proparallel changed', c_names[i];
    END IF;

    RAISE NOTICE 'CW4-P2-01 PASS [%/3]: % proconfig=[%] MD5=% (unchanged)',
      i, c_names[i], c_search_path, v_md5;
  END LOOP;
END;
$$;

-- CW4-P2-02: ACL 불변 검증
DO $$
DECLARE
  r        record;
  v_proacl text;
BEGIN
  FOR r IN SELECT fn_oid, proacl FROM _cw4_reg_acl LOOP
    SELECT p.proacl::text INTO v_proacl FROM pg_proc p WHERE p.oid = r.fn_oid;
    IF v_proacl IS DISTINCT FROM r.proacl THEN
      RAISE EXCEPTION 'CW4-P2-02 FAIL: ACL changed for OID % (before=%, after=%)',
        r.fn_oid, r.proacl, v_proacl;
    END IF;
  END LOOP;
  RAISE NOTICE 'CW4-P2-02 PASS: ACL unchanged (3/3)';
END;
$$;

-- CW4-P2-03: ALTER 후 send_auto_qa_requests 동작 불변
DO $$
DECLARE
  v_cnt  int;
  v_pend int;
BEGIN
  TRUNCATE auto_qa_pending, auto_qa_log;

  SELECT public.send_auto_qa_requests() INTO v_cnt;

  IF v_cnt IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'CW4-P2-03 FAIL: expected 3, got %', v_cnt;
  END IF;

  SELECT COUNT(*) INTO v_pend FROM auto_qa_pending;
  IF v_pend IS DISTINCT FROM 3 THEN
    RAISE EXCEPTION 'CW4-P2-03 FAIL: expected 3 pending rows, got %', v_pend;
  END IF;

  RAISE NOTICE 'CW4-P2-03 PASS: send_auto_qa_requests behavioral invariance (count=%, pending=%)',
    v_cnt, v_pend;
END;
$$;

-- CW4-P2-04: ALTER 후 pg_net 실제 호출 불변 — req_id non-null bigint
DO $$
DECLARE
  v_null_cnt  int;
  v_min_id    bigint;
  v_max_id    bigint;
BEGIN
  SELECT COUNT(*) FILTER (WHERE req_id IS NULL),
         MIN(req_id),
         MAX(req_id)
  INTO v_null_cnt, v_min_id, v_max_id
  FROM auto_qa_pending;

  IF v_null_cnt > 0 THEN
    RAISE EXCEPTION 'CW4-P2-04 FAIL: % req_id NULL after ALTER (net.http_get broken)', v_null_cnt;
  END IF;
  IF v_min_id IS NULL OR v_min_id < 1 THEN
    RAISE EXCEPTION 'CW4-P2-04 FAIL: req_id invalid after ALTER (min=%)', v_min_id;
  END IF;

  RAISE NOTICE 'CW4-P2-04 PASS: net.http_get still returns non-null bigint after ALTER (min=%, max=%)',
    v_min_id, v_max_id;
END;
$$;

-- CW4-P2-05: ALTER 후 collect_auto_qa_results 동작 불변
DO $$
BEGIN
  PERFORM pg_sleep(3);
  RAISE NOTICE 'CW4-P2-05: pg_sleep(3) complete';
END;
$$;

DO $$
DECLARE
  v_pend_cnt int;
  v_log_cnt  int;
BEGIN
  SELECT COUNT(*) INTO v_log_cnt FROM auto_qa_log;
  PERFORM public.collect_auto_qa_results();

  SELECT COUNT(*) INTO v_pend_cnt FROM auto_qa_pending;
  IF v_pend_cnt IS DISTINCT FROM 0 THEN
    RAISE EXCEPTION 'CW4-P2-05 FAIL: pending not cleared after collect (rows=%)', v_pend_cnt;
  END IF;

  SELECT COUNT(*) INTO v_log_cnt FROM auto_qa_log;
  IF v_log_cnt < 3 THEN
    RAISE EXCEPTION 'CW4-P2-05 FAIL: expected ≥3 log rows, got %', v_log_cnt;
  END IF;

  RAISE NOTICE 'CW4-P2-05 PASS: collect_auto_qa_results behavioral invariance after ALTER (log_rows=%)',
    v_log_cnt;
END;
$$;

-- CW4-P2-06: ALTER 후 daily_health_check all_clear 불변
DO $$
DECLARE
  v_result jsonb;
BEGIN
  TRUNCATE fix_chat_sessions;
  SELECT public.daily_health_check() INTO v_result;

  IF (v_result->>'status') IS DISTINCT FROM 'all_clear' THEN
    RAISE EXCEPTION 'CW4-P2-06 FAIL: expected all_clear, got %', v_result->>'status';
  END IF;
  RAISE NOTICE 'CW4-P2-06 PASS: daily_health_check all_clear after ALTER';
END;
$$;

-- CW4-P2-07: ALTER 후 daily_health_check alerts 불변
DO $$
DECLARE
  v_result jsonb;
  v_status text;
  v_alerts jsonb;
BEGIN
  TRUNCATE fix_chat_sessions;

  INSERT INTO fix_chat_sessions (current_turn)
  SELECT CASE WHEN i = 1 THEN 3 ELSE 0 END
  FROM generate_series(1, 10) AS i;

  SELECT public.daily_health_check() INTO v_result;
  v_status := v_result->>'status';
  v_alerts := v_result->'alerts';

  IF v_status IS DISTINCT FROM 'alerts' THEN
    RAISE EXCEPTION 'CW4-P2-07 FAIL: expected alerts, got %', v_status;
  END IF;
  IF NOT (v_alerts::text LIKE '%chat_abandon%') THEN
    RAISE EXCEPTION 'CW4-P2-07 FAIL: expected chat_abandon alert, got %', v_alerts;
  END IF;

  RAISE NOTICE 'CW4-P2-07 PASS: daily_health_check alerts behavioral invariance after ALTER';
END;
$$;

-- CW4-P2-08: ALTER 후 EXECUTE 권한 불변
DO $$
DECLARE
  v_sr    bool;
  v_anon  bool;
  v_auth  bool;
  v_fn    text;
BEGIN
  FOR v_fn IN VALUES
    ('public.collect_auto_qa_results()'),
    ('public.daily_health_check()'),
    ('public.send_auto_qa_requests()')
  LOOP
    v_sr   := has_function_privilege('service_role',  v_fn, 'EXECUTE');
    v_anon := has_function_privilege('anon',          v_fn, 'EXECUTE');
    v_auth := has_function_privilege('authenticated', v_fn, 'EXECUTE');

    IF NOT v_sr  THEN RAISE EXCEPTION 'CW4-P2-08 FAIL: service_role lost EXECUTE on %', v_fn; END IF;
    IF v_anon    THEN RAISE EXCEPTION 'CW4-P2-08 FAIL: anon gained EXECUTE on %', v_fn; END IF;
    IF v_auth    THEN RAISE EXCEPTION 'CW4-P2-08 FAIL: authenticated gained EXECUTE on %', v_fn; END IF;
  END LOOP;
  RAISE NOTICE 'CW4-P2-08 PASS: EXECUTE ACL unchanged after ALTER (3/3)';
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 최종 요약
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
  RAISE NOTICE '=== C-W4 D02 RUNTIME EVIDENCE COMPLETE ===';
  RAISE NOTICE 'P1: 01-send(count+pending) 02-net.http_get(bigint) 03-collect(log+pending) 04-health_all_clear 05-health_alerts 06-ACL_pre';
  RAISE NOTICE 'P2: 01-proconfig+MD5+meta 02-ACL_invariant 03-send 04-net.http_get 05-collect 06-health_all_clear 07-health_alerts 08-ACL_post';
  RAISE NOTICE 'RUNTIME_EVIDENCE: pg_net real calls verified (non-null req_id pre+post ALTER)';
  RAISE NOTICE 'HTTP_ENDPOINT: http://kong:8000 (local Docker, no real external calls)';
  RAISE NOTICE 'PRODUCTION_DB_WRITE: 0';
END;
$$;
