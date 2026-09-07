-- WO-SAFE-COMPANY-ACCESS-001 · WP-A
-- 회사 사용자 초대 테이블 (파일만 생성, APPLY 금지 · 오퍼레이터 별도 승인).
--
-- 규율:
--   token_hash 만 저장 (raw token DB/log/Slack/trace 금지 · SHA-256 hex).
--   partial unique (company_id, lower(email)) WHERE status='PENDING' — 같은 회사에서
--   같은 이메일에 대해 PENDING 중복 초대 방지.
--   RLS enable (service-role 만 조작 · endpoint-level guard 가 접근 통제).

CREATE TABLE IF NOT EXISTS company_user_invites (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          uuid    NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    email               text    NOT NULL,
    role_code           text    NOT NULL REFERENCES roles(role_code),
    factory_id          uuid    NULL REFERENCES factories(id)   ON DELETE SET NULL,
    team_id             uuid    NULL REFERENCES teams(id)       ON DELETE SET NULL,
    status              text    NOT NULL DEFAULT 'PENDING',
    token_hash          text    NOT NULL,
    invited_by          uuid    NULL REFERENCES users(id)       ON DELETE SET NULL,
    accepted_user_id    uuid    NULL REFERENCES users(id)       ON DELETE SET NULL,
    expires_at          timestamptz NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    accepted_at         timestamptz NULL,
    cancelled_at        timestamptz NULL,

    CONSTRAINT company_user_invites_status_check
        CHECK (status IN ('PENDING','ACCEPTED','EXPIRED','CANCELLED')),
    CONSTRAINT company_user_invites_token_hash_key UNIQUE (token_hash)
);

-- 같은 회사 + 같은 이메일 + PENDING 상태의 중복 초대 방지 (partial unique).
CREATE UNIQUE INDEX IF NOT EXISTS company_user_invites_pending_uidx
    ON company_user_invites (company_id, lower(email))
    WHERE status = 'PENDING';

-- 자주 쓰는 조회 인덱스 (company_id + created_at desc).
CREATE INDEX IF NOT EXISTS company_user_invites_company_created_idx
    ON company_user_invites (company_id, created_at DESC);

-- RLS enable · service-role 만 조작 (endpoint-level guard 가 실 권한 검증).
ALTER TABLE company_user_invites ENABLE ROW LEVEL SECURITY;
