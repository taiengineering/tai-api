-- OBJ-CHEM-02 KOSHA MSDS chemical catalog (additive).
-- NOT production-applied in CHEM-02. PROBE snapshots cannot publish global current.
-- Does not alter factory_materials, master_dangerous_goods, Graph, CSI, or Legal Engine.

CREATE TABLE IF NOT EXISTS public.kosha_msds_chemicals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id text NOT NULL DEFAULT 'KOSHA_MSDS' CHECK (source_id = 'KOSHA_MSDS'),
  source_key text NOT NULL,
  chem_id text NOT NULL,
  content_id text NOT NULL CHECK (content_id LIKE 'CHEM:%'),
  identity_status text NOT NULL CHECK (identity_status IN ('READY', 'HOLD')),
  identity_reason text,
  chemical_name_ko text,
  chemical_name_en text,
  cas_no text,
  ke_no text,
  en_no text,
  un_no text,
  last_date date,
  source_content_hash text,
  source_dataset_url text NOT NULL DEFAULT 'https://www.data.go.kr/data/15157612/openapi.do',
  is_current boolean NOT NULL DEFAULT false,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, source_key),
  UNIQUE (content_id),
  CHECK (source_key = chem_id),
  CHECK (chem_id <> '')
);

COMMENT ON TABLE public.kosha_msds_chemicals IS
  'KOSHA MSDS reference chemical identity. source_key=chemId. CAS is nullable attribute, not PK. is_current stays false until a PUBLISHED_FULL snapshot exists.';
COMMENT ON COLUMN public.kosha_msds_chemicals.source_key IS
  'Official OpenAPI chemId. Stable source identity.';
COMMENT ON COLUMN public.kosha_msds_chemicals.content_id IS
  'TAI immutable CHEM:<uuid>. Not regenerated when CAS/name change.';
COMMENT ON COLUMN public.kosha_msds_chemicals.cas_no IS
  'Attribute only. NULL is valid (e.g. chemId 047134).';
COMMENT ON COLUMN public.kosha_msds_chemicals.is_current IS
  'Must remain false for PROBE/BOUNDED_SEARCH. Global current is kosha_msds_current, which requires PUBLISHED_FULL.';

CREATE INDEX IF NOT EXISTS kosha_msds_chemicals_chem_id_idx
  ON public.kosha_msds_chemicals (chem_id);
CREATE INDEX IF NOT EXISTS kosha_msds_chemicals_cas_idx
  ON public.kosha_msds_chemicals (cas_no);
CREATE INDEX IF NOT EXISTS kosha_msds_chemicals_status_idx
  ON public.kosha_msds_chemicals (identity_status);

CREATE TABLE IF NOT EXISTS public.kosha_msds_sections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chemical_id uuid NOT NULL REFERENCES public.kosha_msds_chemicals(id),
  section_no integer NOT NULL CHECK (section_no BETWEEN 1 AND 16),
  payload_json jsonb NOT NULL,
  section_hash text NOT NULL,
  result_code text NOT NULL,
  result_message text,
  fetched_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (chemical_id, section_no)
);

COMMENT ON TABLE public.kosha_msds_sections IS
  'Lossless normalized payload for getChemDetail01-16. Identity owner is chemical_id only; chemId is obtained via JOIN to kosha_msds_chemicals. Empty successful section is valid. Raw XML is not stored.';
COMMENT ON COLUMN public.kosha_msds_sections.payload_json IS
  'Canonical item array. fetched_at is column-only and excluded from chemical source_content_hash.';
COMMENT ON COLUMN public.kosha_msds_sections.chemical_id IS
  'Parent kosha_msds_chemicals.id. Duplicate chem_id column is forbidden to prevent identity drift.';

CREATE TABLE IF NOT EXISTS public.kosha_msds_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id text NOT NULL DEFAULT 'KOSHA_MSDS' CHECK (source_id = 'KOSHA_MSDS'),
  run_type text NOT NULL,
  status text NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
  enumeration_mode text NOT NULL CHECK (enumeration_mode IN ('PROBE', 'BOUNDED_SEARCH', 'FULL_OFFICIAL')),
  publish_state text NOT NULL DEFAULT 'NOT_PUBLISHED'
    CHECK (publish_state IN ('NOT_PUBLISHED', 'PUBLISHED_FULL')),
  expected_count integer,
  discovered_count integer NOT NULL DEFAULT 0,
  started_at timestamptz NOT NULL,
  completed_at timestamptz,
  source_contract_version text NOT NULL,
  error_code text,
  error_message text,
  metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (
    publish_state <> 'PUBLISHED_FULL'
    OR (enumeration_mode = 'FULL_OFFICIAL' AND status = 'COMPLETED')
  )
);

COMMENT ON TABLE public.kosha_msds_snapshots IS
  'KOSHA MSDS fetch runs. CHEM-02 allows PROBE only. FULL_OFFICIAL/PUBLISHED_FULL are blocked until corpus enumeration gate.';
COMMENT ON COLUMN public.kosha_msds_snapshots.expected_count IS
  'Official census only. Must stay NULL while N is UNKNOWN. Do not store unofficial web totals such as 20568.';
