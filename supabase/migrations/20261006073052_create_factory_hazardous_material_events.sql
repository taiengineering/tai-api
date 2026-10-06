-- WO-LFR-OBJ-B03-P4A
-- Hazardous material inbound/outbound operational event records.
-- Source: 초고층 및 지하연계 복합건축물 재난관리에 관한 특별법 시행규칙 제9조
-- Additive only. No DROP, TRUNCATE, or destructive ALTER.

CREATE TABLE IF NOT EXISTS public.factory_hazardous_material_events (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_id              uuid NOT NULL
                                REFERENCES public.factories(id) ON DELETE RESTRICT,

    event_direction         text NOT NULL
                                CHECK (event_direction IN ('INBOUND', 'OUTBOUND')),
    occurred_at             timestamptz,

    purpose                 text,

    material_type           text,
    quantity                numeric,
    quantity_unit           text,
    material_use            text,
    purchase_source         text,

    carrier_name            text,
    responsible_person_name text,
    vehicle_type            text,

    status                  text NOT NULL DEFAULT 'DRAFT'
                                CHECK (status IN ('DRAFT', 'CONFIRMED', 'VOID')),

    confirmed_at            timestamptz,
    voided_at               timestamptz,

    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_draft_timestamps
        CHECK (
            status != 'DRAFT'
            OR (confirmed_at IS NULL AND voided_at IS NULL)
        ),
    CONSTRAINT chk_confirmed_timestamps
        CHECK (
            status != 'CONFIRMED'
            OR (confirmed_at IS NOT NULL AND voided_at IS NULL)
        ),
    CONSTRAINT chk_void_timestamps
        CHECK (
            status != 'VOID'
            OR (confirmed_at IS NOT NULL AND voided_at IS NOT NULL)
        )
);

CREATE INDEX idx_fhme_factory_occurred
    ON public.factory_hazardous_material_events (factory_id, occurred_at DESC);

CREATE INDEX idx_fhme_factory_status_occurred
    ON public.factory_hazardous_material_events (factory_id, status, occurred_at DESC);

ALTER TABLE public.factory_hazardous_material_events
    ENABLE ROW LEVEL SECURITY;
