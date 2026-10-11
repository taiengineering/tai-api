-- =============================================================================
-- Migration: 20261011140000_wo018_p1_view_format_preview.sql
-- WO-018 P1: Add format + has_preview to qa_pass_files in reference_form_public_view
--
-- Changes:
--   qa_pass_files jsonb objects gain two new fields:
--     "format"      TEXT    — 'pdf' | 'docx' | 'xlsx'
--     "has_preview" BOOLEAN — true only when a preview artifact is linked
--
-- file_ref remains NOT exposed (internal Storage path).
-- =============================================================================

CREATE OR REPLACE VIEW public.reference_form_public_view
WITH (security_invoker = true)
AS
SELECT
    rf.id,
    rfc.canonical_slug,
    rfc.title,
    rfc.description,
    rf.published_at,
    GREATEST(rf.updated_at, rfc.updated_at)           AS updated_at,
    ra.id                                              AS approval_id,
    (rfc.content_hash = ra.approved_content_hash)     AS content_approved,
    COALESCE(
        (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'file_id',     f.id,
                    'sha256',      f.sha256,
                    'approved_at', f.approved_at,
                    'format',      lower(split_part(f.file_ref, '.', -1)),
                    'has_preview', (f.preview_artifact_id IS NOT NULL)
                )
                ORDER BY f.created_at
            )
            FROM public.reference_form_files f
            WHERE f.form_id = rf.id
              AND f.is_active = true
              AND f.qa_status = 'QA_PASS'
              AND f.approved_at IS NOT NULL
        ),
        '[]'::JSONB
    )                                                  AS qa_pass_files,
    COALESCE(
        (
            SELECT array_agg(DISTINCT lower(split_part(f2.file_ref, '.', -1))
                             ORDER BY lower(split_part(f2.file_ref, '.', -1)))
            FROM public.reference_form_files f2
            WHERE f2.form_id = rf.id
              AND f2.is_active = true
              AND f2.qa_status = 'QA_PASS'
        ),
        ARRAY[]::TEXT[]
    )                                                  AS formats,
    COALESCE(
        (
            SELECT array_agg(ll.legacy_code ORDER BY ll.legacy_code)
            FROM public.reference_form_legacy_links ll
            WHERE ll.form_id = rf.id
              AND ll.is_active = true
        ),
        ARRAY[]::TEXT[]
    )                                                  AS legacy_codes
FROM public.reference_forms rf
JOIN public.reference_form_content rfc
    ON rfc.form_id = rf.id AND rfc.lang = 'ko'
JOIN public.reference_form_approvals ra
    ON ra.form_id = rf.id
    AND ra.is_current = true
    AND ra.approval_status = 'APPROVED'
WHERE rf.status = 'PUBLISHED'
  AND rfc.content_hash = ra.approved_content_hash;
