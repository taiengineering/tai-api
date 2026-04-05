-- 익명 무료 법령진단 결과 (public_token으로 조회, 로그인 후 claim)
-- Supabase SQL Editor 또는 마이그레이션으로 실행

CREATE TABLE IF NOT EXISTS public.anonymous_diagnosis_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_token text NOT NULL UNIQUE,
  input_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  partial_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  full_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  claimed_user_id uuid NULL REFERENCES public.users (id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'ACTIVE',
  source_type text NULL DEFAULT 'site_free',
  engine_version text NULL,
  rule_version text NULL
);

CREATE INDEX IF NOT EXISTS idx_anon_diag_expires ON public.anonymous_diagnosis_results (expires_at);
CREATE INDEX IF NOT EXISTS idx_anon_diag_claimed ON public.anonymous_diagnosis_results (claimed_user_id);

COMMENT ON TABLE public.anonymous_diagnosis_results IS '비로그인 무료진단 결과 임시 저장 (token 조회, 7일 만료, claim 시 users 귀속)';
