-- WO-TAI-SEC-SEARCHPATH-REM97-CW4-D02-RUNTIME-EVIDENCE-001
-- C-W4 격리 환경 설정: collect_auto_qa_results / daily_health_check / send_auto_qa_requests
-- Run BEFORE run_cw4_regression.sql in cw4_d02_test database
-- Target DB: cw4_d02_test (local Supabase postgres container)
-- HTTP endpoint: http://kong:8000 (local Docker — no real external calls)

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

-- ─── monitoring_config ───────────────────────────────────────────────────────
CREATE TABLE public.monitoring_config (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- ─── auto_qa_checks ──────────────────────────────────────────────────────────
CREATE TABLE public.auto_qa_checks (
  id        UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  is_active BOOL    NOT NULL DEFAULT TRUE,
  method    TEXT    NOT NULL,
  priority  TEXT    NOT NULL DEFAULT 'P1',
  name      TEXT    NOT NULL,
  endpoint  TEXT    NOT NULL
);

-- ─── auto_qa_pending ─────────────────────────────────────────────────────────
-- sent_at DEFAULT needed: send function does not INSERT sent_at explicitly
CREATE TABLE public.auto_qa_pending (
  check_id  UUID         NOT NULL,
  req_id    BIGINT       NOT NULL,
  sent_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ─── auto_qa_log ─────────────────────────────────────────────────────────────
CREATE TABLE public.auto_qa_log (
  id          BIGSERIAL    PRIMARY KEY,
  check_id    UUID,
  status      TEXT,
  status_code INT,
  latency_ms  INT,
  error_msg   TEXT,
  created_at  TIMESTAMPTZ  DEFAULT now()
);

-- ─── fix_chat_sessions ───────────────────────────────────────────────────────
CREATE TABLE public.fix_chat_sessions (
  id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  current_turn INT          NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ─── collect_auto_qa_results (proconfig=NULL — 운영 기준선 재현) ───────────────
-- prosrc: 운영 DB에서 직접 추출 (OID=18553, MD5=43f43f91b3a21b9265010cd2c8c0c615)
CREATE OR REPLACE FUNCTION public.collect_auto_qa_results()
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
DECLARE
  rec          RECORD;
  v_api_url    TEXT;
  v_alert_email TEXT;
  v_fail_count INT := 0;
  v_fail_items TEXT := '';
BEGIN
  SELECT value INTO v_api_url     FROM monitoring_config WHERE key = 'api_url';
  SELECT value INTO v_alert_email FROM monitoring_config WHERE key = 'alert_email';

  -- pending이 없으면 아직 send 안 된 것
  IF NOT EXISTS (SELECT 1 FROM auto_qa_pending) THEN
    RETURN;
  END IF;

  -- POST/기타 SKIP 로그
  FOR rec IN
    SELECT * FROM auto_qa_checks
    WHERE is_active = true AND method != 'GET'
  LOOP
    INSERT INTO auto_qa_log (check_id, status, status_code, latency_ms, error_msg)
    VALUES (rec.id, 'skip', NULL, NULL, 'POST 자동 체크 미구현');
  END LOOP;

  -- GET 응답 수집
  FOR rec IN
    SELECT
      p.check_id,
      p.sent_at,
      r.status_code,
      r.timed_out,
      r.error_msg AS http_error,
      c.priority,
      c.name
    FROM auto_qa_pending p
    LEFT JOIN net._http_response r ON r.id = p.req_id
    JOIN auto_qa_checks c ON c.id = p.check_id
    ORDER BY c.priority, p.check_id
  LOOP
    DECLARE
      v_status  TEXT;
      v_error   TEXT;
      v_latency INT;
    BEGIN
      v_latency := (EXTRACT(EPOCH FROM (NOW() - rec.sent_at)) * 1000)::INT;

      IF rec.status_code IS NULL THEN
        v_status := 'fail'; v_error := 'timeout (응답 없음)';
      ELSIF rec.timed_out THEN
        v_status := 'fail'; v_error := 'timeout';
      ELSIF rec.status_code BETWEEN 200 AND 299 THEN
        v_status := 'ok';   v_error := NULL;
      ELSE
        v_status := 'fail'; v_error := 'HTTP ' || rec.status_code;
      END IF;

      INSERT INTO auto_qa_log (check_id, status, status_code, latency_ms, error_msg)
      VALUES (rec.check_id, v_status, rec.status_code, v_latency, v_error);

      IF v_status = 'fail' AND rec.priority = 'P0' THEN
        v_fail_count := v_fail_count + 1;
        v_fail_items := v_fail_items ||
          E'\n  [' || rec.check_id || '] ' || rec.name ||
          ' → ' || COALESCE(v_error, '?');
      END IF;
    END;
  END LOOP;

  -- pending 정리
  DELETE FROM auto_qa_pending;

  -- P0 실패 시 이메일
  IF v_fail_count > 0 AND v_alert_email IS NOT NULL THEN
    PERFORM net.http_post(
      url  := v_api_url || '/mail/send-system',
      body := json_build_object(
        'to',      v_alert_email,
        'subject', '[TAI 자동QA] P0 장애 ' || v_fail_count || '건 — ' ||
                   TO_CHAR(NOW() AT TIME ZONE 'Asia/Seoul', 'MM/DD HH24:MI'),
        'body',    'P0 이상 감지:' || v_fail_items ||
                   E'\n\n확인 시각: ' || TO_CHAR(NOW() AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS')
      )::jsonb
    );
  END IF;

END;
$$;

-- ─── daily_health_check (proconfig=NULL — 운영 기준선 재현) ────────────────────
-- prosrc: 운영 DB에서 직접 추출 (OID=18555, MD5=6c2dc44e46fa7dc46c97028d9d20af41)
CREATE OR REPLACE FUNCTION public.daily_health_check()
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
DECLARE
  v_alerts text[] := '{}';
  v_total_sessions int;
  v_abandoned int;
  v_abandon_rate numeric;
  v_empty_diag int;
  v_msg text;
  v_phone text;
  v_api text;
BEGIN
  SELECT count(*), count(*) FILTER (WHERE current_turn = 0)
  INTO v_total_sessions, v_abandoned
  FROM fix_chat_sessions
  WHERE created_at > now() - interval '24 hours';

  IF v_total_sessions > 0 THEN
    v_abandon_rate := round(v_abandoned::numeric / v_total_sessions * 100);
    IF v_abandon_rate > 80 THEN
      v_alerts := array_append(v_alerts,
        format('chat_abandon_%s_pct', v_abandon_rate));
    END IF;
  END IF;

  IF array_length(v_alerts, 1) IS NULL THEN
    RETURN jsonb_build_object('status', 'all_clear', 'checked_at', now());
  END IF;

  SELECT value INTO v_phone FROM monitoring_config WHERE key = 'alert_phone';
  SELECT value INTO v_api FROM monitoring_config WHERE key = 'api_url';

  IF v_phone IS NOT NULL AND v_api IS NOT NULL THEN
    v_msg := 'TAI_Daily_' || array_to_string(v_alerts, '_');
    PERFORM net.http_get(
      url := v_api || '/messaging/debug-send?receiver=' || v_phone || '&message=' || left(v_msg, 90)
    );
  END IF;

  RETURN jsonb_build_object(
    'status', 'alerts',
    'alerts', to_jsonb(v_alerts),
    'checked_at', now()
  );
END;
$$;

-- ─── send_auto_qa_requests (proconfig=NULL — 운영 기준선 재현) ────────────────
-- prosrc: 운영 DB에서 직접 추출 (OID=18574, MD5=f7829e2463819ebd000836db971485d8)
CREATE OR REPLACE FUNCTION public.send_auto_qa_requests()
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
DECLARE
  rec     RECORD;
  v_url   TEXT;
  v_api   TEXT;
  cnt     INT := 0;
BEGIN
  SELECT value INTO v_api FROM monitoring_config WHERE key = 'api_url';

  -- 이전 미수집 요청 정리
  DELETE FROM auto_qa_pending;

  FOR rec IN
    SELECT * FROM auto_qa_checks
    WHERE is_active = true AND method = 'GET'
    ORDER BY priority, id
  LOOP
    v_url := CASE WHEN rec.endpoint LIKE 'http%'
                  THEN rec.endpoint
                  ELSE v_api || rec.endpoint END;

    INSERT INTO auto_qa_pending (check_id, req_id)
    VALUES (rec.id, net.http_get(url := v_url));

    cnt := cnt + 1;
  END LOOP;

  RETURN cnt;
END;
$$;

-- ─── 권한 부여 (service_role 전용) ──────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON public.monitoring_config TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.auto_qa_log_id_seq TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.auto_qa_checks     TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.auto_qa_pending    TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.auto_qa_log        TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.fix_chat_sessions  TO service_role;

REVOKE EXECUTE ON FUNCTION public.collect_auto_qa_results()  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.daily_health_check()       FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.send_auto_qa_requests()    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.collect_auto_qa_results()   TO service_role;
GRANT EXECUTE ON FUNCTION public.daily_health_check()        TO service_role;
GRANT EXECUTE ON FUNCTION public.send_auto_qa_requests()     TO service_role;

-- net 스키마 접근 (pg_net 0.20.0 실제 시그니처)
GRANT USAGE ON SCHEMA net TO service_role;
GRANT EXECUTE ON FUNCTION net.http_get(text, jsonb, jsonb, integer)         TO service_role;
GRANT EXECUTE ON FUNCTION net.http_post(text, jsonb, jsonb, jsonb, integer) TO service_role;
GRANT SELECT ON net._http_response TO service_role;

-- ─── 설정 검증 ────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_fn  text;
  v_cnt int;
BEGIN
  -- 함수 3건 존재 확인
  FOR v_fn IN VALUES
    ('collect_auto_qa_results'),
    ('daily_health_check'),
    ('send_auto_qa_requests')
  LOOP
    SELECT COUNT(*) INTO v_cnt FROM pg_proc WHERE proname = v_fn;
    IF v_cnt IS DISTINCT FROM 1 THEN
      RAISE EXCEPTION 'SETUP FAILED: % not found (count=%)', v_fn, v_cnt;
    END IF;
  END LOOP;

  -- proconfig=NULL 확인
  SELECT COUNT(*) INTO v_cnt
  FROM pg_proc
  WHERE proname IN ('collect_auto_qa_results','daily_health_check','send_auto_qa_requests')
    AND proconfig IS NOT NULL;
  IF v_cnt > 0 THEN
    RAISE EXCEPTION 'SETUP FAILED: proconfig already set on % function(s)', v_cnt;
  END IF;

  -- service_role EXECUTE 확인
  IF NOT has_function_privilege('service_role', 'public.collect_auto_qa_results()', 'EXECUTE') THEN
    RAISE EXCEPTION 'SETUP FAILED: service_role lacks EXECUTE on collect_auto_qa_results';
  END IF;
  IF NOT has_function_privilege('service_role', 'public.daily_health_check()', 'EXECUTE') THEN
    RAISE EXCEPTION 'SETUP FAILED: service_role lacks EXECUTE on daily_health_check';
  END IF;
  IF NOT has_function_privilege('service_role', 'public.send_auto_qa_requests()', 'EXECUTE') THEN
    RAISE EXCEPTION 'SETUP FAILED: service_role lacks EXECUTE on send_auto_qa_requests';
  END IF;

  -- 테이블 5건 확인
  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname='monitoring_config'  AND relkind='r') THEN
    RAISE EXCEPTION 'SETUP FAILED: monitoring_config missing';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname='auto_qa_checks'     AND relkind='r') THEN
    RAISE EXCEPTION 'SETUP FAILED: auto_qa_checks missing';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname='auto_qa_pending'    AND relkind='r') THEN
    RAISE EXCEPTION 'SETUP FAILED: auto_qa_pending missing';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname='auto_qa_log'        AND relkind='r') THEN
    RAISE EXCEPTION 'SETUP FAILED: auto_qa_log missing';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname='fix_chat_sessions'  AND relkind='r') THEN
    RAISE EXCEPTION 'SETUP FAILED: fix_chat_sessions missing';
  END IF;

  -- pg_net 확인
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_net') THEN
    RAISE EXCEPTION 'SETUP FAILED: pg_net extension not installed';
  END IF;

  RAISE NOTICE 'SETUP OK: 3 functions (proconfig=NULL) + 5 tables + roles + service_role EXECUTE + pg_net';
END;
$$;
