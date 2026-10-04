-- Migration: expose msds_ref schema to PostgREST
-- Purpose  : Supabase REST API (PostgREST) 가 msds_ref 스키마를 인식하도록
--            authenticator role 기본 설정에 추가.
--            이 설정이 없으면 PGRST106 "Invalid schema: msds_ref" 발생.
-- Schema   : global (authenticator role 설정)
-- Applied  : leg-prod 2026-10-04 (apply_migration 으로 기적용)
-- NOTE     : DB에 이미 적용됨 — 재실행 시 멱등성 보장 (SET은 덮어쓰기).

ALTER ROLE authenticator SET pgrst.db_schemas = 'public, msds_ref';
NOTIFY pgrst, 'reload schema';
