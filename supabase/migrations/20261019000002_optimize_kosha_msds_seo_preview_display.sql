-- WO-TAI-SUPABASE-ERROR-CLOSURE-20261019-001
-- Optimize kosha_msds_seo_preview_display to avoid full-table scan on per-row queries.
--
-- Problem:
--   The current view defines items CTE as:
--       SELECT s.chemical_id, s.section_no, e.value->> ... AS code, e.value->> ... AS val
--       FROM kosha_msds_sections s
--       CROSS JOIN LATERAL jsonb_array_elements(s.payload_json) e(value)
--       WHERE s.section_no = ANY(ARRAY[1,2,3,15])
--   This reads ALL ~300,000 rows from kosha_msds_sections before filtering by chemical_id.
--   When a caller queries by chem_id (single row), the planner cannot push the predicate
--   through the CTE barrier → full table scan on every request → 57014 statement_timeout.
--
-- Fix:
--   Restructure the CTE so that kosha_msds_seo_preview_current v is the leading relation.
--   By joining sections to the current snapshot members first, the existing UNIQUE index
--   on (chemical_id, section_no) can be used for index-only seeks when chem_id is filtered.
--
-- Column contract: identical to existing view.
--   id, content_id, source_id, source_key, chem_id, identity_status,
--   chemical_name_ko, chemical_name_en, cas_no, ke_no, en_no, un_no,
--   source_content_hash, source_dataset_url, snapshot_id,
--   hazard_class, signal_word, pictograms, reg_saolaw, reg_dangerous, last_date
--
-- GRANT preservation:
--   anon: SELECT (existing; other DML grants are Postgres view defaults — left intact)
--   authenticated: SELECT
--   service_role: SELECT
--   (No new grants. No grant removal.)
--
-- Security: reloptions was NULL (owner-based execution, no security_invoker) → preserved.
--
-- Rollback:
--   Restore previous view definition from this migration's DROP target or from
--   the pg_get_viewdef snapshot in WO-TAI-SUPABASE-ERROR-CLOSURE-20261019-001 evidence.
--
-- No base-table GRANT change.
-- No RLS change.
-- No DML.
-- Production apply requires Owner approval + GPT independent verification.

BEGIN;

-- Drop and recreate — ALTER VIEW cannot change the SELECT body.
DROP VIEW IF EXISTS public.kosha_msds_seo_preview_display;

CREATE VIEW public.kosha_msds_seo_preview_display AS
WITH
-- Step 1: start from the current-snapshot members only (bounded set).
--   Joining sections HERE means the planner can use the (chemical_id, section_no)
--   UNIQUE index when an outer predicate filters on v.chem_id.
items AS (
    SELECT
        v.id            AS chemical_id,
        s.section_no,
        e.value ->> 'msdsItemCode' AS code,
        e.value ->> 'itemDetail'   AS val
    FROM public.kosha_msds_seo_preview_current v
    JOIN public.kosha_msds_sections s
        ON s.chemical_id = v.id
       AND s.section_no = ANY(ARRAY[1, 2, 3, 15])
    CROSS JOIN LATERAL jsonb_array_elements(s.payload_json) e(value)
),
pick AS (
    SELECT
        chemical_id,
        max(val) FILTER (WHERE section_no = 1  AND code = 'A02')   AS a02,
        max(val) FILTER (WHERE section_no = 3  AND code = 'C06')   AS c06,
        max(val) FILTER (WHERE section_no = 2  AND code = 'B02')   AS b02,
        max(val) FILTER (WHERE section_no = 2  AND code = 'B0404') AS b0404,
        max(val) FILTER (WHERE section_no = 2  AND code = 'B0402') AS b0402,
        max(val) FILTER (WHERE section_no = 15 AND code = 'O02')   AS o02,
        max(val) FILTER (WHERE section_no = 15 AND code = 'O06')   AS o06
    FROM items
    GROUP BY chemical_id
),
nz AS (
    SELECT
        chemical_id,
        NULLIF(NULLIF(btrim(COALESCE(a02,   '')), '자료없음'), '해당없음') AS a02,
        NULLIF(NULLIF(btrim(COALESCE(c06,   '')), '자료없음'), '해당없음') AS c06,
        NULLIF(NULLIF(btrim(COALESCE(b02,   '')), '자료없음'), '해당없음') AS b02,
        NULLIF(NULLIF(btrim(COALESCE(b0404, '')), '자료없음'), '해당없음') AS b0404,
        NULLIF(NULLIF(btrim(COALESCE(b0402, '')), '자료없음'), '해당없음') AS b0402,
        NULLIF(NULLIF(btrim(COALESCE(o02,   '')), '자료없음'), '해당없음') AS o02,
        NULLIF(NULLIF(btrim(COALESCE(o06,   '')), '자료없음'), '해당없음') AS o06
    FROM pick
)
SELECT
    v.id,
    v.content_id,
    v.source_id,
    v.source_key,
    v.chem_id,
    v.identity_status,
    COALESCE(NULLIF(btrim(COALESCE(v.chemical_name_ko, '')), ''), p.a02) AS chemical_name_ko,
    v.chemical_name_en,
    COALESCE(NULLIF(btrim(COALESCE(v.cas_no, '')), ''), p.c06) AS cas_no,
    v.ke_no,
    v.en_no,
    v.un_no,
    v.source_content_hash,
    v.source_dataset_url,
    v.snapshot_id,
    p.b02   AS hazard_class,
    p.b0404 AS signal_word,
    p.b0402 AS pictograms,
    p.o02   AS reg_saolaw,
    p.o06   AS reg_dangerous,
    c.last_date
FROM public.kosha_msds_seo_preview_current v
LEFT JOIN nz p ON p.chemical_id = v.id
LEFT JOIN public.kosha_msds_chemicals c ON c.id = v.id;

-- Restore grants (mirrors pre-existing state confirmed via information_schema 2026-10-19)
GRANT SELECT ON public.kosha_msds_seo_preview_display TO anon;
GRANT SELECT ON public.kosha_msds_seo_preview_display TO authenticated;
GRANT SELECT ON public.kosha_msds_seo_preview_display TO service_role;

COMMIT;
