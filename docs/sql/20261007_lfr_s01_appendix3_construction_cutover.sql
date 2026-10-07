-- WO-LFR-OBJ-S01-P1-001 PATCH-01
-- ⚠️ PREPARE ONLY. SQL APPLY = 0.
-- DO NOT execute until:
--   1. GPT independent verification of LEG PR #166 PASS
--   2. GPT independent verification of TAI-API PR #543 PASS
--   3. is_construction active-use census CONFIRMED (S01 14 only)
--   4. Owner approval for catalog cutover
--
-- Purpose:
--   CONSTRUCTION FREE/PAID catalog cutover:
--   1. Add appendix3_item_no select field (1..49, same options as BUILDING/INDUSTRIAL)
--   2. Deactivate is_construction (is_active=false, is_required=false)
--   3. Update child visibility: is_construction=true → appendix3_item_no=49
--
-- Pre-conditions assumed from 20260913_core22_explicit_construction_predicates.sql:
--   is_construction: is_active=true, is_required=true, visibility_condition=NULL
--   is_relationship_contractor: visibility_condition={"field_code":"is_construction","op":"eq","value":true}
--   is_civil_construction: visibility_condition={"field_code":"is_construction","op":"eq","value":true}
--   appendix3_item_no: NOT PRESENT for CONSTRUCTION
--
-- APPLY = 0. DO NOT RUN.

BEGIN;

-- ─── PRE-FLIGHT: exact row count guard ────────────────────────────────────────

DO $$
DECLARE
  n_appendix3 int;
  n_is_construction int;
  n_rel int;
  n_civil int;
  n_rel_vis text;
  n_civil_vis text;
BEGIN
  -- Guard: appendix3_item_no must NOT exist for CONSTRUCTION yet
  SELECT count(*) INTO n_appendix3 FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'appendix3_item_no'
     AND tier IN ('FREE', 'PAID');
  IF n_appendix3 > 0 THEN
    RAISE EXCEPTION
      'appendix3_item_no already exists for CONSTRUCTION (% rows) — abort', n_appendix3;
  END IF;

  -- Guard: is_construction must exist and be active
  SELECT count(*) INTO n_is_construction FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_construction'
     AND tier IN ('FREE', 'PAID')
     AND is_active = true;
  IF n_is_construction != 2 THEN
    RAISE EXCEPTION
      'Expected 2 active is_construction rows for CONSTRUCTION, found % — abort', n_is_construction;
  END IF;

  -- Guard: is_relationship_contractor must have is_construction visibility condition
  SELECT count(*) INTO n_rel FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_relationship_contractor'
     AND tier IN ('FREE', 'PAID')
     AND visibility_condition->>'field_code' = 'is_construction';
  IF n_rel != 2 THEN
    RAISE EXCEPTION
      'Expected 2 is_relationship_contractor rows with is_construction visibility, found % — abort', n_rel;
  END IF;

  -- Guard: is_civil_construction must have is_construction visibility condition
  SELECT count(*) INTO n_civil FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_civil_construction'
     AND tier IN ('FREE', 'PAID')
     AND visibility_condition->>'field_code' = 'is_construction';
  IF n_civil != 2 THEN
    RAISE EXCEPTION
      'Expected 2 is_civil_construction rows with is_construction visibility, found % — abort', n_civil;
  END IF;
END $$;

-- ─── Q1: Add appendix3_item_no for CONSTRUCTION FREE/PAID ─────────────────────
-- Options: exact snapshot from 20260913_core22_appendix3_explicit_classification.sql
-- law_version_id = 1fa1f5af-3575-461d-8d8c-4389d0e128d8

INSERT INTO public.diagnosis_input_fields
  (sector, tier, field_code, field_type, field_name, field_group, is_active, is_required,
   input_options, visibility_condition, sort_order, help_text)
