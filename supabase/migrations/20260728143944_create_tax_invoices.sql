-- WO-4 InvoiceService: 세금계산서·현금영수증 원장 (Goal G-ms4je4z3-33eada)
-- 팝빌 발행 상태·문서번호(mgtKey)·국세청승인번호·응답 보관. doc_type으로 두 문서 통합.
CREATE TABLE IF NOT EXISTS public.tax_invoices (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_id      uuid REFERENCES public.payments(id),
  company_id      uuid REFERENCES public.companies(id),
  doc_type        text NOT NULL CHECK (doc_type IN ('TAX_INVOICE','CASH_RECEIPT')),
  mgt_key         text NOT NULL,
  trade_usage     text,
  invoicee_type   text,
  identity_num    text,
  supply_cost     integer NOT NULL,
  tax             integer NOT NULL,
  total_amount    integer NOT NULL,
  nts_confirm_num text,
  status          text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','ISSUED','CANCELLED','FAILED')),
  popbill_raw     jsonb,
  issued_at       timestamptz,
  created_by      text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tax_invoices_payment ON public.tax_invoices(payment_id);
CREATE INDEX IF NOT EXISTS idx_tax_invoices_company ON public.tax_invoices(company_id);
CREATE INDEX IF NOT EXISTS idx_tax_invoices_status  ON public.tax_invoices(status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tax_invoices_mgtkey ON public.tax_invoices(doc_type, mgt_key);
COMMENT ON TABLE public.tax_invoices IS 'WO-4 세금계산서·현금영수증 원장(팝빌). doc_type=TAX_INVOICE|CASH_RECEIPT. mgt_key=팝빌 문서번호.';