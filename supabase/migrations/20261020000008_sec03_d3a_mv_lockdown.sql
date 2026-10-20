-- SEC-03 D3-A Materialized View 직접 접근 차단
-- WO-TAI-SEC03-D3A-MATERIALIZED-VIEW-LOCKDOWN-001
--
-- 대상: public.dashboard_stats, public.engine_equipment_summary (Materialized View 2개)
-- 조치: anon, authenticated 직접 객체 권한 전부 제거
-- 보존: postgres, service_role 권한 / MV 정의 / 적재 데이터 / Refresh 방식
--
-- BASE_SHA = 48441217f70abcef60f344d77b9f58470a35aaf3

-- FIX-A: dashboard_stats — anon/authenticated 직접 권한 제거
REVOKE ALL PRIVILEGES ON TABLE public.dashboard_stats FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.dashboard_stats FROM authenticated;

-- FIX-B: engine_equipment_summary — anon/authenticated 직접 권한 제거
REVOKE ALL PRIVILEGES ON TABLE public.engine_equipment_summary FROM anon;
REVOKE ALL PRIVILEGES ON TABLE public.engine_equipment_summary FROM authenticated;