SELECT
  'CONSTRUCTION', t.tier, 'appendix3_item_no', 'select',
  '산업안전보건법 시행령 별표 3에서 사업장에 해당하는 사업 종류를 선택해 주세요.',
  '기본정보',
  true, true,
  '[{"value": 1, "label": "1. 토사석 광업"}, {"value": 2, "label": "2. 식료품 제조업, 음료 제조업"}, {"value": 3, "label": "3. 섬유제품 제조업; 의복 제외"}, {"value": 4, "label": "4. 목재 및 나무제품 제조업; 가구 제외"}, {"value": 5, "label": "5. 펄프, 종이 및 종이제품 제조업"}, {"value": 6, "label": "6. 코크스, 연탄 및 석유정제품 제조업"}, {"value": 7, "label": "7. 화학물질 및 화학제품 제조업; 의약품 제외"}, {"value": 8, "label": "8. 의료용 물질 및 의약품 제외"}, {"value": 9, "label": "9. 고무 및 플라스틱제품 제조업"}, {"value": 10, "label": "10. 비금속 광물제품 제조업"}, {"value": 11, "label": "11. 1차 금속 제조업"}, {"value": 12, "label": "12. 금속가공제품 제조업; 기계 및 가구 제외"}, {"value": 13, "label": "13. 전자부품, 컴퓨터, 영상, 음향 및 통신장비 제조업"}, {"value": 14, "label": "14. 의료, 정밀, 광학기기 및 시계 제조업"}, {"value": 15, "label": "15. 전기장비 제조업"}, {"value": 16, "label": "16. 기타 기계 및 장비 제조업"}, {"value": 17, "label": "17. 자동차 및 트레일러 제조업"}, {"value": 18, "label": "18. 기타 운송장비 제조업"}, {"value": 19, "label": "19. 가구 제조업"}, {"value": 20, "label": "20. 기타 제품 제조업"}, {"value": 21, "label": "21. 산업용 기계 및 장비 수리업"}, {"value": 22, "label": "22. 서적, 잡지 및 기타 인쇄물 출판업"}, {"value": 23, "label": "23. 폐기물 수집, 운반, 처리 및 원료 재생업"}, {"value": 24, "label": "24. 환경 정화 및 복원업"}, {"value": 25, "label": "25. 자동차 종합 수리업, 자동차 전문 수리업"}, {"value": 26, "label": "26. 발전업"}, {"value": 27, "label": "27. 운수 및 창고업"}, {"value": 28, "label": "28. 농업, 임업 및 어업"}, {"value": 29, "label": "29. 제2호부터 제21호까지의 사업을 제외한 제조업"}, {"value": 30, "label": "30. 전기, 가스, 증기 및 공기조절 공급업(발전업은 제외한다)"}, {"value": 31, "label": "31. 수도, 하수 및 폐기물 처리, 원료 재생업(제23호 및 제24호에 해당하는 사업은 제외한다)"}, {"value": 32, "label": "32. 도매 및 소매업"}, {"value": 33, "label": "33. 숙박 및 음식점업"}, {"value": 34, "label": "34. 영상ㆍ오디오 기록물 제작 및 배급업"}, {"value": 35, "label": "35. 라디오 방송업 및 텔레비전 방송업"}, {"value": 36, "label": "36. 우편 및 통신업"}, {"value": 37, "label": "37. 부동산업"}, {"value": 38, "label": "38. 임대업; 부동산 제외"}, {"value": 39, "label": "39. 연구개발업"}, {"value": 40, "label": "40. 사진처리업"}, {"value": 41, "label": "41. 사업시설 관리 및 조경 서비스업"}, {"value": 42, "label": "42. 청소년 수련시설 운영업"}, {"value": 43, "label": "43. 보건업"}, {"value": 44, "label": "44. 예술, 스포츠 및 여가 관련 서비스업"}, {"value": 45, "label": "45. 개인 및 소비용품수리업(제25호에 해당하는 사업은 제외한다)"}, {"value": 46, "label": "46. 기타 개인 서비스업"}, {"value": 47, "label": "47. 공공행정(청소, 시설관리, 조리 등 현업업무에 종사하는 사람으로서 고용노동부장관이 정하여 고시하는 사람으로 한정한다)"}, {"value": 48, "label": "48. 교육서비스업 중 초등ㆍ중등ㆍ고등 교육기관, 특수학교ㆍ외국인학교 및 대안학교(청소, 시설관리, 조리 등 현업업무에 종사하는 사람으로서 고용노동부장관이 정하여 고시하는 사람으로 한정한다)"}, {"value": 49, "label": "49. 건설업"}]'::jsonb,
  NULL,
  (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM public.diagnosis_input_fields
    WHERE sector = 'CONSTRUCTION' AND tier = t.tier AND field_group = '기본정보'),
  '「산업안전보건법 시행령」 별표 3. law_version_id=1fa1f5af-3575-461d-8d8c-4389d0e128d8'
FROM (VALUES ('FREE'), ('PAID')) AS t(tier);

