-- WO-MSDS-04A-IMPLEMENTATION-001: MSDS Document Intake & Deterministic Matching
-- Tables: msds_intakes, msds_intake_artifacts, msds_intake_facts, msds_match_candidates, msds_reference_links
-- RLS: anon=NO, authenticated=NO, service_role=YES

-- ─── msds_intakes ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.msds_intakes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    factory_id uuid NOT NULL REFERENCES public.factories(id),
    source_type text NOT NULL,
    status text NOT NULL DEFAULT 'RECEIVED',
    selected_product_id uuid REFERENCES public.chemical_products(id),
    final_msds_version_id uuid REFERENCES public.customer_msds_versions(id),
    reference_snapshot_id uuid,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    confirmed_at timestamptz,
    finalized_at timestamptz,
    error_code text,
    error_detail text,
    CONSTRAINT chk_mi_source_type CHECK (source_type IN ('PDF','PHOTO','BARCODE','QR')),
    CONSTRAINT chk_mi_status CHECK (status IN (
        'RECEIVED','PROCESSING','OCR_REQUIRED','REVIEW_REQUIRED',
        'CONFIRMED','FINALIZED','FAILED','CANCELLED'
    ))
);
CREATE INDEX IF NOT EXISTS idx_mi_factory ON public.msds_intakes(factory_id);
CREATE INDEX IF NOT EXISTS idx_mi_status ON public.msds_intakes(status);
ALTER TABLE public.msds_intakes ENABLE ROW LEVEL SECURITY;
CREATE POLICY mi_no_anon ON public.msds_intakes AS RESTRICTIVE FOR ALL TO anon USING (false);
CREATE POLICY mi_no_authenticated ON public.msds_intakes AS RESTRICTIVE FOR ALL TO authenticated USING (false);
REVOKE ALL ON public.msds_intakes FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.msds_intakes TO service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.msds_intakes FROM service_role;

-- ─── msds_intake_artifacts ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.msds_intake_artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    intake_id uuid NOT NULL REFERENCES public.msds_intakes(id),
    artifact_type text NOT NULL,
    bucket_id text NOT NULL,
    storage_path text NOT NULL,
    file_name text NOT NULL,
    mime_type text NOT NULL,
    file_size integer NOT NULL,
    content_sha256 text NOT NULL,
    page_count integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_mia_type CHECK (artifact_type IN ('PDF','PHOTO')),
    CONSTRAINT chk_mia_sha CHECK (length(content_sha256) = 64 AND content_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE INDEX IF NOT EXISTS idx_mia_intake ON public.msds_intake_artifacts(intake_id);
ALTER TABLE public.msds_intake_artifacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY mia_no_anon ON public.msds_intake_artifacts AS RESTRICTIVE FOR ALL TO anon USING (false);
CREATE POLICY mia_no_authenticated ON public.msds_intake_artifacts AS RESTRICTIVE FOR ALL TO authenticated USING (false);
REVOKE ALL ON public.msds_intake_artifacts FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.msds_intake_artifacts TO service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.msds_intake_artifacts FROM service_role;

-- ─── msds_intake_facts ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.msds_intake_facts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    intake_id uuid NOT NULL REFERENCES public.msds_intakes(id),
    fact_type text NOT NULL,
    raw_value text NOT NULL,
    normalized_value text NOT NULL,
    extraction_method text NOT NULL DEFAULT 'PDF_NATIVE',
    source_artifact_id uuid REFERENCES public.msds_intake_artifacts(id),
    source_page integer,
    evidence_json jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_mif_fact_type CHECK (fact_type IN (
        'PRODUCT_NAME','MANUFACTURER_NAME','SUPPLIER_NAME','PRODUCT_CODE',
        'CAS','GTIN','EAN','UPC','BARCODE','QR_ALIAS'
    )),
    CONSTRAINT chk_mif_method CHECK (extraction_method IN ('PDF_NATIVE','BARCODE_SCAN','QR_SCAN','MANUAL','OCR','VISION'))
);
CREATE INDEX IF NOT EXISTS idx_mif_intake ON public.msds_intake_facts(intake_id);
CREATE INDEX IF NOT EXISTS idx_mif_type ON public.msds_intake_facts(intake_id, fact_type);
ALTER TABLE public.msds_intake_facts ENABLE ROW LEVEL SECURITY;
CREATE POLICY mif_no_anon ON public.msds_intake_facts AS RESTRICTIVE FOR ALL TO anon USING (false);
CREATE POLICY mif_no_authenticated ON public.msds_intake_facts AS RESTRICTIVE FOR ALL TO authenticated USING (false);
REVOKE ALL ON public.msds_intake_facts FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.msds_intake_facts TO service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.msds_intake_facts FROM service_role;

