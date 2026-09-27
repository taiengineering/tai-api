-- WO-PAID-LEG-FRONT-PARITY-IMPLEMENT-001 PATCH-D (R1 revised)
-- paid diagnosis_input_fields parity: BUILDING +3 / INDUSTRIAL +1 / CONSTRUCTION +13 / visibility +2×3
-- PRODUCTION_DB_WRITE = 0 (Owner Approval 후 별도 execution)
--
-- MIGRATION MODE = EXACT-BEFORE / FAIL-CLOSED / ONE-TIME
--   PRECHECK: all 17 new rows absent, all 6 visibility rows have NULL.
--   If any precheck fails → RAISE EXCEPTION → rollback.
--   ON CONFLICT DO NOTHING = defensive guard only, NOT idempotency guarantee.
--
-- EXPECTED BEFORE:
--   BUILDING/PAID  = 45 active rows (missing: has_high_pressure_gas, has_chemical_substance, has_hazardous_material)
--   INDUSTRIAL/PAID1 = existing rows (missing: building_use_type)
--   CONSTRUCTION/PAID = 20 active rows (missing: 13 SEM-003 + HPCC axes)
--   truck_loading_height_m.visibility_condition  = NULL  for BUILDING/PAID, INDUSTRIAL/PAID1, CONSTRUCTION/PAID
--   manual_handling_weight_kg.visibility_condition = NULL  for BUILDING/PAID, INDUSTRIAL/PAID1, CONSTRUCTION/PAID
--
-- EXPECTED AFTER:
--   BUILDING/PAID  → 48 active rows (+3)
--   INDUSTRIAL/PAID1 → +1 row (building_use_type with input_options copied from INDUSTRIAL/FREE source)
--   CONSTRUCTION/PAID → 33 active rows (+13)
--   truck_loading_height_m.visibility_condition  = {"field_code":"has_truck_loading_unloading","op":"eq","value":true}
--     for BUILDING/PAID, INDUSTRIAL/PAID1, CONSTRUCTION/PAID (3 rows exact)
--   manual_handling_weight_kg.visibility_condition = {"field_code":"has_manual_heavy_handling","op":"eq","value":true}
--     for BUILDING/PAID, INDUSTRIAL/PAID1, CONSTRUCTION/PAID (3 rows exact)
--
-- NO delete, NO deactivate, NO sector-move, NO update to other rows.

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════
-- PRECHECK-1: confirm all 17 new rows are absent
-- ═══════════════════════════════════════════════════════════════════════════
DO $$
DECLARE v_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO v_count
  FROM public.diagnosis_input_fields
  WHERE (sector, tier, field_code) IN (
    -- BUILDING +3
    ('BUILDING','PAID','has_high_pressure_gas'),
    ('BUILDING','PAID','has_chemical_substance'),
    ('BUILDING','PAID','has_hazardous_material'),
    -- INDUSTRIAL +1
    ('INDUSTRIAL','PAID1','building_use_type'),
    -- CONSTRUCTION +13
    ('CONSTRUCTION','PAID','has_scuba_diving'),
    ('CONSTRUCTION','PAID','has_surface_supplied_diving'),
    ('CONSTRUCTION','PAID','has_pressure_adjustment_chamber'),
    ('CONSTRUCTION','PAID','supplies_air_to_diver_from_air_compressor'),
    ('CONSTRUCTION','PAID','supplies_breathing_gas_to_diver_from_cylinder'),
    ('CONSTRUCTION','PAID','breathing_gas_cylinder_pressure_kgf_cm2'),
    ('CONSTRUCTION','PAID','diving_depth_m'),
    ('CONSTRUCTION','PAID','diving_surface_ascent_restricted'),
    ('CONSTRUCTION','PAID','diving_decompression_stop_required'),
    ('CONSTRUCTION','PAID','has_high_pressure_work'),
    ('CONSTRUCTION','PAID','has_air_compressor'),
    ('CONSTRUCTION','PAID','supplies_air_to_high_pressure_workroom_or_airlock'),
    ('CONSTRUCTION','PAID','has_caisson_work')
  );
  IF v_count > 0 THEN
    RAISE EXCEPTION 'PRECHECK-1 FAILED: % of 17 target rows already exist. This is an exact-before migration. ABORT.', v_count;
  END IF;
  RAISE NOTICE 'PRECHECK-1 OK: all 17 new rows absent';
