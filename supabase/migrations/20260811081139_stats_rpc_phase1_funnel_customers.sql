-- Phase 1 운영자 통계 RPC: Area A(진단 퍼널), Area C(고객사·사업장)
-- 읽기전용 집계 함수 (테이블/컬럼 변경 없음). 기존 dashboard_stats RPC와 동일 패턴.
-- 반환 형태: { summary, chart, by_* } — tai-api 라우터가 { status, data } 로 래핑.
-- 근거(실데이터 검증 2026-08-11):
--   익명진단 23,894 (5/20~8/11, 8월 16,856 급증) / 공개요청 4,014 (status 대부분 NEW=미처리 4,004)
--   companies 181: business_sector 117·address_sido 113·employee_count 109 충전(분석가능)
--   factories 5,475: ksic 19·sido 326 로 분석축 미충전 → 분포는 companies 기준, factories는 등록수/추이만
--   source_type factory_test·runtime_compiler_projection = 테스트/엔진 트래픽 → real 집계에서 제외

CREATE OR REPLACE FUNCTION public.stats_diagnosis_funnel(
  p_start date DEFAULT (now() - interval '30 days')::date,
  p_end   date DEFAULT now()::date,
  p_period text DEFAULT 'daily'
) RETURNS jsonb
LANGUAGE sql STABLE
AS $$
WITH u AS (
  SELECT CASE lower(p_period) WHEN 'weekly' THEN 'week' WHEN 'monthly' THEN 'month' ELSE 'day' END AS unit
),
anon AS (
  SELECT created_at, source_type, COALESCE(paid_amount,0) AS paid_amount,
         (source_type NOT IN ('factory_test','runtime_compiler_projection')) AS is_real
  FROM anonymous_diagnosis_results
  WHERE created_at >= p_start AND created_at < (p_end + 1)
),
pub AS (
  SELECT status_code FROM public_diagnosis_requests
  WHERE created_at >= p_start AND created_at < (p_end + 1)
)
SELECT jsonb_build_object(
  'summary', jsonb_build_object(
     'anon_total',  (SELECT count(*) FROM anon),
     'anon_real',   (SELECT count(*) FROM anon WHERE is_real),
     'anon_test',   (SELECT count(*) FROM anon WHERE NOT is_real),
     'paid_total',  (SELECT count(*) FROM anon WHERE paid_amount > 0),
     'pub_total',   (SELECT count(*) FROM pub),
     'pub_pending', (SELECT count(*) FROM pub WHERE status_code = 'NEW'),
     'conv_rate',   CASE WHEN (SELECT count(*) FROM anon WHERE is_real) > 0
                         THEN round((SELECT count(*) FROM anon WHERE paid_amount>0)::numeric * 100
                                    / (SELECT count(*) FROM anon WHERE is_real), 2)
                         ELSE 0 END
  ),
  'chart', COALESCE((
     SELECT jsonb_agg(jsonb_build_object('date', to_char(d,'YYYY-MM-DD'), 'total', tc, 'real', rc) ORDER BY d)
     FROM (
       SELECT date_trunc((SELECT unit FROM u), created_at)::date AS d,
              count(*) AS tc, count(*) FILTER (WHERE is_real) AS rc
       FROM anon GROUP BY 1
     ) t
  ), '[]'::jsonb),
  'by_source', COALESCE((
     SELECT jsonb_agg(jsonb_build_object('label', COALESCE(source_type,'(미상)'), 'count', c) ORDER BY c DESC)
     FROM (SELECT source_type, count(*) c FROM anon GROUP BY source_type) s
  ), '[]'::jsonb),
  'pub_status', COALESCE((
     SELECT jsonb_agg(jsonb_build_object('label', COALESCE(status_code,'(미상)'), 'count', c) ORDER BY c DESC)
     FROM (SELECT status_code, count(*) c FROM pub GROUP BY status_code) s
  ), '[]'::jsonb)
);
$$;

CREATE OR REPLACE FUNCTION public.stats_customer_sites(
  p_start date DEFAULT (now() - interval '30 days')::date,
  p_end   date DEFAULT now()::date,
  p_period text DEFAULT 'daily'
) RETURNS jsonb
LANGUAGE sql STABLE
AS $$
WITH u AS (
  SELECT CASE lower(p_period) WHEN 'weekly' THEN 'week' WHEN 'monthly' THEN 'month' ELSE 'day' END AS unit
),
co AS (SELECT * FROM companies WHERE deleted_at IS NULL),
fa AS (SELECT * FROM factories WHERE deleted_at IS NULL)
SELECT jsonb_build_object(
  'summary', jsonb_build_object(
     'companies_total', (SELECT count(*) FROM co),
     'factories_total', (SELECT count(*) FROM fa),
     'new_companies',   (SELECT count(*) FROM co WHERE created_at >= p_start AND created_at < (p_end+1)),
     'new_factories',   (SELECT count(*) FROM fa WHERE created_at >= p_start AND created_at < (p_end+1))
  ),
  'chart', COALESCE((
     SELECT jsonb_agg(jsonb_build_object('date', to_char(d,'YYYY-MM-DD'), 'companies', cc, 'factories', fc) ORDER BY d)
     FROM (
       SELECT d, count(*) FILTER (WHERE src='co') AS cc, count(*) FILTER (WHERE src='fa') AS fc
       FROM (
         SELECT date_trunc((SELECT unit FROM u), created_at)::date AS d, 'co' AS src FROM co WHERE created_at >= p_start AND created_at < (p_end+1)
         UNION ALL
         SELECT date_trunc((SELECT unit FROM u), created_at)::date AS d, 'fa' AS src FROM fa WHERE created_at >= p_start AND created_at < (p_end+1)
       ) z GROUP BY d
     ) t
  ), '[]'::jsonb),
  'by_sector', COALESCE((
     SELECT jsonb_agg(jsonb_build_object('label', business_sector, 'count', c) ORDER BY c DESC)
     FROM (SELECT business_sector, count(*) c FROM co WHERE business_sector IS NOT NULL AND business_sector<>'' GROUP BY business_sector ORDER BY c DESC LIMIT 10) s
  ), '[]'::jsonb),
  'by_region', COALESCE((
     SELECT jsonb_agg(jsonb_build_object('label', address_sido, 'count', c) ORDER BY c DESC)
     FROM (SELECT address_sido, count(*) c FROM co WHERE address_sido IS NOT NULL AND address_sido<>'' GROUP BY address_sido ORDER BY c DESC LIMIT 15) s
  ), '[]'::jsonb),
  'by_size', COALESCE((
     SELECT jsonb_agg(jsonb_build_object('label', b, 'count', c) ORDER BY ord)
     FROM (
       SELECT b, ord, count(*) c FROM (
         SELECT
           CASE WHEN COALESCE(employee_count,0)=0 THEN '미상'
                WHEN employee_count < 5   THEN '5인 미만'
                WHEN employee_count < 50  THEN '5-49인'
                WHEN employee_count < 300 THEN '50-299인'
                ELSE '300인 이상' END AS b,
           CASE WHEN COALESCE(employee_count,0)=0 THEN 9
                WHEN employee_count < 5   THEN 1
                WHEN employee_count < 50  THEN 2
                WHEN employee_count < 300 THEN 3
                ELSE 4 END AS ord
         FROM co
       ) x GROUP BY b, ord
     ) y
  ), '[]'::jsonb)
);
$$;

GRANT EXECUTE ON FUNCTION public.stats_diagnosis_funnel(date,date,text) TO service_role, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.stats_customer_sites(date,date,text)   TO service_role, anon, authenticated;