-- WO-MSDS-04A: leg-prod msds_ref.identity_projection
-- Derived read model from chemicals + sections for OBJ-MSDS-04A matching
-- Source corpus (chemicals, sections, snapshots, snapshot_items) = READ ONLY, NO MODIFICATION
-- This table is rebuilt per snapshot. Current snapshot: 0ad73e46-d61b-474d-a90e-5b5ab8080d80

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

-- RLS: service_role read-only
ALTER TABLE msds_ref.identity_projection ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON msds_ref.identity_projection FROM PUBLIC, anon, authenticated;
GRANT SELECT ON msds_ref.identity_projection TO service_role;

-- Populate from snapshot 0ad73e46-d61b-474d-a90e-5b5ab8080d80
-- (insert only chemicals belonging to this snapshot)
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
    -- normalized: lowercase trim
    lower(trim((SELECT elem->>'itemDetail'
     FROM msds_ref.sections s1,
          jsonb_array_elements(s1.payload_json) elem
     WHERE s1.chemical_id = c.id AND s1.section_no = 1
       AND elem->>'msdsItemCode' = 'A02'
     LIMIT 1))) AS product_name_normalized,
    -- Section 3 C02: substance_name
    (SELECT elem->>'itemDetail'
     FROM msds_ref.sections s3,
          jsonb_array_elements(s3.payload_json) elem
     WHERE s3.chemical_id = c.id AND s3.section_no = 3
       AND elem->>'msdsItemCode' = 'C02'
     LIMIT 1) AS substance_name,
    lower(trim((SELECT elem->>'itemDetail'
     FROM msds_ref.sections s3,
          jsonb_array_elements(s3.payload_json) elem
     WHERE s3.chemical_id = c.id AND s3.section_no = 3
       AND elem->>'msdsItemCode' = 'C02'
     LIMIT 1))) AS substance_name_normalized,
    -- Section 3 C04: alias
    (SELECT elem->>'itemDetail'
     FROM msds_ref.sections s3,
          jsonb_array_elements(s3.payload_json) elem
     WHERE s3.chemical_id = c.id AND s3.section_no = 3
       AND elem->>'msdsItemCode' = 'C04'
     LIMIT 1) AS alias_text,
    lower(trim((SELECT elem->>'itemDetail'
     FROM msds_ref.sections s3,
          jsonb_array_elements(s3.payload_json) elem
     WHERE s3.chemical_id = c.id AND s3.section_no = 3
       AND elem->>'msdsItemCode' = 'C04'
     LIMIT 1))) AS alias_normalized,
    -- Section 3 C06: CAS
    (SELECT nullif(trim(elem->>'itemDetail'), '')
     FROM msds_ref.sections s3,
          jsonb_array_elements(s3.payload_json) elem
     WHERE s3.chemical_id = c.id AND s3.section_no = 3
       AND elem->>'msdsItemCode' = 'C06'
     LIMIT 1) AS cas_no,
    c.source_content_hash
FROM msds_ref.chemicals c
JOIN msds_ref.snapshot_items si
    ON si.chemical_id = c.id
    AND si.snapshot_id = '0ad73e46-d61b-474d-a90e-5b5ab8080d80'
ON CONFLICT (snapshot_id, content_id) DO NOTHING;
