-- WO-SAFE-LEGAL-IND-IMPLEMENT-001-R1 / STEP2-PATCH-1 — SAFE INDUSTRIAL Marketing-Contract Adapter (UP)
--
-- Persist ONLY the Marketing INDUSTRIAL paid contract facts that Safe's existing domain
-- model (factories / factory_process / equipment_assets) does NOT already hold.
-- Contract SoT = tai-www 유료진단 INDUSTRIAL 현재 입력계약. CONTRACT = MKT_IND_PAID_CONTRACT_V1 (29).
--
-- STEP2-PATCH-1 corrections (GPT independent review):
--   P1 material_profile shape → immutable helper fn (CHECK subquery 불가 blocker 해결)
--   P2 DOWN idempotence (개별 DROP TRIGGER/POLICY 제거; 파일 별도)
--   P3 server-only access: REVOKE PUBLIC/anon/authenticated, GRANT service_role, NO row policies
--   P4 process constraint 존재확인에 conrelid 고정
--   P5 UNIQUE(factory_id) 가 index 생성 → 중복 index 제거
--   P6 M1~M3 유지: company_id 로컬컬럼 0 / array default 0 / numeric>=0 / false·0 보존
--
-- NO synthetic default for any diagnosis input. Absence stays NULL. false/0/[] valid, distinct from NULL.
-- APPLY POLICY: artifact only. DB APPLY = BLOCKED until GPT PASS-A.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 0) material_profile shape helper (P1) — CHECK 에서 subquery 없이 호출.
--    값 shape 만 검증(허용 key ⊆ {material_category, handling_modes}). vocabulary 검증은 backend validator.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.fn_fldp_material_profile_shape_ok(p jsonb)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $fn$
DECLARE
    elem jsonb;
BEGIN
    IF jsonb_typeof(p) <> 'array' THEN
        RETURN false;
    END IF;

    FOR elem IN
        SELECT value FROM jsonb_array_elements(p) AS t(value)
    LOOP
        IF jsonb_typeof(elem) <> 'object' THEN
            RETURN false;
        END IF;
        IF EXISTS (
            SELECT 1 FROM jsonb_object_keys(elem) AS k
            WHERE k NOT IN ('material_category', 'handling_modes')
        ) THEN
            RETURN false;
        END IF;
    END LOOP;

    RETURN true;
END
$fn$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1) factory_legal_diagnosis_profile
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.factory_legal_diagnosis_profile (
    id                            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_id                    uuid NOT NULL,
    contract_version              text NOT NULL DEFAULT 'MKT_IND_PAID_CONTRACT_V1',

    -- ADD 7
    work_height_m                 numeric,
    has_truck_loading_unloading   boolean,
    truck_loading_height_m        numeric,
    has_manual_heavy_handling     boolean,
    manual_handling_weight_kg     numeric,
    business_activity_types       text[],
    hazardous_work_environments   text[],

    -- facility-level GAP 보충 (기존 29 계약의 부족값)
    ksic_list                     text[],
    total_floor_area              numeric,
    material_profile              jsonb,
    building_qualifications       text[],
    regulated_facility_types      text[],

    created_at                    timestamptz NOT NULL DEFAULT now(),
    updated_at                    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT fk_fldp_factory
        FOREIGN KEY (factory_id) REFERENCES public.factories(id) ON DELETE CASCADE,
    CONSTRAINT uq_fldp_factory UNIQUE (factory_id),

    -- M3 numeric constraints (NULL 허용; 음수 거부)
    CONSTRAINT ck_fldp_work_height        CHECK (work_height_m IS NULL OR work_height_m >= 0),
    CONSTRAINT ck_fldp_truck_height       CHECK (truck_loading_height_m IS NULL OR truck_loading_height_m >= 0),
    CONSTRAINT ck_fldp_manual_weight      CHECK (manual_handling_weight_kg IS NULL OR manual_handling_weight_kg >= 0),
    CONSTRAINT ck_fldp_total_floor_area   CHECK (total_floor_area IS NULL OR total_floor_area >= 0),

    -- P1 material_profile shape (no subquery; immutable helper call)
    CONSTRAINT ck_fldp_material_profile_shape
        CHECK (material_profile IS NULL OR public.fn_fldp_material_profile_shape_ok(material_profile))
);

COMMENT ON TABLE public.factory_legal_diagnosis_profile IS
    'WO-SAFE-LEGAL-IND-IMPLEMENT-001: Marketing INDUSTRIAL paid-contract supplemental facts (ADD 7 + facility-level GAP) not held by factories base model. 1:1 with factories. Ownership via factory_id->factories.company_id (no local company_id). Server-only access (service_role). Contract=MKT_IND_PAID_CONTRACT_V1.';
