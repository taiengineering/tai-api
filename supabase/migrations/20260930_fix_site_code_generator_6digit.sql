-- ============================================================================
-- Fix fn_generate_site_code: prevent 6-digit sequence truncation
-- Date: 2026-09-30
-- Related: WO-E2E300-3SECTOR-PILOT-GATE-CLOSEOUT-005C PATCH-2
--
-- Root cause:
--   lpad(nextval::text, 5, '0') truncates strings longer than 5 chars.
--   When seq_site_code exceeds 99999 (6+ digits), PostgreSQL lpad truncates
--   from the right, producing duplicate codes:
--     513350..513354 all map to SITE51335
--
-- Fix:
--   Replace hardcoded 5 with greatest(5, length(seq_val::text)).
--   Preserves all existing SITE00001..SITE99999 values unchanged.
--
-- Verification:
--   1      -> SITE00001  (unchanged)
--   99999  -> SITE99999  (unchanged)
--   100000 -> SITE100000 (was SITE10000, now correct)
--   513354 -> SITE513354 (was SITE51335, now correct)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.fn_generate_site_code()
RETURNS trigger
LANGUAGE plpgsql
AS $$
declare
  v_site_seq bigint;
begin
  if new.site_code is null or trim(new.site_code) = '' then
    v_site_seq := nextval('seq_site_code');
    new.site_code :=
      'SITE' ||
      lpad(
        v_site_seq::text,
        greatest(5, length(v_site_seq::text)),
        '0'
      );
  end if;
  return new;
end;
$$;
