-- 견적(quotes) — 법적진단 설문(https://taieng.co.kr/survey) 저장
-- Supabase → SQL Editor에서 실행

ALTER TABLE public.quotes
  ADD COLUMN IF NOT EXISTS survey_data jsonb DEFAULT '{}'::jsonb;

ALTER TABLE public.quotes
  ADD COLUMN IF NOT EXISTS source text;

ALTER TABLE public.quotes
  ADD COLUMN IF NOT EXISTS company_name text;

ALTER TABLE public.quotes
  ADD COLUMN IF NOT EXISTS contact_phone text;

ALTER TABLE public.quotes
  ADD COLUMN IF NOT EXISTS contact_email text;

-- 웹 설문은 회사 미선택 → NULL 허용 (이미 허용이면 에러 없이 통과하지 않을 수 있음 — 무시)
ALTER TABLE public.quotes
  ALTER COLUMN company_id DROP NOT NULL;

COMMENT ON COLUMN public.quotes.survey_data IS '법적진단 설문 원본 JSON';
