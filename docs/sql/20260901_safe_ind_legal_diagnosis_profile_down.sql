-- WO-SAFE-LEGAL-IND-IMPLEMENT-001-R1 / STEP 2A — SAFE INDUSTRIAL Marketing-Contract Adapter (DOWN)
-- Reverses the UP migration. Idempotent. APPLY POLICY: artifact only. DB APPLY = BLOCKED until GPT PASS-A.

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

-- 1) factory_legal_diagnosis_profile (table drop removes columns/constraints/indexes/trigger/policies)
DROP TRIGGER IF EXISTS trg_fldp_touch_updated_at ON public.factory_legal_diagnosis_profile;
DROP POLICY IF EXISTS p_fldp_authenticated_company ON public.factory_legal_diagnosis_profile;
DROP POLICY IF EXISTS p_fldp_service_all ON public.factory_legal_diagnosis_profile;
DROP TABLE IF EXISTS public.factory_legal_diagnosis_profile;
DROP FUNCTION IF EXISTS public.fn_fldp_touch_updated_at();

COMMIT;
