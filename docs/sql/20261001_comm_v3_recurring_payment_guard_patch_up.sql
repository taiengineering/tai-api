-- WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-PATCH-001 / PATCH-B
-- UP: Split manual renewal guard from recurring active-attempt guard.
-- No Production apply in this WO. Owner DDL gate required before apply.
-- Production manual renewal index is still the old broad definition — DO NOT apply yet.

-- ── Duplicate-precheck queries for Owner DDL gate ─────────────────────────────
-- Run these before applying to verify no in-flight rows would be duplicated:
--
--   -- Check existing RENEWAL rows that would conflict with manual index narrowing:
--   SELECT quote_id, COUNT(*)
--   FROM public.payments
--   WHERE quote_id IS NOT NULL
--     AND product_type = 'SAAS'
--     AND payment_type = 'RENEWAL'
--     AND is_recurring IS NOT TRUE
--     AND status_code IN ('PENDING', 'PAID', 'SUCCESS')
--   GROUP BY quote_id HAVING COUNT(*) > 1;
--
--   -- Check existing RENEWAL RECURRING rows that would conflict with new index:
--   SELECT subscription_id, charge_cycle, COUNT(*)
--   FROM public.payments
--   WHERE subscription_id IS NOT NULL
--     AND charge_cycle IS NOT NULL
--     AND product_type = 'SAAS'
--     AND payment_type = 'RENEWAL'
--     AND is_recurring IS TRUE
--     AND status_code IN ('PENDING', 'PAID', 'SUCCESS')
--   GROUP BY subscription_id, charge_cycle HAVING COUNT(*) > 1;
--
-- Both queries must return 0 rows before applying.
-- ─────────────────────────────────────────────────────────────────────────────

-- 3.1: Narrow existing manual renewal index to is_recurring IS NOT TRUE only.
-- DROP the broad index first, then recreate with the narrowed partial filter.
DROP INDEX IF EXISTS public.uix_payments_quote_v3_renewal_active;

CREATE UNIQUE INDEX uix_payments_quote_v3_renewal_active
    ON public.payments (quote_id)
    WHERE quote_id IS NOT NULL
      AND product_type = 'SAAS'
      AND payment_type = 'RENEWAL'
      AND is_recurring IS NOT TRUE
      AND status_code IN ('PENDING', 'PAID', 'SUCCESS');

-- 3.2: New recurring active-attempt guard — prevents duplicate in-flight charges
--      for the same subscription + cycle via scheduler or manual trigger.
CREATE UNIQUE INDEX uix_payments_subscription_cycle_v3_recurring_active
    ON public.payments (subscription_id, charge_cycle)
    WHERE subscription_id IS NOT NULL
      AND charge_cycle IS NOT NULL
      AND product_type = 'SAAS'
      AND payment_type = 'RENEWAL'
      AND is_recurring IS TRUE
      AND status_code IN ('PENDING', 'PAID', 'SUCCESS');
