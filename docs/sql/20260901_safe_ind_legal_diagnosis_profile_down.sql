-- WO-SAFE-LEGAL-IND-IMPLEMENT-001-R1 / STEP2-PATCH-1 — SAFE INDUSTRIAL Marketing-Contract Adapter (DOWN)
-- Reverses the UP migration. Idempotent (repeat-safe). APPLY POLICY: artifact only. DB APPLY = BLOCKED.
--
-- P2: table DROP removes its own trigger/policies/constraints/indexes — no per-object DROP on a
--     possibly-missing table (missing-table safe). Helper functions dropped after the table.

BEGIN;

-- 3) equipment_assets columns
ALTER TABLE public.equipment_assets
    DROP COLUMN IF EXISTS legal_usage_types,
    DROP COLUMN IF EXISTS legal_relation_types;

-- 2) factory_process columns (+ CHECK)
ALTER TABLE public.factory_process
    DROP CONSTRAINT IF EXISTS ck_factory_process_legal_worker_count;
ALTER TABLE public.factory_process
    DROP COLUMN IF EXISTS legal_hazard_codes,
    DROP COLUMN IF EXISTS legal_worker_count,
    DROP COLUMN IF EXISTS legal_activity_types;

-- 1) factory_legal_diagnosis_profile: table drop cascades trigger/policies/constraints/indexes.
DROP TABLE IF EXISTS public.factory_legal_diagnosis_profile;

-- helper functions (dropped after the table that referenced them)
DROP FUNCTION IF EXISTS public.fn_fldp_touch_updated_at();
DROP FUNCTION IF EXISTS public.fn_fldp_material_profile_shape_ok(jsonb);

COMMIT;
