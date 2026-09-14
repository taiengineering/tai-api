-- OBJ-RISK-03 TAI canonical process/task + controlled source mapping.
-- Additive. Production apply = 0. No Graph, Legal Engine, CHEM, or SaaS objects.
-- MODEL D frozen: A/B/C stay source-native. Do not copy source rows into canonical tables.
-- Does not modify 20260915_risk_source_catalog.sql.

CREATE TABLE IF NOT EXISTS public.risk_canonical_nodes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_code text UNIQUE,
  node_kind text NOT NULL CHECK (node_kind IN ('PROCESS', 'TASK')),
  parent_id uuid REFERENCES public.risk_canonical_nodes (id),
  name text NOT NULL,
  name_normalized text NOT NULL,
  description text,
  status text NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT', 'ACTIVE', 'RETIRED')),
  origin_type text NOT NULL
    CHECK (origin_type IN (
      'TAI_NATIVE',
      'PROMOTED_FROM_SOURCE',
      'MERGED_FROM_REVIEWED_SOURCES'
    )),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE public.risk_canonical_nodes IS
  'TAI-owned process/task concepts. Identity is UUID, not a source path hash or W-code.';
COMMENT ON COLUMN public.risk_canonical_nodes.id IS
  'TAI canonical identity. Survives rename and reparent. Not a source-derived hash.';
COMMENT ON COLUMN public.risk_canonical_nodes.canonical_code IS
  'Optional TAI-owned stable code. Source-independent. Nullable until assigned.';
COMMENT ON COLUMN public.risk_canonical_nodes.status IS
  'New nodes default DRAFT. Source presence does not auto-ACTIVE.';
COMMENT ON COLUMN public.risk_canonical_nodes.origin_type IS
  'How the concept entered TAI. Promotion still requires review; not auto-ACTIVE.';

CREATE INDEX IF NOT EXISTS risk_canonical_nodes_parent_idx
  ON public.risk_canonical_nodes (parent_id);
CREATE INDEX IF NOT EXISTS risk_canonical_nodes_kind_status_idx
  ON public.risk_canonical_nodes (node_kind, status);

CREATE TABLE IF NOT EXISTS public.risk_canonical_node_sectors (
  canonical_id uuid NOT NULL REFERENCES public.risk_canonical_nodes (id),
  sector_code text NOT NULL,
  PRIMARY KEY (canonical_id, sector_code)
);

COMMENT ON TABLE public.risk_canonical_node_sectors IS
  'Optional many-to-many sector links. No construction-only enum. One node may be global, one sector, or many sectors.';
COMMENT ON COLUMN public.risk_canonical_node_sectors.sector_code IS
  'Free text sector code. Examples include BUILDING, MANUFACTURING, CONSTRUCTION. Not an exclusive CHECK enum.';

CREATE TABLE IF NOT EXISTS public.risk_source_mappings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id text NOT NULL,
  source_key text NOT NULL,
  canonical_id uuid NOT NULL REFERENCES public.risk_canonical_nodes (id),
  mapping_type text NOT NULL
    CHECK (mapping_type IN (
      'EXACT_EQUIVALENT',
      'PARENT_CHILD',
      'BROADER_THAN',
      'NARROWER_THAN',
      'POSSIBLE_RELATED',
      'NO_MATCH',
      'AMBIGUOUS'
    )),
  mapping_status text NOT NULL
    CHECK (mapping_status IN ('PROPOSED', 'APPROVED', 'REJECTED', 'HOLD')),
  mapping_method text NOT NULL
    CHECK (mapping_method IN ('EXACT_PATH', 'EXACT_NAME', 'MANUAL_REVIEW')),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source_id, source_key, canonical_id, mapping_type),
  FOREIGN KEY (source_id, source_key)
    REFERENCES public.risk_source_nodes (source_id, source_key)
);

COMMENT ON TABLE public.risk_source_mappings IS
  'Controlled mapping from A/B/C source nodes to TAI canonical nodes. Source rows are not copied.';
COMMENT ON COLUMN public.risk_source_mappings.mapping_status IS
  'PROPOSED/HOLD/REJECTED are not consumer-eligible. Only APPROVED may be consumed.';
COMMENT ON COLUMN public.risk_source_mappings.evidence IS
  'source_path, canonical_path, normalization rule, candidate reason, review note.';

CREATE UNIQUE INDEX IF NOT EXISTS risk_source_mappings_one_approved_exact
  ON public.risk_source_mappings (source_id, source_key)
  WHERE mapping_status = 'APPROVED' AND mapping_type = 'EXACT_EQUIVALENT';

CREATE INDEX IF NOT EXISTS risk_source_mappings_canonical_idx
  ON public.risk_source_mappings (canonical_id, mapping_status);
CREATE INDEX IF NOT EXISTS risk_source_mappings_status_idx
  ON public.risk_source_mappings (mapping_status, mapping_type);

ALTER TABLE public.risk_canonical_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_canonical_node_sectors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_source_mappings ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.risk_canonical_nodes FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.risk_canonical_node_sectors FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.risk_source_mappings FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE ON public.risk_canonical_nodes TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.risk_canonical_node_sectors TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.risk_source_mappings TO service_role;

REVOKE DELETE, TRUNCATE ON public.risk_canonical_nodes FROM service_role;
REVOKE DELETE, TRUNCATE ON public.risk_canonical_node_sectors FROM service_role;
REVOKE DELETE, TRUNCATE ON public.risk_source_mappings FROM service_role;
