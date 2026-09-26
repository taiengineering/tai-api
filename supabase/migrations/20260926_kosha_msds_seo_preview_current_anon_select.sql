-- WO-MSDS-SITEMAP-ANON-GRANT-20260926-001
-- Root cause: kosha_msds_seo_preview_display (security_invoker=true)
-- references kosha_msds_seo_preview_current internally. The existing
-- migration 20260918_kosha_msds_seo_preview.sql intentionally restricted
-- current to service_role only. That design worked while display used
-- security_definer semantics, but display was created with
-- security_invoker=true, so Postgres propagates the invoker's permissions
-- to the underlying view. The anon role (used by tai-www Worker for
-- /sitemap_msds.xml) therefore lacks permission to resolve the current
-- view and the sitemap returns HTTP 502.
--
-- Fix: grant anon SELECT-only on the current view so the invoker chain
-- completes. No DML, no RLS, no view structure change.
--
-- Rollback:
--   REVOKE SELECT ON public.kosha_msds_seo_preview_current FROM anon;

BEGIN;

GRANT SELECT
    ON public.kosha_msds_seo_preview_current
    TO anon;

COMMIT;
