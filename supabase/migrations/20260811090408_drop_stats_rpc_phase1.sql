-- 임시 Phase1 통계 RPC 폐기 — admin-vue3 신규 설계로 재구현하므로 제거.
-- (오배치/중복: 기존 /stats/dashboard(stats_dashboard_svc)와 병행이던 임시 함수)
DROP FUNCTION IF EXISTS public.stats_diagnosis_funnel(date, date, text);
DROP FUNCTION IF EXISTS public.stats_customer_sites(date, date, text);