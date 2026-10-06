-- OBJ-H02-P1: factory_occupancy_capacity_assessments
-- Lifecycle: DRAFT → CONFIRMED → VOID (no hard DELETE)
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
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.factory_occupancy_capacity_assessments ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.factory_occupancy_capacity_assessments FROM anon;
REVOKE ALL ON TABLE public.factory_occupancy_capacity_assessments FROM authenticated;
REVOKE ALL ON TABLE public.factory_occupancy_capacity_assessments FROM service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.factory_occupancy_capacity_assessments TO service_role;

COMMENT ON TABLE public.factory_occupancy_capacity_assessments IS
    'H02 occupancy_capacity legal calculation snapshots. '
    'Canonical source per 초고층재난관리법 시행령 제2조②항. '
    'Direct numeric input prohibited (WO-LFR-OBJ-H02-P0). '
    'Only CONFIRMED assessments with current ruleset may feed the LEG runtime.';

COMMENT ON COLUMN public.factory_occupancy_capacity_assessments.ruleset_sha256 IS
    'SHA-256 of legal_density_rules json used at calculation time; must match current code file at confirm.';

COMMENT ON COLUMN public.factory_occupancy_capacity_assessments.result_numerator IS
    'Exact rational result: persons = result_numerator / result_denominator. '
    'Stored as integer (no float); threshold comparison must use exact arithmetic.';
