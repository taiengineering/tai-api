-- WO-SAFE-LEGAL-IND-CANONICAL-IMPLEMENT-001 / STEP1 — SAFE INDUSTRIAL Canonical Asset Extension (UP)
--
-- CORRECTION-002 CLOSED 결과: 법령진단 전용 profile 을 만들지 않는다. 사용자는 사실을 한 번만 등록하고,
-- Marketing INDUSTRIAL 29 는 실제 자산(factories / factory_process / equipment_assets / factory_materials)에서
-- 조립되는 transport contract 다. 본 migration 은 이전 R2 profile 설계를 완전 폐기하고 canonical 자산을 확장한다.
--
-- 폐기(이 파일 이전 버전 대비): factory_legal_diagnosis_profile CREATE / trigger / RLS / grants / material helper /
--   index, legal_* 컬럼, building_use_type_override / main_structure_override, ksic_list, material_profile JSONB.
-- NO-STORAGE targets(assembler derive; 신규 저장 컬럼 금지): total_floor_area, building_use_type, main_structure,
--   building_qualifications, regulated_facility_types.
-- NULL=미확인 / []=명시적 없음 / false=명시적 아니오 / 0=실제 zero. array DEFAULT '{}' 금지. 추정/default 금지.
-- facility_profiles / facility_condition = 진단 snapshot/cache (SoT 아님) → 변경/신규컬럼 0.
-- factory_process_id = 동결(변경 0). building-register /apply 의존 0.
-- APPLY POLICY: artifact only. DB APPLY = BLOCKED until GPT PASS.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1) factories — canonical extension (작업형태/작업환경 + 건물구성/규제지정 원자)
--    9 신규 nullable 컬럼. building_composition_codes / regulatory_designation_codes 는
--    Marketing building_qualifications / regulated_facility_types 저장 컬럼이 아니라 "실제 사실" 원자 저장이며
--    Marketing 값은 assembler 가 이들 + 기존 canonical 에서 derive 한다(법적 판정 결과 저장 금지).
-- ---------------------------------------------------------------------------
ALTER TABLE public.factories
    ADD COLUMN IF NOT EXISTS work_height_m                numeric,
    ADD COLUMN IF NOT EXISTS has_truck_loading_unloading  boolean,
    ADD COLUMN IF NOT EXISTS truck_loading_height_m       numeric,
    ADD COLUMN IF NOT EXISTS has_manual_heavy_handling    boolean,
    ADD COLUMN IF NOT EXISTS manual_handling_weight_kg    numeric,
    ADD COLUMN IF NOT EXISTS business_activity_types      text[],
    ADD COLUMN IF NOT EXISTS hazardous_work_environments  text[],
    ADD COLUMN IF NOT EXISTS building_composition_codes   text[],
    ADD COLUMN IF NOT EXISTS regulatory_designation_codes text[];

-- factories numeric CHECK (NULL 허용, 음수 거부; idempotent conrelid-scoped)
DO $ck$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_factories_work_height_m' AND conrelid='public.factories'::regclass) THEN
        ALTER TABLE public.factories ADD CONSTRAINT ck_factories_work_height_m
            CHECK (work_height_m IS NULL OR work_height_m >= 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_factories_truck_loading_height_m' AND conrelid='public.factories'::regclass) THEN
        ALTER TABLE public.factories ADD CONSTRAINT ck_factories_truck_loading_height_m
            CHECK (truck_loading_height_m IS NULL OR truck_loading_height_m >= 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_factories_manual_handling_weight_kg' AND conrelid='public.factories'::regclass) THEN
        ALTER TABLE public.factories ADD CONSTRAINT ck_factories_manual_handling_weight_kg
            CHECK (manual_handling_weight_kg IS NULL OR manual_handling_weight_kg >= 0);
    END IF;
END
$ck$;

COMMENT ON COLUMN public.factories.work_height_m IS
    'WO-CANONICAL: 시설 대표/최대 작업높이(m). NULL=미확인. 추정 금지.';
COMMENT ON COLUMN public.factories.has_truck_loading_unloading IS
    'WO-CANONICAL: 차량 상·하차 작업 유무. false=명시적 아니오 / NULL=미확인.';
COMMENT ON COLUMN public.factories.truck_loading_height_m IS
    'WO-CANONICAL: 상·하차 높이(m). NULL=미확인.';
COMMENT ON COLUMN public.factories.has_manual_heavy_handling IS
    'WO-CANONICAL: 중량물 수작업 유무. false=명시적 아니오 / NULL=미확인.';
COMMENT ON COLUMN public.factories.manual_handling_weight_kg IS
    'WO-CANONICAL: 중량물 무게(kg). 0=실제 zero / NULL=미확인.';
COMMENT ON COLUMN public.factories.business_activity_types IS
    'WO-CANONICAL: 실제 사업활동 유형(다중). NULL=미확인 / []=명시적 없음.';
COMMENT ON COLUMN public.factories.hazardous_work_environments IS
    'WO-CANONICAL: 실제 유해작업환경 유형(다중). NULL=미확인 / []=명시적 없음.';
COMMENT ON COLUMN public.factories.building_composition_codes IS
    'WO-CANONICAL: 실제 건물/단지 구성 사실 원자(다중). Marketing building_qualifications 저장컬럼 아님. 법적 판정(예: 의무관리대상 공동주택) 저장 금지 → assembler derive. NULL=미확인 / []=명시적 없음.';
COMMENT ON COLUMN public.factories.regulatory_designation_codes IS
    'WO-CANONICAL: 실제 취득/지정/허가 상태 원자(다중). Marketing regulated_facility_types 저장컬럼 아님. 법적 판정 결과(예: 안전성평가 대상시설) 저장 금지 → assembler derive. 물리시설 보유는 equipment_assets/기존 factory field 정본. NULL=미확인 / []=명시적 없음.';

-- ---------------------------------------------------------------------------
-- 2) factory_process — canonical extension (legal_ prefix REJECT → 실제 공정 속성)
-- ---------------------------------------------------------------------------
ALTER TABLE public.factory_process
    ADD COLUMN IF NOT EXISTS hazard_codes   text[],
    ADD COLUMN IF NOT EXISTS worker_count   integer,
    ADD COLUMN IF NOT EXISTS activity_types text[];

DO $wc$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_factory_process_worker_count' AND conrelid='public.factory_process'::regclass) THEN
        ALTER TABLE public.factory_process ADD CONSTRAINT ck_factory_process_worker_count
            CHECK (worker_count IS NULL OR worker_count >= 0);
    END IF;
END
$wc$;

COMMENT ON COLUMN public.factory_process.hazard_codes IS
    'WO-CANONICAL: 공정 위험요인 코드(다중). Marketing process_list.hazard_codes 정본. NULL=미확인 / []=명시적 없음.';
COMMENT ON COLUMN public.factory_process.worker_count IS
    'WO-CANONICAL: 해당 공정 작업자 수. 0=해당 공정 작업자 0 / NULL=미확인 (factory.employee_count 와 별개).';
COMMENT ON COLUMN public.factory_process.activity_types IS
    'WO-CANONICAL: 공정 작업활동 유형(다중). Marketing process_list.activity_type 정본. NULL=미확인 / []=명시적 없음.';

-- ---------------------------------------------------------------------------
-- 3) equipment_assets — canonical extension (legal_ prefix REJECT; TAG only)
--    factory_process_id(실제 관계 FK) 변경 없음. relation_types 는 관계 semantic TAG, FK 대체 아님.
-- ---------------------------------------------------------------------------
ALTER TABLE public.equipment_assets
    ADD COLUMN IF NOT EXISTS usage_types    text[],
    ADD COLUMN IF NOT EXISTS relation_types text[];

