-- WO-SEO-NAVER-INDEXNOW-V2-004B: IndexNow Snapshot Diff State
-- RC4: retry_failed fix (no updated_at, attempt_count=0, processing_at=NULL), queue field cleanup,
--      baseline post-verify RPC, preflight order enforced in JS.
-- Production DB apply: NOT YET AUTHORIZED.
--
-- Security: internal schema NOT exposed via PostgREST (public schema only).
--   anon/authenticated have zero access to these tables.
--   All access via public.* RPCs (SECURITY INVOKER, service_role only).
--
-- State contract:
--   Persistent URL states: ACTIVE | MISSING_CANDIDATE | INACTIVE
--   DELETE_READY is a diff classification, NOT a persistent DB state.
--
-- Delivery contract:
--   current_fingerprint        = fingerprint from last scan when URL was present
--   last_submitted_fingerprint = fingerprint of last successfully delivered state (NULL = never)
--   Delivery on: current != last_submitted (or last_submitted IS NULL)
--   last_submitted updated ONLY on Naver HTTP 200/202.
--
-- Queue idempotency (RC3):
--   UNIQUE (url, event_type, target_fingerprint) — full unique, status-independent.
--   FAILED row blocks re-insert; requires explicit recovery via retry_failed RPC.
--
-- Retry scheduling (RC3):
--   attempt 0 fail → RETRY, next_retry_at = +10 min
--   attempt 1 fail → RETRY, next_retry_at = +30 min
--   attempt 2 fail → FAILED (max 3 attempts)
--
-- Stale PROCESSING reclaim threshold: 30 minutes.
--
-- CORR-01: RAISE EXCEPTION (not ASSERT) for all guards.
-- CORR-02: information_schema queries qualify table_schema.
-- CORR-03: No explicit BEGIN/COMMIT — Supabase CLI wraps each migration file.

-- ============================================================
-- STEP 1: PRE-CONDITION GUARDS
-- ============================================================
DO $check_pre$ BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.schemata
    WHERE schema_name = 'internal'
  ) THEN
    RAISE EXCEPTION 'PRE FAIL: schema internal already exists';
  END IF;
END $check_pre$;

-- ============================================================
-- STEP 2: SCHEMA
-- ============================================================
CREATE SCHEMA internal;

REVOKE ALL ON SCHEMA internal FROM PUBLIC;
REVOKE ALL ON SCHEMA internal FROM anon;
REVOKE ALL ON SCHEMA internal FROM authenticated;
GRANT USAGE ON SCHEMA internal TO service_role;

-- ============================================================
-- STEP 3: TABLES
-- ============================================================

