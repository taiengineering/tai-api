-- Migration: 20261022000001_sec04_csi_privilege_function_revoke.sql
-- WO: WO-TAI-SUPABASE-SEC04-CSI4-REVOKE-IMPLEMENT-001
-- SEC-04: CSI SECURITY DEFINER 함수 4개 공개 실행권한 제거.
--
-- 배경:
--   네 함수 모두 SECURITY DEFINER + Vault internal_api_secret 참조.
--   anon/authenticated EXECUTE 허용 상태 → Data API 경유 외부 호출 가능.
--   기존 Python API(admin_csi_keyword_extract.py)는 이 함수들을 사용하지 않음.
--   pg_cron 13건 내 직접 참조 0건.
--
-- 변경 범위:
--   PUBLIC, anon, authenticated → EXECUTE 회수.
--   service_role → 기존 명시적 GRANT 유지 (본 migration에서 변경 없음).
--   함수 본문·SECURITY DEFINER 속성·Vault 설정 변경 없음.
--
-- 기준: GPT_SEC04_CSI4_REVOKE_DESIGN_IV = PASS_WITH_ANNOTATIONS
-- 패턴: 20261021000002_udl_rpc_permission_fix.sql

REVOKE EXECUTE ON FUNCTION
    public.invoke_csi_keyword_extract(integer)
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.repair_csi_blocklist_keywords(integer)
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.start_csi_keyword_extract_job()
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.status_csi_keyword_extract_job()
FROM PUBLIC, anon, authenticated;
