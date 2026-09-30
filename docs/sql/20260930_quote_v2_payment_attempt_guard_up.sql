-- WO-FE-WWW-04-PRE-001: Frozen Quote V2 Duplicate Payment Guard
-- Partial unique index: 동일 quote에 대해 PENDING/PAID/SUCCESS 결제는 최대 1건.
-- FAILED 상태는 predicate 밖 — 재시도 허용.
-- quote_id IS NOT NULL: Frozen Quote V2 초기 결제에 한정하는 명시적 범위.

CREATE UNIQUE INDEX IF NOT EXISTS uix_payments_quote_v2_initial_active
    ON public.payments (quote_id)
    WHERE quote_id IS NOT NULL
      AND product_type = 'SAAS'
      AND payment_type = 'CARD'
      AND status_code IN ('PENDING', 'PAID', 'SUCCESS');
