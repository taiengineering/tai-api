-- Migration: heartbeat_at column + atomic runtime lock for keco_ingestion_runs
-- Purpose:
--   heartbeat_at  — stale RUNNING run 복구 기준 시간.
--                   COALESCE(heartbeat_at, started_at) < threshold 으로 stale 판정.
--                   NULL = heartbeat 미지원 이전 run (started_at 기준 fallback).
--   unique index  — INITIAL_BULK/MANUAL_SINGLE/RETRY/SCHEDULED_REFRESH 동시 실행 방지.
--                   start_exclusive_run()이 23505 unique violation을 locked=True 로 처리.
-- Schema  : msds_ref (LEG DB)
-- Applied : leg-prod (apply_migration 필요)

ALTER TABLE msds_ref.keco_ingestion_runs
  ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;

COMMENT ON COLUMN msds_ref.keco_ingestion_runs.heartbeat_at
  IS 'Last heartbeat timestamp for in-progress runs. NULL = pre-heartbeat era. Used by recover_stale_runs() via COALESCE(heartbeat_at, started_at).';

-- Atomic runtime lock: runtime run_type 중 최대 1개만 RUNNING 허용.
-- (1) expression index → WHERE 조건 만족 row가 2개 이상이면 23505 unique_violation 발생.
CREATE UNIQUE INDEX IF NOT EXISTS keco_ingestion_runs_one_active_runtime
  ON msds_ref.keco_ingestion_runs ((1))
  WHERE status = 'RUNNING'
    AND run_type IN ('INITIAL_BULK', 'MANUAL_SINGLE', 'RETRY', 'SCHEDULED_REFRESH');
