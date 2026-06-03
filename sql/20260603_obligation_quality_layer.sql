-- Phase 9 — Obligation Quality Layer MVP
-- obligation_quality : 의무 품질상태 저장 (Check 결과 소비 결과)
-- admin_obligation_queue : 보정 작업 큐 (CORRECTION_REQUIRED 발생 시)
-- 새 엔진 아님. Check/LEG 결과를 운영에 연결하는 운영 테이블.

-- ============================================================
-- obligation_quality
-- ============================================================
CREATE TABLE IF NOT EXISTS obligation_quality (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    obligation_id   text NOT NULL,
    quality_status  text NOT NULL CHECK (quality_status IN ('READY','TRACE_REQUIRED','CORRECTION_REQUIRED')),
    quality_reason  text,
    check_report_id text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT obligation_quality_obligation_id_key UNIQUE (obligation_id)
);

CREATE INDEX IF NOT EXISTS idx_obligation_quality_status
    ON obligation_quality (quality_status);

-- 백엔드는 service role 키로 접근(RLS 우회). anon 차단 위해 RLS 활성화.
ALTER TABLE obligation_quality ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- admin_obligation_queue
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_obligation_queue (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    obligation_id text NOT NULL,
    reason        text,
    status        text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED')),
    assigned_to   text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    resolved_at   timestamptz
);

CREATE INDEX IF NOT EXISTS idx_admin_obligation_queue_status
    ON admin_obligation_queue (status);
CREATE INDEX IF NOT EXISTS idx_admin_obligation_queue_obligation_id
    ON admin_obligation_queue (obligation_id);

ALTER TABLE admin_obligation_queue ENABLE ROW LEVEL SECURITY;
