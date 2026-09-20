-- =============================================================================
-- 20260920_shared_search_incremental_outbox.sql
-- Shared Search — durable outbox + incremental indexing infrastructure
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
    claimed_by      TEXT,
    claimed_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    failed_at       TIMESTAMPTZ,
    failure_reason  TEXT,
    attempt_no      INT         NOT NULL DEFAULT 0,
    worker_id       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_search_index_outbox_status_id
    ON public.search_index_outbox (status, id);

CREATE INDEX IF NOT EXISTS idx_search_index_outbox_domain_canonical
    ON public.search_index_outbox (domain_name, canonical_id);

-- ---------------------------------------------------------------------------
-- search_index_fence — rebuild active flag (fail-closed gate)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.search_index_fence (
    id              INT PRIMARY KEY DEFAULT 1,
    rebuild_active  BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT search_index_fence_singleton CHECK (id = 1)
);

-- Ensure the singleton row exists
INSERT INTO public.search_index_fence (id, rebuild_active)
VALUES (1, FALSE)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- RPC: enqueue_search_index_sync
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.enqueue_search_index_sync(
    p_domain_name   TEXT,
    p_object_type   TEXT,
    p_canonical_id  TEXT,
    p_event_key     TEXT,
    p_reason        TEXT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    INSERT INTO public.search_index_outbox
        (domain_name, object_type, canonical_id, event_key, reason, status, created_at, updated_at)
    VALUES
        (p_domain_name, p_object_type, p_canonical_id, p_event_key, p_reason, 'PENDING', NOW(), NOW())
    ON CONFLICT DO NOTHING
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- RPC: claim_search_index_events
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.claim_search_index_events(
    p_worker_id  TEXT,
    p_batch_size INT DEFAULT 50
)
RETURNS SETOF public.search_index_outbox
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.search_index_outbox
    SET
        status     = 'CLAIMED',
        claimed_by = p_worker_id,
        claimed_at = NOW(),
        attempt_no = attempt_no + 1,
        worker_id  = p_worker_id,
        updated_at = NOW()
    WHERE id IN (
        SELECT id
        FROM public.search_index_outbox
        WHERE status = 'PENDING'
        ORDER BY id
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$;

-- ---------------------------------------------------------------------------
-- RPC: complete_search_index_event
-- Returns TRUE on success, FALSE if fence is active (fail-closed)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.complete_search_index_event(
    p_event_id   BIGINT,
    p_worker_id  TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_fence BOOLEAN;
BEGIN
    SELECT rebuild_active INTO v_fence FROM public.search_index_fence WHERE id = 1;
    IF v_fence IS TRUE THEN
        RETURN FALSE;
    END IF;

    UPDATE public.search_index_outbox
    SET
        status       = 'COMPLETED',
        completed_at = NOW(),
        updated_at   = NOW()
    WHERE id = p_event_id
      AND worker_id = p_worker_id
      AND status = 'CLAIMED';

    RETURN TRUE;
END;
$$;

-- ---------------------------------------------------------------------------
-- RPC: fail_search_index_event
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.fail_search_index_event(
    p_event_id  BIGINT,
    p_reason    TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE public.search_index_outbox
    SET
        status         = 'FAILED',
        failed_at      = NOW(),
        failure_reason = p_reason,
        updated_at     = NOW()
    WHERE id = p_event_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- RPC: requeue_search_index_event
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
