-- WO-NUMERIC-FREE-SURFACE-CONTRACT-007 PATCH-3 STEP-2A
-- ARTIFACT ONLY — DO NOT EXECUTE in this WO (DB EXECUTION=0 / DDL EXECUTION=0).
-- PRECHECK (required before apply): exact (sector,tier=FREE,field_code) for all 18 targets MUST be 0.
-- ON CONFLICT DO UPDATE 금지. 기존 PAID/inactive row UPDATE/DELETE/activate/deactivate/sector-move 금지.
--
-- A) schema: visibility_condition jsonb NULL (idempotent)
-- B) INSERT exactly 18 FREE rows (trigger 11 physical + conditional numeric 7)
-- C) POSTCHECK / ROLLBACK templates below

-- ═══════════════════════════════════════════════════════════════════════════
-- A. SCHEMA (idempotent)
-- ═══════════════════════════════════════════════════════════════════════════
ALTER TABLE public.diagnosis_input_fields
  ADD COLUMN IF NOT EXISTS visibility_condition jsonb NULL;

COMMENT ON COLUMN public.diagnosis_input_fields.visibility_condition IS
  'WO-007: NULL=always visible. Recognized: {"field_code":"<parent>","op":"eq","value":true}. Malformed non-null → UI fail-closed hide.';

-- ═══════════════════════════════════════════════════════════════════════════
-- B. PRECHECK (must return 0 before INSERT)
-- ═══════════════════════════════════════════════════════════════════════════
-- SELECT count(*) AS existing_target_rows FROM public.diagnosis_input_fields d
-- WHERE (d.sector, d.tier, d.field_code) IN (
--   ('BUILDING','FREE','has_structure'),('BUILDING','FREE','structure_height_m'),('BUILDING','FREE','has_hazmat_storage'),
--   ('CONSTRUCTION','FREE','has_construction_machine'),('CONSTRUCTION','FREE','construction_machine_weight_ton'),('CONSTRUCTION','FREE','has_hazmat_storage'),
--   ('INDUSTRIAL','FREE','has_scaffold'),('INDUSTRIAL','FREE','scaffold_height_m'),
--   ('INDUSTRIAL','FREE','has_grinding'),('INDUSTRIAL','FREE','grinding_wheel_diameter_cm'),
--   ('INDUSTRIAL','FREE','has_diving'),('INDUSTRIAL','FREE','diving_worker_count'),
--   ('INDUSTRIAL','FREE','has_object_drop'),('INDUSTRIAL','FREE','object_drop_height_m'),
--   ('INDUSTRIAL','FREE','has_high_speed_rotor'),
--   ('INDUSTRIAL','FREE','has_subcontractor'),('INDUSTRIAL','FREE','same_site_construction_count'),
--   ('INDUSTRIAL','FREE','has_hazmat_storage')
-- );
-- → 1+ 이면 STOP (UPSERT 금지). metadata 제출 후 재지시.

-- ═══════════════════════════════════════════════════════════════════════════
-- C. INSERT — exact 18 FREE rows (sector literal = BUILDING|CONSTRUCTION|INDUSTRIAL)
-- ═══════════════════════════════════════════════════════════════════════════
INSERT INTO public.diagnosis_input_fields (
  sector, tier, field_group, field_code, field_name, field_type,
  unit, is_required, help_text, sort_order, is_active, visibility_condition
) VALUES
-- BUILDING (sort 100+)
('BUILDING','FREE','작업·설비 확인','has_structure','건축물·공작물 설비가 있습니까?','boolean',
 NULL, true, NULL, 100, true, NULL),
('BUILDING','FREE','작업·설비 확인','structure_height_m','건축물·공작물의 높이는 몇 m입니까?','number',
 'm', true, NULL, 101, true, '{"field_code":"has_structure","op":"eq","value":true}'::jsonb),
('BUILDING','FREE','작업·설비 확인','has_hazmat_storage','위험물저장소 유무','boolean',
 NULL, true, NULL, 102, true, NULL),

-- CONSTRUCTION (sort 100+)
('CONSTRUCTION','FREE','작업·설비 확인','has_construction_machine','건설기계 설비가 있습니까?','boolean',
 NULL, true, NULL, 100, true, NULL),
('CONSTRUCTION','FREE','작업·설비 확인','construction_machine_weight_ton','건설기계의 총중량은 몇 톤입니까?','number',
 '톤', true, NULL, 101, true, '{"field_code":"has_construction_machine","op":"eq","value":true}'::jsonb),
('CONSTRUCTION','FREE','작업·설비 확인','has_hazmat_storage','위험물저장소 유무','boolean',
 NULL, true, NULL, 102, true, NULL),

-- INDUSTRIAL (sort 100+)
('INDUSTRIAL','FREE','작업·설비 확인','has_scaffold','비계를 사용합니까?','boolean',
 NULL, true, NULL, 100, true, NULL),
