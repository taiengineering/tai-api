-- ============================================================================
-- Restore TEMP UUID branch in fn_generate_site_code
-- Date: 2026-09-30
-- Related: WO-E2E300-PILOT-PATCH3 — corrects PATCH-2 regression
--
-- PATCH-2 (20260930_fix_site_code_generator_6digit.sql) replaced the entire
-- function body with only the greatest(5,len) fix, accidentally removing the
-- TEMP UUID branch for status_code in (ANON_TEMP, E2E_TEMP, REGA_TEMP,
-- REGB_TEMP, E2E_TEST).
--
-- This migration restores the TEMP branch AND keeps the lpad truncation fix.
--
-- Final function behaviour:
--   status_code in TEMP set  → 'TMP-' || random UUID (32 hex chars, no dashes)
--   all other status_codes   → 'SITE' || lpad(seq, greatest(5,len(seq)), '0')
--
-- Verification simulations (no DB writes):
--   seq=1       → SITE00001   (5-digit min preserved)
--   seq=99999   → SITE99999   (unchanged)
--   seq=100000  → SITE100000  (was SITE10000 before lpad fix)
--   seq=513357  → SITE513357  (was SITE51335 before lpad fix)
--   ANON_TEMP   → TMP-<uuid32>
--   E2E_TEMP    → TMP-<uuid32>
-- ============================================================================

CREATE OR REPLACE FUNCTION public.fn_generate_site_code()
RETURNS trigger
LANGUAGE plpgsql
AS $$
declare
  v_site_seq bigint;
begin
  if new.site_code is null or trim(new.site_code) = '' then
    if new.status_code in ('ANON_TEMP','E2E_TEMP','REGA_TEMP','REGB_TEMP','E2E_TEST') then
      new.site_code := 'TMP-' || replace(gen_random_uuid()::text, '-', '');
    else
      v_site_seq := nextval('seq_site_code');
      new.site_code :=
        'SITE' ||
        lpad(
          v_site_seq::text,
          greatest(5, length(v_site_seq::text)),
          '0'
        );
    end if;
  end if;
  return new;
end;
$$;
