-- OBJ-KG KOSHA GUIDE current snapshot (additive).
-- Catalog SoT remains public.kosha_guide. No column drop/rename/type change.

ALTER TABLE public.kosha_guide
  ADD COLUMN IF NOT EXISTS category_code text,
  ADD COLUMN IF NOT EXISTS category_name text,
  ADD COLUMN IF NOT EXISTS content_hash text,
  ADD COLUMN IF NOT EXISTS first_seen_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_seen_at timestamptz,
  ADD COLUMN IF NOT EXISTS metadata_license text,
  ADD COLUMN IF NOT EXISTS original_rights_mode text,
  ADD COLUMN IF NOT EXISTS binary_storage_allowed boolean;

UPDATE public.kosha_guide
SET
  metadata_license = COALESCE(NULLIF(metadata_license, ''), 'CLEAR'),
  original_rights_mode = COALESCE(NULLIF(original_rights_mode, ''), 'LINK_ONLY'),
  binary_storage_allowed = COALESCE(binary_storage_allowed, false),
  first_seen_at = COALESCE(first_seen_at, collected_at),
  last_seen_at = COALESCE(last_seen_at, collected_at);

ALTER TABLE public.kosha_guide
  ALTER COLUMN metadata_license SET DEFAULT 'CLEAR',
  ALTER COLUMN original_rights_mode SET DEFAULT 'LINK_ONLY',
  ALTER COLUMN binary_storage_allowed SET DEFAULT false;

COMMENT ON COLUMN public.kosha_guide.metadata_license IS
  'API metadata rights. GUIDE default CLEAR. Not PDF/original rights.';
COMMENT ON COLUMN public.kosha_guide.original_rights_mode IS
  'PDF/original policy only. GUIDE default LINK_ONLY.';
COMMENT ON COLUMN public.kosha_guide.binary_storage_allowed IS
  'GUIDE originals are not stored. Default false.';
COMMENT ON COLUMN public.kosha_guide.category_code IS
  'Prefix from techGdlnNo. 4-part keeps two letters (A-G).';
COMMENT ON COLUMN public.kosha_guide.category_name IS
  'Official 1-letter label only. 4-part labels stay NULL.';

CREATE TABLE IF NOT EXISTS public.kosha_guide_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status text NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
  source_path text NOT NULL,
  call_api_id text NOT NULL,
  declared_total integer,
  fetched_count integer,
  unique_count integer,
  snapshot_hash text,
  started_at timestamptz NOT NULL,
  completed_at timestamptz,
  failure_reason text
);

CREATE INDEX IF NOT EXISTS kosha_guide_snapshots_completed_idx
  ON public.kosha_guide_snapshots (status, completed_at DESC);

COMMENT ON TABLE public.kosha_guide_snapshots IS
  'GUIDE full-set sync runs. Consumer current = latest COMPLETED only.';

CREATE TABLE IF NOT EXISTS public.kosha_guide_snapshot_items (
  snapshot_id uuid NOT NULL REFERENCES public.kosha_guide_snapshots(id),
  guide_id text NOT NULL REFERENCES public.kosha_guide(id),
  content_hash text,
  PRIMARY KEY (snapshot_id, guide_id)
);

CREATE INDEX IF NOT EXISTS kosha_guide_snapshot_items_guide_idx
  ON public.kosha_guide_snapshot_items (guide_id);

COMMENT ON TABLE public.kosha_guide_snapshot_items IS
  'Membership of a GUIDE snapshot. Does not delete catalog history.';

ALTER TABLE public.kosha_guide_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.kosha_guide_snapshot_items ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.kosha_guide_snapshots FROM anon, authenticated;
REVOKE ALL ON public.kosha_guide_snapshot_items FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.kosha_guide_snapshots TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.kosha_guide_snapshot_items TO service_role;

CREATE OR REPLACE VIEW public.kosha_guide_current AS
SELECT
  g.id,
  g.guide_no,
  g.guide_title,
  g.category_code,
  g.category_name,
  g.guide_url,
  g.regist_date,
  g.content_hash,
  g.metadata_license,
  g.original_rights_mode,
  g.binary_storage_allowed,
  s.id AS snapshot_id
FROM public.kosha_guide_snapshots s
JOIN public.kosha_guide_snapshot_items i ON i.snapshot_id = s.id
JOIN public.kosha_guide g ON g.id = i.guide_id
WHERE s.id = (
  SELECT id
  FROM public.kosha_guide_snapshots
  WHERE status = 'COMPLETED'
  ORDER BY completed_at DESC NULLS LAST, started_at DESC
  LIMIT 1
);

COMMENT ON VIEW public.kosha_guide_current IS
  'Public GUIDE read model: latest COMPLETED snapshot membership only. No raw_json.';

GRANT SELECT ON public.kosha_guide_current TO anon, authenticated, service_role;