('INDUSTRIAL','FREE','작업·설비 확인','scaffold_height_m','비계의 높이는 몇 m입니까?','number',
 'm', true, NULL, 101, true, '{"field_code":"has_scaffold","op":"eq","value":true}'::jsonb),
('INDUSTRIAL','FREE','작업·설비 확인','has_grinding','연삭 작업을 합니까?','boolean',
 NULL, true, NULL, 102, true, NULL),
('INDUSTRIAL','FREE','작업·설비 확인','grinding_wheel_diameter_cm','연삭숫돌 지름은 몇 cm입니까?','number',
 'cm', true, NULL, 103, true, '{"field_code":"has_grinding","op":"eq","value":true}'::jsonb),
('INDUSTRIAL','FREE','작업·설비 확인','has_diving','잠수 작업이 있습니까?','boolean',
 NULL, true, NULL, 104, true, NULL),
('INDUSTRIAL','FREE','작업·설비 확인','diving_worker_count','잠수 작업 인원은 몇 명입니까?','number',
 '명', true, NULL, 105, true, '{"field_code":"has_diving","op":"eq","value":true}'::jsonb),
('INDUSTRIAL','FREE','작업·설비 확인','has_object_drop','물체 투하 작업이 있습니까?','boolean',
 NULL, true, NULL, 106, true, NULL),
('INDUSTRIAL','FREE','작업·설비 확인','object_drop_height_m','물체 투하 높이는 몇 m입니까?','number',
 'm', true, NULL, 107, true, '{"field_code":"has_object_drop","op":"eq","value":true}'::jsonb),
('INDUSTRIAL','FREE','작업·설비 확인','has_high_speed_rotor','고속회전체 설비가 있습니까?','boolean',
 NULL, true, NULL, 108, true, NULL),
('INDUSTRIAL','FREE','작업·설비 확인','has_subcontractor','하도급 유무','boolean',
 NULL, true, NULL, 109, true, NULL),
('INDUSTRIAL','FREE','작업·설비 확인','same_site_construction_count','같은 장소 건설공사 건수는 몇 건입니까?','number',
 '건', true, NULL, 110, true, '{"field_code":"has_subcontractor","op":"eq","value":true}'::jsonb),
('INDUSTRIAL','FREE','작업·설비 확인','has_hazmat_storage','위험물저장소 유무','boolean',
 NULL, true, NULL, 111, true, NULL);

-- ═══════════════════════════════════════════════════════════════════════════
-- D. POSTCHECK (apply 후)
-- ═══════════════════════════════════════════════════════════════════════════
-- SELECT count(*) FROM diagnosis_input_fields
-- WHERE tier='FREE' AND field_code IN (
--   'has_structure','structure_height_m','has_hazmat_storage',
--   'has_construction_machine','construction_machine_weight_ton',
--   'has_scaffold','scaffold_height_m','has_grinding','grinding_wheel_diameter_cm',
--   'has_diving','diving_worker_count','has_object_drop','object_drop_height_m',
--   'has_high_speed_rotor','has_subcontractor','same_site_construction_count'
-- ) AND (
--   (sector='BUILDING' AND field_code IN ('has_structure','structure_height_m','has_hazmat_storage'))
--   OR (sector='CONSTRUCTION' AND field_code IN ('has_construction_machine','construction_machine_weight_ton','has_hazmat_storage'))
--   OR (sector='INDUSTRIAL' AND field_code IN (
--        'has_scaffold','scaffold_height_m','has_grinding','grinding_wheel_diameter_cm',
--        'has_diving','diving_worker_count','has_object_drop','object_drop_height_m',
--        'has_high_speed_rotor','has_subcontractor','same_site_construction_count','has_hazmat_storage'))
-- );
-- expect = 18 · duplicate exact (sector,tier,field_code) = 0 · PAID delta 0

-- ═══════════════════════════════════════════════════════════════════════════
-- E. ROLLBACK (artifact only)
-- ═══════════════════════════════════════════════════════════════════════════
-- DELETE FROM public.diagnosis_input_fields
-- WHERE tier='FREE' AND (
--   (sector='BUILDING' AND field_code IN ('has_structure','structure_height_m','has_hazmat_storage'))
--   OR (sector='CONSTRUCTION' AND field_code IN ('has_construction_machine','construction_machine_weight_ton','has_hazmat_storage'))
--   OR (sector='INDUSTRIAL' AND field_code IN (
--        'has_scaffold','scaffold_height_m','has_grinding','grinding_wheel_diameter_cm',
--        'has_diving','diving_worker_count','has_object_drop','object_drop_height_m',
--        'has_high_speed_rotor','has_subcontractor','same_site_construction_count','has_hazmat_storage'))
-- );
-- -- visibility_condition 컬럼 제거는 선택(기존 NULL rows 무영향). 필요 시:
-- -- ALTER TABLE public.diagnosis_input_fields DROP COLUMN IF EXISTS visibility_condition;
