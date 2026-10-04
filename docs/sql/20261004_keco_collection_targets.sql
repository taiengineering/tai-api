-- KECO Collection Targets Migration
-- Target DB: leg-prod (wrfcedzgdrfupenzqhur)
-- Schema: msds_ref
-- Applied: apply_migration via Supabase MCP
-- WO: CHEM-WO-DATA-KECO-003
-- Idempotent: IF NOT EXISTS throughout

BEGIN;

-- keco_collection_targets: CAS target queue — bulk / refresh / retry state machine
CREATE TABLE IF NOT EXISTS msds_ref.keco_collection_targets (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  target_type         text        NOT NULL CHECK (target_type = 'CAS'),
  target_value        text        NOT NULL CHECK (btrim(target_value) <> ''),
  status              text        NOT NULL DEFAULT 'PENDING'
                                  CHECK (status IN (
                                    'PENDING', 'RUNNING', 'DONE',
                                    'EMPTY', 'RETRY', 'FAILED', 'CONFLICT'
                                  )),
  attempt_count       integer     NOT NULL DEFAULT 0,
  api_request_count   integer     NOT NULL DEFAULT 0,
  source_item_count   integer     NOT NULL DEFAULT 0,
  last_run_id         uuid        REFERENCES msds_ref.keco_ingestion_runs(id),
  last_error_code     text,
  last_error_message  text,
  first_attempted_at  timestamptz,
  last_attempted_at   timestamptz,
  last_success_at     timestamptz,
  next_refresh_at     timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT keco_collection_targets_unique UNIQUE (target_type, target_value)
);

COMMENT ON TABLE msds_ref.keco_collection_targets IS
  'KECO 15149420 collection target queue. CAS refresh state machine. CHEM-WO-DATA-KECO-003.';

CREATE INDEX IF NOT EXISTS idx_keco_targets_status
  ON msds_ref.keco_collection_targets(status);

CREATE INDEX IF NOT EXISTS idx_keco_targets_next_refresh
  ON msds_ref.keco_collection_targets(next_refresh_at)
  WHERE next_refresh_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_keco_targets_last_attempted
  ON msds_ref.keco_collection_targets(last_attempted_at);

-- RLS: service_role only — anon/authenticated = 0
ALTER TABLE msds_ref.keco_collection_targets ENABLE ROW LEVEL SECURITY;

GRANT USAGE ON SCHEMA msds_ref TO service_role;
GRANT SELECT, INSERT, UPDATE ON msds_ref.keco_collection_targets TO service_role;

COMMIT;
