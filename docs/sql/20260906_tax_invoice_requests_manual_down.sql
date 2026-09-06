-- WO-TAX-INVOICE-MANUAL-01 WP-A DOWN — 롤백 (역순).
--
-- 주의: 이 DOWN 을 적용하면 ADMIN_MANUAL row / AUTO_PAYMENT row 가 삭제되지 않은 상태에서
--   CHECK 위반이 발생할 수 있음. 실제 롤백 전 데이터 정리 스크립트 필요.
--   이 파일은 static test / 감사용. apply 금지.

BEGIN;

-- A3 DOWN — partial UNIQUE 제거 + 컬럼 제거
DROP INDEX IF EXISTS public.uq_tax_invoice_requests_admin_manual_idem;

ALTER TABLE public.tax_invoice_requests
  DROP COLUMN IF EXISTS issue_reason;

ALTER TABLE public.tax_invoice_requests
  DROP COLUMN IF EXISTS item_name;

ALTER TABLE public.tax_invoice_requests
  DROP COLUMN IF EXISTS idempotency_key;

-- A1 DOWN — invariant CHECK 제거 + NOT NULL 복원
ALTER TABLE public.tax_invoice_requests
  DROP CONSTRAINT IF EXISTS tax_invoice_requests_admin_manual_payment_check;

-- NOT NULL 복원 전 데이터 정리 필요 (ADMIN_MANUAL row 삭제 후 진행).
ALTER TABLE public.tax_invoice_requests
  ALTER COLUMN payment_id SET NOT NULL;

ALTER TABLE public.tax_invoice_requests
  ALTER COLUMN company_id SET NOT NULL;

-- A2 DOWN — source_check 되돌림 (defect 상태로 복귀 — AUTO_PAYMENT 제거).
--   ※ AUTO_* row 가 남아있으면 CHECK 위반. 데이터 정리 필요.
ALTER TABLE public.tax_invoice_requests
  DROP CONSTRAINT IF EXISTS tax_invoice_requests_source_check;

ALTER TABLE public.tax_invoice_requests
  ADD CONSTRAINT tax_invoice_requests_source_check
  CHECK (source = ANY (ARRAY['MYPAGE', 'SAAS', 'AUTO_SAAS']));

COMMIT;
