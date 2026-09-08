-- WO-E2E-OBJ-SEM-001-IMPLEMENT-REV1-PATCH1 — subcontractor_work_types source field
-- deploy-ready UP artifact. ⚠️ DB APPLY = 0 (실행은 cutover 승인 후). 파일 자체는 실제 실행 가능한 UP SQL.
-- diagnosis_input_fields 에 CONSTRUCTION FREE/PAID 2 row 추가.
--   field_group = 각 tier의 has_subcontractor parent row field_group EXACT 복사 (literal 금지)
--   sort_order  = 같은 (sector,tier,field_group)의 MAX(sort_order)+1
--   ON CONFLICT DO UPDATE 금지. 기존 row 무변경.
BEGIN;

-- PRECHECK: exact (sector,tier,field_code) 2쌍이 아직 없어야 함
DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM public.diagnosis_input_fields
   WHERE sector='CONSTRUCTION' AND tier IN ('FREE','PAID') AND field_code='subcontractor_work_types';
  IF n > 0 THEN
    RAISE EXCEPTION 'subcontractor_work_types already exists (% rows) — abort (no ON CONFLICT UPDATE)', n;
  END IF;
END $$;

-- INSERT FREE + PAID. field_group/sort_order 는 parent(has_subcontractor) 기준 동적 계산.
INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_code, field_type, field_name, field_group, is_active, is_required,
   input_options, visibility_condition, sort_order)
SELECT
  'CONSTRUCTION', p.tier, 'subcontractor_work_types', 'multi_select',
  '하도급 중 해당되는 공사 유형을 모두 선택해주세요.',
  p.field_group,                                   -- parent field_group EXACT 복사
  true, true,
  '[{"value":"GENERAL_CONSTRUCTION","label":"일반 건설공사"},{"value":"FIRE_FACILITY","label":"소방시설공사"},{"value":"ICT","label":"정보통신공사"},{"value":"OTHER","label":"기타 공사"}]'::jsonb,
  '{"field_code":"has_subcontractor","op":"eq","value":true}'::jsonb,
  (SELECT COALESCE(MAX(sort_order),0)+1 FROM public.diagnosis_input_fields
   WHERE sector='CONSTRUCTION' AND tier=p.tier AND field_group=p.field_group)   -- 같은 group MAX+1
FROM public.diagnosis_input_fields p
WHERE p.sector='CONSTRUCTION' AND p.field_code='has_subcontractor' AND p.tier IN ('FREE','PAID');

-- POSTCHECK: 2 row 정확히 생성 + field_group parent 일치 확인
SELECT s.tier, s.field_code, s.field_group, s.sort_order, s.is_required, s.visibility_condition,
       (s.field_group = p.field_group) AS field_group_matches_parent
FROM public.diagnosis_input_fields s
JOIN public.diagnosis_input_fields p
  ON p.sector='CONSTRUCTION' AND p.field_code='has_subcontractor' AND p.tier=s.tier
WHERE s.sector='CONSTRUCTION' AND s.field_code='subcontractor_work_types'
ORDER BY s.tier;

COMMIT;

-- ROLLBACK 예시 (필요 시 수동 실행 — 이 파일에 포함되지 않음):
--   DELETE FROM public.diagnosis_input_fields
--    WHERE sector='CONSTRUCTION' AND tier IN ('FREE','PAID') AND field_code='subcontractor_work_types';