END $$;

-- ═══════════════════════════════════════════════════════════════════════════
-- PRECHECK-2: confirm 6 visibility target rows currently have NULL condition
-- ═══════════════════════════════════════════════════════════════════════════
DO $$
DECLARE v_null INTEGER; v_total INTEGER;
BEGIN
  SELECT COUNT(*) INTO v_total
  FROM public.diagnosis_input_fields
  WHERE (sector, tier, field_code) IN (
    ('BUILDING','PAID','truck_loading_height_m'),
    ('INDUSTRIAL','PAID1','truck_loading_height_m'),
    ('CONSTRUCTION','PAID','truck_loading_height_m'),
    ('BUILDING','PAID','manual_handling_weight_kg'),
    ('INDUSTRIAL','PAID1','manual_handling_weight_kg'),
    ('CONSTRUCTION','PAID','manual_handling_weight_kg')
  ) AND is_active = true;

  SELECT COUNT(*) INTO v_null
  FROM public.diagnosis_input_fields
  WHERE (sector, tier, field_code) IN (
    ('BUILDING','PAID','truck_loading_height_m'),
    ('INDUSTRIAL','PAID1','truck_loading_height_m'),
    ('CONSTRUCTION','PAID','truck_loading_height_m'),
    ('BUILDING','PAID','manual_handling_weight_kg'),
    ('INDUSTRIAL','PAID1','manual_handling_weight_kg'),
    ('CONSTRUCTION','PAID','manual_handling_weight_kg')
  ) AND is_active = true AND visibility_condition IS NULL;

  IF v_null != v_total THEN
    RAISE EXCEPTION 'PRECHECK-2 FAILED: % of % visibility target rows already have non-NULL condition. Expected 6/6 NULL. ABORT.', (v_total - v_null), v_total;
  END IF;
  IF v_total != 6 THEN
    RAISE EXCEPTION 'PRECHECK-2 FAILED: expected exactly 6 visibility target rows, found %. ABORT.', v_total;
  END IF;
  RAISE NOTICE 'PRECHECK-2 OK: 6/6 visibility target rows have NULL condition';
END $$;

-- ═══════════════════════════════════════════════════════════════════════════
-- PRECHECK-3: confirm INDUSTRIAL/FREE/building_use_type source row exists (exactly 1)
-- ═══════════════════════════════════════════════════════════════════════════
DO $$
DECLARE v_src INTEGER;
BEGIN
  SELECT COUNT(*) INTO v_src
  FROM public.diagnosis_input_fields
  WHERE sector='INDUSTRIAL' AND tier='FREE' AND field_code='building_use_type' AND is_active=true;
  IF v_src != 1 THEN
    RAISE EXCEPTION 'PRECHECK-3 FAILED: INDUSTRIAL/FREE/building_use_type source row count=% (expected 1). ABORT.', v_src;
  END IF;
  RAISE NOTICE 'PRECHECK-3 OK: INDUSTRIAL/FREE/building_use_type source row confirmed';
END $$;

-- ═══════════════════════════════════════════════════════════════════════════
-- BUILDING/PAID +3: has_high_pressure_gas, has_chemical_substance, has_hazardous_material
-- Authority: SafeBuildingConsumerInput GAS/CHEM G1/C1 comment (schemas/legal_engine.py)
-- Alias 금지: has_gas ≠ has_high_pressure_gas, has_chemical ≠ has_chemical_substance,
--             has_hazmat_storage ≠ has_hazardous_material
-- ═══════════════════════════════════════════════════════════════════════════
INSERT INTO public.diagnosis_input_fields (
  sector, tier, field_group, field_code, field_name, field_type,
  unit, is_required, help_text, sort_order, is_active, visibility_condition
) VALUES
('BUILDING','PAID','가스·위험물','has_high_pressure_gas',
 '고압가스 시설이 있습니까?','boolean',
 NULL, false,
 '고압가스 안전관리법 적용 대상 시설(충전·저장·판매·사용). 도시가스(has_gas)와 별개.',
 910, true, NULL),
