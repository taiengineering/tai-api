-- =============================================================================
-- WP-DATA-ARCH-04A  Inspection → Document Source Anchor  (DOWN)
-- ARTIFACT AUTHORING ONLY · NOT EXECUTED · NOT COMMITTED
-- intended path      : tai-api/docs/sql/20260824_inspection_document_source_anchor_down.sql
-- source API base    : e1506aa45d3b35bf4d99d3c123600e9f19ab6996
-- canonical plan     : taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a
-- MUTATION           : DB 0 / DDL 0 / DML 0 / DEPLOY 0  (this file is authored, not applied)
--
-- Exact reverse of UP (removes the same 3 objects, reverse order). No other object touched.
-- Restores runtime_document_data to the PRE-STATE anchor recorded in the UP file.
-- Assumes UP was applied; run in a single transaction.
-- =============================================================================

-- reverse (3) UNIQUE
ALTER TABLE public.runtime_document_data
    DROP CONSTRAINT uq_rdd_source_inspection_form_schema;

-- reverse (2) FK
ALTER TABLE public.runtime_document_data
    DROP CONSTRAINT runtime_document_data_source_inspection_id_fkey;

-- reverse (1) column
ALTER TABLE public.runtime_document_data
    DROP COLUMN source_inspection_id;
