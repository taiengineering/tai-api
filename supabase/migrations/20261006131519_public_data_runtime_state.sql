-- WO-PUBLIC-DATA-SYNC-WP1B-RUNTIME-STATE-001
-- PATCH: WO-PUBLIC-DATA-SYNC-WP1B-PATCH-RUNTIME-CORRECTNESS-001
-- Public Data Control Plane — runtime state + run evidence + atomic claim RPCs
-- Production DDL: NOT applied here. Apply via: supabase db push --linked

-- =============================================================================
-- TABLE: public_data_source_runtime
-- Mutable operational state only. Static metadata SoT = registry.py
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.public_data_source_runtime (
    source_id               text        PRIMARY KEY,

    is_enabled              boolean     NOT NULL DEFAULT false,

    cadence_seconds         integer,
    next_due_at             timestamptz,
    retry_not_before        timestamptz,

    current_run_id          uuid,
    last_run_id             uuid,
    last_status             text        CHECK (last_status IN (
                                            'RUNNING','SUCCESS','NO_CHANGE',
                                            'PARTIAL','FAILED','SKIPPED')),

    last_started_at         timestamptz,
    last_finished_at        timestamptz,

    consecutive_failures    integer     NOT NULL DEFAULT 0,

    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.public_data_source_runtime ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.public_data_source_runtime IS
    'WP-1B runtime operational state for public-data sources. Static metadata SoT = services/public_data_sync/registry.py';

-- =============================================================================
-- TABLE: public_data_sync_runs
-- Run evidence. FK -> source_runtime RESTRICT (evidence preserved on source remove).
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.public_data_sync_runs (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    source_id           text        NOT NULL
                                    REFERENCES public.public_data_source_runtime(source_id)
                                    ON DELETE RESTRICT,

    trigger             text        NOT NULL
                                    CHECK (trigger IN ('SCHEDULED','MANUAL','RETRY')),

    status              text        NOT NULL
                                    CHECK (status IN (
                                        'RUNNING','SUCCESS','NO_CHANGE',
                                        'PARTIAL','FAILED','SKIPPED')),

    attempt_no          integer     NOT NULL DEFAULT 1,

    credential_pool     text        NOT NULL,
    rate_limit_group    text        NOT NULL,

    source_slot         integer     NOT NULL,
    credential_slot     integer     NOT NULL,
    rate_limit_slot     integer     NOT NULL,

    scheduled_for       timestamptz,

    started_at          timestamptz NOT NULL,
    heartbeat_at        timestamptz NOT NULL,
    lease_until         timestamptz NOT NULL,
    finished_at         timestamptz,

    fetched             integer     NOT NULL DEFAULT 0,
    created_count       integer     NOT NULL DEFAULT 0,
    changed_count       integer     NOT NULL DEFAULT 0,
    unchanged_count     integer     NOT NULL DEFAULT 0,
    removed_count       integer     NOT NULL DEFAULT 0,
    failed_count        integer     NOT NULL DEFAULT 0,

    source_version      text,
    content_hash        text,
    change_detected     boolean     NOT NULL DEFAULT false,

    error_code          text,
    error_message       text,
    details             jsonb,

    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.public_data_sync_runs ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.public_data_sync_runs IS
    'WP-1B Control Plane run evidence. Domain-level run tables (KECO etc.) are separate.';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_pdsr_source_status
    ON public.public_data_sync_runs (source_id, status);

CREATE INDEX IF NOT EXISTS idx_pdsr_started
    ON public.public_data_sync_runs (started_at DESC);

-- Partial unique indexes: slot-based concurrency (DB-level race guard)
CREATE UNIQUE INDEX IF NOT EXISTS udx_pdsr_source_slot_running
    ON public.public_data_sync_runs (source_id, source_slot)
    WHERE status = 'RUNNING';

CREATE UNIQUE INDEX IF NOT EXISTS udx_pdsr_credential_slot_running
    ON public.public_data_sync_runs (credential_pool, credential_slot)
    WHERE status = 'RUNNING';

CREATE UNIQUE INDEX IF NOT EXISTS udx_pdsr_ratelimit_slot_running
    ON public.public_data_sync_runs (rate_limit_group, rate_limit_slot)
    WHERE status = 'RUNNING';

-- =============================================================================
-- TABLE GRANTS
-- =============================================================================

REVOKE ALL ON TABLE public.public_data_source_runtime  FROM anon, authenticated;
REVOKE ALL ON TABLE public.public_data_sync_runs       FROM anon, authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.public_data_source_runtime  TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.public_data_sync_runs       TO service_role;

-- =============================================================================
-- RPC: fn_public_data_claim_run
-- PATCH changes vs original:
--   1. Source limit guard: p_source_limit != 1 → SOURCE_LIMIT_UNSUPPORTED
--   2. Stale recovery expanded: credential_pool + rate_limit_group scope added
--   3. Stale reflect: p_source_id runtime cleared when its current_run was staled
--   4. EXCEPTION: GET STACKED DIAGNOSTICS → accurate CREDENTIAL_BUSY / RATE_LIMIT_BUSY
-- =============================================================================

CREATE OR REPLACE FUNCTION public.fn_public_data_claim_run(
    p_run_id            uuid,
    p_source_id         text,
    p_trigger           text,
    p_scheduled_for     timestamptz,
    p_now               timestamptz,
    p_lease_seconds     integer,
    p_credential_pool   text,
    p_rate_limit_group  text,
    p_source_limit      integer,
    p_credential_limit  integer,
    p_rate_limit_limit  integer
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_runtime       record;
    v_stale_id      uuid;
    v_source_slot   integer;
    v_cred_slot     integer;
    v_rl_slot       integer;
    v_lease_until   timestamptz;
    v_constraint    text;
BEGIN
    SELECT * INTO v_runtime
    FROM public.public_data_source_runtime
    WHERE source_id = p_source_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'claimed', false, 'run_id', p_run_id, 'reason', 'UNKNOWN_SOURCE_RUNTIME');
    END IF;

    -- Source concurrency guard: only source_limit = 1 is supported.
    -- Concurrency > 1 requires multi-run source_runtime state (separate WP).
    IF p_source_limit IS NULL OR p_source_limit < 1 OR p_source_limit > 1 THEN
        RETURN jsonb_build_object(
            'claimed', false, 'run_id', p_run_id, 'reason', 'SOURCE_LIMIT_UNSUPPORTED');
    END IF;

    IF p_trigger = 'SCHEDULED' THEN
        IF NOT v_runtime.is_enabled THEN
            RETURN jsonb_build_object(
                'claimed', false, 'run_id', p_run_id, 'reason', 'DISABLED');
        END IF;
        IF v_runtime.next_due_at IS NULL OR v_runtime.next_due_at > p_now THEN
            RETURN jsonb_build_object(
                'claimed', false, 'run_id', p_run_id, 'reason', 'NOT_DUE');
        END IF;
        IF v_runtime.retry_not_before IS NOT NULL
           AND v_runtime.retry_not_before > p_now THEN
            RETURN jsonb_build_object(
                'claimed', false, 'run_id', p_run_id, 'reason', 'RETRY_NOT_BEFORE');
        END IF;
    END IF;

    -- Stale recovery: expanded scope — p_source_id + shared credential_pool + rate_limit_group.
    -- Unblocks slots occupied by crashed/expired runs across all shared resources so that
    -- a source sharing credential_pool or rate_limit_group is not permanently blocked by
    -- another source's stale RUNNING row.
    UPDATE public.public_data_sync_runs
    SET status      = 'FAILED',
        error_code  = 'LEASE_EXPIRED',
        finished_at = p_now
    WHERE status      = 'RUNNING'
      AND lease_until <= p_now
      AND (
          source_id        = p_source_id
          OR credential_pool   = p_credential_pool
          OR rate_limit_group  = p_rate_limit_group
      );

    -- Reflect stale recovery in p_source_id runtime (we hold FOR UPDATE lock on this row).
    -- Only update if p_source_id's current_run_id was the run just staled.
    -- Other sources' runtimes self-heal on their next claim; touching them here
    -- would risk deadlock with concurrent claims on those sources.
    IF v_runtime.current_run_id IS NOT NULL THEN
        SELECT id INTO v_stale_id
        FROM public.public_data_sync_runs
        WHERE id         = v_runtime.current_run_id
          AND status     = 'FAILED'
          AND error_code = 'LEASE_EXPIRED';

        IF FOUND THEN
            UPDATE public.public_data_source_runtime
            SET current_run_id   = NULL,
                last_run_id      = v_stale_id,
                last_status      = 'FAILED',
                last_finished_at = p_now,
                updated_at       = p_now
            WHERE source_id = p_source_id;
        END IF;
    END IF;

    -- Source slot
    SELECT MIN(s) INTO v_source_slot
    FROM generate_series(1, p_source_limit) s
    WHERE NOT EXISTS (
        SELECT 1 FROM public.public_data_sync_runs r
        WHERE r.source_id   = p_source_id
          AND r.source_slot = s
          AND r.status      = 'RUNNING'
    );
    IF v_source_slot IS NULL THEN
        RETURN jsonb_build_object(
            'claimed', false, 'run_id', p_run_id, 'reason', 'SOURCE_BUSY');
    END IF;

    -- Credential slot
    SELECT MIN(s) INTO v_cred_slot
    FROM generate_series(1, p_credential_limit) s
    WHERE NOT EXISTS (
        SELECT 1 FROM public.public_data_sync_runs r
        WHERE r.credential_pool = p_credential_pool
          AND r.credential_slot = s
          AND r.status          = 'RUNNING'
    );
    IF v_cred_slot IS NULL THEN
        RETURN jsonb_build_object(
            'claimed', false, 'run_id', p_run_id, 'reason', 'CREDENTIAL_BUSY');
    END IF;

    -- Rate-limit slot
    SELECT MIN(s) INTO v_rl_slot
    FROM generate_series(1, p_rate_limit_limit) s
    WHERE NOT EXISTS (
        SELECT 1 FROM public.public_data_sync_runs r
        WHERE r.rate_limit_group = p_rate_limit_group
          AND r.rate_limit_slot  = s
          AND r.status           = 'RUNNING'
    );
    IF v_rl_slot IS NULL THEN
        RETURN jsonb_build_object(
            'claimed', false, 'run_id', p_run_id, 'reason', 'RATE_LIMIT_BUSY');
    END IF;

    v_lease_until := p_now + (p_lease_seconds * interval '1 second');

    INSERT INTO public.public_data_sync_runs (
        id, source_id, trigger, status,
        credential_pool, rate_limit_group,
        source_slot, credential_slot, rate_limit_slot,
        scheduled_for, started_at, heartbeat_at, lease_until, created_at
    ) VALUES (
        p_run_id, p_source_id, p_trigger, 'RUNNING',
        p_credential_pool, p_rate_limit_group,
        v_source_slot, v_cred_slot, v_rl_slot,
        p_scheduled_for, p_now, p_now, v_lease_until, p_now
    );

    UPDATE public.public_data_source_runtime
    SET current_run_id  = p_run_id,
        last_started_at = p_now,
        updated_at      = p_now
    WHERE source_id = p_source_id;

    RETURN jsonb_build_object(
        'claimed',         true,
        'run_id',          p_run_id,
        'reason',          'CLAIMED',
        'lease_until',     v_lease_until,
        'source_slot',     v_source_slot,
        'credential_slot', v_cred_slot,
        'rate_limit_slot', v_rl_slot
    );

EXCEPTION WHEN unique_violation THEN
    -- Identify which constraint was violated to return accurate reason.
    GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
    IF v_constraint = 'udx_pdsr_source_slot_running' THEN
        RETURN jsonb_build_object(
            'claimed', false, 'run_id', p_run_id, 'reason', 'SOURCE_BUSY');
    ELSIF v_constraint = 'udx_pdsr_credential_slot_running' THEN
        RETURN jsonb_build_object(
            'claimed', false, 'run_id', p_run_id, 'reason', 'CREDENTIAL_BUSY');
    ELSIF v_constraint = 'udx_pdsr_ratelimit_slot_running' THEN
        RETURN jsonb_build_object(
            'claimed', false, 'run_id', p_run_id, 'reason', 'RATE_LIMIT_BUSY');
    ELSIF v_constraint = 'public_data_sync_runs_pkey' THEN
        RETURN jsonb_build_object(
            'claimed', false, 'run_id', p_run_id, 'reason', 'RUN_ID_CONFLICT');
    ELSE
        RETURN jsonb_build_object(
            'claimed', false, 'run_id', p_run_id, 'reason', 'UNIQUE_CONFLICT');
    END IF;
END;
$fn$;

REVOKE ALL ON FUNCTION public.fn_public_data_claim_run(
    uuid, text, text, timestamptz, timestamptz, integer,
    text, text, integer, integer, integer
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_public_data_claim_run(
    uuid, text, text, timestamptz, timestamptz, integer,
    text, text, integer, integer, integer
) TO service_role;

-- =============================================================================
-- RPC: fn_public_data_heartbeat_run
-- PATCH: Added current_run_id fence via EXISTS on source_runtime.
-- Prevents a stale/recovered run from refreshing its own lease.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.fn_public_data_heartbeat_run(
    p_run_id        uuid,
    p_now           timestamptz,
    p_lease_seconds integer
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_count integer;
BEGIN
    UPDATE public.public_data_sync_runs r
    SET heartbeat_at = p_now,
        lease_until  = p_now + (p_lease_seconds * interval '1 second')
    WHERE r.id     = p_run_id
      AND r.status = 'RUNNING'
      AND EXISTS (
          SELECT 1 FROM public.public_data_source_runtime rt
          WHERE rt.source_id      = r.source_id
            AND rt.current_run_id = p_run_id
      );

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count > 0;
END;
$fn$;

REVOKE ALL ON FUNCTION public.fn_public_data_heartbeat_run(uuid, timestamptz, integer)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_public_data_heartbeat_run(uuid, timestamptz, integer)
    TO service_role;

-- =============================================================================
-- RPC: fn_public_data_complete_run
-- PATCH: Added current_run_id fence — SELECT FOR UPDATE on source_runtime
-- WHERE current_run_id = p_run_id. Returns false if source_runtime no longer
-- points to this run (stale recovery or racing completion took over).
-- =============================================================================

CREATE OR REPLACE FUNCTION public.fn_public_data_complete_run(
    p_run_id            uuid,
    p_status            text,
    p_finished_at       timestamptz,
    p_fetched           integer,
    p_created           integer,
    p_changed           integer,
    p_unchanged         integer,
    p_removed           integer,
    p_failed            integer,
    p_source_version    text,
    p_content_hash      text,
    p_change_detected   boolean,
    p_error_code        text,
    p_error_message     text,
    p_details           jsonb,
    p_next_due_at       timestamptz,
    p_retry_not_before  timestamptz
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_run   record;
    v_rt    record;
BEGIN
    SELECT * INTO v_run
    FROM public.public_data_sync_runs
    WHERE id     = p_run_id
      AND status = 'RUNNING'
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN false;
    END IF;

    -- Concurrency fence: source_runtime must still point to this run.
    -- With source_limit=1 enforced, if current_run_id != p_run_id, a stale
    -- recovery or a racing completion already updated source state — do not
    -- overwrite it.
    SELECT * INTO v_rt
    FROM public.public_data_source_runtime
    WHERE source_id      = v_run.source_id
      AND current_run_id = p_run_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN false;
    END IF;

    UPDATE public.public_data_sync_runs
    SET status          = p_status,
        finished_at     = p_finished_at,
        fetched         = p_fetched,
        created_count   = p_created,
        changed_count   = p_changed,
        unchanged_count = p_unchanged,
        removed_count   = p_removed,
        failed_count    = p_failed,
        source_version  = p_source_version,
        content_hash    = p_content_hash,
        change_detected = p_change_detected,
        error_code      = p_error_code,
        error_message   = p_error_message,
        details         = p_details
    WHERE id = p_run_id;

    -- current_run_id = p_run_id is guaranteed by the fence above.
    UPDATE public.public_data_source_runtime
    SET current_run_id   = NULL,
        last_run_id      = p_run_id,
        last_status      = p_status,
        last_finished_at = p_finished_at,
        next_due_at      = p_next_due_at,
        retry_not_before = CASE
                               WHEN p_status IN ('SUCCESS', 'NO_CHANGE', 'SKIPPED')
                                   THEN NULL
                               ELSE p_retry_not_before
                           END,
        consecutive_failures = CASE
                               WHEN p_status = 'FAILED'
                                   THEN consecutive_failures + 1
                               WHEN p_status IN ('SUCCESS', 'NO_CHANGE', 'SKIPPED')
                                   THEN 0
                               ELSE consecutive_failures
                           END,
        updated_at       = p_finished_at
    WHERE source_id = v_run.source_id;

    RETURN true;
END;
$fn$;

REVOKE ALL ON FUNCTION public.fn_public_data_complete_run(
    uuid, text, timestamptz,
    integer, integer, integer, integer, integer, integer,
    text, text, boolean,
    text, text, jsonb,
    timestamptz, timestamptz
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_public_data_complete_run(
    uuid, text, timestamptz,
    integer, integer, integer, integer, integer, integer,
    text, text, boolean,
    text, text, jsonb,
    timestamptz, timestamptz
) TO service_role;

-- =============================================================================
-- SEED: 12 approved WP-1A sources — all disabled, no schedule
-- LEGAL_TEXT_SYNC and KSIC_SYNC are excluded.
-- =============================================================================

INSERT INTO public.public_data_source_runtime (source_id, is_enabled)
VALUES
    ('KOSHA_SAFETY_MATERIAL',           false),
    ('KOSHA_GUIDE',                     false),
    ('KOSHA_MSDS',                      false),
    ('KECO_15149420',                   false),
    ('KOSHA_ACCIDENT_CASES',            false),
    ('KOSHA_CONSTRUCTION_ACCIDENTS',    false),
    ('KOSHA_CONSTRUCTION_SAFETY_LIGHT', false),
    ('KOSHA_RISK_ASSESSMENT',           false),
    ('CSI_ACCIDENT',                    false),
    ('KCSC',                            false),
    ('INDUSTRIAL_ACCIDENT_PRECEDENT',   false),
    ('HOLIDAY',                         false)
ON CONFLICT (source_id) DO NOTHING;