('BUILDING','PAID','가스·위험물','has_chemical_substance',
 '유해화학물질을 취급합니까?','boolean',
 NULL, false,
 '화학물질관리법 유해화학물질 해당 여부. has_chemical과 별개(화관법 도급 조항 전용).',
 920, true, NULL),
('BUILDING','PAID','가스·위험물','has_hazardous_material',
 '산안법 위험물(인화성·폭발성 등)을 취급합니까?','boolean',
 NULL, false,
 '산업안전보건법 별표1 위험물(인화성·폭발성·급성독성). 위험물저장소(has_hazmat_storage)와 별개.',
 930, true, NULL)
ON CONFLICT (sector, tier, field_code) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════════
-- INDUSTRIAL/PAID1 +1: building_use_type
-- Authority: SafeIndustrialConsumerInput (schemas/legal_engine.py)
-- input_options: copied from INDUSTRIAL/FREE/building_use_type (authoritative source).
-- PRECHECK-3 above guarantees exactly 1 source row.
-- ═══════════════════════════════════════════════════════════════════════════
INSERT INTO public.diagnosis_input_fields (
  sector, tier, field_group, field_code, field_name, field_type,
  unit, is_required, help_text, sort_order, is_active, visibility_condition,
  input_options
)
SELECT
  'INDUSTRIAL', 'PAID1', '기본정보', 'building_use_type',
  src.field_name, 'select',
  NULL, false,
  '사업장 건물의 주 용도 (건축법 기준). 관련 소방·건축 의무 판정에 사용.',
  910, true, NULL,
  src.input_options
FROM public.diagnosis_input_fields src
WHERE src.sector = 'INDUSTRIAL'
  AND src.tier = 'FREE'
  AND src.field_code = 'building_use_type'
  AND src.is_active = true
ON CONFLICT (sector, tier, field_code) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════════
-- CONSTRUCTION/PAID +13: SEM-003 Diving (9) + HPCC (4)
-- Authority: SafeConstructionConsumerInput (schemas/legal_engine.py)
-- Conditional hierarchy per WO §20:
--   has_diving=true → has_scuba_diving, has_surface_supplied_diving,
--                     supplies_air_to_diver_from_air_compressor,
--                     supplies_breathing_gas_to_diver_from_cylinder
--   supplies_breathing_gas_to_diver_from_cylinder=true → breathing_gas_cylinder_pressure_kgf_cm2
--   has_surface_supplied_diving=true → diving_depth_m, diving_surface_ascent_restricted,
--                                      diving_decompression_stop_required
--   has_pressure_adjustment_chamber: HP common, standalone (NULL visibility)
--   has_high_pressure_work=true → supplies_air_to_high_pressure_workroom_or_airlock, has_caisson_work
--   has_air_compressor: HP common, standalone (NULL visibility)
-- ═══════════════════════════════════════════════════════════════════════════
INSERT INTO public.diagnosis_input_fields (
  sector, tier, field_group, field_code, field_name, field_type,
  unit, is_required, help_text, sort_order, is_active, visibility_condition
) VALUES
-- ── 잠수작업 세부 ────────────────────────────────────────────────────────────
('CONSTRUCTION','PAID','잠수작업','has_scuba_diving',
 '스쿠버 잠수 방식을 사용합니까?','boolean',
 NULL, false, NULL,
 910, true,
 '{"field_code":"has_diving","op":"eq","value":true}'::jsonb),

('CONSTRUCTION','PAID','잠수작업','has_surface_supplied_diving',
 '수면공급식 잠수 방식을 사용합니까?','boolean',
 NULL, false, NULL,
 920, true,
 '{"field_code":"has_diving","op":"eq","value":true}'::jsonb),

('CONSTRUCTION','PAID','잠수작업','supplies_air_to_diver_from_air_compressor',
 '공기압축기로 잠수자에게 공기를 공급합니까?','boolean',
 NULL, false, NULL,
 930, true,
 '{"field_code":"has_diving","op":"eq","value":true}'::jsonb),

