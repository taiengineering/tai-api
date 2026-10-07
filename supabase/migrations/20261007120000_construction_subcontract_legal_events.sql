-- construction_subcontract_legal_events
-- S02-L2: Art.35~37 건설산업기본법 하도급 stateful legal events
-- DRAFT → CONFIRMED → VOID lifecycle

CREATE TABLE IF NOT EXISTS construction_subcontract_legal_events (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    tenant_company_id               uuid NOT NULL,
    site_id                         uuid NOT NULL REFERENCES construction_sites(id),
    subcontractor_id                uuid NOT NULL REFERENCES subcontractors(id),
    subcontractor_company_id        uuid NOT NULL,

    event_type                      text NOT NULL,
    event_version                   int NOT NULL DEFAULT 1,

    obligated_actor_role            text NOT NULL,
    obligated_actor_company_id      uuid,
    counterparty_company_id         uuid,

    occurred_at                     timestamptz,

    basis_type                      text,
    adjustment_reason               text,
    original_amount                 numeric,
    adjusted_amount                 numeric,

    notice_type                     text,
    notice_received_at              timestamptz,

    inspection_completed_at         timestamptz,
    design_conformance_confirmed    boolean,
    notice_event_id                 uuid REFERENCES construction_subcontract_legal_events(id),

    scope_description               text,
    evidence_ref                    text,

    status                          text NOT NULL DEFAULT 'DRAFT',
    confirmed_at                    timestamptz,
    voided_at                       timestamptz,

    created_by                      uuid,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);

-- Event type enum guard
ALTER TABLE construction_subcontract_legal_events
    ADD CONSTRAINT csle_event_type_check CHECK (event_type IN (
        'ART35_DIRECT_PAYMENT_CONFIRMATION_REQUIRED',
        'ART35_DIRECT_PAYMENT_BASIS',
        'ART36_PAYMENT_INCREASE_RECEIVED',
        'ART36_PAYMENT_REDUCTION_RECEIVED',
        'ART37_COMPLETION_OR_PROGRESS_NOTICE_RECEIVED',
        'ART37_INSPECTION_COMPLETED_AS_DESIGNED'
    ));

-- Status enum guard
ALTER TABLE construction_subcontract_legal_events
    ADD CONSTRAINT csle_status_check CHECK (status IN ('DRAFT', 'CONFIRMED', 'VOID'));

-- Actor role guard
ALTER TABLE construction_subcontract_legal_events
    ADD CONSTRAINT csle_actor_role_check CHECK (obligated_actor_role IN ('GENERAL_CONTRACTOR', 'PROJECT_OWNER'));

-- basis_type guard (nullable — only required for ART35_DIRECT_PAYMENT_BASIS)
ALTER TABLE construction_subcontract_legal_events
    ADD CONSTRAINT csle_basis_type_check CHECK (
        basis_type IS NULL OR basis_type IN (
            'AGREEMENT', 'COURT_ORDER', 'PAYMENT_DEFAULT_2X',
            'INSOLVENT', 'NO_PAYMENT_GUARANTEE', 'PUBLIC_LOWBID'
        )
    );

-- adjustment_reason guard
ALTER TABLE construction_subcontract_legal_events
    ADD CONSTRAINT csle_adjustment_reason_check CHECK (
        adjustment_reason IS NULL OR adjustment_reason IN ('DESIGN_CHANGE', 'ECONOMIC_CHANGE')
    );

-- notice_type guard
ALTER TABLE construction_subcontract_legal_events
    ADD CONSTRAINT csle_notice_type_check CHECK (
        notice_type IS NULL OR notice_type IN ('COMPLETION', 'PROGRESS')
    );

-- Performance indexes
CREATE INDEX csle_site_sub_status_idx ON construction_subcontract_legal_events(site_id, subcontractor_id, status);
CREATE INDEX csle_tenant_idx ON construction_subcontract_legal_events(tenant_company_id);
