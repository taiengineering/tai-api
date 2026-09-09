-- WO-COMMON-TIER-PAYMENT-GATE-MODULARIZE-001 / B3
-- saas_tier_upgrade_transitions : 티어 업그레이드 durable ledger.
--
-- ARTIFACT ONLY — PRODUCTION APPLY = 0 (운영자/GPT 승인 후 별도 실행).
-- idempotent: IF NOT EXISTS. payment_id UNIQUE.

CREATE TABLE IF NOT EXISTS public.saas_tier_upgrade_transitions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id uuid NOT NULL UNIQUE,
    company_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    sector text NOT NULL,
    from_plan_code text NOT NULL,
    target_plan_code text NOT NULL,
    billing_unit text NOT NULL,
    current_supply_amount numeric NOT NULL,
    target_supply_amount numeric NOT NULL,
    delta_supply_amount numeric NOT NULL,
    delta_vat_amount numeric NOT NULL,
    delta_total_amount numeric NOT NULL,
    target_vat_amount numeric NOT NULL,
    target_total_amount numeric NOT NULL,
    status text NOT NULL,
    last_error text,
    applied_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    subscription_id uuid,
    subscription_snapshot jsonb,
    target_plan_name text,
    CONSTRAINT saas_tier_upgrade_transitions_entity_type_chk
        CHECK (entity_type IN ('factory', 'site')),
    CONSTRAINT saas_tier_upgrade_transitions_status_chk
        CHECK (status IN ('PREPARED', 'APPLIED', 'APPLY_FAILED'))
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'saas_tier_upgrade_transitions_payment_fk'
    ) THEN
        ALTER TABLE public.saas_tier_upgrade_transitions
            ADD CONSTRAINT saas_tier_upgrade_transitions_payment_fk
            FOREIGN KEY (payment_id) REFERENCES public.payments(id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'saas_tier_upgrade_transitions_contract_fk'
    ) THEN
        ALTER TABLE public.saas_tier_upgrade_transitions
            ADD CONSTRAINT saas_tier_upgrade_transitions_contract_fk
            FOREIGN KEY (contract_id) REFERENCES public.contracts(id);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_saas_tier_upgrade_transitions_payment_id
    ON public.saas_tier_upgrade_transitions (payment_id);

COMMENT ON TABLE public.saas_tier_upgrade_transitions IS
    'SaaS tier upgrade durable ledger. payment=delta, contract/subscription=target FULL. PRODUCTION APPLY=0 until GPT gate.';
