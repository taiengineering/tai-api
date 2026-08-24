-- =============================================================================
-- WP-DATA-ARCH-04B  Safety Inspection Submitter Anchor  (DOWN)
-- LEVEL-B ADDITIVE MIGRATION · schema-only
-- intended path   : tai-api/docs/sql/20260824_safety_inspection_submitter_anchor_down.sql
-- source API base : e1506aa45d3b35bf4d99d3c123600e9f19ab6996
-- canonical plan  : taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a
--
-- Exact reverse of UP (removes the same 2 objects, reverse order). No other object touched.
-- Restores safety_inspections to the PRE-STATE anchor recorded in the UP file.
-- Assumes UP was applied; run in a single transaction.
-- =============================================================================

-- reverse (2) FK
ALTER TABLE public.safety_inspections
    DROP CONSTRAINT safety_inspections_submitted_by_fkey;

-- reverse (1) column
ALTER TABLE public.safety_inspections
    DROP COLUMN submitted_by;