-- ─── msds_match_candidates ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.msds_match_candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    intake_id uuid NOT NULL REFERENCES public.msds_intakes(id),
    candidate_type text NOT NULL,
    candidate_product_id uuid REFERENCES public.chemical_products(id),
    reference_content_id text,
    reference_chem_id text,
    reference_snapshot_id uuid,
    match_reason text NOT NULL,
    rank_no integer NOT NULL DEFAULT 1,
    evidence_json jsonb NOT NULL DEFAULT '{}',
    decision_status text NOT NULL DEFAULT 'PENDING',
    decided_by uuid,
    decided_at timestamptz,
    CONSTRAINT chk_mmc_type CHECK (candidate_type IN ('CUSTOMER_PRODUCT','REFERENCE')),
    CONSTRAINT chk_mmc_reason CHECK (match_reason IN (
        'EXACT_IDENTIFIER','EXACT_NAME_MANUFACTURER','EXACT_NAME',
        'EXACT_CAS','EXACT_REFERENCE_PRODUCT_NAME','EXACT_SUBSTANCE_NAME','EXACT_ALIAS'
    )),
    CONSTRAINT chk_mmc_decision CHECK (decision_status IN ('PENDING','SELECTED','REJECTED'))
);
CREATE INDEX IF NOT EXISTS idx_mmc_intake ON public.msds_match_candidates(intake_id);
CREATE INDEX IF NOT EXISTS idx_mmc_type ON public.msds_match_candidates(intake_id, candidate_type);
ALTER TABLE public.msds_match_candidates ENABLE ROW LEVEL SECURITY;
CREATE POLICY mmc_no_anon ON public.msds_match_candidates AS RESTRICTIVE FOR ALL TO anon USING (false);
CREATE POLICY mmc_no_authenticated ON public.msds_match_candidates AS RESTRICTIVE FOR ALL TO authenticated USING (false);
REVOKE ALL ON public.msds_match_candidates FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.msds_match_candidates TO service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.msds_match_candidates FROM service_role;

-- ─── msds_reference_links ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.msds_reference_links (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_msds_version_id uuid NOT NULL REFERENCES public.customer_msds_versions(id),
    reference_content_id text NOT NULL,
    reference_chem_id text NOT NULL,
    reference_snapshot_id uuid NOT NULL,
    cas_no text,
    match_reason text NOT NULL,
    confirmed_by uuid,
    confirmed_at timestamptz NOT NULL DEFAULT now(),
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT uq_mrl_version_ref UNIQUE (customer_msds_version_id, reference_content_id),
    CONSTRAINT chk_mrl_reason CHECK (match_reason IN (
        'EXACT_CAS','EXACT_REFERENCE_PRODUCT_NAME','EXACT_SUBSTANCE_NAME','EXACT_ALIAS',
        'EXACT_IDENTIFIER','EXACT_NAME_MANUFACTURER','EXACT_NAME','MANUAL'
    ))
);
CREATE INDEX IF NOT EXISTS idx_mrl_version ON public.msds_reference_links(customer_msds_version_id);
CREATE INDEX IF NOT EXISTS idx_mrl_content ON public.msds_reference_links(reference_content_id);
ALTER TABLE public.msds_reference_links ENABLE ROW LEVEL SECURITY;
CREATE POLICY mrl_no_anon ON public.msds_reference_links AS RESTRICTIVE FOR ALL TO anon USING (false);
CREATE POLICY mrl_no_authenticated ON public.msds_reference_links AS RESTRICTIVE FOR ALL TO authenticated USING (false);
REVOKE ALL ON public.msds_reference_links FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.msds_reference_links TO service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.msds_reference_links FROM service_role;
