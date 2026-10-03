-- WO-MSDS-04A-PATCH-001: leg-prod msds_ref.identity_projection + public view
-- TARGET DB: leg-prod (wrfcedzgdrfupenzqhur) — NOT TAI SaaS DB
-- Source corpus (chemicals, sections, snapshots, snapshot_items) = READ ONLY, NO MODIFICATION
-- Current snapshot: 0ad73e46-d61b-474d-a90e-5b5ab8080d80
--
-- Apply order:
--   1. msds_ref.identity_projection (table + data)
--   2. public.msds_ref_identity_projection_v (view)
--   3. Grants

-- ─── GRANT schema USAGE to service_role ──────────────────────────────────────

GRANT USAGE ON SCHEMA msds_ref TO service_role;

-- ─── Table: msds_ref.identity_projection ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS msds_ref.identity_projection (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id uuid NOT NULL,
    chemical_id uuid NOT NULL REFERENCES msds_ref.chemicals(id),
    content_id text NOT NULL,
    chem_id text NOT NULL,
    product_name text,
    product_name_normalized text,
    substance_name text,
    substance_name_normalized text,
    alias_text text,
    alias_normalized text,
    cas_no text,
    source_content_hash text,
    built_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_ip_snapshot_content UNIQUE (snapshot_id, content_id)
);

CREATE INDEX IF NOT EXISTS idx_ip_snapshot ON msds_ref.identity_projection(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_ip_content ON msds_ref.identity_projection(content_id);
CREATE INDEX IF NOT EXISTS idx_ip_cas ON msds_ref.identity_projection(cas_no) WHERE cas_no IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ip_name_norm ON msds_ref.identity_projection(product_name_normalized) WHERE product_name_normalized IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ip_substance_norm ON msds_ref.identity_projection(substance_name_normalized) WHERE substance_name_normalized IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ip_alias_norm ON msds_ref.identity_projection(alias_normalized) WHERE alias_normalized IS NOT NULL;

-- RLS: service_role only
ALTER TABLE msds_ref.identity_projection ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON msds_ref.identity_projection FROM PUBLIC, anon, authenticated;
GRANT SELECT ON msds_ref.identity_projection TO service_role;

-- ─── Populate from snapshot 0ad73e46-d61b-474d-a90e-5b5ab8080d80 ─────────────

INSERT INTO msds_ref.identity_projection (
    snapshot_id, chemical_id, content_id, chem_id,
    product_name, product_name_normalized,
    substance_name, substance_name_normalized,
    alias_text, alias_normalized,
    cas_no, source_content_hash
)
SELECT
    '0ad73e46-d61b-474d-a90e-5b5ab8080d80'::uuid AS snapshot_id,
    c.id AS chemical_id,
    c.content_id,
    c.chem_id,
    -- Section 1 A02: product_name
    (SELECT elem->>'itemDetail'
     FROM msds_ref.sections s1,
          jsonb_array_elements(s1.payload_json) elem
     WHERE s1.chemical_id = c.id AND s1.section_no = 1
       AND elem->>'msdsItemCode' = 'A02'
     LIMIT 1) AS product_name,
    -- normalized: lower + trim + collapse whitespace
    lower(regexp_replace(btrim(COALESCE(
        (SELECT elem->>'itemDetail'
         FROM msds_ref.sections s1,
              jsonb_array_elements(s1.payload_json) elem
         WHERE s1.chemical_id = c.id AND s1.section_no = 1
           AND elem->>'msdsItemCode' = 'A02'
         LIMIT 1), ''
    )), '\s+', ' ', 'g')) AS product_name_normalized,
    -- Section 3 C02: substance_name
    (SELECT elem->>'itemDetail'
     FROM msds_ref.sections s3,
          jsonb_array_elements(s3.payload_json) elem
     WHERE s3.chemical_id = c.id AND s3.section_no = 3
       AND elem->>'msdsItemCode' = 'C02'
     LIMIT 1) AS substance_name,
    lower(regexp_replace(btrim(COALESCE(
        (SELECT elem->>'itemDetail'
         FROM msds_ref.sections s3,
              jsonb_array_elements(s3.payload_json) elem
         WHERE s3.chemical_id = c.id AND s3.section_no = 3
           AND elem->>'msdsItemCode' = 'C02'
         LIMIT 1), ''
    )), '\s+', ' ', 'g')) AS substance_name_normalized,
    -- Section 3 C04: alias
    (SELECT elem->>'itemDetail'
     FROM msds_ref.sections s3,
          jsonb_array_elements(s3.payload_json) elem
     WHERE s3.chemical_id = c.id AND s3.section_no = 3
       AND elem->>'msdsItemCode' = 'C04'
     LIMIT 1) AS alias_text,
    lower(regexp_replace(btrim(COALESCE(
        (SELECT elem->>'itemDetail'
         FROM msds_ref.sections s3,
              jsonb_array_elements(s3.payload_json) elem
         WHERE s3.chemical_id = c.id AND s3.section_no = 3
           AND elem->>'msdsItemCode' = 'C04'
         LIMIT 1), ''
    )), '\s+', ' ', 'g')) AS alias_normalized,
    -- Section 3 C06: CAS
    nullif(btrim(COALESCE(
        (SELECT elem->>'itemDetail'
         FROM msds_ref.sections s3,
              jsonb_array_elements(s3.payload_json) elem
         WHERE s3.chemical_id = c.id AND s3.section_no = 3
           AND elem->>'msdsItemCode' = 'C06'
         LIMIT 1), ''
    )), '') AS cas_no,
    c.source_content_hash
FROM msds_ref.chemicals c
JOIN msds_ref.snapshot_items si
    ON si.chemical_id = c.id
    AND si.snapshot_id = '0ad73e46-d61b-474d-a90e-5b5ab8080d80'
ON CONFLICT (snapshot_id, content_id) DO NOTHING;

-- ─── Public view: service_role read surface ───────────────────────────────────
-- SECURITY INVOKER (default for views in Postgres 15+)
-- TAI backend queries public.msds_ref_identity_projection_v via PostgREST

CREATE OR REPLACE VIEW public.msds_ref_identity_projection_v
WITH (security_invoker = true)
AS
SELECT
    id,
    snapshot_id,
    chemical_id,
    content_id,
    chem_id,
    product_name,
    product_name_normalized,
    substance_name,
    substance_name_normalized,
    alias_text,
    alias_normalized,
    cas_no,
    built_at
FROM msds_ref.identity_projection;

REVOKE ALL ON public.msds_ref_identity_projection_v FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.msds_ref_identity_projection_v TO service_role;
