-- OBJ-H02-P1: factory_occupancy_capacity_assessments
-- Lifecycle: DRAFT → CONFIRMED → VOID (no hard DELETE)
-- Transition authority: application store (store.py), not DB triggers
--   DRAFT→VOID prohibition is enforced by void_assessment() checking status==CONFIRMED
--   DB CHECK constraints enforce per-status invariants, not inter-status transitions
-- RLS: ENABLED; anon/authenticated REVOKED; service_role only

CREATE TABLE public.factory_occupancy_capacity_assessments (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    factory_id uuid NOT NULL REFERENCES factories(id) ON DELETE RESTRICT,
    status text NOT NULL CHECK (status IN ('DRAFT', 'CONFIRMED', 'VOID')),
    ruleset_version text NOT NULL,
    ruleset_sha256 text NOT NULL,
    input_segments jsonb NOT NULL DEFAULT '[]',
    coverage_attested boolean NOT NULL DEFAULT false,
    calculation_trace jsonb,
    result_numerator numeric(78,0),
    result_denominator numeric(78,0),
    confirmed_by_user_id uuid,
    confirmed_at timestamptz,
    voided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    -- result_denominator must be positive when present
    CONSTRAINT chk_result_denominator_positive
        CHECK (result_denominator IS NULL OR result_denominator > 0),

    -- result pair: numerator/denominator/trace must all be set or all NULL
    CONSTRAINT chk_result_pair
        CHECK (
            (result_numerator IS NULL AND result_denominator IS NULL AND calculation_trace IS NULL)
            OR (result_numerator IS NOT NULL AND result_denominator IS NOT NULL AND calculation_trace IS NOT NULL)
        ),

    -- input_segments must be a JSON array
    CONSTRAINT chk_input_segments_array
        CHECK (jsonb_typeof(input_segments) = 'array'),

    -- calculation_trace must be a JSON object when present
    CONSTRAINT chk_calculation_trace_object
        CHECK (calculation_trace IS NULL OR jsonb_typeof(calculation_trace) = 'object'),

    -- DRAFT invariant: not yet confirmed or voided; may have result (DRAFT-B) or not (DRAFT-A)
    --   DRAFT-A: result=NULL, coverage_attested=false
    --   DRAFT-B: result=NOT NULL, coverage_attested=false (calculation attached, not yet confirmed)
    CONSTRAINT chk_draft_invariant
        CHECK (
            status != 'DRAFT' OR (
                coverage_attested = false
                AND confirmed_at IS NULL
                AND confirmed_by_user_id IS NULL
                AND voided_at IS NULL
            )
        ),

    -- CONFIRMED invariant: result present, attested, confirmed fields populated, not voided
    CONSTRAINT chk_confirmed_invariant
        CHECK (
            status != 'CONFIRMED' OR (
                result_numerator IS NOT NULL
                AND result_denominator IS NOT NULL
                AND calculation_trace IS NOT NULL
                AND coverage_attested = true
                AND confirmed_at IS NOT NULL
                AND confirmed_by_user_id IS NOT NULL
                AND voided_at IS NULL
            )
        ),

    -- VOID invariant: carries all CONFIRMED evidence + voided timestamp
    CONSTRAINT chk_void_invariant
        CHECK (
            status != 'VOID' OR (
                result_numerator IS NOT NULL
                AND result_denominator IS NOT NULL
                AND calculation_trace IS NOT NULL
                AND coverage_attested = true
                AND confirmed_at IS NOT NULL
                AND confirmed_by_user_id IS NOT NULL
                AND voided_at IS NOT NULL
            )
        )
);

ALTER TABLE public.factory_occupancy_capacity_assessments ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.factory_occupancy_capacity_assessments FROM anon;
REVOKE ALL ON TABLE public.factory_occupancy_capacity_assessments FROM authenticated;
REVOKE ALL ON TABLE public.factory_occupancy_capacity_assessments FROM service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.factory_occupancy_capacity_assessments TO service_role;

-- Index 1: factory-level lookup by status and recency (canonical adapter query path)
CREATE INDEX idx_foca_factory_status_confirmed
    ON public.factory_occupancy_capacity_assessments (factory_id, status, confirmed_at DESC);

-- Index 2: factory-level listing ordered by creation time (list endpoint)
CREATE INDEX idx_foca_factory_created
    ON public.factory_occupancy_capacity_assessments (factory_id, created_at DESC);

COMMENT ON TABLE public.factory_occupancy_capacity_assessments IS
    'H02 occupancy_capacity legal calculation snapshots. '
    'Canonical source per 초고층재난관리법 시행령 제2조②항. '
    'Direct numeric input prohibited (WO-LFR-OBJ-H02-P0). '
    'Lifecycle: DRAFT→CONFIRMED→VOID; DRAFT→VOID is forbidden (application-level guard). '
    'DRAFT may carry result (DRAFT-B: after attach_calculation) or not (DRAFT-A: before). '
    'Only CONFIRMED assessments with current ruleset may feed the LEG runtime.';

COMMENT ON COLUMN public.factory_occupancy_capacity_assessments.ruleset_sha256 IS
    'SHA-256 of raw legal_density_rules JSON bytes at calculation time; must match current code at confirm.';

COMMENT ON COLUMN public.factory_occupancy_capacity_assessments.result_numerator IS
    'Exact rational result: persons = result_numerator / result_denominator. '
    'Stored as integer pair (no float). threshold comparison uses exact arithmetic.';

COMMENT ON COLUMN public.factory_occupancy_capacity_assessments.input_segments IS
    'Canonical decimal string serialization of segments (Decimal fields stored as strings).';
