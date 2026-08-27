-- WP-INSPECTION-OPS / OBJ-01 INSPECTION RECORD / DEBT-W3-02
-- SAFE RESULT INITIAL-BATCH IDEMPOTENCY - DOWN
--
-- Drops the SAFE result batch idempotency RPC. No data is touched; no receipt
-- table, index, or base row is involved.

BEGIN;

DROP FUNCTION IF EXISTS public.fn_record_safe_inspection_result_batch(uuid, jsonb);

COMMIT;
