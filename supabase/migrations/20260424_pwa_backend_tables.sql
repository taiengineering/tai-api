-- PWA 백엔드 보강: 긴급신고 + 이상신고 테이블
-- 2026-04-24

-- 긴급신고
CREATE TABLE IF NOT EXISTS emergency_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_number   TEXT UNIQUE NOT NULL,
    phone           TEXT NOT NULL,
    worker_name     TEXT NOT NULL,
    accident_type   TEXT NOT NULL,
    accident_type_key TEXT NOT NULL,
    location        TEXT,
    location_lat    DOUBLE PRECISION,
    location_lng    DOUBLE PRECISION,
    photo_urls      JSONB DEFAULT '[]'::jsonb,
    reporter_id     UUID REFERENCES users(id),
    status          TEXT DEFAULT 'RECEIVED',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_emergency_reports_number ON emergency_reports(report_number);
CREATE INDEX IF NOT EXISTS idx_emergency_reports_created ON emergency_reports(created_at DESC);

-- 이상신고
CREATE TABLE IF NOT EXISTS safety_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_number   TEXT UNIQUE NOT NULL,
    phone           TEXT NOT NULL,
    worker_id       UUID,
    factory_id      UUID,
    site_id         UUID,
    report_type     TEXT NOT NULL,
    description     TEXT NOT NULL,
    urgency         TEXT DEFAULT 'normal',
    location_lat    DOUBLE PRECISION,
    location_lng    DOUBLE PRECISION,
    location_text   TEXT,
    photo_urls      JSONB DEFAULT '[]'::jsonb,
    reporter_id     UUID REFERENCES users(id),
    status          TEXT DEFAULT 'RECEIVED',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_safety_reports_number ON safety_reports(report_number);
CREATE INDEX IF NOT EXISTS idx_safety_reports_created ON safety_reports(created_at DESC);

-- safety_inspection_results에 photo_urls 컬럼 추가 (worker-check 보강)
ALTER TABLE safety_inspection_results
    ADD COLUMN IF NOT EXISTS photo_urls JSONB DEFAULT '[]'::jsonb;
