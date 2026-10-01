-- WO-COMM-V3-PAYMENT-MYPAGE-RENEWAL-WIRING-PATCH-002
-- Renewal Quote 중복 발행 방지 — 같은 계약 버전당 하나의 활성 Renewal Quote만 허용
-- Production 적용 = Owner Approval 필요
-- Pre-condition: renewal_quotes=0, V3 renewal payments=0

CREATE UNIQUE INDEX uix_quotes_v3_renewal_source_active
ON public.quotes (
  company_id,
  (survey_data #>> '{commercial_v3_renewal,contract_id}'),
  (survey_data #>> '{commercial_v3_renewal,current_version_no}')
)
WHERE source = 'member_auto'
  AND service_type = 'SAAS'
  AND status_code = 'ISSUED'
  AND survey_data ? 'commercial_v3_renewal';

-- Renewal Payment 중복 결제 방지 — 같은 Renewal Quote당 하나의 활성 Payment만 허용
CREATE UNIQUE INDEX uix_payments_quote_v3_renewal_active
ON public.payments (quote_id)
WHERE quote_id IS NOT NULL
  AND product_type = 'SAAS'
  AND payment_type = 'RENEWAL'
  AND status_code IN ('PENDING', 'PAID', 'SUCCESS');
