-- WO-SAFE-LEGAL-IND-CANONICAL-IMPLEMENT-001 / STEP3B-IMPL — canonical vocabulary (UP)
--
-- Safe actual factory fact 전용 controlled vocabulary. Marketing diagnosis_input_fields 는 SoT 아님.
-- 4 category / 15 item (A business 7, B hazard 3, C composition 4, D designation 1).
-- 저장 금지(별도 처리): 의무관리대상 공동주택(LEGAL DERIVED) / 안전성평가 대상시설(LEGAL DERIVED) /
--   제조소등·개인하수처리시설(existing-source CONDITIONAL derive) / 배출·방지·공동방지(equipment CONDITIONAL derive) /
--   전기·기계·계측 복합(COMPOSITE derive). → system_codes INSERT 0.
-- UNIQUE(category, code) 기준 idempotent: ON CONFLICT DO NOTHING(기존 row overwrite 금지).
-- APPLY POLICY: artifact only. ACTUAL DB INSERT = BLOCKED until GPT PASS + operator apply.

BEGIN;

INSERT INTO public.system_codes
    (category, category_name, code, code_name, description, sort_order, is_active, is_system, depth, state)
VALUES
    -- A. factory_business_activity (실제 사업활동 유형) — 7
    ('factory_business_activity','사업장 사업활동','REMODEL_OPERATION','리모델링 수행',
     '사업장이 실제 리모델링 사업을 수행하는 사실', 1, true, true, 1, '사용'),
    ('factory_business_activity','사업장 사업활동','DEVELOPMENT_PLAN_EXECUTION','개발계획 수립·이행',
     '사업장이 개발계획을 수립·이행하는 사실', 2, true, true, 1, '사용'),
    ('factory_business_activity','사업장 사업활동','ELECTRICITY_USER_SUPPLY','전기사용자 공급',
     '사업장이 전기사용자에게 공급하는 사실', 3, true, true, 1, '사용'),
    ('factory_business_activity','사업장 사업활동','PUBLIC_SEWER_OPERATION','공공하수도 운영·관리',
     '사업장이 공공하수도를 운영·관리하는 사실', 4, true, true, 1, '사용'),
    ('factory_business_activity','사업장 사업활동','BUSINESS_FACILITY_ACQUIRE_LEASE','영업시설 양수·임차 사용',
     '사업장이 영업시설을 양수 또는 임차하여 사용하는 사실', 5, true, true, 1, '사용'),
    ('factory_business_activity','사업장 사업활동','COMPLEX_DEVELOPMENT_PROJECT','단지조성사업 시행',
     '사업장이 단지조성사업을 시행하는 사실', 6, true, true, 1, '사용'),
    ('factory_business_activity','사업장 사업활동','EMISSION_FACILITY_OPERATION','배출시설 운영',
     '사업장이 배출시설을 운영하는 사실', 7, true, true, 1, '사용'),

    -- B. factory_hazardous_environment (실제 유해작업환경) — 3
    ('factory_hazardous_environment','사업장 유해작업환경','INDOOR_HIGH_HEAT','고열작업(실내)',
     '사업장 실내에 고열작업 환경이 존재하는 사실', 1, true, true, 1, '사용'),
    ('factory_hazardous_environment','사업장 유해작업환경','CONTAMINATED_AREA_WORK','오염된 지역 작업',
     '사업장에 오염된 지역 작업 환경이 존재하는 사실', 2, true, true, 1, '사용'),
    ('factory_hazardous_environment','사업장 유해작업환경','FIRE_EXPLOSION_HAZARD_AREA','화재·폭발 위험장소',
     '사업장에 화재·폭발 위험장소가 존재하는 사실', 3, true, true, 1, '사용'),

    -- C. factory_building_composition (실제 건물·단지 구성) — 4 (의무관리대상=LEGAL DERIVED, 미포함)
    ('factory_building_composition','건물·단지 구성','ROWHOUSE_MULTIFAMILY_COEXISTENCE','단지형 연립/다세대 병존',
     '단지형 연립주택과 다세대주택이 병존하는 실제 구성', 1, true, true, 1, '사용'),
    ('factory_building_composition','건물·단지 구성','URBAN_LIVING_OTHER_HOUSING_MIXED','도시형생활주택·타주택 복합',
     '도시형생활주택과 타주택이 복합된 실제 구성', 2, true, true, 1, '사용'),
    ('factory_building_composition','건물·단지 구성','URBAN_LIVING_OTHER_HOUSING_COEXISTENCE','도시형생활주택·타주택 병존',
     '도시형생활주택과 타주택이 병존하는 실제 구성', 3, true, true, 1, '사용'),
    ('factory_building_composition','건물·단지 구성','BASEMENT_COMMUNITY_FACILITY_USE','지하층 주민공동시설 활용',
     '지하층을 주민공동시설로 활용하는 실제 구성', 4, true, true, 1, '사용'),

    -- D. factory_regulatory_designation (실제 행정 지정) — 1 (나머지 6개는 reuse/derive/legal, 미포함)
    ('factory_regulatory_designation','사업장 행정 지정','SOIL_CONTAMINATION_MANAGEMENT_DESIGNATION','특정토양오염관리대상시설',
     '사업장이 행정적으로 특정토양오염관리대상시설로 지정된 사실', 1, true, true, 1, '사용')
ON CONFLICT (category, code) DO NOTHING;

COMMIT;
