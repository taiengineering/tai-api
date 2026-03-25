-- ============================================================
-- quotes 테이블: survey(웹 견적문의) 대응 컬럼 추가
-- Supabase SQL Editor에서 실행
-- ============================================================

-- 1. company_id NOT NULL 제약 제거 (survey는 company_id 없이 접수)
ALTER TABLE quotes ALTER COLUMN company_id DROP NOT NULL;

-- 2. survey 관련 컬럼 추가 (이미 존재하면 무시)
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS company_name   TEXT;
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS source         TEXT DEFAULT 'admin';
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS survey_data    JSONB;
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS survey_type    TEXT DEFAULT 'basic';

-- 3. 확인
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'quotes'
ORDER BY ordinal_position;
