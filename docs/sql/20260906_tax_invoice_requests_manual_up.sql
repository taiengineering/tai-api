-- WO-TAX-INVOICE-MANUAL-01 WP-A — tax_invoice_requests DDL for Admin 수동발행 + AUTO_PAYMENT defect fix
--
-- 목적:
--   A1  payment_id / company_id 을 nullable 로 완화 (ADMIN_MANUAL 만 payment-less 허용).
--       invariant CHECK 로 non-ADMIN_MANUAL 은 여전히 NOT NULL 보장.
--   A2  source_check 재정의: MYPAGE/SAAS/AUTO_PAYMENT/AUTO_SAAS/ADMIN_MANUAL.
--       (기존 CHECK 는 AUTO_PAYMENT 누락 defect — 코드/DB 불일치. WO-TAX-INVOICE-AUTO-01
--        의 AUTO orchestrator 가 프로덕션 CHECK 위반으로 실패하는 문제를 여기서 동시 수정)
--   A3  manual metadata 컬럼 신설 (idempotency_key uuid, item_name text, issue_reason text)
--       + partial UNIQUE (idempotency_key) WHERE source='ADMIN_MANUAL' AND idempotency_key IS NOT NULL
--   A4  amount_check (total = supply + vat) 유지 (삭제/완화 금지 — 이 파일은 이 CHECK 를 건드리지 않음)
--
-- 적용 순서:
--   1) DROP 기존 source_check → ADD 새 source_check
--   2) ALTER payment_id/company_id DROP NOT NULL
--   3) ADD invariant CHECK (source='ADMIN_MANUAL' AND payment_id IS NULL)
--                        OR (source<>'ADMIN_MANUAL' AND payment_id IS NOT NULL AND company_id IS NOT NULL)
--   4) ADD COLUMN idempotency_key uuid NULL, item_name text NULL, issue_reason text NULL
--   5) CREATE UNIQUE INDEX ... WHERE source='ADMIN_MANUAL' AND idempotency_key IS NOT NULL
--
-- ※ 이 파일은 apply_migration 로 프로덕션에 반영하지 말 것. 파일 작성 + static test 만.
--   실제 적용은 별도 릴리스 스텝에서 GPT/대표 명시 승인 후.

BEGIN;

-- ────────────────────────────────────────────────────────────────
-- A2 — source_check 재정의 (AUTO_PAYMENT defect 동시 수정)
-- ────────────────────────────────────────────────────────────────
ALTER TABLE public.tax_invoice_requests
  DROP CONSTRAINT IF EXISTS tax_invoice_requests_source_check;

ALTER TABLE public.tax_invoice_requests
  ADD CONSTRAINT tax_invoice_requests_source_check
  CHECK (source = ANY (ARRAY['MYPAGE', 'SAAS', 'AUTO_PAYMENT', 'AUTO_SAAS', 'ADMIN_MANUAL']));

-- ────────────────────────────────────────────────────────────────
-- A1 — payment_id / company_id 를 nullable 로 (ADMIN_MANUAL 전용)
--     기존 non-null 계약은 아래 invariant CHECK 로 유지.
-- ────────────────────────────────────────────────────────────────
ALTER TABLE public.tax_invoice_requests
  ALTER COLUMN payment_id DROP NOT NULL;

ALTER TABLE public.tax_invoice_requests
  ALTER COLUMN company_id DROP NOT NULL;

-- invariant: ADMIN_MANUAL 만 payment_id NULL 허용. 그 외 source 는 payment_id·company_id 반드시 NOT NULL.
-- (기존 MYPAGE/SAAS/AUTO_* 가 payment-less 로 새는 것 방지)
ALTER TABLE public.tax_invoice_requests
  DROP CONSTRAINT IF EXISTS tax_invoice_requests_admin_manual_payment_check;

ALTER TABLE public.tax_invoice_requests
  ADD CONSTRAINT tax_invoice_requests_admin_manual_payment_check
  CHECK (
    (source = 'ADMIN_MANUAL' AND payment_id IS NULL)
    OR
    (source <> 'ADMIN_MANUAL' AND payment_id IS NOT NULL AND company_id IS NOT NULL)
  );

-- ────────────────────────────────────────────────────────────────
-- A3 — manual metadata 컬럼 + partial UNIQUE index
-- ────────────────────────────────────────────────────────────────
ALTER TABLE public.tax_invoice_requests
  ADD COLUMN IF NOT EXISTS idempotency_key uuid NULL;

ALTER TABLE public.tax_invoice_requests
  ADD COLUMN IF NOT EXISTS item_name text NULL;

ALTER TABLE public.tax_invoice_requests
  ADD COLUMN IF NOT EXISTS issue_reason text NULL;

-- 더블클릭 / 재시도 방어. ADMIN_MANUAL 이고 idempotency_key 있을 때만 UNIQUE.
CREATE UNIQUE INDEX IF NOT EXISTS uq_tax_invoice_requests_admin_manual_idem
  ON public.tax_invoice_requests (idempotency_key)
  WHERE source = 'ADMIN_MANUAL' AND idempotency_key IS NOT NULL;

-- ────────────────────────────────────────────────────────────────
-- A4 — amount_check (total = supply + vat) 유지 확인 주석
-- ────────────────────────────────────────────────────────────────
-- 기존 tax_invoice_requests_amount_check 는 유지 (이 마이그레이션은 삭제/완화하지 않음).
-- 서버(라우터/서비스)에서 total = supply + vat 를 계산해 저장하므로 DB CHECK 는 항상 통과.

COMMIT;
