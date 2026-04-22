-- SESSION 1 / Phase 1-1-2: 재수집 전 법령별 품질 baseline 스냅샷
-- Supabase SQL Editor에서 1회 실행 (기존 law_article 등은 변경 없음)
-- 문서: docs/ISSUE_37_XML_ANALYSIS.md

CREATE TABLE IF NOT EXISTS law_quality_snapshot_20260422 AS
SELECT
  lm.law_name,
  lm.id AS law_id,
  COUNT(*) AS total_rows,
  COUNT(DISTINCT la.article_no) AS unique_articles,
  COUNT(*) FILTER (WHERE LENGTH(la.article_text) > 500) AS valid_articles,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE LENGTH(la.article_text) > 500)
    / NULLIF(COUNT(*), 0),
    2
  ) AS valid_pct,
  NOW() AS snapshot_at
FROM law_article la
JOIN law_version lv ON la.law_version_id = lv.id
JOIN law_master lm ON lv.law_id = lm.id
WHERE lv.is_current = true
  AND lm.is_active = true
GROUP BY lm.law_name, lm.id;

-- 선택: 조회
-- SELECT COUNT(*) FROM law_quality_snapshot_20260422;
-- SELECT * FROM law_quality_snapshot_20260422 ORDER BY valid_pct ASC LIMIT 20;
