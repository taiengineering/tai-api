-- WO-1 RefundService: 환불 대장 (Goal G-ms4je4z3-33eada)
-- 불변식: 한 payment 다건 환불 허용, SUM(amount WHERE status='DONE') <= payments.total_amount (서비스 로직 강제)
CREATE TABLE IF NOT EXISTS public.refunds (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_id          uuid NOT NULL REFERENCES public.payments(id),
  refund_type         text NOT NULL CHECK (refund_type IN ('FULL','PARTIAL')),
  amount              integer NOT NULL CHECK (amount > 0),
  cumulative_refunded integer NOT NULL DEFAULT 0,
  reason_code         text,
  reason_text         text NOT NULL,
  inicis_tid          text,
  inicis_refund_tid   text,
  inicis_raw          jsonb,
  status              text NOT NULL DEFAULT 'REQUESTED' CHECK (status IN ('REQUESTED','DONE','FAILED')),
  processed_by        text,
  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_refunds_payment ON public.refunds(payment_id);
CREATE INDEX IF NOT EXISTS idx_refunds_status  ON public.refunds(status);
COMMENT ON TABLE public.refunds IS 'WO-1 환불 대장: 이니시스 취소/환불 원장. 사유·누적환불액·PG응답 기록.';