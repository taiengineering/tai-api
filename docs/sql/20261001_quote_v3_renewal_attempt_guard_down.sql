-- WO-COMM-V3-PAYMENT-MYPAGE-RENEWAL-WIRING-PATCH-002 — Rollback
DROP INDEX IF EXISTS public.uix_quotes_v3_renewal_source_active;
DROP INDEX IF EXISTS public.uix_payments_quote_v3_renewal_active;
