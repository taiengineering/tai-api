-- reparse_job_log: reparse-master 백그라운드 작업 추적 테이블
-- 2026-04-20

CREATE TABLE IF NOT EXISTS reparse_job_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  job_id UUID NOT NULL,
  sector VARCHAR(50),
  total_targeted INT DEFAULT 0,
  processed INT DEFAULT 0,
  updated INT DEFAULT 0,
  skipped INT DEFAULT 0,
  errors INT DEFAULT 0,
  error_details JSONB DEFAULT '[]',
  changed_fields JSONB DEFAULT '{}',
  status VARCHAR(20) DEFAULT 'RUNNING',  -- RUNNING / COMPLETED / FAILED
  started_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- job_id 인덱스 (상태 조회용)
CREATE INDEX IF NOT EXISTS idx_reparse_job_log_job_id ON reparse_job_log (job_id);

-- status 인덱스 (목록 조회용)
CREATE INDEX IF NOT EXISTS idx_reparse_job_log_status ON reparse_job_log (status);

-- RLS 비활성화 (내부 서비스 전용 테이블)
ALTER TABLE reparse_job_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON reparse_job_log
  FOR ALL
  USING (true)
  WITH CHECK (true);
