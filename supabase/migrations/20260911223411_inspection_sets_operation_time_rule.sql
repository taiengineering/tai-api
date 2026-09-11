-- WO-SAFE-OPERATION-TIME-BACKEND-V1-001 / MIGRATION-GATE-001
-- Additive: inspection_sets.operation_time_rule JSONB (NULL default).
-- Idempotent. No backfill. NOT NULL 금지. cycle_* unchanged.

ALTER TABLE public.inspection_sets
  ADD COLUMN IF NOT EXISTS operation_time_rule jsonb NULL;

COMMENT ON COLUMN public.inspection_sets.operation_time_rule IS
  'SaaS OPERATION_TIME_RULE v1 (EVERY/WITHIN/BEFORE/UNTIL). LEGAL_NORMALIZED_TIME 과 별축. NULL=미설정.';
