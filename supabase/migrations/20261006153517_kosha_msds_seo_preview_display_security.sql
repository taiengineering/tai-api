-- WO-MSDS-SITEMAP-DISPLAY-SECURITY-20260926-001
-- The display view was created with security_invoker=true, which means
-- PostgreSQL evaluates all underlying object access using the invoker's
-- (anon) privileges. The view references kosha_msds_sections,
-- kosha_msds_chemicals, and kosha_msds_seo_preview_current — none of the
-- base tables carry anon SELECT. Granting anon on base tables (Path B)
-- would expand the public read surface unnecessarily.
--
-- Fix (Path A): remove the security_invoker option so the view executes
-- under the owner's (postgres) privileges, which already cover all
-- referenced objects. RESET restores the PostgreSQL default (owner-based
-- security), without altering the view's SELECT body.
--
-- No base-table GRANT, no RLS change, no view definition change.
--
-- Rollback:
--   ALTER VIEW public.kosha_msds_seo_preview_display
--   SET (security_invoker = true);

BEGIN;

ALTER VIEW public.kosha_msds_seo_preview_display
    RESET (security_invoker);

COMMIT;
