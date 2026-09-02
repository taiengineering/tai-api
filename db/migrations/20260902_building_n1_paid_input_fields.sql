-- WO-BLD-MKT-CONSUMER-INPUT-WIRING-016 STEP-2 (ARTIFACT ONLY -- DO NOT EXECUTE without verifier gate)
-- BUILDING + PAID only. FREE/INDUSTRIAL/CONSTRUCTION delta = 0. idempotent. destructive update 0.
-- 31 new raw primitive(optional) + building_use_type option '오피스텔' append.
-- WP-C applicable.py frozen tree Leaf.field 와 exact 일치. raw fact only.
BEGIN;

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','building_height_m','건축물 높이','number',NULL,'m',false,true,100
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='building_height_m');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','floor_area_sum_at_or_above_11f','11층 이상 층 바닥면적 합계','number',NULL,'㎡',false,true,101
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='floor_area_sum_at_or_above_11f');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','performance_use_floor_area_sum','공연·집회·관람·전시 용도 바닥면적 합계','number',NULL,'㎡',false,true,102
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='performance_use_floor_area_sum');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','cantilever_projection_m','캔틸레버 돌출 길이','number',NULL,'m',false,true,103
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='cantilever_projection_m');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','column_span_m','기둥 간 최대 스팬','number',NULL,'m',false,true,104
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='column_span_m');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','flat_plate_column_section_ratio','무량판 기둥 단면적 비율(0~1)','number',NULL,NULL,false,true,105
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='flat_plate_column_section_ratio');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','occupancy_capacity','수용 인원','number',NULL,'명',false,true,106
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='occupancy_capacity');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','underground_connection_entrance_distance_m','지하 연결 출입구 간 거리','number',NULL,'m',false,true,107
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='underground_connection_entrance_distance_m');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','connection_open_space_floor_area_m2','연결 공지 바닥면적','number',NULL,'㎡',false,true,108
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='connection_open_space_floor_area_m2');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','connection_open_space_open_area_ratio','연결 공지 개방면적 비율(0~1)','number',NULL,NULL,false,true,109
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='connection_open_space_open_area_ratio');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','stair_or_ramp_effective_width_m','계단·경사로 유효 폭','number',NULL,'m',false,true,110
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='stair_or_ramp_effective_width_m');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','building_activity_type','건축 행위 유형','select','[{"label": "건축", "value": "건축"}, {"label": "대수선", "value": "대수선"}]'::jsonb,NULL,false,true,111
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='building_activity_type');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','building_use_category','건축물 용도 분류','select','[{"label": "CULTURE_ASSEMBLY", "value": "CULTURE_ASSEMBLY"}, {"label": "RETAIL", "value": "RETAIL"}, {"label": "TRANSPORT", "value": "TRANSPORT"}, {"label": "OFFICE", "value": "OFFICE"}, {"label": "LODGING", "value": "LODGING"}, {"label": "THEME_PARK", "value": "THEME_PARK"}, {"label": "GENERAL_HOSPITAL", "value": "GENERAL_HOSPITAL"}, {"label": "GERIATRIC_HOSPITAL", "value": "GERIATRIC_HOSPITAL"}]'::jsonb,NULL,false,true,112
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='building_use_category');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_performance_assembly_use','공연·집회·관람 용도 포함 여부','boolean',NULL,NULL,false,true,113
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_performance_assembly_use');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','is_target_facility_in_basement','해당 시설이 지하층에 있는지','boolean',NULL,NULL,false,true,114
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='is_target_facility_in_basement');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_gas_boiler_heating_system','가스보일러 난방설비 여부','boolean',NULL,NULL,false,true,115
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_gas_boiler_heating_system');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_centralized_gas_supply','중앙집중식 가스공급 여부','boolean',NULL,NULL,false,true,116
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_centralized_gas_supply');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','is_collapse_risk_land','손궤(붕괴) 우려가 있는 토지 여부','boolean',NULL,NULL,false,true,117
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='is_collapse_risk_land');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_land_preparation','토지 굴착·성토 등 정지작업 여부','boolean',NULL,NULL,false,true,118
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_land_preparation');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_building_construction_activity','건축(신축·증축 등) 행위 여부','boolean',NULL,NULL,false,true,119
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_building_construction_activity');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_wet_land','습한 토지 여부','boolean',NULL,NULL,false,true,120
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_wet_land');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_water_seepage_risk','물이 스며들 우려가 있는 토지 여부','boolean',NULL,NULL,false,true,121
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_water_seepage_risk');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_landfill_or_similar_ground','매립지 등 유사 지반 여부','boolean',NULL,NULL,false,true,122
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_landfill_or_similar_ground');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_flat_plate_structure','무량판 구조 여부','boolean',NULL,NULL,false,true,123
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_flat_plate_structure');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','authority_designated_special_structure','관계기관이 지정·고시한 특수구조 여부','boolean',NULL,NULL,false,true,124
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='authority_designated_special_structure');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','article32_3_alternative_confirmation_subject','제32조의3 대체확인 대상 여부','boolean',NULL,NULL,false,true,125
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='article32_3_alternative_confirmation_subject');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_wall_between_connection_entrances','연결 출입구 사이 벽체 유무','boolean',NULL,NULL,false,true,126
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_wall_between_connection_entrances');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','wall_between_connection_entrances_is_fire_resistant','해당 벽체가 내화구조인지','boolean',NULL,NULL,false,true,127
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='wall_between_connection_entrances_is_fire_resistant');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_stair_or_ramp_in_open_space','연결 공지 내 계단·경사로 유무','boolean',NULL,NULL,false,true,128
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_stair_or_ramp_in_open_space');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','is_connected_to_subway_or_underground_mall','지하철·지하도상가와 연결 여부','boolean',NULL,NULL,false,true,129
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='is_connected_to_subway_or_underground_mall');

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_group, field_code, field_name, field_type, input_options, unit, is_required, is_active, sort_order)
SELECT 'BUILDING','PAID','건축물 N1','has_hazardous_material_in_out_event','유해물질 반출입 행위 여부','boolean',NULL,NULL,false,true,130
WHERE NOT EXISTS (SELECT 1 FROM public.diagnosis_input_fields WHERE sector='BUILDING' AND tier='PAID' AND field_code='has_hazardous_material_in_out_event');

-- building_use_type: '오피스텔' exact option append (destructive 0, dedup)
UPDATE public.diagnosis_input_fields
SET input_options = input_options || '[{"label":"오피스텔","value":"오피스텔"}]'::jsonb
WHERE sector='BUILDING' AND tier='PAID' AND field_code='building_use_type'
  AND NOT (input_options @> '[{"value":"오피스텔"}]'::jsonb);

COMMIT;
