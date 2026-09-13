-- OBJ-CSI accident catalog + annual snapshots.
-- Additive. Does not alter kosha or graph tables.
-- Current = latest COMPLETED snapshot membership. No current flag column on cases.

CREATE TABLE IF NOT EXISTS public.csi_accident_cases (
  content_id text PRIMARY KEY
    CHECK (content_id LIKE 'CSI:%'),
  source_id text NOT NULL DEFAULT 'CSI' CHECK (source_id = 'CSI'),
  source_key text,
  identity_fingerprint text NOT NULL,
  identity_status text NOT NULL CHECK (identity_status IN ('READY', 'HOLD')),
  identity_reason text,
  fingerprint_version text NOT NULL DEFAULT 'CSI_EVENT_FINGERPRINT_V1',
  first_seen_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

COMMENT ON TABLE public.csi_accident_cases IS
  'TAI immutable CSI accident identity. source_key is unavailable (NULL). content_id is not a row hash.';
COMMENT ON COLUMN public.csi_accident_cases.source_key IS
  'Official source-native ID. CSI file has none; remains NULL.';
COMMENT ON COLUMN public.csi_accident_cases.identity_fingerprint IS
  'CSI_EVENT_FINGERPRINT_V1 reconciliation key. Not public content_id.';
COMMENT ON COLUMN public.csi_accident_cases.identity_status IS
  'READY = unique fingerprint. HOLD = collision/ambiguous. HOLD is not public/Graph eligible.';

CREATE INDEX IF NOT EXISTS csi_accident_cases_fp_idx
  ON public.csi_accident_cases (identity_fingerprint);
CREATE INDEX IF NOT EXISTS csi_accident_cases_status_idx
  ON public.csi_accident_cases (identity_status);

CREATE TABLE IF NOT EXISTS public.csi_accident_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
  dataset_id text NOT NULL,
  effective_date date NOT NULL,
  filename text NOT NULL,
  bytes bigint NOT NULL,
  file_sha256 text NOT NULL,
  encoding text NOT NULL,
  declared_rows integer NOT NULL,
  parsed_rows integer NOT NULL,
  row_count_mismatch boolean NOT NULL,
  header_count integer NOT NULL,
  download_url text,
  proposed_raw_object_key text,
  r2_written boolean NOT NULL DEFAULT false,
  started_at timestamptz NOT NULL,
  completed_at timestamptz,
  failure_reason text
);

CREATE INDEX IF NOT EXISTS csi_accident_snapshots_completed_idx
  ON public.csi_accident_snapshots (status, completed_at DESC);
CREATE INDEX IF NOT EXISTS csi_accident_snapshots_sha_idx
  ON public.csi_accident_snapshots (file_sha256);

COMMENT ON TABLE public.csi_accident_snapshots IS
  'Annual CSI full-file snapshots. Consumer current = latest COMPLETED only. declared_rows may differ from parsed_rows.';
COMMENT ON COLUMN public.csi_accident_snapshots.row_count_mismatch IS
  'True when portal declared_rows != parsed_rows. Mismatch is recorded, not a snapshot failure.';
COMMENT ON COLUMN public.csi_accident_snapshots.r2_written IS
  'Raw CSV object write. This core PR keeps false; overwrite/delete forbidden.';

CREATE TABLE IF NOT EXISTS public.csi_accident_snapshot_items (
  snapshot_id uuid NOT NULL REFERENCES public.csi_accident_snapshots(id),
  row_number integer NOT NULL,
  content_id text NOT NULL REFERENCES public.csi_accident_cases(content_id),
  source_content_hash text NOT NULL,
  identity_fingerprint text NOT NULL,
  identity_status text NOT NULL CHECK (identity_status IN ('READY', 'HOLD')),
  identity_reason text,
  title text,
  occurred_at timestamptz,
  construction_type text,
  process_major text,
  process_minor text,
  object_major text,
  object_minor text,
  work_process text,
  accident_type_major text,
  accident_type text,
  cause_major text,
  cause_mid text,
  cause_minor text,
  cause_detail text,
  summary text,
  death_count integer,
  injury_count integer,
  source_dataset_url text,
  source_item_url text,
  raw_json jsonb NOT NULL,
  PRIMARY KEY (snapshot_id, row_number)
);

CREATE INDEX IF NOT EXISTS csi_accident_snapshot_items_case_idx
  ON public.csi_accident_snapshot_items (content_id);
CREATE INDEX IF NOT EXISTS csi_accident_snapshot_items_hash_idx
  ON public.csi_accident_snapshot_items (source_content_hash);
CREATE INDEX IF NOT EXISTS csi_accident_snapshot_items_fp_idx
  ON public.csi_accident_snapshot_items (identity_fingerprint);

COMMENT ON TABLE public.csi_accident_snapshot_items IS
  'Versioned CSI row membership. source_content_hash is the version identity; raw_json keeps 미입력.';
COMMENT ON COLUMN public.csi_accident_snapshot_items.source_item_url IS
  'Portal case URL. NULL until a non-scraped official item URL exists.';

ALTER TABLE public.csi_accident_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.csi_accident_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.csi_accident_snapshot_items ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.csi_accident_cases FROM anon, authenticated;
REVOKE ALL ON public.csi_accident_snapshots FROM anon, authenticated;
REVOKE ALL ON public.csi_accident_snapshot_items FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.csi_accident_cases TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.csi_accident_snapshots TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.csi_accident_snapshot_items TO service_role;

CREATE OR REPLACE VIEW public.csi_accident_current AS
SELECT
  c.content_id,
  c.source_id,
  c.source_key,
  c.identity_fingerprint,
  i.identity_status,
  i.identity_reason,
  i.title,
  i.occurred_at,
  i.construction_type,
  i.process_major,
  i.process_minor,
  i.object_major,
  i.object_minor,
  i.work_process,
  i.accident_type_major,
  i.accident_type,
  i.cause_major,
  i.cause_mid,
  i.cause_minor,
  i.cause_detail,
  i.summary,
  i.death_count,
  i.injury_count,
  i.source_dataset_url,
  i.source_item_url,
  i.source_content_hash,
  s.id AS snapshot_id
FROM public.csi_accident_snapshots s
JOIN public.csi_accident_snapshot_items i ON i.snapshot_id = s.id
JOIN public.csi_accident_cases c ON c.content_id = i.content_id
WHERE s.id = (
  SELECT id
  FROM public.csi_accident_snapshots
  WHERE status = 'COMPLETED'
  ORDER BY completed_at DESC NULLS LAST, started_at DESC
  LIMIT 1
);

COMMENT ON VIEW public.csi_accident_current IS
  'Latest COMPLETED CSI snapshot membership. HOLD rows remain visible here; public/Graph eligibility is READY-only and not granted to anon in this PR.';

GRANT SELECT ON public.csi_accident_current TO service_role;
