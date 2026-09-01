-- TAI scheduler atomic state machine DOWN. EXECUTE = 0. Do not run against TAI Supabase.
-- Drops the two RPCs only. Unique occurrence index is retained.

DROP FUNCTION IF EXISTS public.tai_scheduler_claim_occurrence(text, timestamptz, timestamptz, interval, text);
DROP FUNCTION IF EXISTS public.tai_scheduler_complete_occurrence(text, timestamptz, uuid, integer, text, jsonb, timestamptz, timestamptz);
