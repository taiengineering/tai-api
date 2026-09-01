-- WO-SAFE-LEGAL-BLD-CANONICAL-IMPLEMENT-001 / STEP2 — BUILDING factories canonical extension (UP)
--
-- BUILDING Marketing 36 중 C EXTEND_EXISTING_ASSET 10개(실제 건물/시설 사실)만 기존 canonical root
-- public.factories 에 추가한다. 신규 BUILDING profile/table 미생성. buildings/facility_profiles 미접촉.
-- NULL=unknown / false=explicit no / 0=actual zero / []=explicit none. boolean·numeric·array DEFAULT 금지.
-- water_tank_ton 만 NULL 허용·음수 거부 CHECK. multi_use_type 은 text[](vocabulary/CHECK 미생성).
-- C5 5개(work_height_m 등)는 기존 INDUSTRIAL migration 설계분 → 여기서 중복 추가 0. E5 저장 0. has_chemical 추가 0.
-- backfill(UPDATE/INSERT/DELETE) 0. APPLY POLICY: artifact only. DB APPLY = BLOCKED until GPT PASS + operator apply.

BEGIN;

ALTER TABLE public.factories
    ADD COLUMN IF NOT EXISTS has_sprinkler            boolean,
    ADD COLUMN IF NOT EXISTS has_fire_hydrant         boolean,
    ADD COLUMN IF NOT EXISTS has_emergency_broadcast  boolean,
    ADD COLUMN IF NOT EXISTS has_emergency_gen        boolean,
    ADD COLUMN IF NOT EXISTS has_gas                  boolean,
    ADD COLUMN IF NOT EXISTS has_hazmat_storage       boolean,
    ADD COLUMN IF NOT EXISTS has_water_tank           boolean,
    ADD COLUMN IF NOT EXISTS water_tank_ton           numeric,
    ADD COLUMN IF NOT EXISTS multi_use_type           text[],
    ADD COLUMN IF NOT EXISTS has_smoke_control        boolean;

-- numeric CHECK (NULL 허용, 음수 거부; idempotent conrelid-scoped) — EXACT 1
DO $ck$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_factories_water_tank_ton' AND conrelid='public.factories'::regclass) THEN
        ALTER TABLE public.factories ADD CONSTRAINT ck_factories_water_tank_ton
            CHECK (water_tank_ton IS NULL OR water_tank_ton >= 0);
    END IF;
END
$ck$;

COMMENT ON COLUMN public.factories.has_sprinkler IS
    'WO-BLD-CANONICAL STEP2: 스프링클러 실제 설치 여부. NULL=미확인 / false=명시적 미설치. 법적 설치의무 판정 아님.';
COMMENT ON COLUMN public.factories.has_fire_hydrant IS
    'WO-BLD-CANONICAL STEP2: 옥내소화전 실제 설치 여부. NULL=미확인 / false=명시적 미설치.';
COMMENT ON COLUMN public.factories.has_emergency_broadcast IS
    'WO-BLD-CANONICAL STEP2: 비상방송설비 실제 설치 여부. NULL=미확인 / false=명시적 미설치.';
COMMENT ON COLUMN public.factories.has_emergency_gen IS
    'WO-BLD-CANONICAL STEP2: 비상발전기 실제 설치 여부. NULL=미확인 / false=명시적 미설치.';
COMMENT ON COLUMN public.factories.has_gas IS
    'WO-BLD-CANONICAL STEP2: 시설의 일반 가스 사용 사실. 고압가스(has_high_pressure_gas)와 별도. NULL=미확인. 용량으로 파생 금지.';
COMMENT ON COLUMN public.factories.has_hazmat_storage IS
    'WO-BLD-CANONICAL STEP2: 위험물 저장시설 실제 보유 여부. is_hazardous_material(취급)과 별도. NULL=미확인.';
COMMENT ON COLUMN public.factories.has_water_tank IS
    'WO-BLD-CANONICAL STEP2: 물탱크 실제 설치 여부. water_tank_ton 과 개별 fact. NULL=미확인 / false=명시적 미설치.';
COMMENT ON COLUMN public.factories.water_tank_ton IS
    'WO-BLD-CANONICAL STEP2: 물탱크 용량(ton). 0=actual zero / NULL=미확인. has_water_tank 와 개별 fact.';
COMMENT ON COLUMN public.factories.multi_use_type IS
    'WO-BLD-CANONICAL STEP2: 실제 다중이용 업종 입력값(다중, text[]). 법적 다중이용업소 판정 결과 아님. vocabulary 미확정. NULL=미확인 / []=명시적 없음.';
COMMENT ON COLUMN public.factories.has_smoke_control IS
    'WO-BLD-CANONICAL STEP2: 제연설비 실제 설치 여부. NULL=미확인 / false=명시적 미설치.';

COMMIT;
