-- ============================================================================
-- Billing Phase 2 schema adjustments
-- Date: 2026-04-23
-- Related: tai-api #45 (Billing endpoints)
--
-- Changes:
--   1) subscriptions.billing_key_id -> NULLABLE
--      reason: During PENDING (before BillKey issuance), the key does not
--              yet exist. We populate billing_key_id only after the
--              /billing/return callback succeeds.
--
--   2) subscriptions.inicis_order_id (new TEXT column)
--      reason: The callback from INICIS arrives with orderNumber (oid).
--              We need an indexed column to look up the PENDING subscription
--              by oid. Same pattern as payments.inicis_order_id.
--
--   3) payments(subscription_id, charge_cycle) UNIQUE (partial)
--      reason: Idempotency guard for recurring charges. Prevents two
--              charges from being recorded for the same subscription/cycle
--              when a retry or duplicate cron tick occurs.
-- ============================================================================

-- 1) Allow NULL for billing_key_id during PENDING state
ALTER TABLE subscriptions
    ALTER COLUMN billing_key_id DROP NOT NULL;

COMMENT ON COLUMN subscriptions.billing_key_id IS
    'FK to billing_keys.id. NULL while subscription is PENDING (before BillKeyAuth). Set after /billing/return succeeds.';

-- 2) Add inicis_order_id for callback lookup
ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS inicis_order_id TEXT;

COMMENT ON COLUMN subscriptions.inicis_order_id IS
    'INICIS oid issued at /billing/prepare (e.g. TAI-BIL-YYYYMMDDhhmmss-xxxxxx). Used to match the /billing/return callback to the PENDING subscription row.';

-- Unique index on non-null inicis_order_id (duplicate prepare guard)
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_inicis_order_id
    ON subscriptions(inicis_order_id)
    WHERE inicis_order_id IS NOT NULL;

-- 3) Idempotency guard for recurring charges
CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_subscription_cycle
    ON payments(subscription_id, charge_cycle)
    WHERE subscription_id IS NOT NULL;

COMMENT ON INDEX idx_payments_subscription_cycle IS
    'Prevents duplicate charges for the same subscription/cycle (retry or cron double-tick).';
