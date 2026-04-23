-- ========================================================
-- Phase A-2 검증 SQL (Supabase Dashboard > SQL Editor)
-- https://supabase.com/dashboard/project/xntdkrjhgcscmqctdzyo/sql/new
-- ========================================================
-- service role 권한 필요 (RLS 우회).
-- 대시보드 SQL Editor는 기본적으로 service 권한으로 실행됨.

-- ========================================================
-- 검증 1: 엔진 반환 시뮬레이션 (fetch_article_contexts 파이프)
-- ========================================================
-- 일반 룰 5개를 렌더링했을 때 조문 본문이 어떻게 나오는지 확인
WITH sample_rules AS (
  SELECT rule_id, law_name, law_article
  FROM master_building_legal_rules
  WHERE is_active = true
  ORDER BY RANDOM()
  LIMIT 5
)
SELECT 
  sr.rule_id,
  sr.law_name,
  sr.law_article AS 참조,
  ram.article_internal_key AS 조문키,
  la.article_title AS 제목,
  LEFT(la.article_text, 200) AS 본문_미리보기,
  CASE
    WHEN ram.article_internal_key ~ '^0[0-9]{6}$' THEN 'LEGAL'
    WHEN ram.article_internal_key LIKE 'nfpc-%' THEN 'NFPC'
    WHEN ram.article_internal_key LIKE 'nftc-%' THEN 'NFTC'
    WHEN ram.article_internal_key LIKE 'admrul-%' THEN 'ADMRUL'
    ELSE 'NOT_MAPPED'
  END AS 체계
FROM sample_rules sr
LEFT JOIN rule_article_mapping ram ON ram.rule_id = sr.rule_id
LEFT JOIN law_article la ON la.id = ram.article_id AND la.article_status_code = 'ACTIVE';


-- ========================================================
-- 검증 2: 전체 커버리지 집계
-- ========================================================
WITH active_rules AS (
  SELECT rule_id FROM master_building_legal_rules WHERE is_active = true
),
mapped AS (
  SELECT 
    ar.rule_id,
    ram.article_internal_key,
    CASE
      WHEN ram.article_internal_key ~ '^0[0-9]{6}$' THEN 'LEGAL'
      WHEN ram.article_internal_key LIKE 'nfpc-%' THEN 'NFPC'
      WHEN ram.article_internal_key LIKE 'nftc-%' THEN 'NFTC'
      WHEN ram.article_internal_key LIKE 'admrul-%' THEN 'ADMRUL'
      ELSE 'NOT_MAPPED'
    END AS law_system,
    la.id IS NOT NULL AS has_article_text
  FROM active_rules ar
  LEFT JOIN rule_article_mapping ram ON ram.rule_id = ar.rule_id
  LEFT JOIN law_article la ON la.id = ram.article_id AND la.article_status_code = 'ACTIVE'
)
SELECT 
  law_system AS 체계,
  COUNT(*) AS 룰수,
  COUNT(*) FILTER (WHERE has_article_text) AS 본문포함,
  ROUND(COUNT(*) FILTER (WHERE has_article_text) * 100.0 / NULLIF(COUNT(*), 0), 1) AS 커버리지_pct
FROM mapped
GROUP BY law_system
ORDER BY 룰수 DESC;


-- ========================================================
-- 검증 3: 실제 factory의 진단 결과에 article_text 들어갔는지
-- ========================================================
-- 신규 Phase A-2 구현 이후 생성된 결과에는 유의미한 데이터
-- (구 데이터 43건은 영향 없음 — 기존 포맷 유지)
SELECT 
  id,
  created_at,
  sector,
  diagnosis_stage,
  result_data->'article_mapping_stats' AS mapping_stats,  -- v5.8.0 신규
  (
    SELECT jsonb_agg(jsonb_build_object(
      'rule_code', r->>'rule_code',
      'has_article_text', r->'has_article_text',
      'article_internal_key', r->>'article_internal_key',
      'article_title', r->>'article_title'
    ))
    FROM jsonb_array_elements(result_data->'rules') r
    LIMIT 3
  ) AS rules_preview
FROM factory_diagnosis_results
ORDER BY created_at DESC
LIMIT 3;


-- ========================================================
-- 검증 4: NFTC 룰 매핑 이슈 상세 (Phase B 서넌)
-- ========================================================
-- 기대: NFTC는 "1.1.1" 체계인데 룰이 "제4조"로 참조 → 고셀쇼스
-- 이 룰들은 Phase A-2 범위 외. Phase B에서 개선 예정
SELECT 
  mblr.rule_id,
  mblr.law_name,
  mblr.law_article AS 룰_참조,
  lm.law_name AS 수집된_법령,
  COUNT(la.id) FILTER (WHERE la.article_status_code='ACTIVE') AS 해당법령_조문수
FROM master_building_legal_rules mblr
LEFT JOIN law_master lm ON lm.law_name = mblr.law_name
LEFT JOIN law_article la ON la.law_id = lm.id
WHERE mblr.is_active = true
  AND (mblr.law_name ILIKE '%NFTC%' OR mblr.law_name ILIKE '%NFPC%')
GROUP BY mblr.rule_id, mblr.law_name, mblr.law_article, lm.law_name
ORDER BY mblr.rule_id;
