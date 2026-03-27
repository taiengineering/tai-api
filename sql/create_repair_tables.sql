-- 수선중개 테이블 생성
-- Supabase SQL Editor에서 실행

-- 1. 수선업체
CREATE TABLE IF NOT EXISTS repair_companies (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name        text NOT NULL,
    representative_name text,
    contact_phone       text,
    contact_email       text,
    address             text,
    service_regions     text[] DEFAULT '{}',
    max_project_amount  int,
    verified_status     text DEFAULT 'UNVERIFIED',
    is_active           bool DEFAULT true,
    created_at          timestamptz DEFAULT now(),
    updated_at          timestamptz
);

-- 2. 수선 의뢰
CREATE TABLE IF NOT EXISTS repair_requests (
    id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_id                uuid REFERENCES factories(id),
    company_id                uuid REFERENCES companies(id),
    request_title             text NOT NULL,
    request_content           text,
    project_amount            int DEFAULT 0,
    fee_amount                int DEFAULT 0,
    matched_repair_company_id uuid REFERENCES repair_companies(id),
    status_code               text DEFAULT 'PENDING',
    created_at                timestamptz DEFAULT now(),
    updated_at                timestamptz
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_repair_companies_active ON repair_companies(is_active);
CREATE INDEX IF NOT EXISTS idx_repair_requests_status ON repair_requests(status_code);
CREATE INDEX IF NOT EXISTS idx_repair_requests_factory ON repair_requests(factory_id);
