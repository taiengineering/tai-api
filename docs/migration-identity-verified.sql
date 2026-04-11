-- 마이그레이션: users 테이블 본인인증 컬럼 추가
-- 상태: 준비됨 (미실행) — 이니시스 본인인증 연동 후 실행
-- 작성: 2026-04-11
--
-- 실행 시점:
--   이니시스 본인인증 신청 완료 → Supabase MCP apply_migration 으로 실행
--
-- 향후 연동 흐름:
--   POST /auth/verify-identity  → 이니시스 결과 수신 → users 업데이트
--   GET  /auth/me               → identity_verified 필드 포함 반환
--   유료 진단 폼 진입 시         → identity_verified=false이면 본인인증 페이지로 redirect

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS identity_verified     BOOLEAN   DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS identity_verified_at  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS identity_name         VARCHAR(50),
  ADD COLUMN IF NOT EXISTS identity_phone        VARCHAR(20);

COMMENT ON COLUMN users.identity_verified     IS '본인인증 완료 여부 (이니시스)';
COMMENT ON COLUMN users.identity_verified_at  IS '본인인증 완료 시각';
COMMENT ON COLUMN users.identity_name         IS '본인인증된 실명';
COMMENT ON COLUMN users.identity_phone        IS '본인인증된 휴대폰 번호';
