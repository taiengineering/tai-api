-- WO-CHEM-SEO-PREVIEW-LIVE-001
-- Adds the temporary SEO preview publication path.
--
-- Delta rules:
--   * PUBLISHED_FULL semantics UNCHANGED (WO §2 "kosha_msds_current의 FULL 의미 변경 금지").
--   * enumeration_mode UNCHANGED — the source hydration is still FULL_OFFICIAL.
--     Preview is a PUBLICATION-scope distinction, not a hydration-mode distinction.
--   * publish_state gets one new allowed value: PUBLISHED_SEO_PREVIEW.
--   * A separate view kosha_msds_seo_preview_current serves the preview slice.
--   * kosha_msds_current view is NOT modified (still filters on PUBLISHED_FULL only).
--
-- No data mutation. No row insert/update/delete. Grants/RLS mirror the FULL view.

BEGIN;

-- 1) Extend the publish_state CHECK constraint to allow PUBLISHED_SEO_PREVIEW.
--    Drop the old constraint and re-create it (Postgres has no CHECK altering).
ALTER TABLE public.kosha_msds_snapshots
  DROP CONSTRAINT IF EXISTS kosha_msds_snapshots_publish_state_check;

ALTER TABLE public.kosha_msds_snapshots
  ADD CONSTRAINT kosha_msds_snapshots_publish_state_check
  CHECK (publish_state IN ('NOT_PUBLISHED', 'PUBLISHED_FULL', 'PUBLISHED_SEO_PREVIEW'));

-- 2) Extend the pair-constraint. Every published state (FULL or SEO_PREVIEW)
--    requires enumeration_mode=FULL_OFFICIAL and status=COMPLETED. This keeps
--    the fail-closed provenance contract of the original migration.
--    NOTE: The original migration created an unnamed CHECK. We add a named one;
--    Postgres will keep the unnamed one too but both must hold. To avoid double
--    fencing (which is harmless but noisy), we don't drop the unnamed one — it
--    already permits PUBLISHED_SEO_PREVIEW paths because publish_state <> PUBLISHED_FULL
--    is the only branch, and PUBLISHED_SEO_PREVIEW satisfies that.
ALTER TABLE public.kosha_msds_snapshots
  ADD CONSTRAINT kosha_msds_snapshots_seo_preview_pair_check
  CHECK (
    publish_state <> 'PUBLISHED_SEO_PREVIEW'
    OR (enumeration_mode = 'FULL_OFFICIAL' AND status = 'COMPLETED')
  );

-- 3) Preview view. Same projection + join structure as kosha_msds_current;
--    only the WHERE predicate differs (PUBLISHED_SEO_PREVIEW instead of PUBLISHED_FULL).
--    Picks the newest completed_at winner so a re-published preview snapshot
--    supersedes older ones automatically (WO §17 rollback path).
CREATE OR REPLACE VIEW public.kosha_msds_seo_preview_current AS
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
  AND s.publish_state = 'PUBLISHED_SEO_PREVIEW'
  AND s.id = (
    SELECT id
    FROM public.kosha_msds_snapshots
    WHERE status = 'COMPLETED'
      AND enumeration_mode = 'FULL_OFFICIAL'
      AND publish_state = 'PUBLISHED_SEO_PREVIEW'
    ORDER BY completed_at DESC NULLS LAST, started_at DESC
    LIMIT 1
  );

COMMENT ON VIEW public.kosha_msds_seo_preview_current IS
  'Temporary SEO preview slice (WO-CHEM-SEO-PREVIEW-LIVE-001). '
  'Empty until a PUBLISHED_SEO_PREVIEW FULL_OFFICIAL snapshot exists. '
  'Distinct from kosha_msds_current (PUBLISHED_FULL). '
  'Full-corpus rollout supersedes preview by publishing PUBLISHED_FULL.';

REVOKE ALL ON public.kosha_msds_seo_preview_current FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.kosha_msds_seo_preview_current TO service_role;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON public.kosha_msds_seo_preview_current FROM service_role;

COMMIT;
