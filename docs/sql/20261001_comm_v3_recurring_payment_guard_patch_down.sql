-- WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-PATCH-001 / PATCH-B
-- DOWN: Revert index split.
-- Removes the new recurring active-attempt guard and restores the broad manual renewal index.

-- Remove recurring guard (added in UP)
DROP INDEX IF EXISTS public.uix_payments_subscription_cycle_v3_recurring_active;

-- Remove narrowed manual index (added in UP)
DROP INDEX IF EXISTS public.uix_payments_quote_v3_renewal_active;

-- Restore original broad manual renewal index
CREATE UNIQUE INDEX uix_payments_quote_v3_renewal_active
    ON public.payments (quote_id)
    WHERE quote_id IS NOT NULL
      AND product_type = 'SAAS'
      AND payment_type = 'RENEWAL'
      AND status_code IN ('PENDING', 'PAID', 'SUCCESS');
