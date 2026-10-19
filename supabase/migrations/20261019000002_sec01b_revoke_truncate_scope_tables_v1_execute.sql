-- SEC-01B: WO-TAI-SUPABASE-SEC-01B
-- truncate_scope_tables_v1() 외부 실행 권한 차단
--
-- 이 함수는 SECURITY DEFINER로 실행되며 내부에서
-- TRUNCATE TABLE master_rule_scope CASCADE를 수행합니다.
-- (master_rule_scope_mapping, master_rule_scope_threshold CASCADE 포함)
--
-- 소스코드 호출 없음 확인 (org:taiengineering 전수검색, incomplete_results=false)
-- service_role / postgres 권한은 유지합니다.

REVOKE EXECUTE
  ON FUNCTION public.truncate_scope_tables_v1()
  FROM PUBLIC, anon, authenticated;
