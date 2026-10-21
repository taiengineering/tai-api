-- ============================================================
-- Migration: 20261021000002_udl_rpc_permission_fix.sql
-- WO-TAI-DOC-WP03B-SIMPLIFY-001 작업 A
--
-- 목적: fn_udl_propose / fn_udl_transition EXECUTE 권한
--       PUBLIC, anon, authenticated 명시 회수.
-- 배경: Supabase 환경에서 CREATE FUNCTION 시 anon/authenticated에
--       자동 GRANT가 선행될 수 있으므로 PUBLIC REVOKE 외
--       역할별 명시 REVOKE 추가.
-- 함수 본문·테이블·트리거·데이터 변경 없음.
-- service_role EXECUTE 유지.
-- ============================================================

REVOKE EXECUTE ON FUNCTION
  public.fn_udl_propose(TEXT, UUID, UUID, TEXT, TEXT)
FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION
  public.fn_udl_transition(TEXT, UUID, TEXT, TEXT)
FROM PUBLIC, anon, authenticated;
