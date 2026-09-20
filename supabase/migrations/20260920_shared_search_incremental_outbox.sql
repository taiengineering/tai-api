-- WO-TAI-SHARED-SEARCH-INCREMENTAL-001
-- Durable outbox + runtime state for incremental OpenSearch indexing.
--
-- §7  search_index_outbox        — SYNC_OBJECT event queue
-- §9  id bigint identity         — monotonic, watermark authority
-- §12 claim_search_index_events  — atomic FOR UPDATE SKIP LOCKED
-- §13 complete_search_index_event — fenced completion
-- §39 search_index_runtime_state — rebuild fence singleton
--
-- Idempotent.

-- ---------------------------------------------------------------------------
-- search_index_outbox
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS search_index_outbox (
    id              bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    event_type      text    NOT NULL DEFAULT 'SYNC_OBJECT'
                            CHECK (event_type = 'SYNC_OBJECT'),

    domain_name     text    NOT NULL,
    object_type     text    NOT NULL,
    canonical_id    text    NOT NULL,

    source_event_key text   UNIQUE,          -- idempotency key; NULL = no dedup
    reason          text,

    status          text    NOT NULL DEFAULT 'PENDING'
                            CHECK (status IN ('PENDING','PROCESSING','DONE','DEAD')),

    attempt_no      integer NOT NULL DEFAULT 0,

    available_at    timestamptz NOT NULL DEFAULT now(),
    lease_until     timestamptz,
    worker_id       text,

    last_error      text,

    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    processed_at    timestamptz
);

-- Processing index: PENDING events available now (hot path)
CREATE INDEX IF NOT EXISTS sio_pending_available
    ON search_index_outbox (available_at)
    WHERE status = 'PENDING';

-- Lease expiry reclaim: stale PROCESSING events
CREATE INDEX IF NOT EXISTS sio_processing_lease
    ON search_index_outbox (lease_until)
    WHERE status = 'PROCESSING';

-- Retention queries
CREATE INDEX IF NOT EXISTS sio_status_processed
    ON search_index_outbox (status, processed_at);

-- ---------------------------------------------------------------------------
-- search_index_runtime_state  (singleton: id = 1 enforced)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS search_index_runtime_state (
    id                  integer     PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    rebuild_active      boolean     NOT NULL DEFAULT false,
    candidate_index     text,
    rebuild_started_at  timestamptz,
    start_event_id      bigint,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Seed the singleton row
INSERT INTO search_index_runtime_state (id) VALUES (1)
    ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- enqueue_search_index_sync
-- §10 common enqueue function — never INSERT directly from callers
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION enqueue_search_index_sync(
    p_domain_name   text,
    p_object_type   text,
    p_canonical_id  text,
    p_event_key     text    DEFAULT NULL,
    p_reason        text    DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_id bigint;
BEGIN
    INSERT INTO search_index_outbox
        (domain_name, object_type, canonical_id, source_event_key, reason)
    VALUES
        (p_domain_name, p_object_type, p_canonical_id, p_event_key, p_reason)
    ON CONFLICT (source_event_key) DO NOTHING
    RETURNING id INTO v_id;

    -- If source_event_key already existed the insert was skipped; return NULL.
    RETURN v_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- claim_search_index_events
-- §12 atomic claim via FOR UPDATE SKIP LOCKED
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION claim_search_index_events(
    p_limit         integer,
    p_worker_id     text,
    p_lease_seconds integer DEFAULT 120
) RETURNS SETOF search_index_outbox
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE search_index_outbox
    SET
        status      = 'PROCESSING',
        attempt_no  = attempt_no + 1,
        worker_id   = p_worker_id,
        lease_until = now() + (p_lease_seconds || ' seconds')::interval,
        updated_at  = now()
    WHERE id IN (
        SELECT id
        FROM search_index_outbox
        WHERE
            -- PENDING events whose delay has elapsed
            (status = 'PENDING' AND available_at <= now())
            OR
            -- PROCESSING events with expired lease (stale worker)
            (status = 'PROCESSING' AND lease_until < now())
        ORDER BY id ASC
        LIMIT p_limit
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$;

-- ---------------------------------------------------------------------------
-- complete_search_index_event
-- §13 fenced completion — worker_id + attempt_no must match
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION complete_search_index_event(
    p_event_id  bigint,
    p_worker_id text,
    p_attempt   integer
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_updated integer;
BEGIN
    UPDATE search_index_outbox
    SET
        status       = 'DONE',
        processed_at = now(),
        updated_at   = now(),
        last_error   = NULL
    WHERE
        id         = p_event_id
        AND status = 'PROCESSING'
        AND worker_id  = p_worker_id
        AND attempt_no = p_attempt;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated > 0;
END;
$$;

-- ---------------------------------------------------------------------------
-- fail_search_index_event
-- Mark event PENDING (retry) or DEAD after max attempts
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION fail_search_index_event(
    p_event_id      bigint,
    p_worker_id     text,
    p_attempt       integer,
    p_error         text,
    p_max_attempts  integer DEFAULT 8,
    p_backoff_secs  integer DEFAULT NULL
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_next_status text;
    v_delay       interval;
    v_updated     integer;
BEGIN
    IF p_attempt >= p_max_attempts THEN
        v_next_status := 'DEAD';
        v_delay       := '0 seconds'::interval;
    ELSE
        v_next_status := 'PENDING';
        -- Exponential back-off: 60s, 120s, 300s, 600s, 1800s, 3600s, 7200s
        v_delay := CASE p_attempt
            WHEN 1 THEN '60 seconds'::interval
            WHEN 2 THEN '120 seconds'::interval
            WHEN 3 THEN '300 seconds'::interval
            WHEN 4 THEN '600 seconds'::interval
            WHEN 5 THEN '1800 seconds'::interval
            WHEN 6 THEN '3600 seconds'::interval
            ELSE         '7200 seconds'::interval
        END;
        IF p_backoff_secs IS NOT NULL THEN
            v_delay := (p_backoff_secs || ' seconds')::interval;
        END IF;
    END IF;

    UPDATE search_index_outbox
    SET
        status       = v_next_status,
        last_error   = left(p_error, 1000),
        available_at = CASE WHEN v_next_status = 'PENDING'
                           THEN now() + v_delay
                           ELSE available_at END,
        lease_until  = NULL,
        worker_id    = NULL,
        updated_at   = now()
    WHERE
        id         = p_event_id
        AND status = 'PROCESSING'
        AND worker_id  = p_worker_id
        AND attempt_no = p_attempt;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN CASE WHEN v_updated > 0 THEN v_next_status ELSE 'FENCED' END;
END;
$$;

-- ---------------------------------------------------------------------------
-- RLS / access control
-- §8: service-role only — never expose to anonymous/client
-- ---------------------------------------------------------------------------

ALTER TABLE search_index_outbox       ENABLE ROW LEVEL SECURITY;
ALTER TABLE search_index_runtime_state ENABLE ROW LEVEL SECURITY;

-- No permissive policies → anon/client cannot access.
-- service_role bypasses RLS by default in Supabase.
