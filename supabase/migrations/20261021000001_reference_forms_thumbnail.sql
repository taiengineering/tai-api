-- =============================================================================
-- Migration: 20261021000001_reference_forms_thumbnail.sql
-- WO-WWW-SS-THUMBNAIL-001 P2 — thumbnail metadata columns
--
-- Adds 6 nullable columns to reference_form_preview_artifacts for pre-generated
-- WebP thumbnail tracking. All columns NULL by default — existing 138 rows
-- are unaffected. Migration is additive only; no data modified.
--
-- thumbnail_qa_status constraint mirrors existing qa_status pattern.
-- NULL = not yet generated  PENDING = in progress  QA_PASS/QA_FAIL = final
--
-- NOT applied to production DB.
-- Requires separate Owner approval (G3) before production apply.
-- =============================================================================

ALTER TABLE public.reference_form_preview_artifacts
    ADD COLUMN IF NOT EXISTS thumbnail_ref                TEXT,
    ADD COLUMN IF NOT EXISTS thumbnail_sha256             TEXT,
    ADD COLUMN IF NOT EXISTS thumbnail_input_sha256       TEXT,
    ADD COLUMN IF NOT EXISTS thumbnail_generation_version TEXT,
    ADD COLUMN IF NOT EXISTS thumbnail_qa_status          TEXT
        CONSTRAINT chk_pa_thumbnail_qa_status
        CHECK (thumbnail_qa_status IS NULL OR
               thumbnail_qa_status IN ('PENDING', 'QA_PASS', 'QA_FAIL')),
    ADD COLUMN IF NOT EXISTS thumbnail_bytes              INTEGER;

-- Partial index for backfill queries (only rows with non-null status)
CREATE INDEX IF NOT EXISTS idx_ref_preview_thumbnail_qa
    ON public.reference_form_preview_artifacts (thumbnail_qa_status)
    WHERE thumbnail_qa_status IS NOT NULL;

COMMENT ON COLUMN public.reference_form_preview_artifacts.thumbnail_ref IS
    'storage://reference-forms-preview/thumbnails/<uuid>-v1.webp — pre-generated WebP thumbnail';
COMMENT ON COLUMN public.reference_form_preview_artifacts.thumbnail_sha256 IS
    'SHA-256 of the generated WebP thumbnail bytes';
COMMENT ON COLUMN public.reference_form_preview_artifacts.thumbnail_input_sha256 IS
    'SHA-256 of the Preview PNG used as input to the WebP conversion';
COMMENT ON COLUMN public.reference_form_preview_artifacts.thumbnail_generation_version IS
    'Generation version string, e.g. "v1-pillow-10.4.0"';
COMMENT ON COLUMN public.reference_form_preview_artifacts.thumbnail_qa_status IS
    'NULL=not generated, PENDING=in progress, QA_PASS=valid, QA_FAIL=failed';
COMMENT ON COLUMN public.reference_form_preview_artifacts.thumbnail_bytes IS
    'Byte size of the generated WebP thumbnail (enforced <= 71680 by generator)';
