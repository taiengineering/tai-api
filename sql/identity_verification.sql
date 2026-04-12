-- ============================================================
-- TAI API — 본인인증 DB 마이그레이션
-- 작성일: 2025-04-12
-- ============================================================

-- ── 1. users 테이블 컬럼 추가 ──────────────────────────────

ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_ci        text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_di        text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_name      text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_birth     text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_gender    text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_nation    text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_phone     text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_carrier   text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_method    text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_verified  boolean DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_verified_at timestamp;

-- CI 유니크 인덱스 (동일인 중복 가입 방지)
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_identity_ci
  ON users(identity_ci)
  WHERE identity_ci IS NOT NULL;

-- DI 인덱스
CREATE INDEX IF NOT EXISTS idx_users_identity_di
  ON users(identity_di)
  WHERE identity_di IS NOT NULL;


-- ── 2. identity_logs 테이블 신규 생성 ─────────────────────

CREATE TABLE IF NOT EXISTS identity_logs (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid REFERENCES users(id),
  method       text NOT NULL,           -- PHONE / KAKAO / PASS
  status       text NOT NULL,           -- PENDING / SUCCESS / FAILED
  request_id   text,
  ci           text,
  di           text,
  fail_reason  text,
  ip_address   text,
  user_agent   text,
  created_at   timestamp DEFAULT now(),
  completed_at timestamp
);

CREATE INDEX IF NOT EXISTS idx_identity_logs_user_id ON identity_logs(user_id);


-- ── 3. system_codes 등록 ──────────────────────────────────

-- 인증 방법
INSERT INTO system_codes (category, category_name, code, code_name, sort_order, is_active)
VALUES
  ('identity_method', '본인인증방법', 'PHONE', '휴대폰 인증',      1, true),
  ('identity_method', '본인인증방법', 'KAKAO', '카카오 간편인증',  2, true),
  ('identity_method', '본인인증방법', 'PASS',  'PASS 앱 인증',     3, true)
ON CONFLICT (category, code) DO NOTHING;

-- 통신사
INSERT INTO system_codes (category, category_name, code, code_name, sort_order, is_active)
VALUES
  ('identity_carrier', '통신사', 'SKT',     'SKT',       1, true),
  ('identity_carrier', '통신사', 'KT',      'KT',        2, true),
  ('identity_carrier', '통신사', 'LGU',     'LGU+',      3, true),
  ('identity_carrier', '통신사', 'SKT_MVN', 'SKT 알뜰',  4, true),
  ('identity_carrier', '통신사', 'KT_MVN',  'KT 알뜰',   5, true),
  ('identity_carrier', '통신사', 'LGU_MVN', 'LGU 알뜰',  6, true)
ON CONFLICT (category, code) DO NOTHING;
