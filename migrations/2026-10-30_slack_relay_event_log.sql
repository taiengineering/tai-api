-- WO-TAI-SLACK-BOT-UNIFIED-001-R3 — Slack Events Relay 영속 로그
-- 운영 DB 적용 금지 (Owner Gate 별도)
-- Addendum FINAL 확정 스키마 (COR-01 포함)

CREATE TABLE IF NOT EXISTS public.slack_relay_event_log (
    id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id             text        NOT NULL UNIQUE,
    relay_channel        text        NOT NULL,
    target_channel       text        NOT NULL,
    message_text         text        NOT NULL CHECK (char_length(message_text) <= 4000),
    sender_id            text,
    source_message_ts    text,
    status               text        NOT NULL DEFAULT 'PENDING'
                             CHECK (status IN ('PENDING','CLAIMED','SENDING','SENT',
                                               'RETRY','UNKNOWN','FAILED_PERMANENT')),
    retry_count          int         NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    next_attempt_at      timestamptz,
    claimed_at           timestamptz,
    dispatch_started_at  timestamptz,
    sent_at              timestamptz,
    slack_ts             text,
    claim_token          text,
    claim_expires        timestamptz,                                     -- COR-04: lease expiry
    error_detail         text CHECK (char_length(error_detail) <= 2000),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

-- 복구 Worker 스캔 인덱스: PENDING/RETRY 행을 created_at 순 조회
CREATE INDEX IF NOT EXISTS idx_srel_status_next
    ON public.slack_relay_event_log (status, next_attempt_at, created_at);

-- event_id 조회 인덱스 (accept_relay_event 중복 검사)
CREATE INDEX IF NOT EXISTS idx_srel_event_id
    ON public.slack_relay_event_log (event_id);

-- updated_at 인덱스 (stale CLAIMED/SENDING 복구 스캔)
CREATE INDEX IF NOT EXISTS idx_srel_updated_at
    ON public.slack_relay_event_log (updated_at);

-- ─── RLS ──────────────────────────────────────────────────────────────────────
ALTER TABLE public.slack_relay_event_log ENABLE ROW LEVEL SECURITY;

-- anon/authenticated: 모든 접근 거부 (서버 전용 테이블)
CREATE POLICY "srel_deny_anon"    ON public.slack_relay_event_log AS RESTRICTIVE TO anon        USING (FALSE);
CREATE POLICY "srel_deny_auth"    ON public.slack_relay_event_log AS RESTRICTIVE TO authenticated USING (FALSE);

-- service_role: 제한 없음 (서버 서비스 계정)
CREATE POLICY "srel_allow_service" ON public.slack_relay_event_log TO service_role USING (TRUE) WITH CHECK (TRUE);

-- ─── 보관 정책 ────────────────────────────────────────────────────────────────
-- SENT / FAILED_PERMANENT: 90일 후 삭제 (Owner 승인 후 pg_cron 설정)
-- UNKNOWN: 30일 후 운영자 수동 검토
-- 예시 cron (Owner 설정):
-- SELECT cron.schedule('slack-relay-cleanup', '0 3 * * *',
--   $$DELETE FROM public.slack_relay_event_log
--     WHERE status IN ('SENT','FAILED_PERMANENT') AND created_at < now() - INTERVAL '90 days'$$);
