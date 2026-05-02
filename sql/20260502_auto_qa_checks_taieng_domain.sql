-- 자동 QA 대시보드(auto_qa_checks): 마케팅 도메인 new.taieng.co.kr → taieng.co.kr 일괄 치환
-- 실행 위치: Supabase SQL Editor (해당 프로젝트)
-- 대상: endpoint 컬럼에 'new.taieng.co.kr'이 포함된 행

BEGIN;

-- 영향 범위 미리보기
-- SELECT id, name, endpoint FROM public.auto_qa_checks
--   WHERE endpoint IS NOT NULL AND endpoint LIKE '%new.taieng.co.kr%';

UPDATE public.auto_qa_checks
SET endpoint = replace(endpoint, 'new.taieng.co.kr', 'taieng.co.kr')
WHERE endpoint IS NOT NULL
  AND endpoint LIKE '%new.taieng.co.kr%';

COMMIT;

-- 확인
-- SELECT id, name, endpoint FROM public.auto_qa_checks WHERE site = 'marketing' ORDER BY id;
