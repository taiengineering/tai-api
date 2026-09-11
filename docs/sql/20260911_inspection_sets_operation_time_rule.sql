-- WO-SAFE-OPERATION-TIME-BACKEND-V1-001
-- Additive: inspection_sets.operation_time_rule JSONB (NULL default).
-- File-only / APPLY by operator approval. Idempotent.
-- Existing cycle_unit / cycle_value unchanged. No backfill. NOT NULL 금지.

ALTER TABLE public.inspection_sets
  ADD COLUMN IF NOT EXISTS operation_time_rule jsonb NULL;

COMMENT ON COLUMN public.inspection_sets.operation_time_rule IS
  'SaaS OPERATION_TIME_RULE v1 (EVERY/WITHIN/BEFORE/UNTIL). LEGAL_NORMALIZED_TIME 과 별축. NULL=미설정.';
