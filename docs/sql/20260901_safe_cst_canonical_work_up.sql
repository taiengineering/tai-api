-- WO-SAFE-LEGAL-CST-CANONICAL-IMPLEMENT-001 / STEP2 — construction_works canonical extension (UP)
--
-- 실제 개별 작업(construction_works) 에 현재 없는 실 작업 사실 5개만 추가한다.
-- 법령진단 전용 profile/table 미생성. construction_sites 중복 저장 금지. E 15개(위험/규제 boolean) 저장컬럼 추가 금지.
-- NULL=unknown / false=explicit no / 0=actual zero. boolean·numeric DEFAULT 금지(자동 false/0 인정 방지).
-- numeric 3개는 NULL 허용·음수 거부 CHECK. special_work_type/hazard_codes/worker_count 미변경.
-- APPLY POLICY: artifact only. DB APPLY = BLOCKED until GPT PASS + operator apply.

BEGIN;

ALTER TABLE public.construction_works
    ADD COLUMN IF NOT EXISTS work_height_m                numeric,
    ADD COLUMN IF NOT EXISTS has_truck_loading_unloading  boolean,
    ADD COLUMN IF NOT EXISTS truck_loading_height_m       numeric,
    ADD COLUMN IF NOT EXISTS has_manual_heavy_handling    boolean,
    ADD COLUMN IF NOT EXISTS manual_handling_weight_kg    numeric;

-- numeric CHECK (NULL 허용, 음수 거부; idempotent conrelid-scoped)
DO $ck$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_construction_works_work_height_m' AND conrelid='public.construction_works'::regclass) THEN
        ALTER TABLE public.construction_works ADD CONSTRAINT ck_construction_works_work_height_m
            CHECK (work_height_m IS NULL OR work_height_m >= 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_construction_works_truck_loading_height_m' AND conrelid='public.construction_works'::regclass) THEN
        ALTER TABLE public.construction_works ADD CONSTRAINT ck_construction_works_truck_loading_height_m
            CHECK (truck_loading_height_m IS NULL OR truck_loading_height_m >= 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_construction_works_manual_handling_weight_kg' AND conrelid='public.construction_works'::regclass) THEN
        ALTER TABLE public.construction_works ADD CONSTRAINT ck_construction_works_manual_handling_weight_kg
            CHECK (manual_handling_weight_kg IS NULL OR manual_handling_weight_kg >= 0);
    END IF;
END
$ck$;

COMMENT ON COLUMN public.construction_works.work_height_m IS
    'WO-CST-CANONICAL STEP2: 작업 높이(m). NULL=unknown. 추정 금지.';
COMMENT ON COLUMN public.construction_works.has_truck_loading_unloading IS
    'WO-CST-CANONICAL STEP2: 차량 상·하차 작업 유무. false=explicit no / NULL=unknown.';
COMMENT ON COLUMN public.construction_works.truck_loading_height_m IS
    'WO-CST-CANONICAL STEP2: 상·하차 높이(m). NULL=unknown.';
COMMENT ON COLUMN public.construction_works.has_manual_heavy_handling IS
    'WO-CST-CANONICAL STEP2: 중량물 수작업 유무. false=explicit no / NULL=unknown.';
COMMENT ON COLUMN public.construction_works.manual_handling_weight_kg IS
    'WO-CST-CANONICAL STEP2: 중량물 무게(kg). 0=actual zero / NULL=unknown.';

COMMIT;
