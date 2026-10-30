-- WO-016 WP-C: QA Monitor Notification Outbox
-- 상태: DRAFT — 운영 DB 미적용. Owner 승인 및 별도 Gate 필요.
--
-- 목적: WP-D Workflow 미시작 경보의 Slack 발송을 원자적으로 관리.
--       UNIQUE(dedupe_key)로 동일 Workflow 동일 예정 실행의 중복 경보 억제.
--
-- R1-03 dedupe_key 형식: "{owner}/{repo}|{workflow}|{slot_utc}|{event_type}"
-- R1-05 RLS: anon/authenticated 접근 차단, service_role 전용
--
-- 적용 전 확인 사항:
--   1. qa_monitor_outbox_svc.py R1 GPT IV 완료
--   2. QA_MONITOR_SLACK_ENABLED env var 준비
--   3. staging 환경 검증 후 운영 DB 적용

CREATE TABLE IF NOT EXISTS public.qa_monitor_notification_outbox (
    id                   uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
    dedupe_key           text        NOT NULL,   -- "{owner}/{repo}|{workflow}|{slot_utc}|{event_type}"
    slot_utc             text        NOT NULL,
    status_code          text        NOT NULL,
    slack_payload        jsonb       NOT NULL,
    status               text        NOT NULL DEFAULT 'PENDING',
    claim_token          uuid,
    claimed_at           timestamptz,
    claim_expires        timestamptz,
    dispatch_started_at  timestamptz,
    sent_at              timestamptz,
    error_detail         text,
    created_at           timestamptz DEFAULT now() NOT NULL,
    updated_at           timestamptz DEFAULT now() NOT NULL,

    CONSTRAINT qa_monitor_outbox_dedupe  UNIQUE (dedupe_key),
    CONSTRAINT qa_monitor_outbox_status  CHECK  (status IN (
        'PENDING','CLAIMED','SENDING','SENT','SENT_DB_FAILED','UNKNOWN','FAILED'
    ))
);

-- ─── 인덱스 ────────────────────────────────────────────────────────────────────

-- 미처리 PENDING/UNKNOWN 행 빠른 조회
CREATE INDEX IF NOT EXISTS idx_qa_monitor_outbox_status_created
    ON public.qa_monitor_notification_outbox (status, created_at)
    WHERE status IN ('PENDING', 'UNKNOWN');

-- stale CLAIMED 복구 쿼리 지원 (claim_expires 기준)
CREATE INDEX IF NOT EXISTS idx_qa_monitor_outbox_claim_expires
    ON public.qa_monitor_notification_outbox (claim_expires)
    WHERE status = 'CLAIMED';

-- ─── RLS ──────────────────────────────────────────────────────────────────────
-- R1-05: 서버 전용 테이블 — anon/authenticated 모든 접근 차단

ALTER TABLE public.qa_monitor_notification_outbox ENABLE ROW LEVEL SECURITY;

-- anon: 모든 접근 거부
CREATE POLICY "qamno_deny_anon"
    ON public.qa_monitor_notification_outbox
    AS RESTRICTIVE
    TO anon
    USING (FALSE);

-- authenticated: 모든 접근 거부 (Admin UI 직접 조회 금지)
CREATE POLICY "qamno_deny_auth"
    ON public.qa_monitor_notification_outbox
    AS RESTRICTIVE
    TO authenticated
    USING (FALSE);

-- service_role: 제한 없음 (서버 서비스 계정 전용)
CREATE POLICY "qamno_allow_service"
    ON public.qa_monitor_notification_outbox
    TO service_role
    USING (TRUE)
    WITH CHECK (TRUE);

-- ─── 코멘트 ────────────────────────────────────────────────────────────────────
COMMENT ON TABLE public.qa_monitor_notification_outbox IS
    'WO-016 WP-C R1: Workflow 미시작 경보 Slack 발송 아웃박스. '
    'UNIQUE(dedupe_key={owner}/{repo}|{workflow}|{slot_utc}|{event_type})로 중복 발송 억제. '
    'RLS: service_role 전용, anon/authenticated 차단.';

-- ─── 보관 정책 ────────────────────────────────────────────────────────────────
-- SENT / SENT_DB_FAILED / FAILED: 90일 후 삭제 (Owner 승인 후 pg_cron 설정)
-- UNKNOWN: 30일 후 운영자 수동 검토
-- 예시 cron (Owner 설정):
-- SELECT cron.schedule('qa-monitor-outbox-retention', '0 3 * * *',
--   $$DELETE FROM public.qa_monitor_notification_outbox
--     WHERE status IN ('SENT','SENT_DB_FAILED','FAILED')
--       AND created_at < now() - interval '90 days'$$);
