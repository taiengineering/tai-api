-- Migration: 20261022000002_sec04_udl7_privilege_function_revoke.sql
-- WO: WO-TAI-SEC04-UDL7-IMPLEMENT-001
-- SEC-04: UDL 트리거 함수 7개 공개 실행권한 제거.
--
-- 배경:
--   7개 함수 모두 SECURITY DEFINER + 반환 타입 trigger.
--   20261020000007에서 REVOKE FROM PUBLIC만 적용됐으나
--   Supabase는 함수를 생성할 때 anon/authenticated에 명시적 GRANT를 자동 부여.
--   결과: anon/authenticated EXECUTE 잔존 → 명시 회수 필요.
--
-- 트리거 연결 (8건, 회수 후에도 정상 동작):
--   PostgreSQL은 트리거 호출 시 함수 EXECUTE 권한을 재검사하지 않음.
--   trg_udl_insert_guard   BEFORE INSERT  unified_document_link
--   trg_udl_version_bump   BEFORE UPDATE  unified_document_link
--   trg_udl_immutability   BEFORE UPDATE  unified_document_link
--   trg_udl_state_guard    BEFORE UPDATE  unified_document_link
--   trg_udl_no_delete      BEFORE DELETE  unified_document_link
--   trg_udl_audit          AFTER INSERT OR UPDATE  unified_document_link
--   trg_udl_audit_no_update BEFORE UPDATE unified_document_link_audit
--   trg_udl_audit_no_delete BEFORE DELETE unified_document_link_audit
--
-- 변경 범위:
--   PUBLIC, anon, authenticated → EXECUTE 회수 (7건).
--   service_role → 기존 명시적 GRANT 유지 (본 migration에서 변경 없음).
--   함수 본문·SECURITY DEFINER 속성·트리거 정의 변경 없음.
--
-- 패턴: 20261021000002_udl_rpc_permission_fix.sql
--       20261022000001_sec04_csi_privilege_function_revoke.sql
-- 기준: GPT_SEC04_UDL7_ACL_DESIGN_IV = PASS_WITH_ONE_CORRECTION

REVOKE EXECUTE ON FUNCTION
    public.fn_udl_audit_deny_mutate()
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.fn_udl_audit_state_change()
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.fn_udl_deny_delete()
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.fn_udl_immutability_guard()
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.fn_udl_insert_guard()
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.fn_udl_state_guard()
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
    public.fn_udl_version_bump()
FROM PUBLIC, anon, authenticated;
