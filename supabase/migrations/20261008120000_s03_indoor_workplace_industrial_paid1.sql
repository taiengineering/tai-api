-- WO-LFR-OBJ-S03: Art.19 옥내작업장 경보설비 — indoor_workplace INDUSTRIAL/PAID1 입력 필드.
-- INITIAL_FRONT_FACT. missing != false. INDUSTRIAL 전용: BUILDING/CONSTRUCTION 미적용.
--
-- MIGRATION MODE = EXACT-BEFORE / FAIL-CLOSED / ONE-TIME
--   PRECHECK: (INDUSTRIAL, PAID1, indoor_workplace) row absent.
--   If precheck fails → RAISE EXCEPTION → rollback.
--   ON CONFLICT DO NOTHING = defensive guard only.
--
-- EXPECTED BEFORE: INDUSTRIAL/PAID1/indoor_workplace = absent
-- EXPECTED AFTER:  INDUSTRIAL/PAID1/indoor_workplace = 1 active row

BEGIN;

DO $$
DECLARE v_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO v_count
  FROM public.diagnosis_input_fields
  WHERE sector = 'INDUSTRIAL' AND tier = 'PAID1' AND field_code = 'indoor_workplace';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'PRECHECK FAILED: INDUSTRIAL/PAID1/indoor_workplace already exists (% rows). ABORT.', v_count;
  END IF;
  RAISE NOTICE 'PRECHECK OK: INDUSTRIAL/PAID1/indoor_workplace absent';
END $$;

INSERT INTO public.diagnosis_input_fields (
  sector, tier, field_group, field_code, field_name, field_type,
  unit, is_required, help_text, sort_order, is_active, visibility_condition
) VALUES (
  'INDUSTRIAL', 'PAID1', '작업장 환경', 'indoor_workplace',
  '현재 진단 대상 작업장은 옥내작업장에 해당합니까?', 'boolean',
  NULL, false,
  '「산업안전보건기준에 관한 규칙」 제19조의 ''옥내작업장'' 해당 여부를 확인합니다.',
  850, true, NULL
)
ON CONFLICT (sector, tier, field_code) DO NOTHING;

COMMIT;
