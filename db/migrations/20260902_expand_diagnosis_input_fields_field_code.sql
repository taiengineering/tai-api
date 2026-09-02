-- WO-BLD-MKT-CONSUMER-INPUT-WIRING-016 STEP-3A: field_code 상한 확장.
-- 원인: consumer vocabulary 'wall_between_connection_entrances_is_fire_resistant'(51자)가
--       기존 varchar(50) 초과. 의미/이름/데이터 불변, 컬럼 상한만 확장(저위험).
-- WP-C Leaf.field / build_facility _LEG_INPUT_FIELDS exact-name(51자) 유지. 축약 금지.
ALTER TABLE public.diagnosis_input_fields
ALTER COLUMN field_code TYPE varchar(100);