COMMENT ON COLUMN public.factory_legal_diagnosis_profile.total_floor_area IS
    '연면적(㎡). 정본 source 없을 때만. building_area/arch_area/층수 산술 추정 금지.';
COMMENT ON COLUMN public.factory_legal_diagnosis_profile.material_profile IS
    'JSONB array; 허용 key = material_category, handling_modes 만(P1). vocabulary 검증은 backend validator.';
COMMENT ON COLUMN public.factory_legal_diagnosis_profile.ksic_list IS
    '추가 업종(대분류). assembler 가 factories.ksic_code(industry_master 결정적 해석)와 distinct 병합. NULL=미확인/[]=명시적 없음(M2).';
COMMENT ON COLUMN public.factory_legal_diagnosis_profile.business_activity_types IS
    'NULL=미확인 / []=명시적 없음(M2). Marketing multi_select vocabulary subset.';
COMMENT ON COLUMN public.factory_legal_diagnosis_profile.hazardous_work_environments IS
    'NULL=미확인 / []=명시적 없음(M2). Marketing multi_select vocabulary subset.';

-- P5: no separate ix_fldp_factory_id — UNIQUE(factory_id) already provides the index.

-- updated_at touch trigger (defensive; server also sets updated_at)
CREATE OR REPLACE FUNCTION public.fn_fldp_touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $tg$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$tg$;

DROP TRIGGER IF EXISTS trg_fldp_touch_updated_at ON public.factory_legal_diagnosis_profile;
CREATE TRIGGER trg_fldp_touch_updated_at
    BEFORE UPDATE ON public.factory_legal_diagnosis_profile
    FOR EACH ROW EXECUTE FUNCTION public.fn_fldp_touch_updated_at();

-- P3 server-only access: RLS enabled with NO policies; service_role only (bypasses RLS).
-- Direct authenticated/anon Supabase access intentionally NOT opened (Safe access path =
-- tai-api authenticated route -> services/company_scope ownership -> service_role DB access).
ALTER TABLE public.factory_legal_diagnosis_profile ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.factory_legal_diagnosis_profile FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.factory_legal_diagnosis_profile TO service_role;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2) factory_process — process-level legal supplemental columns
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.factory_process
    ADD COLUMN IF NOT EXISTS legal_hazard_codes   text[],
    ADD COLUMN IF NOT EXISTS legal_worker_count   integer,
    ADD COLUMN IF NOT EXISTS legal_activity_types text[];

-- M3 legal_worker_count >= 0 or NULL (idempotent; P4 conrelid-scoped existence check)
DO $wc$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_factory_process_legal_worker_count'
          AND conrelid = 'public.factory_process'::regclass
    ) THEN
        ALTER TABLE public.factory_process
            ADD CONSTRAINT ck_factory_process_legal_worker_count
            CHECK (legal_worker_count IS NULL OR legal_worker_count >= 0);
    END IF;
END
$wc$;

COMMENT ON COLUMN public.factory_process.legal_hazard_codes IS
    'WO-SAFE-LEGAL-IND-IMPLEMENT-001: Marketing process_list.hazard_codes[]. NULL=미확인/[]=명시적 없음(M2).';
COMMENT ON COLUMN public.factory_process.legal_worker_count IS
    'WO-SAFE-LEGAL-IND-IMPLEMENT-001: Marketing process_list.worker_count (>=0 or NULL).';
COMMENT ON COLUMN public.factory_process.legal_activity_types IS
    'WO-SAFE-LEGAL-IND-IMPLEMENT-001: Marketing process_list.activity_type[]. NULL=미확인/[]=명시적 없음(M2).';

-- ─────────────────────────────────────────────────────────────────────────────
-- 3) equipment_assets — equipment-level legal supplemental columns
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.equipment_assets
    ADD COLUMN IF NOT EXISTS legal_usage_types    text[],
    ADD COLUMN IF NOT EXISTS legal_relation_types text[];

COMMENT ON COLUMN public.equipment_assets.legal_usage_types IS
    'WO-SAFE-LEGAL-IND-IMPLEMENT-001: Marketing equipment_list.usage_type[]. NULL=미확인/[]=명시적 없음(M2).';
COMMENT ON COLUMN public.equipment_assets.legal_relation_types IS
    'WO-SAFE-LEGAL-IND-IMPLEMENT-001: Marketing equipment_list.relation_type[]. NULL=미확인/[]=명시적 없음(M2).';

COMMIT;
