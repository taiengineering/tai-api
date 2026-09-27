-- WO-PAID-LEG-FRONT-PARITY-IMPLEMENT-001 PATCH-D — ROLLBACK
-- Reverses 20260927_paid_leg_field_parity_up.sql
-- Removes only the 17 newly inserted rows.
-- Restores visibility_condition to NULL for truck/manual fields.
-- PRODUCTION_DB_WRITE = 0 (Owner Approval 후 별도 execution)

BEGIN;

-- ── BUILDING/PAID: 신규 3개 row 제거 ──
DELETE FROM public.diagnosis_input_fields
WHERE (sector, tier, field_code) IN (
  ('BUILDING','PAID','has_high_pressure_gas'),
  ('BUILDING','PAID','has_chemical_substance'),
  ('BUILDING','PAID','has_hazardous_material')
);

-- ── INDUSTRIAL/PAID1: 신규 1개 row 제거 ──
DELETE FROM public.diagnosis_input_fields
WHERE (sector, tier, field_code) = ('INDUSTRIAL','PAID1','building_use_type');

-- ── CONSTRUCTION/PAID: 신규 13개 row 제거 ──
DELETE FROM public.diagnosis_input_fields
WHERE (sector, tier, field_code) IN (
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

-- ── visibility_condition 원복: NULL 복원 ──
UPDATE public.diagnosis_input_fields
SET visibility_condition = NULL
WHERE field_code = 'truck_loading_height_m'
  AND is_active = true
  AND visibility_condition->>'field_code' = 'has_truck_loading_unloading';

UPDATE public.diagnosis_input_fields
SET visibility_condition = NULL
WHERE field_code = 'manual_handling_weight_kg'
  AND is_active = true
  AND visibility_condition->>'field_code' = 'has_manual_heavy_handling';

-- ── POSTCHECK ──
DO $$
DECLARE v_remain INTEGER;
BEGIN
  SELECT COUNT(*) INTO v_remain
  FROM public.diagnosis_input_fields
  WHERE (sector, tier, field_code) IN (
    ('BUILDING','PAID','has_high_pressure_gas'),
    ('BUILDING','PAID','has_chemical_substance'),
    ('BUILDING','PAID','has_hazardous_material'),
    ('INDUSTRIAL','PAID1','building_use_type'),
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
  IF v_remain != 0 THEN
    RAISE EXCEPTION 'ROLLBACK POSTCHECK FAILED: % rows still exist (expected 0).', v_remain;
  END IF;
  RAISE NOTICE 'ROLLBACK POSTCHECK OK: 0 rows remain';
END $$;

COMMIT;
