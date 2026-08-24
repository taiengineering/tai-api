-- =============================================================================
-- WP-DATA-ARCH-04A  Inspection → Document Source Anchor  (UP)
-- ARTIFACT AUTHORING ONLY · NOT EXECUTED · NOT COMMITTED
-- intended path      : tai-api/docs/sql/20260824_inspection_document_source_anchor_up.sql
-- source API repo    : taiengineering/tai-api
-- source API base    : e1506aa45d3b35bf4d99d3c123600e9f19ab6996
-- canonical plan     : taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a
-- plan reference     : IMPLEMENTATION_PLAN S1-1 / S1-2 · PHYSICAL_DESIGN(runtime_document_data)
-- MUTATION           : DB 0 / DDL 0 / DML 0 / DEPLOY 0  (this file is authored, not applied)
--
-- PRE-STATE ANCHOR [실측 @ vwlahtguyggrhvslabax, read-only introspection]
--   runtime_document_data : PK(id) · FK(form_schema_id→runtime_form_schema.id)
--                           CHECK(chk_rdd_status, chk_rdd_approval_requires_reviewer)
--                           row_count=1 · form_schema_id NULL=0
--   source_inspection_id column exists      = 0  (safe to ADD)
--   target constraint name collision        = 0  (both names free)
--   safety_inspections PK                    = PRIMARY KEY (id) · id uuid  (single-col FK target valid)
--   composite UNIQUE vs existing rows        = no conflict (col all-NULL after add; PG NULL distinct)
--
-- SCOPE (exactly 3 objects): +1 column, +1 FK, +1 UNIQUE. Nothing else.
-- FORBIDDEN: backfill · source inference · status change · inspection data change
--            · new table/trigger/function · document auto-create
-- =============================================================================

-- (1) additive nullable column — legacy/non-inspection document = NULL allowed;
--     inspection-backed document = set by future code contract (CD5-2), NOT here.
ALTER TABLE public.runtime_document_data
    ADD COLUMN source_inspection_id uuid NULL;

-- (2) FK → safety_inspections(id), ON DELETE RESTRICT (WP-02 sealed contract; SET NULL 금지)
ALTER TABLE public.runtime_document_data
    ADD CONSTRAINT runtime_document_data_source_inspection_id_fkey
    FOREIGN KEY (source_inspection_id)
    REFERENCES public.safety_inspections (id)
    ON DELETE RESTRICT;

-- (3) idempotency guard — composite UNIQUE (NOT UNIQUE on source_inspection_id alone)
ALTER TABLE public.runtime_document_data
    ADD CONSTRAINT uq_rdd_source_inspection_form_schema
    UNIQUE (source_inspection_id, form_schema_id);