('CONSTRUCTION','PAID','잠수작업','supplies_breathing_gas_to_diver_from_cylinder',
 '고압기체용기로 잠수자에게 호흡가스를 공급합니까?','boolean',
 NULL, false, NULL,
 940, true,
 '{"field_code":"has_diving","op":"eq","value":true}'::jsonb),

('CONSTRUCTION','PAID','잠수작업','breathing_gas_cylinder_pressure_kgf_cm2',
 '호흡용 기체용기 최고충전압력 (kgf/cm²)','number',
 'kgf/cm²', false, NULL,
 950, true,
 '{"field_code":"supplies_breathing_gas_to_diver_from_cylinder","op":"eq","value":true}'::jsonb),

('CONSTRUCTION','PAID','잠수작업','diving_depth_m',
 '잠수 최대 심도 (m)','number',
 'm', false, NULL,
 960, true,
 '{"field_code":"has_surface_supplied_diving","op":"eq","value":true}'::jsonb),

('CONSTRUCTION','PAID','잠수작업','diving_surface_ascent_restricted',
 '수면 급부상 제한이 있습니까?','boolean',
 NULL, false, NULL,
 970, true,
 '{"field_code":"has_surface_supplied_diving","op":"eq","value":true}'::jsonb),

('CONSTRUCTION','PAID','잠수작업','diving_decompression_stop_required',
 '감압 정지가 필요합니까?','boolean',
 NULL, false, NULL,
 980, true,
 '{"field_code":"has_surface_supplied_diving","op":"eq","value":true}'::jsonb),

-- ── 이상기압작업 ─────────────────────────────────────────────────────────────
('CONSTRUCTION','PAID','이상기압작업','has_pressure_adjustment_chamber',
 '기압조절실을 사용합니까?','boolean',
 NULL, false, NULL,
 990, true, NULL),

('CONSTRUCTION','PAID','이상기압작업','has_high_pressure_work',
 '이상기압(고압) 작업이 있습니까?','boolean',
 NULL, false, NULL,
 1000, true, NULL),

('CONSTRUCTION','PAID','이상기압작업','has_air_compressor',
 '공기압축기를 사용합니까?','boolean',
 NULL, false, NULL,
 1010, true, NULL),

('CONSTRUCTION','PAID','이상기압작업','supplies_air_to_high_pressure_workroom_or_airlock',
 '작업실 또는 기압조절실에 공기를 공급합니까?','boolean',
 NULL, false, NULL,
 1020, true,
 '{"field_code":"has_high_pressure_work","op":"eq","value":true}'::jsonb),

('CONSTRUCTION','PAID','이상기압작업','has_caisson_work',
 '잠함(케이슨) 공법을 사용합니까?','boolean',
 NULL, false, NULL,
 1030, true,
 '{"field_code":"has_high_pressure_work","op":"eq","value":true}'::jsonb)

ON CONFLICT (sector, tier, field_code) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════════
-- VISIBILITY UPDATE: truck/manual child fields — exact 3 paid sectors only
-- Target: (BUILDING/PAID), (INDUSTRIAL/PAID1), (CONSTRUCTION/PAID) — 3 rows each = 6 total
-- Before (confirmed by PRECHECK-2): visibility_condition IS NULL
-- After:  truck_loading_height_m  → has_truck_loading_unloading == true
--         manual_handling_weight_kg → has_manual_heavy_handling == true
-- ═══════════════════════════════════════════════════════════════════════════
UPDATE public.diagnosis_input_fields
SET visibility_condition = '{"field_code":"has_truck_loading_unloading","op":"eq","value":true}'::jsonb
WHERE (sector, tier, field_code) IN (
  ('BUILDING','PAID','truck_loading_height_m'),
  ('INDUSTRIAL','PAID1','truck_loading_height_m'),
  ('CONSTRUCTION','PAID','truck_loading_height_m')
) AND is_active = true;