COMMENT ON COLUMN public.equipment_assets.usage_types IS
    'WO-CANONICAL: 설비 사용유형 태그(다중). Marketing equipment_list.usage_type 정본. NULL=미확인 / []=명시적 없음.';
COMMENT ON COLUMN public.equipment_assets.relation_types IS
    'WO-CANONICAL: 설비 관계유형 semantic TAG(다중). FK 대체 아님(실제 공정 관계=factory_process_id 동결). NULL=미확인 / []=명시적 없음.';

-- ---------------------------------------------------------------------------
-- 4) factory_materials — NEW real-world canonical asset (사업장 취급물질)
--    1 row = 사업장이 실제 취급하는 하나의 물질/물질 프로파일. Marketing row 복사 테이블 아님.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.factory_materials (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_id              uuid NOT NULL,
    material_name           text,
    material_category_code  text,
    handling_mode_codes     text[],
    is_active               boolean NOT NULL DEFAULT true,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT fk_factory_materials_factory
        FOREIGN KEY (factory_id) REFERENCES public.factories(id) ON DELETE CASCADE,

    -- identity: 이름/분류 둘 다 없는 무의미 row 금지 (빈 문자열도 불허)
    CONSTRAINT ck_factory_materials_identity
        CHECK ( (material_name IS NOT NULL AND btrim(material_name) <> '')
             OR (material_category_code IS NOT NULL AND btrim(material_category_code) <> '') )
);

-- business-key UNIQUE 억지 생성 금지(같은 category 다수 물질 가능). PK id = identity.
CREATE INDEX IF NOT EXISTS ix_factory_materials_factory_id ON public.factory_materials (factory_id);

COMMENT ON TABLE public.factory_materials IS
    'WO-CANONICAL: 사업장 실제 취급물질 자산(1 row=1 물질/프로파일). Marketing material_profile transport 의 정본. 2-key 복사 테이블 아님. Ownership: material->factory->company (API 검증).';
COMMENT ON COLUMN public.factory_materials.material_category_code IS
    'WO-CANONICAL: 물질 분류 코드. vocabulary 검증은 후속 API/assembler 단계.';
COMMENT ON COLUMN public.factory_materials.handling_mode_codes IS
    'WO-CANONICAL: 취급형태 코드(다중). NULL=미확인 / []=명시적 없음.';

-- updated_at touch trigger
CREATE OR REPLACE FUNCTION public.fn_factory_materials_touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $tg$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$tg$;

DROP TRIGGER IF EXISTS trg_factory_materials_touch_updated_at ON public.factory_materials;
CREATE TRIGGER trg_factory_materials_touch_updated_at
    BEFORE UPDATE ON public.factory_materials
    FOR EACH ROW EXECUTE FUNCTION public.fn_factory_materials_touch_updated_at();

-- server-only access (기존 Safe backend ownership 모델: API 경유 service_role)
ALTER TABLE public.factory_materials ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.factory_materials FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.factory_materials TO service_role;

COMMIT;
