-- WP-INSPECTION-OPS-01 / OBJ-01 INSPECTION RECORD / KNOT-2
-- EFFECTIVE READ ADAPTER — DOWN (packaging artifact only; NOT executed here)
--
-- Drops ONLY the list adapter function. Base ledger, STEP-1A foundation
-- objects, and the single-record resolver are untouched.

BEGIN;

DROP FUNCTION IF EXISTS public.fn_list_effective_inspection_records_by_inspector(uuid, integer);

COMMIT;