CREATE TABLE internal.indexnow_scan_runs (
  id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  scan_started_at         TIMESTAMPTZ NOT NULL,
  scan_completed_at       TIMESTAMPTZ,
  -- Sitemap scan counts
  sitemap_ok_count        INT         NOT NULL DEFAULT 0 CHECK (sitemap_ok_count >= 0),
  sitemap_fail_count      INT         NOT NULL DEFAULT 0 CHECK (sitemap_fail_count >= 0),
  -- URL counts (raw = sum of all sitemap rows; unique = after dedup)
  raw_url_count           INT         NOT NULL DEFAULT 0 CHECK (raw_url_count >= 0),
  unique_url_count        INT         NOT NULL DEFAULT 0 CHECK (unique_url_count >= 0),
  duplicate_count         INT         NOT NULL DEFAULT 0 CHECK (duplicate_count >= 0),
  with_lastmod_count      INT         NOT NULL DEFAULT 0 CHECK (with_lastmod_count >= 0),
  without_lastmod_count   INT         NOT NULL DEFAULT 0 CHECK (without_lastmod_count >= 0),
  -- Diff classification counts
  new_count               INT         NOT NULL DEFAULT 0,
  changed_count           INT         NOT NULL DEFAULT 0,
  unchanged_count         INT         NOT NULL DEFAULT 0,
  missing_candidate_count INT         NOT NULL DEFAULT 0,
  delete_ready_count      INT         NOT NULL DEFAULT 0,
  resurrected_count       INT         NOT NULL DEFAULT 0,
  -- Run status
  is_complete             BOOLEAN     NOT NULL DEFAULT false,
  status                  TEXT        NOT NULL DEFAULT 'RUNNING'
                            CONSTRAINT chk_scan_run_status
                              CHECK (status IN ('RUNNING', 'COMPLETE', 'PARTIAL', 'FAILED')),
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE internal.indexnow_url_state (
  url                         TEXT        PRIMARY KEY,
  -- Public state fingerprint (updated every scan when URL is present)
  current_fingerprint         TEXT        NOT NULL,
  current_lastmod             TEXT        NOT NULL DEFAULT '',
  -- Persistent URL state (DELETE_READY is a diff classification, not stored here)
  state                       TEXT        NOT NULL DEFAULT 'ACTIVE'
                                CONSTRAINT chk_url_state_state
                                  CHECK (state IN ('ACTIVE', 'MISSING_CANDIDATE', 'INACTIVE')),
  missing_streak              INT         NOT NULL DEFAULT 0 CHECK (missing_streak >= 0),
  -- Delivery state (separated from scan state per B04)
  -- NULL = never successfully delivered to Naver
  last_submitted_fingerprint  TEXT,
  last_submitted_at           TIMESTAMPTZ,
  last_http_status            INT,
  -- Lifecycle timestamps
  first_seen_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at                TIMESTAMPTZ,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE internal.indexnow_delivery_queue (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id              UUID        NOT NULL
                        REFERENCES internal.indexnow_scan_runs(id)
                        ON DELETE CASCADE,
  url                 TEXT        NOT NULL,
  event_type          TEXT        NOT NULL
                        CONSTRAINT chk_queue_event_type
                          CHECK (event_type IN ('CREATE', 'UPDATE', 'DELETE', 'RESURRECT')),
  -- Target fingerprint: what we are delivering; on success, becomes last_submitted_fingerprint
  target_fingerprint  TEXT        NOT NULL,
  status              TEXT        NOT NULL DEFAULT 'PENDING'
                        CONSTRAINT chk_queue_status
                          CHECK (status IN ('PENDING', 'PROCESSING', 'DELIVERED', 'RETRY', 'FAILED')),
  attempt_count       INT         NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  next_retry_at       TIMESTAMPTZ,
  last_http_status    INT,
  last_error          TEXT,
  queued_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  processing_at       TIMESTAMPTZ,
  delivered_at        TIMESTAMPTZ
);

-- ============================================================
-- STEP 4: INDEXES
-- ============================================================
CREATE INDEX idx_url_state_state
  ON internal.indexnow_url_state (state)
  WHERE state != 'ACTIVE';

CREATE INDEX idx_delivery_queue_run_id
  ON internal.indexnow_delivery_queue (run_id);

CREATE INDEX idx_delivery_queue_pending
  ON internal.indexnow_delivery_queue (status, queued_at)
  WHERE status = 'PENDING';

CREATE INDEX idx_delivery_queue_retry_due
  ON internal.indexnow_delivery_queue (next_retry_at)
  WHERE status = 'RETRY' AND next_retry_at IS NOT NULL;

CREATE INDEX idx_delivery_queue_stale_processing
  ON internal.indexnow_delivery_queue (processing_at)
  WHERE status = 'PROCESSING';

-- RC3: Full unique (no WHERE) — identical (url, event_type, target_fingerprint) blocked regardless of status.
-- FAILED row requires explicit recovery via internal_indexnow_delivery_retry_failed RPC.
CREATE UNIQUE INDEX idx_delivery_queue_idempotent
  ON internal.indexnow_delivery_queue (url, event_type, target_fingerprint);

-- ============================================================
-- STEP 5: TABLE PERMISSIONS
-- ============================================================
GRANT SELECT, INSERT, UPDATE ON internal.indexnow_scan_runs       TO service_role;
GRANT SELECT, INSERT, UPDATE ON internal.indexnow_url_state       TO service_role;
GRANT SELECT, INSERT, UPDATE ON internal.indexnow_delivery_queue  TO service_role;

REVOKE ALL ON internal.indexnow_scan_runs FROM PUBLIC;
REVOKE ALL ON internal.indexnow_scan_runs FROM anon;
REVOKE ALL ON internal.indexnow_scan_runs FROM authenticated;
REVOKE ALL ON internal.indexnow_url_state FROM PUBLIC;
REVOKE ALL ON internal.indexnow_url_state FROM anon;
REVOKE ALL ON internal.indexnow_url_state FROM authenticated;
REVOKE ALL ON internal.indexnow_delivery_queue FROM PUBLIC;
REVOKE ALL ON internal.indexnow_delivery_queue FROM anon;
REVOKE ALL ON internal.indexnow_delivery_queue FROM authenticated;

-- ============================================================
-- STEP 6: RPCs
-- All: SECURITY INVOKER, SET search_path = '', schema-qualified bodies.
-- All: REVOKE from PUBLIC/anon/authenticated, GRANT to service_role.
-- ============================================================

-- ── RPC 1: paginated URL state read ──────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.internal_indexnow_url_state_page(
  p_offset INT DEFAULT 0,
  p_limit  INT DEFAULT 1000
)
RETURNS TABLE (
  url                        TEXT,
  current_fingerprint        TEXT,
  current_lastmod            TEXT,
  state                      TEXT,
  missing_streak             INT,
  last_submitted_fingerprint TEXT
)
LANGUAGE sql
SECURITY INVOKER
SET search_path = ''
AS $$
  SELECT url, current_fingerprint, current_lastmod, state, missing_streak, last_submitted_fingerprint
  FROM internal.indexnow_url_state
  ORDER BY url
  LIMIT p_limit OFFSET p_offset;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_page(INT, INT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_page(INT, INT) FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_page(INT, INT) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_url_state_page(INT, INT) TO service_role;

-- ── RPC 2: create scan run ────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.internal_indexnow_scan_create(
  p_scan_started_at       TIMESTAMPTZ,
  p_sitemap_ok_count      INT,
  p_sitemap_fail_count    INT,
  p_raw_url_count         INT,
  p_unique_url_count      INT,
  p_duplicate_count       INT,
  p_with_lastmod_count    INT,
  p_without_lastmod_count INT,
  p_is_complete           BOOLEAN
)
RETURNS UUID
LANGUAGE sql
SECURITY INVOKER
SET search_path = ''
AS $$
  INSERT INTO internal.indexnow_scan_runs (
    scan_started_at, sitemap_ok_count, sitemap_fail_count,
    raw_url_count, unique_url_count, duplicate_count,
    with_lastmod_count, without_lastmod_count,
    is_complete, status
  ) VALUES (
    p_scan_started_at, p_sitemap_ok_count, p_sitemap_fail_count,
    p_raw_url_count, p_unique_url_count, p_duplicate_count,
    p_with_lastmod_count, p_without_lastmod_count,
    p_is_complete, 'RUNNING'
  )
  RETURNING id;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_scan_create(TIMESTAMPTZ, INT, INT, INT, INT, INT, INT, INT, BOOLEAN) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_scan_create(TIMESTAMPTZ, INT, INT, INT, INT, INT, INT, INT, BOOLEAN) FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_scan_create(TIMESTAMPTZ, INT, INT, INT, INT, INT, INT, INT, BOOLEAN) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_scan_create(TIMESTAMPTZ, INT, INT, INT, INT, INT, INT, INT, BOOLEAN) TO service_role;

-- ── RPC 3: complete scan run ─────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.internal_indexnow_scan_complete(
  p_run_id                  UUID,
  p_new_count               INT,
  p_changed_count           INT,
  p_unchanged_count         INT,
  p_missing_candidate_count INT,
  p_delete_ready_count      INT,
  p_resurrected_count       INT,
  p_status                  TEXT
)
RETURNS VOID
LANGUAGE sql
SECURITY INVOKER
SET search_path = ''
AS $$
  UPDATE internal.indexnow_scan_runs SET
    scan_completed_at       = now(),
    new_count               = p_new_count,
    changed_count           = p_changed_count,
    unchanged_count         = p_unchanged_count,
    missing_candidate_count = p_missing_candidate_count,
    delete_ready_count      = p_delete_ready_count,
    resurrected_count       = p_resurrected_count,
    status                  = p_status
  WHERE id = p_run_id;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_scan_complete(UUID, INT, INT, INT, INT, INT, INT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_scan_complete(UUID, INT, INT, INT, INT, INT, INT, TEXT) FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_scan_complete(UUID, INT, INT, INT, INT, INT, INT, TEXT) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_scan_complete(UUID, INT, INT, INT, INT, INT, INT, TEXT) TO service_role;

-- ── RPC 4: upsert present URLs (ACTIVE state) ────────────────────────────────
-- For NEW, UNCHANGED, CHANGED, RESURRECTED — all have a current fingerprint.
CREATE OR REPLACE FUNCTION public.internal_indexnow_url_state_upsert_present_batch(p_rows jsonb)
RETURNS VOID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
  INSERT INTO internal.indexnow_url_state (
    url, current_fingerprint, current_lastmod, state, missing_streak,
    first_seen_at, last_seen_at, created_at, updated_at
  )
  SELECT
    r->>'url',
    r->>'current_fingerprint',
    COALESCE(r->>'current_lastmod', ''),
    COALESCE(r->>'state', 'ACTIVE'),
    COALESCE((r->>'missing_streak')::int, 0),
    now(), now(), now(), now()
  FROM jsonb_array_elements(p_rows) AS r
  ON CONFLICT (url) DO UPDATE SET
    current_fingerprint = EXCLUDED.current_fingerprint,
    current_lastmod     = EXCLUDED.current_lastmod,
    state               = EXCLUDED.state,
    missing_streak      = EXCLUDED.missing_streak,
    last_seen_at        = now(),
    updated_at          = now();
END;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_upsert_present_batch(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_upsert_present_batch(jsonb) FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_upsert_present_batch(jsonb) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_url_state_upsert_present_batch(jsonb) TO service_role;

-- ── RPC 5: update absent URLs (MISSING_CANDIDATE or INACTIVE) ────────────────
-- Does NOT touch current_fingerprint/current_lastmod — keeps last known scan values.
CREATE OR REPLACE FUNCTION public.internal_indexnow_url_state_update_absent_batch(p_rows jsonb)
RETURNS VOID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
  UPDATE internal.indexnow_url_state AS s SET
    state          = (r->>'state'),
    missing_streak = (r->>'missing_streak')::int,
    updated_at     = now()
  FROM jsonb_array_elements(p_rows) AS r
  WHERE s.url = (r->>'url');
END;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_update_absent_batch(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_update_absent_batch(jsonb) FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_update_absent_batch(jsonb) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_url_state_update_absent_batch(jsonb) TO service_role;

-- ── RPC 6: enqueue delivery batch (idempotent) ───────────────────────────────
-- Full unique (url, event_type, target_fingerprint): ON CONFLICT DO NOTHING for all statuses.
-- FAILED row blocks re-insert; use internal_indexnow_delivery_retry_failed for recovery.
CREATE OR REPLACE FUNCTION public.internal_indexnow_delivery_enqueue_batch(
  p_run_id UUID,
  p_rows   jsonb
)
RETURNS INT
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
  v_count INT;
BEGIN
  INSERT INTO internal.indexnow_delivery_queue (run_id, url, event_type, target_fingerprint)
  SELECT
    p_run_id,
    r->>'url',
    r->>'event_type',
    r->>'target_fingerprint'
  FROM jsonb_array_elements(p_rows) AS r
  ON CONFLICT (url, event_type, target_fingerprint)
  DO NOTHING;

  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_enqueue_batch(UUID, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_enqueue_batch(UUID, jsonb) FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_enqueue_batch(UUID, jsonb) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_delivery_enqueue_batch(UUID, jsonb) TO service_role;

-- ── RPC 7: claim delivery batch (atomic, FOR UPDATE SKIP LOCKED) ─────────────
-- Claims PENDING, due RETRY, and stale PROCESSING (>30 min) rows.
-- Sets claimed rows to PROCESSING atomically.
-- Stale threshold: 30 minutes (crash recovery).
CREATE OR REPLACE FUNCTION public.internal_indexnow_delivery_claim_batch(
  p_limit INT DEFAULT 1000
)
RETURNS TABLE (
  id                 UUID,
  url                TEXT,
  event_type         TEXT,
  target_fingerprint TEXT,
  attempt_count      INT
)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
  RETURN QUERY
  WITH claimed AS (
    SELECT q.id
    FROM internal.indexnow_delivery_queue q
    WHERE q.status = 'PENDING'
       OR (q.status = 'RETRY'
           AND q.next_retry_at IS NOT NULL
           AND q.next_retry_at <= now())
       OR (q.status = 'PROCESSING'
           AND q.processing_at IS NOT NULL
           AND q.processing_at < now() - interval '30 minutes')
    ORDER BY q.queued_at
    LIMIT p_limit
    FOR UPDATE SKIP LOCKED
  )
  UPDATE internal.indexnow_delivery_queue q2 SET
    status        = 'PROCESSING',
    processing_at = now()
  FROM claimed
  WHERE q2.id = claimed.id
  RETURNING q2.id, q2.url, q2.event_type, q2.target_fingerprint, q2.attempt_count;
END;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_claim_batch(INT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_claim_batch(INT) FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_claim_batch(INT) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_delivery_claim_batch(INT) TO service_role;

-- ── RPC 8: update delivery results ───────────────────────────────────────────
-- On success: queue → DELIVERED, url_state.last_submitted_fingerprint updated.
-- On failure: queue → RETRY (with backoff) or FAILED (≥3 attempts), url_state unchanged.
-- Retry backoff: attempt 0 fail → +10 min; attempt 1 fail → +30 min; attempt 2 → FAILED.
CREATE OR REPLACE FUNCTION public.internal_indexnow_delivery_update_batch(p_rows jsonb)
RETURNS VOID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
  r       jsonb;
  v_url   text;
  v_etype text;
  v_tfp   text;
  v_ok    bool;
  v_hs    int;
BEGIN
  FOR r IN SELECT jsonb_array_elements(p_rows) LOOP
    v_url   := r->>'url';
    v_etype := r->>'event_type';
    v_tfp   := r->>'target_fingerprint';
    v_ok    := COALESCE((r->>'success')::boolean, false);
    v_hs    := COALESCE((r->>'http_status')::int, 0);

    IF v_ok THEN
      UPDATE internal.indexnow_delivery_queue SET
        status           = 'DELIVERED',
        delivered_at     = now(),
        last_http_status = v_hs,
        attempt_count    = attempt_count + 1,
        processing_at    = NULL,
        next_retry_at    = NULL,
        last_error       = NULL
      WHERE url = v_url AND event_type = v_etype AND target_fingerprint = v_tfp
        AND status IN ('PENDING', 'PROCESSING', 'RETRY');

      -- Only on success: advance last_submitted_fingerprint
      UPDATE internal.indexnow_url_state SET
        last_submitted_fingerprint = v_tfp,
        last_submitted_at          = now(),
        last_http_status           = v_hs,
        updated_at                 = now()
      WHERE url = v_url;
    ELSE
      -- Retry scheduling: attempt 0 → +10 min; attempt 1 → +30 min; attempt 2+ → FAILED.
      UPDATE internal.indexnow_delivery_queue SET
        status           = CASE WHEN attempt_count + 1 >= 3 THEN 'FAILED' ELSE 'RETRY' END,
        attempt_count    = attempt_count + 1,
        last_http_status = v_hs,
        last_error       = COALESCE(r->>'error', 'HTTP_' || v_hs),
        processing_at    = NULL,
        next_retry_at    = CASE
          WHEN attempt_count + 1 >= 3 THEN NULL
          WHEN attempt_count = 0      THEN now() + interval '10 minutes'
          ELSE                             now() + interval '30 minutes'
        END
      WHERE url = v_url AND event_type = v_etype AND target_fingerprint = v_tfp
        AND status IN ('PENDING', 'PROCESSING', 'RETRY');
      -- url_state last_submitted not updated on failure
    END IF;
  END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_update_batch(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_update_batch(jsonb) FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_update_batch(jsonb) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_delivery_update_batch(jsonb) TO service_role;

-- ── RPC 9: baseline seed batch ───────────────────────────────────────────────
-- Seeds url_state for bootstrap completion: current_fp = last_submitted_fp.
-- No delivery queue rows created. No Naver POST.
-- Guard: ON CONFLICT DO NOTHING — never overwrites existing state.
-- Caller must verify DB is empty before calling (empty DB guard in JS).
CREATE OR REPLACE FUNCTION public.internal_indexnow_baseline_seed_batch(p_rows jsonb)
RETURNS VOID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
  INSERT INTO internal.indexnow_url_state (
    url, current_fingerprint, current_lastmod,
    state, missing_streak,
    last_submitted_fingerprint, last_submitted_at, last_http_status,
    first_seen_at, last_seen_at, created_at, updated_at
  )
  SELECT
    r->>'url',
    r->>'current_fingerprint',
    COALESCE(r->>'current_lastmod', ''),
    'ACTIVE',
    0,
    r->>'current_fingerprint',  -- baseline: last_submitted_fp = current_fp
    now(),
    200,
    now(), now(), now(), now()
  FROM jsonb_array_elements(p_rows) AS r
  ON CONFLICT (url) DO NOTHING;  -- never overwrite: existing rows block baseline
END;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_baseline_seed_batch(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_baseline_seed_batch(jsonb) FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_baseline_seed_batch(jsonb) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_baseline_seed_batch(jsonb) TO service_role;

-- ── RPC 10: URL state count ───────────────────────────────────────────────────
-- Returns total row count for baseline empty-DB guard.
CREATE OR REPLACE FUNCTION public.internal_indexnow_url_state_count()
RETURNS BIGINT
LANGUAGE sql
SECURITY INVOKER
SET search_path = ''
AS $$
  SELECT COUNT(*) FROM internal.indexnow_url_state;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_count() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_count() FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_count() FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_url_state_count() TO service_role;

-- ── RPC 11: explicit FAILED recovery ─────────────────────────────────────────
-- Resets a FAILED row to RETRY for manual/operator recovery.
-- NOT used in production automation. Requires operator/GPT approval.
CREATE OR REPLACE FUNCTION public.internal_indexnow_delivery_retry_failed(
  p_url               TEXT,
  p_event_type        TEXT,
  p_target_fingerprint TEXT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
  UPDATE internal.indexnow_delivery_queue SET
    status        = 'RETRY',
    attempt_count = 0,
    processing_at = NULL,
    next_retry_at = now() + interval '1 minute',
    last_error    = NULL
  WHERE url = p_url AND event_type = p_event_type AND target_fingerprint = p_target_fingerprint
    AND status = 'FAILED';

  IF NOT FOUND THEN
    RAISE EXCEPTION 'FAILED row not found for %, %, %', p_url, p_event_type, p_target_fingerprint;
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_retry_failed(TEXT, TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_retry_failed(TEXT, TEXT, TEXT) FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_delivery_retry_failed(TEXT, TEXT, TEXT) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_delivery_retry_failed(TEXT, TEXT, TEXT) TO service_role;

-- ── RPC 12: baseline verification ────────────────────────────────────────────
-- Returns 4-column aggregate for JS post-seed verification.
-- Pass criteria: total = active = fingerprint_match = expected_unique; queue = 0.
CREATE OR REPLACE FUNCTION public.internal_indexnow_baseline_verify()
RETURNS TABLE (
  total_rows             BIGINT,
  active_rows            BIGINT,
  fingerprint_match_rows BIGINT,
  queue_rows             BIGINT
)
LANGUAGE sql
SECURITY INVOKER
SET search_path = ''
AS $$
  SELECT
    (SELECT COUNT(*) FROM internal.indexnow_url_state)                                          AS total_rows,
    (SELECT COUNT(*) FROM internal.indexnow_url_state WHERE state = 'ACTIVE')                   AS active_rows,
    (SELECT COUNT(*) FROM internal.indexnow_url_state
       WHERE current_fingerprint = last_submitted_fingerprint
         AND last_submitted_fingerprint IS NOT NULL)                                             AS fingerprint_match_rows,
    (SELECT COUNT(*) FROM internal.indexnow_delivery_queue)                                     AS queue_rows;
$$;

REVOKE ALL ON FUNCTION public.internal_indexnow_baseline_verify() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_baseline_verify() FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_baseline_verify() FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_baseline_verify() TO service_role;

-- ============================================================
-- STEP 7: POST-CREATION GUARDS
-- ============================================================
DO $check_post$ DECLARE
  v_count bigint;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.schemata WHERE schema_name = 'internal'
  ) THEN
    RAISE EXCEPTION 'POST FAIL: internal schema missing';
  END IF;

  SELECT COUNT(*) INTO v_count
  FROM information_schema.tables
  WHERE table_schema = 'internal'
    AND table_name IN ('indexnow_scan_runs', 'indexnow_url_state', 'indexnow_delivery_queue');
  IF v_count != 3 THEN
    RAISE EXCEPTION 'POST FAIL: expected 3 tables in internal schema, found %', v_count;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'internal'
      AND table_name   = 'indexnow_url_state'
      AND column_name  = 'current_fingerprint'
  ) THEN
    RAISE EXCEPTION 'POST FAIL: current_fingerprint column missing on internal.indexnow_url_state';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'internal'
      AND table_name   = 'indexnow_url_state'
      AND column_name  = 'last_submitted_fingerprint'
  ) THEN
    RAISE EXCEPTION 'POST FAIL: last_submitted_fingerprint column missing on internal.indexnow_url_state';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'internal'
      AND table_name   = 'indexnow_delivery_queue'
      AND column_name  = 'event_type'
  ) THEN
    RAISE EXCEPTION 'POST FAIL: event_type column missing on internal.indexnow_delivery_queue';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'internal'
      AND tablename  = 'indexnow_delivery_queue'
      AND indexname  = 'idx_delivery_queue_idempotent'
  ) THEN
    RAISE EXCEPTION 'POST FAIL: idx_delivery_queue_idempotent unique index missing';
  END IF;

  -- RC3: verify full unique (not partial)
  IF EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'internal'
      AND tablename  = 'indexnow_delivery_queue'
      AND indexname  = 'idx_delivery_queue_idempotent'
      AND indexdef   LIKE '%WHERE%'
  ) THEN
    RAISE EXCEPTION 'POST FAIL: idx_delivery_queue_idempotent must be full unique (no WHERE clause)';
  END IF;

  SELECT COUNT(*) INTO v_count
  FROM information_schema.routines
  WHERE routine_schema = 'public'
    AND routine_name IN (
      'internal_indexnow_url_state_page',
      'internal_indexnow_scan_create',
      'internal_indexnow_scan_complete',
      'internal_indexnow_url_state_upsert_present_batch',
      'internal_indexnow_url_state_update_absent_batch',
      'internal_indexnow_delivery_enqueue_batch',
      'internal_indexnow_delivery_claim_batch',
      'internal_indexnow_delivery_update_batch',
      'internal_indexnow_baseline_seed_batch',
      'internal_indexnow_url_state_count',
      'internal_indexnow_delivery_retry_failed',
      'internal_indexnow_baseline_verify'
    );
  IF v_count != 12 THEN
    RAISE EXCEPTION 'POST FAIL: expected exactly 12 RPCs in public schema, found %', v_count;
  END IF;
END $check_post$;