COMMENT ON COLUMN public.kosha_msds_snapshots.enumeration_mode IS
  'Immutable provenance after INSERT. PROBE=bounded known chemId set. FULL_OFFICIAL requires a verified dump-all contract and must be set at INSERT. PROBE/BOUNDED_SEARCH cannot be updated to FULL_OFFICIAL.';

CREATE INDEX IF NOT EXISTS kosha_msds_snapshots_status_idx
  ON public.kosha_msds_snapshots (status, completed_at DESC);

CREATE FUNCTION public.fn_kosha_msds_snapshot_enumeration_immutable()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
AS $fn$
BEGIN
  IF OLD.enumeration_mode IS DISTINCT FROM NEW.enumeration_mode THEN
    RAISE EXCEPTION
      'KOSHA_MSDS_ENUMERATION_MODE_IMMUTABLE: cannot change % to %',
      OLD.enumeration_mode,
      NEW.enumeration_mode
      USING ERRCODE = '23001';
  END IF;
  RETURN NEW;
END
$fn$;

COMMENT ON FUNCTION public.fn_kosha_msds_snapshot_enumeration_immutable() IS
  'Fail-closed snapshot provenance. Blocks PROBE→FULL_OFFICIAL, PROBE→BOUNDED_SEARCH, BOUNDED_SEARCH→FULL_OFFICIAL, and any other enumeration_mode rewrite.';

REVOKE ALL ON FUNCTION public.fn_kosha_msds_snapshot_enumeration_immutable() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_kosha_msds_snapshot_enumeration_immutable() TO postgres, service_role;

CREATE TRIGGER trg_kosha_msds_snapshot_enumeration_immutable
BEFORE UPDATE ON public.kosha_msds_snapshots
FOR EACH ROW
EXECUTE FUNCTION public.fn_kosha_msds_snapshot_enumeration_immutable();

ALTER TABLE public.kosha_msds_snapshots
  ENABLE ALWAYS TRIGGER trg_kosha_msds_snapshot_enumeration_immutable;

CREATE TABLE IF NOT EXISTS public.kosha_msds_snapshot_items (
  snapshot_id uuid NOT NULL REFERENCES public.kosha_msds_snapshots(id),
  chemical_id uuid NOT NULL REFERENCES public.kosha_msds_chemicals(id),
  source_content_hash text,
  identity_status text NOT NULL CHECK (identity_status IN ('READY', 'HOLD')),
  detail_status text NOT NULL CHECK (detail_status IN ('COMPLETE', 'INCOMPLETE', 'EMPTY_BUT_VALID')),
  in_snapshot boolean NOT NULL DEFAULT true,
  PRIMARY KEY (snapshot_id, chemical_id)
);

COMMENT ON TABLE public.kosha_msds_snapshot_items IS
  'Membership of a KOSHA MSDS snapshot. Identity owner is chemical_id; source_key is obtained via JOIN to kosha_msds_chemicals. Partial/PROBE membership is not global current.';
COMMENT ON COLUMN public.kosha_msds_snapshot_items.chemical_id IS
  'Parent kosha_msds_chemicals.id. Duplicate source_key column is forbidden to prevent identity drift.';

ALTER TABLE public.kosha_msds_chemicals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.kosha_msds_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.kosha_msds_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.kosha_msds_snapshot_items ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.kosha_msds_chemicals FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.kosha_msds_sections FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.kosha_msds_snapshots FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.kosha_msds_snapshot_items FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE ON public.kosha_msds_chemicals TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.kosha_msds_sections TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.kosha_msds_snapshots TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.kosha_msds_snapshot_items TO service_role;

REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.kosha_msds_chemicals FROM service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.kosha_msds_sections FROM service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.kosha_msds_snapshots FROM service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.kosha_msds_snapshot_items FROM service_role;

CREATE OR REPLACE VIEW public.kosha_msds_current AS
SELECT
  c.id,
  c.content_id,
  c.source_id,
  c.source_key,
  c.chem_id,
  c.identity_status,
  c.chemical_name_ko,
  c.chemical_name_en,
  c.cas_no,
  c.ke_no,
  c.en_no,
  c.un_no,
  c.source_content_hash,
  c.source_dataset_url,
  s.id AS snapshot_id
FROM public.kosha_msds_snapshots s
JOIN public.kosha_msds_snapshot_items i
  ON i.snapshot_id = s.id AND i.in_snapshot IS TRUE
JOIN public.kosha_msds_chemicals c
  ON c.id = i.chemical_id
WHERE s.status = 'COMPLETED'
  AND s.enumeration_mode = 'FULL_OFFICIAL'
  AND s.publish_state = 'PUBLISHED_FULL'
  AND s.id = (
    SELECT id
    FROM public.kosha_msds_snapshots
    WHERE status = 'COMPLETED'
      AND enumeration_mode = 'FULL_OFFICIAL'
      AND publish_state = 'PUBLISHED_FULL'
    ORDER BY completed_at DESC NULLS LAST, started_at DESC
    LIMIT 1
  );

COMMENT ON VIEW public.kosha_msds_current IS
  'Global current KOSHA MSDS catalog. Empty until a PUBLISHED_FULL FULL_OFFICIAL snapshot exists. CHEM-02 expected row count = 0.';

REVOKE ALL ON public.kosha_msds_current FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.kosha_msds_current TO service_role;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.kosha_msds_current FROM service_role;
