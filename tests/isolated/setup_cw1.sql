-- WO-TAI-SEC-SEARCHPATH-REM97-CW1-C3-SOURCE-001
-- C-W1 격리 환경 설정: search_index_outbox + search_index_fence + 역할 + 5개 함수
-- Run BEFORE run_cw1_regression.sql

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

-- ─── search_index_outbox ─────────────────────────────────────────────────────
CREATE TABLE public.search_index_outbox (
  id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  domain_name    TEXT        NOT NULL,
  object_type    TEXT        NOT NULL,
  canonical_id   TEXT        NOT NULL,
  event_key      TEXT        NOT NULL UNIQUE,
  reason         TEXT,
  status         TEXT        NOT NULL DEFAULT 'PENDING',
  available_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  lease_until    TIMESTAMPTZ,
  claimed_by     TEXT,
  claimed_at     TIMESTAMPTZ,
  completed_at   TIMESTAMPTZ,
  failed_at      TIMESTAMPTZ,
  failure_reason TEXT,
  attempt_no     INT         NOT NULL DEFAULT 0,
  worker_id      TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── search_index_fence ──────────────────────────────────────────────────────
CREATE TABLE public.search_index_fence (
  id                 INT         PRIMARY KEY,
  rebuild_active     BOOLEAN     NOT NULL DEFAULT FALSE,
  candidate_index    TEXT,
  rebuild_started_at TIMESTAMPTZ,
  start_event_id     BIGINT      NOT NULL DEFAULT 0,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- complete_search_index_event가 SELECT ... WHERE id = 1로 조회
INSERT INTO public.search_index_fence (id, rebuild_active, start_event_id, updated_at)
VALUES (1, FALSE, 0, NOW());

-- ─── 5개 함수 생성 (proconfig=NULL — 운영 기준선 재현) ───────────────────────
-- prosrc는 운영 DB에서 직접 추출한 값과 동일하게 유지

CREATE OR REPLACE FUNCTION public.enqueue_search_index_sync(
  p_domain_name text,
  p_object_type text,
  p_canonical_id text,
  p_event_key text,
  p_reason text
)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
DECLARE v_id BIGINT;
BEGIN
    INSERT INTO public.search_index_outbox
        (domain_name, object_type, canonical_id, event_key, reason,
         status, available_at, created_at, updated_at)
    VALUES
        (p_domain_name, p_object_type, p_canonical_id, p_event_key, p_reason,
         'PENDING', NOW(), NOW(), NOW())
    ON CONFLICT (event_key) DO NOTHING
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.claim_search_index_events(
  p_worker_id text,
  p_batch_size integer,
  p_lease_secs integer
)
RETURNS SETOF public.search_index_outbox
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
BEGIN
    -- Reclaim expired leases back to PENDING
    UPDATE public.search_index_outbox
    SET status = 'PENDING', claimed_by = NULL, claimed_at = NULL,
        lease_until = NULL, worker_id = NULL, updated_at = NOW()
    WHERE status = 'CLAIMED'
      AND lease_until IS NOT NULL
      AND lease_until < NOW();

    RETURN QUERY
    UPDATE public.search_index_outbox
    SET
        status      = 'CLAIMED',
        claimed_by  = p_worker_id,
        claimed_at  = NOW(),
        lease_until = NOW() + (p_lease_secs || ' seconds')::INTERVAL,
        attempt_no  = attempt_no + 1,
        worker_id   = p_worker_id,
        updated_at  = NOW()
    WHERE id IN (
        SELECT id FROM public.search_index_outbox
        WHERE status = 'PENDING' AND available_at <= NOW()
        ORDER BY id LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$;

CREATE OR REPLACE FUNCTION public.complete_search_index_event(
  p_event_id bigint,
  p_worker_id text
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
DECLARE
    v_fence   BOOLEAN;
    v_rowcount INT;
BEGIN
    SELECT rebuild_active INTO v_fence FROM public.search_index_fence WHERE id = 1;
    IF v_fence IS TRUE THEN RETURN FALSE; END IF;

    UPDATE public.search_index_outbox
    SET status = 'COMPLETED', completed_at = NOW(), updated_at = NOW()
    WHERE id = p_event_id AND worker_id = p_worker_id AND status = 'CLAIMED';

    GET DIAGNOSTICS v_rowcount = ROW_COUNT;
    RETURN v_rowcount > 0;
END;
$$;

CREATE OR REPLACE FUNCTION public.fail_search_index_event(
  p_event_id bigint,
  p_reason text,
  p_worker_id text,
  p_attempt_no integer,
  p_max_attempts integer
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
DECLARE
    v_attempt INT;
    v_delay_s  INT;
BEGIN
    SELECT attempt_no INTO v_attempt
    FROM public.search_index_outbox
    WHERE id = p_event_id AND worker_id = p_worker_id AND attempt_no = p_attempt_no;

    IF NOT FOUND THEN
        RETURN; -- stale worker; row owned by another attempt
    END IF;

    IF COALESCE(v_attempt, 0) >= p_max_attempts THEN
        UPDATE public.search_index_outbox
        SET status = 'DEAD', failed_at = NOW(), failure_reason = p_reason, updated_at = NOW()
        WHERE id = p_event_id AND worker_id = p_worker_id AND attempt_no = p_attempt_no;
    ELSE
        v_delay_s := LEAST(3600, (2 ^ COALESCE(v_attempt, 0))::INT);
        UPDATE public.search_index_outbox
        SET
            status         = 'PENDING',
            available_at   = NOW() + (v_delay_s || ' seconds')::INTERVAL,
            failure_reason = p_reason,
            failed_at      = NOW(),
            updated_at     = NOW()
        WHERE id = p_event_id AND worker_id = p_worker_id AND attempt_no = p_attempt_no;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.requeue_search_index_event(
  p_event_id bigint,
  p_worker_id text,
  p_attempt_no integer,
  p_reason text
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
BEGIN
    UPDATE public.search_index_outbox
    SET
        status         = 'PENDING',
        claimed_by     = NULL,
        claimed_at     = NULL,
        lease_until    = NULL,
        worker_id      = NULL,
        failure_reason = p_reason,
        available_at   = NOW(),
        updated_at     = NOW()
    WHERE id = p_event_id
      AND worker_id   = p_worker_id
      AND attempt_no  = p_attempt_no;
END;
$$;

-- ─── 권한 부여 ───────────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON public.search_index_outbox TO anon, authenticated, service_role;
GRANT SELECT ON public.search_index_fence TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.enqueue_search_index_sync(text,text,text,text,text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.claim_search_index_events(text,integer,integer) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.complete_search_index_event(bigint,text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.fail_search_index_event(bigint,text,text,integer,integer) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.requeue_search_index_event(bigint,text,integer,text) TO anon, authenticated, service_role;

-- ─── 설정 검증 ────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_fn_count  int;
  v_bad_count int;
BEGIN
  SELECT COUNT(*) INTO v_fn_count
  FROM pg_proc
  WHERE proname IN (
    'enqueue_search_index_sync', 'claim_search_index_events',
    'complete_search_index_event', 'fail_search_index_event',
    'requeue_search_index_event'
  );
  IF v_fn_count IS DISTINCT FROM 5 THEN
    RAISE EXCEPTION 'SETUP FAILED: expected 5 functions, found %', v_fn_count;
  END IF;

  SELECT COUNT(*) INTO v_bad_count
  FROM pg_proc
  WHERE proname IN (
    'enqueue_search_index_sync', 'claim_search_index_events',
    'complete_search_index_event', 'fail_search_index_event',
    'requeue_search_index_event'
  ) AND proconfig IS NOT NULL;
  IF v_bad_count > 0 THEN
    RAISE EXCEPTION 'SETUP FAILED: % functions already have proconfig set', v_bad_count;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM public.search_index_fence WHERE id = 1 AND rebuild_active = FALSE) THEN
    RAISE EXCEPTION 'SETUP FAILED: search_index_fence row id=1 missing or rebuild_active not FALSE';
  END IF;

  RAISE NOTICE 'SETUP OK: 5 functions (proconfig=NULL) + tables + roles + fence row';
END;
$$;
