-- SAFE INDUSTRIAL 자산: 공장 사용물질 (factory_materials) — NEW ASSET SCHEMA
--
-- 배경
--   SAFE 산업 법령진단(POST /legal-engine/diagnose/industrial-leg)의 canonical assembler
--   (services/safe_industrial_canonical_assembler.py)가 material_profile 을 조립하기 위해
--   factory_materials 를 READ-ONLY 로 조회하나, 이 테이블이 존재한 적이 없어 PGRST205 로
--   진단이 500 실패한다. 이번에 SAFE 산업 자산 모델의 신규 테이블로 최초 도입한다.
--
--   성격 = NEW ASSET SCHEMA IMPLEMENTATION (누락 복구/원본 복원 아님).
--
-- 소비 계약 (assembler physical contract, frozen)
--   FILTER: factory_id, is_active = true
--   READ  : material_name, material_category_code, handling_mode_codes, is_active
--   semantic:
--     0 active row            -> material_profile = None (정상, 진단 계속)
--     material_category_code NULL -> material_profile UNRESOLVED
--     handling_mode_codes NULL    -> NULL 보존 (미확인)
--     handling_mode_codes []      -> [] 보존 (확인했으나 해당 취급방식 없음)
--   => NULL != [] 를 구분해야 하므로 text[] 를 정본으로 한다(jsonb 아님).
--
-- 보안 (WO-SAFE-IND-ASSET-MATERIALS-001 §8)
--   자매 자산 테이블의 넓은 접근을 복제하지 않는다. RLS enable + policy 0
--   => anon/authenticated 직접 접근 차단(fail-closed). tai-api service_role 만 접근
--      (service_role 은 RLS 를 우회하므로 backend 읽기/쓰기는 정상).

CREATE TABLE public.factory_materials (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- material row 는 반드시 특정 factory 소속. factory 삭제 시 orphan 을 남기지 않는다.
  factory_id             uuid NOT NULL
                           REFERENCES public.factories(id) ON DELETE CASCADE,

  -- 사람이 보는 물질명 (원천 자산 식별값). 예: 신나, 산소, 도료, 황산, 윤활유
  material_name          text NOT NULL,

  -- 법령진단용 category code. 등록은 됐으나 매핑 전이면 NULL. NULL 을 OTHER/''로 강제 치환 금지.
  material_category_code text NULL,

  -- 취급방식 코드 목록. NULL=미확인, []=확인했으나 없음, {STORAGE,TRANSFER}=명시.
  -- NULL != [] 를 보존해야 하므로 text[] (jsonb 아님).
  handling_mode_codes    text[] NULL,

  -- assembler 는 is_active=true 만 소비한다.
  is_active              boolean NOT NULL DEFAULT true,

  created_at             timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.factory_materials IS
  'SAFE 산업 자산: 공장 사용물질. industrial-leg canonical assembler 의 material_profile 원천';
COMMENT ON COLUMN public.factory_materials.material_category_code IS
  '법령진단용 category code. 매핑 전이면 NULL(강제 치환 금지) -> assembler 에서 material_profile UNRESOLVED';
COMMENT ON COLUMN public.factory_materials.handling_mode_codes IS
  '취급방식 코드 목록. NULL=미확인, []=해당없음, {..}=명시. NULL과 [] 를 구분 보존';

-- assembler query(factory_id = ? AND is_active = true)에 정확히 맞춘 인덱스.
CREATE INDEX factory_materials_factory_active_idx
  ON public.factory_materials (factory_id, is_active);

-- 신규 테이블 보안: RLS enable + policy 0 => 브라우저(anon/authenticated) 직접 접근 차단.
-- tai-api service_role 만 접근(RLS 우회). SAFE UI -> tai-api -> AUTH -> factory ownership -> backend.
ALTER TABLE public.factory_materials ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.factory_materials FROM anon, authenticated;

-- service_role TABLE privilege 를 migration 자체에 명시(환경 default ACL 비의존).
--   RLS bypass 와 TABLE privilege 는 별개이므로 신규 정본에서 직접 부여한다.
GRANT SELECT, INSERT, UPDATE, DELETE
  ON TABLE public.factory_materials
  TO service_role;
