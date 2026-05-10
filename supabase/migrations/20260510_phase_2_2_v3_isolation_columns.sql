-- Phase 2.2 v3 — 격리 분석 (FP만 is_isolated, validator·TP 보전)
-- apply: Supabase SQL 또는 psql

ALTER TABLE stage_2_elements
  ADD COLUMN IF NOT EXISTS is_isolated boolean NOT NULL DEFAULT false;

ALTER TABLE stage_2_elements
  ADD COLUMN IF NOT EXISTS isolation_reason text NULL;

ALTER TABLE stage_2_elements
  ADD COLUMN IF NOT EXISTS isolated_at timestamptz NULL;

ALTER TABLE stage_2_elements
  DROP CONSTRAINT IF EXISTS stage_2_elements_isolation_reason_chk;

ALTER TABLE stage_2_elements
  ADD CONSTRAINT stage_2_elements_isolation_reason_chk
  CHECK (
    isolation_reason IS NULL
    OR isolation_reason IN (
      'FP_AS_본다_보조_룰',
      'FP_OBLIGATION_DETAIL_GWAN_SAHANG',
      'FP_DELEGATION_ETRAHADA_별표',
      'FP_PROHIBITION_NOT_DOEN',
      'FP_WEAK_JUNYONG_HADA',
      'FP_OTHER',
      'WARNING_LOW_ACCURACY',
      'MANUAL_REVIEW'
    )
  );

CREATE INDEX IF NOT EXISTS idx_stage_2_elements_isolated
  ON stage_2_elements (is_isolated)
  WHERE is_isolated = true;

COMMENT ON COLUMN stage_2_elements.is_isolated IS 'Phase 2.2 v3: FP 격리 대상 (TP 변동 없음)';
COMMENT ON COLUMN stage_2_elements.isolation_reason IS 'Phase 2.2 v3: 격리 사유 (CHECK 열거)';
COMMENT ON COLUMN stage_2_elements.isolated_at IS 'Phase 2.2 v3: 격리 시각';
