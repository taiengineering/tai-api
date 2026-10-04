-- Migration: heartbeat_at column for keco_ingestion_runs
-- Purpose : stale RUNNING run 복구 기준 시간. recover_stale_runs()에서 참조.
--           NULL = heartbeat 미지원 이전 run (started_at 기준으로 fallback 처리).
-- Schema  : msds_ref (LEG DB)
-- Applied : leg-prod (apply_migration 필요)

ALTER TABLE msds_ref.keco_ingestion_runs
  ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;

COMMENT ON COLUMN msds_ref.keco_ingestion_runs.heartbeat_at
  IS 'Last heartbeat timestamp for in-progress runs. NULL = pre-heartbeat era. Used by recover_stale_runs() to detect crashed processes.';
