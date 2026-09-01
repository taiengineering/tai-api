-- WO-SAFE-LEGAL-CST-CANONICAL-IMPLEMENT-001 / STEP2 — construction_works canonical extension (DOWN)
-- STEP2 가 추가한 5 컬럼 + 3 CHECK 만 제거. 기존 construction_works 컬럼/constraint 삭제 금지. repeat-safe.
-- APPLY POLICY: artifact only. DB APPLY = BLOCKED.

BEGIN;

ALTER TABLE public.construction_works
    DROP CONSTRAINT IF EXISTS ck_construction_works_work_height_m,
    DROP CONSTRAINT IF EXISTS ck_construction_works_truck_loading_height_m,
    DROP CONSTRAINT IF EXISTS ck_construction_works_manual_handling_weight_kg;

ALTER TABLE public.construction_works
    DROP COLUMN IF EXISTS work_height_m,
    DROP COLUMN IF EXISTS has_truck_loading_unloading,
    DROP COLUMN IF EXISTS truck_loading_height_m,
    DROP COLUMN IF EXISTS has_manual_heavy_handling,
    DROP COLUMN IF EXISTS manual_handling_weight_kg;

COMMIT;
