-- WO-FE-WWW-04-PRE-001: Frozen Quote V2 Duplicate Payment Guard
-- Partial unique index: 동일 quote에 대해 PENDING/PAID/SUCCESS 결제는 최대 1건.
-- FAILED 상태는 제외 — 재시도 허용.

CREATE UNIQUE INDEX uix_payments_quote_v2_initial_active
    ON payments (quote_id)
    WHERE product_type = 'SAAS'
      AND payment_type = 'CARD'
      AND status_code IN ('PENDING', 'PAID', 'SUCCESS');
