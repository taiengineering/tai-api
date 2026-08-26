-- WP-INSPECTION-OPS-01 / OBJ-01 INSPECTION RECORD / KNOT-3B
-- WORKER ONE-SHOT RECORD CREATION - DOWN
--
-- Reverses ONLY the KNOT-3B additions. Foundation objects (STEP-1A) and the
-- shared reject function fn_reject_inspection_record_mutation() are NOT dropped.

BEGIN;

DROP FUNCTION IF EXISTS public.fn_create_worker_inspection_record(uuid, text, text, uuid, uuid, uuid, timestamptz, jsonb, jsonb);

DROP TRIGGER IF EXISTS trg_sicreation_append_only ON public.safety_inspection_creation_receipt;

DROP TABLE IF EXISTS public.safety_inspection_creation_receipt;

COMMIT;
