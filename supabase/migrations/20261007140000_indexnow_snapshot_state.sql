-- WO-SEO-NAVER-INDEXNOW-V2-004B: IndexNow Snapshot Diff State
-- RC1: state enum = ACTIVE|MISSING_CANDIDATE|INACTIVE (DELETE_READY is classification only).
--      RPC SECURITY INVOKER + SET search_path = '' + REVOKE from PUBLIC.
-- Production DB apply: NOT YET AUTHORIZED.
--
-- Security: internal schema NOT exposed via PostgREST (public schema only).
--   anon/authenticated have zero access to these tables.
--   Reads via public.internal_indexnow_url_state_page() RPC (service_role only).
--   Writes via service_role JWT through PostgREST or direct pg connection.
--
-- State contract:
--   Persistent URL states: ACTIVE | MISSING_CANDIDATE | INACTIVE
--   INACTIVE: URL absent from >= 2 complete scans (maps from diff classification DELETE_READY).
--   DELETE_READY is a diff classification, NOT a persistent DB state.
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
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  scan_started_at     TIMESTAMPTZ NOT NULL,
  scan_completed_at   TIMESTAMPTZ,
  sitemap_ok_count    INT         NOT NULL CHECK (sitemap_ok_count >= 0),
  sitemap_fail_count  INT         NOT NULL CHECK (sitemap_fail_count >= 0),
  total_url_count     INT         NOT NULL CHECK (total_url_count >= 0),
  is_complete         BOOLEAN     NOT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE internal.indexnow_url_state (
  url               TEXT        PRIMARY KEY,
  fingerprint       TEXT        NOT NULL,
  lastmod           TEXT        NOT NULL DEFAULT '',
  -- Persistent states only (DELETE_READY is a diff classification, not a persistent state):
  -- ACTIVE           = URL present in most recent scan
  -- MISSING_CANDIDATE = URL absent from 1 scan (or partial scan)
  -- INACTIVE         = URL absent from >= 2 complete scans
  state             TEXT        NOT NULL DEFAULT 'ACTIVE'
                                  CONSTRAINT chk_url_state_state
                                    CHECK (state IN ('ACTIVE', 'MISSING_CANDIDATE', 'INACTIVE')),
  missing_streak    INT         NOT NULL DEFAULT 0 CHECK (missing_streak >= 0),
  first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at      TIMESTAMPTZ,
  last_submitted_at TIMESTAMPTZ,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE internal.indexnow_delivery_queue (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id        UUID        NOT NULL
                              REFERENCES internal.indexnow_scan_runs(id)
                              ON DELETE CASCADE,
  url           TEXT        NOT NULL,
  queued_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at  TIMESTAMPTZ,
  status        TEXT        NOT NULL DEFAULT 'PENDING'
                              CONSTRAINT chk_queue_status
                                CHECK (status IN ('PENDING', 'DELIVERED', 'FAILED')),
  http_status   INT
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

-- ============================================================
-- STEP 5: TABLE PERMISSIONS
-- ============================================================
GRANT SELECT, INSERT, UPDATE ON internal.indexnow_scan_runs TO service_role;
GRANT SELECT, INSERT, UPDATE ON internal.indexnow_url_state TO service_role;
GRANT SELECT, INSERT, UPDATE ON internal.indexnow_delivery_queue TO service_role;

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
-- STEP 6: RPC — paginated URL state read
-- SECURITY INVOKER: runs as the calling role (service_role).
-- SET search_path = '': prevent search_path hijacking.
-- All object references are schema-qualified in the function body.
-- ============================================================
CREATE OR REPLACE FUNCTION public.internal_indexnow_url_state_page(
  p_offset INT DEFAULT 0,
  p_limit  INT DEFAULT 1000
)
RETURNS TABLE (
  url            TEXT,
  fingerprint    TEXT,
  lastmod        TEXT,
  state          TEXT,
  missing_streak INT
)
LANGUAGE sql
SECURITY INVOKER
SET search_path = ''
AS $$
  SELECT url, fingerprint, lastmod, state, missing_streak
  FROM internal.indexnow_url_state
  ORDER BY url
  LIMIT p_limit OFFSET p_offset;
$$;

-- Deny all roles, then grant only to service_role.
-- PUBLIC must be revoked explicitly (Supabase 2026-10-30 policy: no implicit grants).
REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_page(INT, INT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_page(INT, INT) FROM anon;
REVOKE ALL ON FUNCTION public.internal_indexnow_url_state_page(INT, INT) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.internal_indexnow_url_state_page(INT, INT) TO service_role;

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
      AND column_name  = 'fingerprint'
  ) THEN
    RAISE EXCEPTION 'POST FAIL: fingerprint column missing on internal.indexnow_url_state';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.routines
    WHERE routine_schema = 'public'
      AND routine_name   = 'internal_indexnow_url_state_page'
  ) THEN
    RAISE EXCEPTION 'POST FAIL: internal_indexnow_url_state_page function missing';
  END IF;
END $check_post$;
