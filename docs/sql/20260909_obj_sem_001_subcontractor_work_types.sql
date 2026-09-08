-- WO-E2E-OBJ-SEM-001-IMPLEMENT-REV1 — subcontractor_work_types source field
-- ⚠️ DB APPLY = 0. artifact only. GPT/USER 승인 후 별도 APPLY.
-- diagnosis_input_fields 에 CONSTRUCTION FREE/PAID 2 row 추가. ON CONFLICT DO UPDATE 금지. 기존 row 무변경.
BEGIN;

-- PRECHECK: 이미 존재하면 중단 (중복 방지)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.diagnosis_input_fields
             WHERE field_code='subcontractor_work_types') THEN
    RAISE EXCEPTION 'subcontractor_work_types already exists — abort (no ON CONFLICT UPDATE)';
  END IF;
END $$;

-- INSERT FREE (CONSTRUCTION)
INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_code, field_type, field_name, field_group, is_active, is_required,
   input_options, visibility_condition, sort_order)
VALUES
  ('CONSTRUCTION','FREE','subcontractor_work_types','multi_select',
   '하도급 중 해당되는 공사 유형을 모두 선택해주세요.','현행 하도급 인접 그룹', true, true,
   '[{"value":"GENERAL_CONSTRUCTION","label":"일반 건설공사"},{"value":"FIRE_FACILITY","label":"소방시설공사"},{"value":"ICT","label":"정보통신공사"},{"value":"OTHER","label":"기타 공사"}]'::jsonb,
   '{"field_code":"has_subcontractor","op":"eq","value":true}'::jsonb,
   (SELECT COALESCE(sort_order,0)+1 FROM public.diagnosis_input_fields
    WHERE sector='CONSTRUCTION' AND tier='FREE' AND field_code='has_subcontractor'));

-- INSERT PAID (CONSTRUCTION)
INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_code, field_type, field_name, field_group, is_active, is_required,
   input_options, visibility_condition, sort_order)
VALUES
  ('CONSTRUCTION','PAID','subcontractor_work_types','multi_select',
   '하도급 중 해당되는 공사 유형을 모두 선택해주세요.','현행 하도급 인접 그룹', true, true,
   '[{"value":"GENERAL_CONSTRUCTION","label":"일반 건설공사"},{"value":"FIRE_FACILITY","label":"소방시설공사"},{"value":"ICT","label":"정보통신공사"},{"value":"OTHER","label":"기타 공사"}]'::jsonb,
   '{"field_code":"has_subcontractor","op":"eq","value":true}'::jsonb,
   (SELECT COALESCE(sort_order,0)+1 FROM public.diagnosis_input_fields
    WHERE sector='CONSTRUCTION' AND tier='PAID' AND field_code='has_subcontractor'));

-- POSTCHECK
SELECT sector, tier, field_code, field_type, is_required, visibility_condition
FROM public.diagnosis_input_fields WHERE field_code='subcontractor_work_types' ORDER BY tier;

-- artifact only — 반드시 ROLLBACK (APPLY는 별도 승인)
ROLLBACK;
