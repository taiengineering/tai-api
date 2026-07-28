-- WO-3 CreditLedger: 전환크레딧 원장 (Goal G-ms4je4z3-33eada)
-- 정책: 진단 유료결제 후 30일 내 SaaS 전환 시 진단 결제액 100% 크레딧
CREATE TABLE IF NOT EXISTS public.credits (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id         uuid NOT NULL REFERENCES public.companies(id),
  source             text NOT NULL CHECK (source IN ('DIAGNOSIS_CONVERT','MANUAL')),
  source_ref         uuid,
  amount             integer NOT NULL CHECK (amount > 0),
  balance            integer NOT NULL CHECK (balance >= 0),
  expires_at         timestamptz,
  applied_payment_id uuid REFERENCES public.payments(id),
  status             text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','USED','EXPIRED')),
  memo               text,
  created_by         text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT credits_balance_le_amount CHECK (balance <= amount)
);
CREATE INDEX IF NOT EXISTS idx_credits_company ON public.credits(company_id);
CREATE INDEX IF NOT EXISTS idx_credits_status  ON public.credits(status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_credits_source_ref ON public.credits(source_ref) WHERE source_ref IS NOT NULL;
COMMENT ON TABLE public.credits IS 'WO-3 전환크레딧 원장: 진단→SaaS 30일 전환 크레딧. FIFO 차감·만료·감사.';