-- ─── Q2: Deactivate is_construction (legacy → not required) ───────────────────
-- is_construction is kept for historical input_data compatibility but no longer
-- drives server gate or child visibility.
-- Guarded: only update if still is_active=true (no blind UPDATE).

UPDATE public.diagnosis_input_fields
   SET is_active = false,
       is_required = false
 WHERE sector = 'CONSTRUCTION'
   AND field_code = 'is_construction'
   AND tier IN ('FREE', 'PAID')
   AND is_active = true;

-- ─── Q3: Update child visibility condition ────────────────────────────────────
-- OLD: {"field_code":"is_construction","op":"eq","value":true}
-- NEW: {"field_code":"appendix3_item_no","op":"eq","value":49}
-- Guarded: only update rows that still have the old condition.

UPDATE public.diagnosis_input_fields
   SET visibility_condition = '{"field_code":"appendix3_item_no","op":"eq","value":49}'::jsonb
 WHERE sector = 'CONSTRUCTION'
   AND field_code IN ('is_relationship_contractor', 'is_civil_construction')
   AND tier IN ('FREE', 'PAID')
   AND visibility_condition->>'field_code' = 'is_construction'
   AND visibility_condition->>'op' = 'eq'
   AND (visibility_condition->>'value')::boolean = true;

-- ─── POST-FLIGHT: readback assertion ─────────────────────────────────────────

DO $$
DECLARE
  n_appendix3_inserted int;
  n_is_construction_active int;
  n_child_new_vis int;
BEGIN
  -- Assert appendix3_item_no was inserted for CONSTRUCTION FREE/PAID
  SELECT count(*) INTO n_appendix3_inserted FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'appendix3_item_no'
     AND tier IN ('FREE', 'PAID')
     AND is_active = true;
  IF n_appendix3_inserted != 2 THEN
    RAISE EXCEPTION
      'Expected 2 appendix3_item_no rows for CONSTRUCTION after insert, found % — ROLLBACK', n_appendix3_inserted;
  END IF;

  -- Assert is_construction is now inactive
  SELECT count(*) INTO n_is_construction_active FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_construction'
     AND tier IN ('FREE', 'PAID')
     AND is_active = true;
  IF n_is_construction_active != 0 THEN
    RAISE EXCEPTION
      'is_construction still active for CONSTRUCTION (% rows) — ROLLBACK', n_is_construction_active;
  END IF;

  -- Assert child visibility updated to appendix3_item_no=49
  SELECT count(*) INTO n_child_new_vis FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code IN ('is_relationship_contractor', 'is_civil_construction')
     AND tier IN ('FREE', 'PAID')
     AND visibility_condition->>'field_code' = 'appendix3_item_no'
     AND (visibility_condition->>'value')::int = 49;
  IF n_child_new_vis != 4 THEN
    RAISE EXCEPTION
      'Expected 4 child rows with appendix3_item_no=49 visibility, found % — ROLLBACK', n_child_new_vis;
  END IF;
END $$;

-- ─── READBACK QUERY (for verification) ───────────────────────────────────────

SELECT sector, tier, field_code, field_type, is_active, is_required,
       visibility_condition, sort_order
  FROM public.diagnosis_input_fields
 WHERE sector = 'CONSTRUCTION'
   AND field_code IN (
     'appendix3_item_no', 'is_construction',
     'is_relationship_contractor', 'is_civil_construction'
   )
 ORDER BY tier, sort_order;

COMMIT;

-- ─── ROLLBACK TEMPLATE (only if applied and needs reverting) ─────────────────
-- DO NOT RUN unless cutover was applied and must be undone:
--
-- BEGIN;
-- DELETE FROM public.diagnosis_input_fields
--  WHERE sector = 'CONSTRUCTION'
--    AND field_code = 'appendix3_item_no'
--    AND tier IN ('FREE', 'PAID');
-- UPDATE public.diagnosis_input_fields
--    SET is_active = true, is_required = true
--  WHERE sector = 'CONSTRUCTION'
--    AND field_code = 'is_construction'
--    AND tier IN ('FREE', 'PAID');
-- UPDATE public.diagnosis_input_fields
--    SET visibility_condition = '{"field_code":"is_construction","op":"eq","value":true}'::jsonb
--  WHERE sector = 'CONSTRUCTION'
--    AND field_code IN ('is_relationship_contractor', 'is_civil_construction')
--    AND tier IN ('FREE', 'PAID');
-- COMMIT;
