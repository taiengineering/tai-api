-- WO-E2E2000-FIXOBJ03-C1-INPUT-SURFACE-002 — C1 catalog patch
-- Defect: diagnosis_input_fields missing appendix3_item_no / is_real_estate_management
--         for BUILDING FREE/PAID and INDUSTRIAL FREE/PAID1.
-- Root cause: 20260913_core22_appendix3_explicit_classification.sql was PREPARE ONLY
--             and was never promoted to production (S01 only applied CONSTRUCTION).
-- Impact: BUILDING/INDUSTRIAL users receive 422 APPENDIX3_EXPLICIT_CLASSIFICATION_REQUIRED
--         on every diagnosis attempt; C1 UI form has no appendix3_item_no selector.
--
-- Mirrors content from docs/sql/20260913_core22_appendix3_explicit_classification.sql
-- Options source: docs/canonical/legal-input/appendix3_items_v1.json
--   law_version_id = 1fa1f5af-3575-461d-8d8c-4389d0e128d8
--   file SHA256    = b106956b54036508576774a48c98e9198facfd6a0d34d52d9e70ab55e07aad69
--
-- INSERT ... WHERE NOT EXISTS: safe to re-run (idempotent).
-- CONSTRUCTION rows: already present (applied in S01 R2). Not re-inserted here.

BEGIN;

-- ── PRE-FLIGHT ───────────────────────────────────────────────────────────────
DO $$
DECLARE n_existing int;
BEGIN
  SELECT count(*) INTO n_existing FROM public.diagnosis_input_fields
   WHERE field_code IN ('appendix3_item_no', 'is_real_estate_management')
     AND (
       (sector = 'BUILDING'    AND tier IN ('FREE', 'PAID'))
       OR (sector = 'INDUSTRIAL' AND tier IN ('FREE', 'PAID1'))
     );
  IF n_existing > 0 THEN
    RAISE NOTICE 'appendix3 catalog rows already exist for BUILDING/INDUSTRIAL (% rows) — skipping INSERT', n_existing;
  END IF;
END $$;

-- ── Q1: appendix3_item_no ─────────────────────────────────────────────────────
-- field_type = 'select', is_required = true, 49 options from 별표 3.
INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_code, field_type, field_name, field_group, is_active, is_required,
   input_options, visibility_condition, sort_order, help_text)
SELECT
  c.sector, c.tier, 'appendix3_item_no', 'select',
  '산업안전보건법 시행령 별표 3에서 사업장에 해당하는 사업 종류를 선택해 주세요.',
  '기본정보',
  true, true,
  '[{"value": 1, "label": "1. 토사석 광업"}, {"value": 2, "label": "2. 식료품 제조업, 음료 제조업"}, {"value": 3, "label": "3. 섬유제품 제조업; 의복 제외"}, {"value": 4, "label": "4. 목재 및 나무제품 제조업; 가구 제외"}, {"value": 5, "label": "5. 펄프, 종이 및 종이제품 제조업"}, {"value": 6, "label": "6. 코크스, 연탄 및 석유정제품 제조업"}, {"value": 7, "label": "7. 화학물질 및 화학제품 제조업; 의약품 제외"}, {"value": 8, "label": "8. 의료용 물질 및 의약품 제조업"}, {"value": 9, "label": "9. 고무 및 플라스틱제품 제조업"}, {"value": 10, "label": "10. 비금속 광물제품 제조업"}, {"value": 11, "label": "11. 1차 금속 제조업"}, {"value": 12, "label": "12. 금속가공제품 제조업; 기계 및 가구 제외"}, {"value": 13, "label": "13. 전자부품, 컴퓨터, 영상, 음향 및 통신장비 제조업"}, {"value": 14, "label": "14. 의료, 정밀, 광학기기 및 시계 제조업"}, {"value": 15, "label": "15. 전기장비 제조업"}, {"value": 16, "label": "16. 기타 기계 및 장비 제조업"}, {"value": 17, "label": "17. 자동차 및 트레일러 제조업"}, {"value": 18, "label": "18. 기타 운송장비 제조업"}, {"value": 19, "label": "19. 가구 제조업"}, {"value": 20, "label": "20. 기타 제품 제조업"}, {"value": 21, "label": "21. 산업용 기계 및 장비 수리업"}, {"value": 22, "label": "22. 서적, 잡지 및 기타 인쇄물 출판업"}, {"value": 23, "label": "23. 폐기물 수집, 운반, 처리 및 원료 재생업"}, {"value": 24, "label": "24. 환경 정화 및 복원업"}, {"value": 25, "label": "25. 자동차 종합 수리업, 자동차 전문 수리업"}, {"value": 26, "label": "26. 발전업"}, {"value": 27, "label": "27. 운수 및 창고업"}, {"value": 28, "label": "28. 농업, 임업 및 어업"}, {"value": 29, "label": "29. 제2호부터 제21호까지의 사업을 제외한 제조업"}, {"value": 30, "label": "30. 전기, 가스, 증기 및 공기조절 공급업(발전업은 제외한다)"}, {"value": 31, "label": "31. 수도, 하수 및 폐기물 처리, 원료 재생업(제23호 및 제24호에 해당하는 사업은 제외한다)"}, {"value": 32, "label": "32. 도매 및 소매업"}, {"value": 33, "label": "33. 숙박 및 음식점업"}, {"value": 34, "label": "34. 영상ㆍ오디오 기록물 제작 및 배급업"}, {"value": 35, "label": "35. 라디오 방송업 및 텔레비전 방송업"}, {"value": 36, "label": "36. 우편 및 통신업"}, {"value": 37, "label": "37. 부동산업"}, {"value": 38, "label": "38. 임대업; 부동산 제외"}, {"value": 39, "label": "39. 연구개발업"}, {"value": 40, "label": "40. 사진처리업"}, {"value": 41, "label": "41. 사업시설 관리 및 조경 서비스업"}, {"value": 42, "label": "42. 청소년 수련시설 운영업"}, {"value": 43, "label": "43. 보건업"}, {"value": 44, "label": "44. 예술, 스포츠 및 여가 관련 서비스업"}, {"value": 45, "label": "45. 개인 및 소비용품수리업(제25호에 해당하는 사업은 제외한다)"}, {"value": 46, "label": "46. 기타 개인 서비스업"}, {"value": 47, "label": "47. 공공행정(청소, 시설관리, 조리 등 현업업무에 종사하는 사람으로서 고용노동부장관이 정하여 고시하는 사람으로 한정한다)"}, {"value": 48, "label": "48. 교육서비스업 중 초등ㆍ중등ㆍ고등 교육기관, 특수학교ㆍ외국인학교 및 대안학교(청소, 시설관리, 조리 등 현업업무에 종사하는 사람으로서 고용노동부장관이 정하여 고시하는 사람으로 한정한다)"}, {"value": 49, "label": "49. 건설업"}]'::jsonb,
  NULL,
  (SELECT COALESCE(MAX(sort_order), 0) + 1
     FROM public.diagnosis_input_fields
    WHERE sector = c.sector AND tier = c.tier AND field_group = '기본정보'),
  '「산업안전보건법 시행령」 별표 3. law_version_id=1fa1f5af-3575-461d-8d8c-4389d0e128d8'
