-- WO-SAFE-LEGAL-IND-IMPLEMENT-001-R1 / STEP 2A — SAFE INDUSTRIAL Marketing-Contract Adapter (UP)
--
-- Persist ONLY the Marketing INDUSTRIAL paid contract facts that Safe's existing domain
-- model (factories / factory_process / equipment_assets) does NOT already hold.
-- Contract SoT = tai-www 유료진단 INDUSTRIAL 현재 입력계약. CONTRACT = MKT_IND_PAID_CONTRACT_V1 (29).
--
-- Scope (idempotent, additive only; NO destructive change to foundation objects):
--   1) NEW  factory_legal_diagnosis_profile   (1:1 factories; ADD 7 + facility-level GAP supplements)
--   2) ALTER factory_process   ADD legal_hazard_codes / legal_worker_count / legal_activity_types
--   3) ALTER equipment_assets  ADD legal_usage_types / legal_relation_types
--
-- CORRECTIONS APPLIED (WO-R1):
--   M1  company_id 컬럼 미보존 — ownership = factory_id -> factories.company_id -> user scope (중복 SoT 방지)
--   M2  배열 컬럼 DEFAULT '{}' 금지 — NULL=미확인 / []=명시적 없음 구분 보존
--   M3  numeric CHECK (>=0 또는 NULL): work_height_m / truck_loading_height_m /
--       manual_handling_weight_kg / total_floor_area / factory_process.legal_worker_count
--   M4  material_profile = JSON array of objects, keys ⊆ {material_category, handling_modes}
--   M5  RLS authenticated ownership = factory_id -> factories 관계 (profile.company_id 단순비교 금지)
--
-- NO synthetic default for any diagnosis input (WO §22/§27). Absence stays NULL.
-- false/0/[] are valid values distinct from NULL (WO §27).
-- APPLY POLICY: artifact only. DB APPLY = BLOCKED until GPT PASS-A (WO §42).
-- REVIEW NOTE(GPT): authenticated RLS JWT claim path(company_id) must be convention-confirmed;
--   server path uses service_role (get_supabase) and enforces ownership via services/company_scope.

BEGIN;

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

    -- M4 material_profile shape
    CONSTRAINT ck_fldp_material_profile_shape CHECK (
        material_profile IS NULL
        OR (
            jsonb_typeof(material_profile) = 'array'
            AND NOT EXISTS (
                SELECT 1
                FROM jsonb_array_elements(material_profile) AS e
                WHERE jsonb_typeof(e) <> 'object'
                   OR EXISTS (
                        SELECT 1 FROM jsonb_object_keys(e) AS k
                        WHERE k NOT IN ('material_category', 'handling_modes')
                   )
            )
        )
    )
);

COMMENT ON TABLE public.factory_legal_diagnosis_profile IS
    'WO-SAFE-LEGAL-IND-IMPLEMENT-001: Marketing INDUSTRIAL paid-contract supplemental facts (ADD 7 + facility-level GAP) not held by factories base model. 1:1 with factories. Ownership via factory_id->factories.company_id (no local company_id). Contract=MKT_IND_PAID_CONTRACT_V1.';
COMMENT ON COLUMN public.factory_legal_diagnosis_profile.total_floor_area IS
    '연면적(㎡). 정본 source 없을 때만. building_area/arch_area/층수 산술 추정 금지(WO §22/§24).';
COMMENT ON COLUMN public.factory_legal_diagnosis_profile.material_profile IS
    'JSONB array; 허용 key = material_category, handling_modes 만(WO §11/M4). 임의 key 금지.';
COMMENT ON COLUMN public.factory_legal_diagnosis_profile.ksic_list IS
    '추가 업종(대분류). assembler 가 factories.ksic_code(industry_master 결정적 해석)와 distinct 병합(WO §23). NULL=미확인/[]=명시적 없음(M2).';
COMMENT ON COLUMN public.factory_legal_diagnosis_profile.business_activity_types IS
    'NULL=미확인 / []=명시적 없음(M2). Marketing multi_select vocabulary subset.';
COMMENT ON COLUMN public.factory_legal_diagnosis_profile.hazardous_work_environments IS
    'NULL=미확인 / []=명시적 없음(M2). Marketing multi_select vocabulary subset.';

CREATE INDEX IF NOT EXISTS ix_fldp_factory_id ON public.factory_legal_diagnosis_profile (factory_id);

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

-- M5 RLS: service_role full; authenticated SELECT scoped by factory_id -> factories ownership.
ALTER TABLE public.factory_legal_diagnosis_profile ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.factory_legal_diagnosis_profile FROM PUBLIC, anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.factory_legal_diagnosis_profile TO service_role;

DROP POLICY IF EXISTS p_fldp_service_all ON public.factory_legal_diagnosis_profile;
CREATE POLICY p_fldp_service_all ON public.factory_legal_diagnosis_profile
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS p_fldp_authenticated_company ON public.factory_legal_diagnosis_profile;
CREATE POLICY p_fldp_authenticated_company ON public.factory_legal_diagnosis_profile
    FOR SELECT TO authenticated
    USING (
        factory_id IN (
            SELECT f.id FROM public.factories f
            WHERE f.company_id = (auth.jwt() ->> 'company_id')::uuid
        )
    );

-- ─────────────────────────────────────────────────────────────────────────────
-- 2) factory_process — process-level legal supplemental columns (WO §13)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.factory_process
    ADD COLUMN IF NOT EXISTS legal_hazard_codes   text[],
    ADD COLUMN IF NOT EXISTS legal_worker_count   integer,
    ADD COLUMN IF NOT EXISTS legal_activity_types text[];

-- M3 legal_worker_count >= 0 or NULL (idempotent add)
DO $wc$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_factory_process_legal_worker_count') THEN
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
-- 3) equipment_assets — equipment-level legal supplemental columns (WO §14)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.equipment_assets
    ADD COLUMN IF NOT EXISTS legal_usage_types    text[],
    ADD COLUMN IF NOT EXISTS legal_relation_types text[];

COMMENT ON COLUMN public.equipment_assets.legal_usage_types IS
    'WO-SAFE-LEGAL-IND-IMPLEMENT-001: Marketing equipment_list.usage_type[]. NULL=미확인/[]=명시적 없음(M2).';
COMMENT ON COLUMN public.equipment_assets.legal_relation_types IS
    'WO-SAFE-LEGAL-IND-IMPLEMENT-001: Marketing equipment_list.relation_type[]. NULL=미확인/[]=명시적 없음(M2).';

COMMIT;
