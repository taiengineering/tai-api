-- SEC-03 RPC-ENGINE-EQUIPMENT-LOCKDOWN
-- WO-TAI-SEC03-RPC-ENGINE-EQUIPMENT-LOCKDOWN-001
--
-- 대상: public.refresh_engine_equipment_summary()
-- 조치: PUBLIC, anon, authenticated EXECUTE 권한 제거
-- 보존: postgres, service_role EXECUTE / 함수 정의 / SECURITY DEFINER
--
-- BASE_SHA = e820ed064eab4f22eadb4facf8d6515583a00adf

REVOKE EXECUTE
ON FUNCTION public.refresh_engine_equipment_summary()
FROM PUBLIC, anon, authenticated;
