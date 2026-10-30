-- WO-016 WP-C: QA Monitor Notification Outbox
-- 상태: DRAFT — 운영 DB 미적용. Owner 승인 및 별도 Gate 필요.
--
-- 목적: WP-D Workflow 미시작 경보의 Slack 발송을 원자적으로 관리.
--       UNIQUE(dedupe_key)로 동일 Slot+상태에 대한 중복 경보 억제.
--
-- 적용 전 확인 사항:
--   1. qa_monitor_outbox_svc.py 코드 GPT IV 완료
--   2. QA_MONITOR_SLACK_ENABLED env var 준비
--   3. 운영 DB에 적용 전 staging 환경 검증

CREATE TABLE IF NOT EXISTS qa_monitor_notification_outbox (
    id                   uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
    dedupe_key           text        NOT NULL,           -- "<slot_utc>|<status_code>"
    slot_utc             text        NOT NULL,
    status_code          text        NOT NULL,
    slack_payload        jsonb       NOT NULL,
    status               text        NOT NULL DEFAULT 'PENDING',  -- PENDING/CLAIMED/SENDING/SENT/UNKNOWN/FAILED
    claim_token          uuid,
    claimed_at           timestamptz,
    claim_expires        timestamptz,
    dispatch_started_at  timestamptz,
    sent_at              timestamptz,
    error_detail         text,
    created_at           timestamptz DEFAULT now() NOT NULL,
    updated_at           timestamptz DEFAULT now() NOT NULL,

    CONSTRAINT qa_monitor_notification_outbox_dedupe UNIQUE (dedupe_key),
    CONSTRAINT qa_monitor_notification_outbox_status_check
        CHECK (status IN ('PENDING','CLAIMED','SENDING','SENT','UNKNOWN','FAILED'))
);

-- 미처리 PENDING/UNKNOWN 행 빠른 조회
CREATE INDEX IF NOT EXISTS idx_qa_monitor_outbox_status_created
    ON qa_monitor_notification_outbox (status, created_at)
    WHERE status IN ('PENDING', 'UNKNOWN');

-- stale CLAIMED/SENDING 복구 쿼리 지원
CREATE INDEX IF NOT EXISTS idx_qa_monitor_outbox_claim_expires
    ON qa_monitor_notification_outbox (claim_expires)
    WHERE status = 'CLAIMED';

COMMENT ON TABLE qa_monitor_notification_outbox IS
    'WO-016 WP-C: Workflow 미시작 경보 Slack 발송 아웃박스. '
    'UNIQUE(dedupe_key)로 동일 Slot+상태 중복 발송 억제.';