UPDATE public.diagnosis_input_fields
SET visibility_condition = '{"field_code":"has_manual_heavy_handling","op":"eq","value":true}'::jsonb
WHERE (sector, tier, field_code) IN (
  ('BUILDING','PAID','manual_handling_weight_kg'),
  ('INDUSTRIAL','PAID1','manual_handling_weight_kg'),
  ('CONSTRUCTION','PAID','manual_handling_weight_kg')
) AND is_active = true;

-- ═══════════════════════════════════════════════════════════════════════════
-- POSTCHECK (exact counts — no >= shorthand)
-- ═══════════════════════════════════════════════════════════════════════════
DO $$
DECLARE
  v_building   INTEGER;
  v_industrial INTEGER;
  v_construction INTEGER;
  v_truck      INTEGER;
  v_manual     INTEGER;
BEGIN
  SELECT COUNT(*) INTO v_building
  FROM public.diagnosis_input_fields
  WHERE sector='BUILDING' AND tier='PAID' AND is_active=true
    AND field_code IN ('has_high_pressure_gas','has_chemical_substance','has_hazardous_material');

  SELECT COUNT(*) INTO v_industrial
  FROM public.diagnosis_input_fields
  WHERE sector='INDUSTRIAL' AND tier='PAID1' AND is_active=true
    AND field_code = 'building_use_type';

  SELECT COUNT(*) INTO v_construction
  FROM public.diagnosis_input_fields
  WHERE sector='CONSTRUCTION' AND tier='PAID' AND is_active=true
    AND field_code IN (
      'has_scuba_diving','has_surface_supplied_diving','has_pressure_adjustment_chamber',
      'supplies_air_to_diver_from_air_compressor','supplies_breathing_gas_to_diver_from_cylinder',
      'breathing_gas_cylinder_pressure_kgf_cm2','diving_depth_m','diving_surface_ascent_restricted',
      'diving_decompression_stop_required','has_high_pressure_work','has_air_compressor',
      'supplies_air_to_high_pressure_workroom_or_airlock','has_caisson_work'
    );

  SELECT COUNT(*) INTO v_truck
  FROM public.diagnosis_input_fields
  WHERE (sector, tier, field_code) IN (
    ('BUILDING','PAID','truck_loading_height_m'),
    ('INDUSTRIAL','PAID1','truck_loading_height_m'),
    ('CONSTRUCTION','PAID','truck_loading_height_m')
  ) AND is_active=true
    AND visibility_condition->>'field_code' = 'has_truck_loading_unloading';

  SELECT COUNT(*) INTO v_manual
  FROM public.diagnosis_input_fields
  WHERE (sector, tier, field_code) IN (
    ('BUILDING','PAID','manual_handling_weight_kg'),
    ('INDUSTRIAL','PAID1','manual_handling_weight_kg'),
    ('CONSTRUCTION','PAID','manual_handling_weight_kg')
  ) AND is_active=true
    AND visibility_condition->>'field_code' = 'has_manual_heavy_handling';

  RAISE NOTICE 'POSTCHECK: BUILDING=% (expect 3), INDUSTRIAL=% (expect 1), CONSTRUCTION=% (expect 13), truck_vis=% (expect 3), manual_vis=% (expect 3)',
    v_building, v_industrial, v_construction, v_truck, v_manual;

  IF v_building     != 3  THEN RAISE EXCEPTION 'BUILDING new rows mismatch: % (expect 3)', v_building; END IF;
  IF v_industrial   != 1  THEN RAISE EXCEPTION 'INDUSTRIAL new rows mismatch: % (expect 1)', v_industrial; END IF;
  IF v_construction != 13 THEN RAISE EXCEPTION 'CONSTRUCTION new rows mismatch: % (expect 13)', v_construction; END IF;
  IF v_truck        != 3  THEN RAISE EXCEPTION 'truck visibility mismatch: % (expect 3)', v_truck; END IF;
  IF v_manual       != 3  THEN RAISE EXCEPTION 'manual visibility mismatch: % (expect 3)', v_manual; END IF;

  RAISE NOTICE 'POSTCHECK OK: all 5 counts match';
END $$;

COMMIT;
