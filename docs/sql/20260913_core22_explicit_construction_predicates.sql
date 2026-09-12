-- WO-SM-CORE22-CONSTRUCTION-PREDICATE-EXPLICIT-INPUT-CONTRACT-001
-- deploy-ready UP artifact. ⚠️ DB APPLY = 0 (실행은 producer cutover 승인 후).
-- CONSTRUCTION FREE/PAID catalog: 3 explicit canonical legal facts.
-- No derivation from sector / construction_type / construction_type_code / order_type.
-- ON CONFLICT DO UPDATE 금지. 기존 row 무변경.
-- help_text = 승인된 법령 명칭 인용만. 새 법적 정의 해석 없음.
BEGIN;

DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM public.diagnosis_input_fields
   WHERE sector='CONSTRUCTION'
     AND tier IN ('FREE','PAID')
     AND field_code IN ('is_construction','is_relationship_contractor','is_civil_construction');
  IF n > 0 THEN
    RAISE EXCEPTION 'explicit construction predicates already exist (% rows) — abort', n;
  END IF;
END $$;

-- Q1 is_construction: CONSTRUCTION 항상 표시, 예/아니오 필수.
INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_code, field_type, field_name, field_group, is_active, is_required,
   help_text, visibility_condition, sort_order)
SELECT
  'CONSTRUCTION', t.tier, 'is_construction', 'boolean',
  '이 사업/공사는 산업안전보건법 시행령 별표 3 제49호의 건설업에 해당합니까?',
  '기본정보',
  true, true,
  '「산업안전보건법 시행령」 별표 3 제49호',
  NULL,
  3
FROM (VALUES ('FREE'), ('PAID')) AS t(tier);

-- Q2/Q3: is_construction=true 일 때만 표시. 예/아니오. 하도급/토목 문자열 자동선택 없음.
INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_code, field_type, field_name, field_group, is_active, is_required,
   help_text, visibility_condition, sort_order)
SELECT
  'CONSTRUCTION', t.tier, 'is_relationship_contractor', 'boolean',
  '귀사는 이 공사에서 관계수급인에 해당합니까?',
  '기본정보',
  true, true,
  '「산업안전보건법」 관계수급인',
  '{"field_code":"is_construction","op":"eq","value":true}'::jsonb,
  4
FROM (VALUES ('FREE'), ('PAID')) AS t(tier);

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_code, field_type, field_name, field_group, is_active, is_required,
   help_text, visibility_condition, sort_order)
SELECT
  'CONSTRUCTION', t.tier, 'is_civil_construction', 'boolean',
  '해당 공사는 토목공사업에 해당합니까?',
  '기본정보',
  true, true,
  '「건설산업기본법 시행령」 별표 1 종합공사를 시공하는 업종의 건설업종란 제1호',
  '{"field_code":"is_construction","op":"eq","value":true}'::jsonb,
  5
FROM (VALUES ('FREE'), ('PAID')) AS t(tier);

SELECT sector, tier, field_code, is_required, visibility_condition, sort_order
FROM public.diagnosis_input_fields
WHERE sector='CONSTRUCTION'
  AND field_code IN ('is_construction','is_relationship_contractor','is_civil_construction')
ORDER BY tier, sort_order;

COMMIT;
