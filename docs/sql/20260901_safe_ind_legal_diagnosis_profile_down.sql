-- WO-SAFE-LEGAL-IND-CANONICAL-IMPLEMENT-001 / STEP1 — SAFE INDUSTRIAL Canonical Asset Extension (DOWN)
-- UP 의 canonical 변경을 정확히 역전. repeat-safe. APPLY POLICY: artifact only. DB APPLY = BLOCKED.
-- 순서: factory_materials → equipment cols → process cols(+CHECK) → factory cols(+CHECK).
-- 다른 기존 data/table 삭제 금지. facility_profiles/facility_condition/factory_process_id 미변경.

BEGIN;

-- 4) factory_materials (table drop cascades trigger/policies/index/constraints), then helper fn
DROP TABLE IF EXISTS public.factory_materials;
DROP FUNCTION IF EXISTS public.fn_factory_materials_touch_updated_at();

-- 3) equipment_assets columns
ALTER TABLE public.equipment_assets
    DROP COLUMN IF EXISTS usage_types,
    DROP COLUMN IF EXISTS relation_types;

-- 2) factory_process columns (+ CHECK)
ALTER TABLE public.factory_process
    DROP CONSTRAINT IF EXISTS ck_factory_process_worker_count;
ALTER TABLE public.factory_process
    DROP COLUMN IF EXISTS hazard_codes,
    DROP COLUMN IF EXISTS worker_count,
    DROP COLUMN IF EXISTS activity_types;

-- 1) factories columns (+ CHECK)
ALTER TABLE public.factories
    DROP CONSTRAINT IF EXISTS ck_factories_work_height_m,
    DROP CONSTRAINT IF EXISTS ck_factories_truck_loading_height_m,
    DROP CONSTRAINT IF EXISTS ck_factories_manual_handling_weight_kg;
ALTER TABLE public.factories
    DROP COLUMN IF EXISTS work_height_m,
    DROP COLUMN IF EXISTS has_truck_loading_unloading,
    DROP COLUMN IF EXISTS truck_loading_height_m,
    DROP COLUMN IF EXISTS has_manual_heavy_handling,
    DROP COLUMN IF EXISTS manual_handling_weight_kg,
    DROP COLUMN IF EXISTS business_activity_types,
    DROP COLUMN IF EXISTS hazardous_work_environments,
    DROP COLUMN IF EXISTS building_composition_codes,
    DROP COLUMN IF EXISTS regulatory_designation_codes;

COMMIT;
