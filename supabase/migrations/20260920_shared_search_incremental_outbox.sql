-- =============================================================================
-- 20260920_shared_search_incremental_outbox.sql
-- Shared Search — durable outbox + incremental indexing infrastructure
-- PATCH-2: UNIQUE(event_key), available_at, lease_until, exponential backoff,
--          DEAD after 8 attempts, expired lease reclaim, rowcount completion,
--          fence extra columns, RLS + REVOKE
-- =============================================================================

-- ---------------------------------------------------------------------------
-- search_index_outbox — durable event log for incremental index updates
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.search_index_outbox (
    id              BIGSERIAL PRIMARY KEY,
    domain_name     TEXT        NOT NULL,
    object_type     TEXT        NOT NULL,
    canonical_id    TEXT        NOT NULL,
    event_key       TEXT        NOT NULL,
    reason          TEXT,
    status          TEXT        NOT NULL DEFAULT 'PENDING',
    available_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_until     TIMESTAMPTZ,
    claimed_by      TEXT,
    claimed_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    failed_at       TIMESTAMPTZ,
    failure_reason  TEXT,
    attempt_no      INT         NOT NULL DEFAULT 0,
    worker_id       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT search_index_outbox_event_key_key UNIQUE (event_key)
);

CREATE INDEX IF NOT EXISTS idx_search_index_outbox_status_id
    ON public.search_index_outbox (status, id);

CREATE INDEX IF NOT EXISTS idx_search_index_outbox_domain_canonical
    ON public.search_index_outbox (domain_name, canonical_id);

CREATE INDEX IF NOT EXISTS idx_search_index_outbox_pending_available
    ON public.search_index_outbox (available_at, id)
    WHERE status = 'PENDING';

-- ---------------------------------------------------------------------------
-- search_index_fence — rebuild active flag (fail-closed gate)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.search_index_fence (
    id                  INT         PRIMARY KEY DEFAULT 1,
    rebuild_active      BOOLEAN     NOT NULL DEFAULT FALSE,
    candidate_index     TEXT,
    rebuild_started_at  TIMESTAMPTZ,
    start_event_id      BIGINT      NOT NULL DEFAULT 0,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT search_index_fence_singleton CHECK (id = 1)
);

-- Ensure the singleton row exists
INSERT INTO public.search_index_fence (id, rebuild_active)
VALUES (1, FALSE)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- RPC: enqueue_search_index_sync
-- ON CONFLICT (event_key) DO NOTHING now works via the UNIQUE constraint
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.enqueue_search_index_sync(
    p_domain_name   TEXT,
    p_object_type   TEXT,
    p_canonical_id  TEXT,
    p_event_key     TEXT,
    p_reason        TEXT DEFAULT NULL
) RETURNS BIGINT LANGUAGE plpgsql AS $$
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

-- ---------------------------------------------------------------------------
-- RPC: claim_search_index_events
-- Reclaims expired CLAIMED leases back to PENDING before claiming new batch.
-- Filters by available_at <= NOW() so backoff delays are respected.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.claim_search_index_events(
    p_worker_id  TEXT,
    p_batch_size INT DEFAULT 50,
    p_lease_secs INT DEFAULT 300
) RETURNS SETOF public.search_index_outbox LANGUAGE plpgsql AS $$
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

-- ---------------------------------------------------------------------------
-- RPC: complete_search_index_event
-- Returns TRUE on success (rowcount-checked), FALSE if fence is active
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.complete_search_index_event(
    p_event_id   BIGINT,
    p_worker_id  TEXT
) RETURNS BOOLEAN LANGUAGE plpgsql AS $$
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

-- ---------------------------------------------------------------------------
-- RPC: fail_search_index_event
-- Exponential backoff retry (PENDING) up to p_max_attempts; DEAD after that.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.fail_search_index_event(
    p_event_id     BIGINT,
    p_reason       TEXT,
    p_max_attempts INT DEFAULT 8
) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_attempt INT;
    v_delay_s  INT;
BEGIN
    SELECT attempt_no INTO v_attempt FROM public.search_index_outbox WHERE id = p_event_id;

    IF COALESCE(v_attempt, 0) >= p_max_attempts THEN
        UPDATE public.search_index_outbox
        SET status = 'DEAD', failed_at = NOW(), failure_reason = p_reason, updated_at = NOW()
        WHERE id = p_event_id;
    ELSE
        v_delay_s := LEAST(3600, (2 ^ COALESCE(v_attempt, 0))::INT);
        UPDATE public.search_index_outbox
        SET
            status         = 'PENDING',
            available_at   = NOW() + (v_delay_s || ' seconds')::INTERVAL,
            failure_reason = p_reason,
            failed_at      = NOW(),
            updated_at     = NOW()
        WHERE id = p_event_id;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- RPC: requeue_search_index_event (unchanged)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.requeue_search_index_event(
    p_event_id  BIGINT,
    p_reason    TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE public.search_index_outbox
    SET
        status         = 'PENDING',
        claimed_by     = NULL,
        claimed_at     = NULL,
        worker_id      = NULL,
        failure_reason = p_reason,
        updated_at     = NOW()
    WHERE id = p_event_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- RLS: backend-only access
-- ---------------------------------------------------------------------------

ALTER TABLE public.search_index_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.search_index_fence  ENABLE ROW LEVEL SECURITY;

CREATE POLICY search_index_outbox_service_role ON public.search_index_outbox
    TO service_role USING (true) WITH CHECK (true);
CREATE POLICY search_index_fence_service_role ON public.search_index_fence
    TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON public.search_index_outbox FROM anon, authenticated;
REVOKE ALL ON public.search_index_fence  FROM anon, authenticated;
GRANT  ALL ON public.search_index_outbox TO service_role;
GRANT  ALL ON public.search_index_fence  TO service_role;
GRANT  USAGE, SELECT ON SEQUENCE public.search_index_outbox_id_seq TO service_role;

-- ---------------------------------------------------------------------------
-- Incremental indexing scheduler jobs (INACTIVE — activation is separate)
-- ---------------------------------------------------------------------------

INSERT INTO public.cron_job_master
    (job_code, job_name, cron_expression, is_active, endpoint_url, http_method,
     category, schedule_desc, timeout_seconds, is_system)
VALUES
    ('shared_search_incremental',
     '공유검색 증분색인 (outbox drain)',
     '* * * * *',
     false,
     'direct://shared_search_incremental',
     'DIRECT',
     'SEARCH',
     '매분 outbox 처리 (비활성)',
     120,
     true),
    ('shared_search_reconcile',
     '공유검색 조정 (SoT ↔ OpenSearch)',
     '0 3 * * *',
     false,
     'direct://shared_search_reconcile',
     'DIRECT',
     'SEARCH',
     '매일 03:00 정합성 검증 (비활성)',
     600,
     true)
ON CONFLICT (job_code) DO NOTHING;

INSERT INTO public.cron_schedule_config (job_id, job_code, cron_expression, is_enabled)
SELECT m.id, m.job_code, m.cron_expression, m.is_active
FROM public.cron_job_master m
WHERE m.job_code IN ('shared_search_incremental', 'shared_search_reconcile')
  AND NOT EXISTS (
    SELECT 1 FROM public.cron_schedule_config c WHERE c.job_code = m.job_code
  );
