-- WP-INSPECTION-OPS-01 / OBJ-01 INSPECTION RECORD / STEP-1A
-- ADDITIVE FOUNDATION — DOWN (packaging artifact only; NOT executed in STEP-1A)
--
-- Reverses the UP additively-created objects in dependency order.
-- MUST NOT contain any CREATE of foundation objects, and MUST NOT touch the
-- base ledger (safety_inspections / safety_inspection_results): no ALTER,
-- UPDATE, DELETE, or DROP of base objects here.

BEGIN;

DROP TRIGGER IF EXISTS trg_sirj_append_only  ON public.safety_inspection_record_journal;
DROP TRIGGER IF EXISTS trg_sicr_append_only  ON public.safety_inspection_command_receipt;

DROP FUNCTION IF EXISTS public.fn_apply_inspection_record_command(
    uuid, bigint, uuid, text, uuid, jsonb, text, uuid, text, text
);
DROP FUNCTION IF EXISTS public.fn_resolve_inspection_record(uuid);
DROP FUNCTION IF EXISTS public.fn_reject_inspection_record_mutation();

DROP TABLE IF EXISTS public.safety_inspection_command_receipt;
DROP TABLE IF EXISTS public.safety_inspection_record_journal;

COMMIT;
