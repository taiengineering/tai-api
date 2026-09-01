-- WO-SAFE-LEGAL-IND-CANONICAL-IMPLEMENT-001 / STEP3B-IMPL — canonical vocabulary (DOWN)
-- 이번 WO 가 생성한 4 category / 15 code 만 exact delete. 다른 system_codes 삭제 금지. repeat-safe.
-- APPLY POLICY: artifact only. ACTUAL DB DELETE = BLOCKED.

BEGIN;

DELETE FROM public.system_codes
WHERE (category, code) IN (
    ('factory_business_activity','REMODEL_OPERATION'),
    ('factory_business_activity','DEVELOPMENT_PLAN_EXECUTION'),
    ('factory_business_activity','ELECTRICITY_USER_SUPPLY'),
    ('factory_business_activity','PUBLIC_SEWER_OPERATION'),
    ('factory_business_activity','BUSINESS_FACILITY_ACQUIRE_LEASE'),
    ('factory_business_activity','COMPLEX_DEVELOPMENT_PROJECT'),
    ('factory_business_activity','EMISSION_FACILITY_OPERATION'),
    ('factory_hazardous_environment','INDOOR_HIGH_HEAT'),
    ('factory_hazardous_environment','CONTAMINATED_AREA_WORK'),
    ('factory_hazardous_environment','FIRE_EXPLOSION_HAZARD_AREA'),
    ('factory_building_composition','ROWHOUSE_MULTIFAMILY_COEXISTENCE'),
    ('factory_building_composition','URBAN_LIVING_OTHER_HOUSING_MIXED'),
    ('factory_building_composition','URBAN_LIVING_OTHER_HOUSING_COEXISTENCE'),
    ('factory_building_composition','BASEMENT_COMMUNITY_FACILITY_USE'),
    ('factory_regulatory_designation','SOIL_CONTAMINATION_MANAGEMENT_DESIGNATION')
);

COMMIT;
