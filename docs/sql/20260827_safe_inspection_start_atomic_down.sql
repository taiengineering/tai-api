-- WP-INSPECTION-OPS-01 / OBJ-01 INSPECTION RECORD / KNOT-3C1
-- SAFE START ATOMIC + IDEMPOTENT CREATOR - DOWN
--
-- Drops the atomic SAFE start creator RPC. No data is touched; the base ledger,
-- work_schedules, and foundation objects are never modified by this DOWN.

BEGIN;

DROP FUNCTION IF EXISTS public.fn_start_safe_inspection_record(uuid, uuid, timestamptz, text);

COMMIT;