FROM (VALUES
  ('BUILDING',    'FREE'),
  ('BUILDING',    'PAID'),
  ('INDUSTRIAL',  'FREE'),
  ('INDUSTRIAL',  'PAID1')
) AS c(sector, tier)
WHERE NOT EXISTS (
  SELECT 1 FROM public.diagnosis_input_fields
   WHERE sector = c.sector AND tier = c.tier AND field_code = 'appendix3_item_no'
);

-- ── Q2: is_real_estate_management ────────────────────────────────────────────
-- Only visible when appendix3_item_no = 37 (부동산업). missing ≠ false.
INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_code, field_type, field_name, field_group, is_active, is_required,
   visibility_condition, sort_order, help_text)
SELECT
  c.sector, c.tier, 'is_real_estate_management', 'boolean',
  '해당 사업은 부동산 관리업입니까?',
  '기본정보',
  true, true,
  '{"field_code":"appendix3_item_no","op":"eq","value":37}'::jsonb,
  (SELECT COALESCE(MAX(sort_order), 0) + 1
     FROM public.diagnosis_input_fields
    WHERE sector = c.sector AND tier = c.tier AND field_group = '기본정보'),
  '「산업안전보건법 시행령」 별표 3 제37호 부동산업의 부동산 관리업 여부. 예=true, 아니오=false.'
FROM (VALUES
  ('BUILDING',    'FREE'),
  ('BUILDING',    'PAID'),
  ('INDUSTRIAL',  'FREE'),
  ('INDUSTRIAL',  'PAID1')
) AS c(sector, tier)
WHERE NOT EXISTS (
  SELECT 1 FROM public.diagnosis_input_fields
   WHERE sector = c.sector AND tier = c.tier AND field_code = 'is_real_estate_management'
);

-- ── POST-FLIGHT ───────────────────────────────────────────────────────────────
DO $$
DECLARE
  n_item    int;
  n_sub     int;
BEGIN
  SELECT count(*) INTO n_item FROM public.diagnosis_input_fields
   WHERE field_code = 'appendix3_item_no'
     AND (
       (sector = 'BUILDING'    AND tier IN ('FREE', 'PAID'))
       OR (sector = 'INDUSTRIAL' AND tier IN ('FREE', 'PAID1'))
     )
     AND is_active = true;
  SELECT count(*) INTO n_sub FROM public.diagnosis_input_fields
   WHERE field_code = 'is_real_estate_management'
     AND (
       (sector = 'BUILDING'    AND tier IN ('FREE', 'PAID'))
       OR (sector = 'INDUSTRIAL' AND tier IN ('FREE', 'PAID1'))
     )
     AND is_active = true;
  IF n_item < 4 THEN
    RAISE EXCEPTION
      'POST-FLIGHT FAIL: appendix3_item_no active rows = % (expected >= 4)', n_item;
  END IF;
  IF n_sub < 4 THEN
    RAISE EXCEPTION
      'POST-FLIGHT FAIL: is_real_estate_management active rows = % (expected >= 4)', n_sub;
  END IF;
  RAISE NOTICE 'POST-FLIGHT PASS: appendix3_item_no=% rows, is_real_estate_management=% rows', n_item, n_sub;
END $$;

-- ── READBACK ──────────────────────────────────────────────────────────────────
SELECT sector, tier, field_code, field_type, is_required, is_active,
       visibility_condition, sort_order
  FROM public.diagnosis_input_fields
 WHERE field_code IN ('appendix3_item_no', 'is_real_estate_management')
   AND (
     (sector = 'BUILDING'    AND tier IN ('FREE', 'PAID'))
     OR (sector = 'INDUSTRIAL' AND tier IN ('FREE', 'PAID1'))
   )
 ORDER BY sector, tier, sort_order;

COMMIT;
