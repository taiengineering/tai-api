-- TAI TIME PHASE 2 STEP D artifact. EXECUTE = 0.
-- Direct 236 ALTERs + view recreate are NOT generated: ACTIVE column json_agg
-- and 3 viewdefs were not attached to the Cursor work order (see manifests sot_status).
-- This file records the locked ordering only.

BEGIN;

-- 3 view DROP (explicit, CASCADE 금지)
DROP VIEW public.v_equipment_unified;
DROP VIEW public.v_payments_list;
DROP VIEW public.v_process_unified;

-- 236 direct physical ALTER — REQUIRES TAI_TIME_ACTIVE_COLUMN_MANIFEST.json columns[]
-- 1 partition-root ALTER (16 children inherit)
ALTER TABLE public.work_schedules
  ALTER COLUMN reviewed_at TYPE timestamptz
  USING reviewed_at AT TIME ZONE 'Asia/Seoul';

-- 3 view EXACT recreate + OWNER/GRANT/COMMENT — REQUIRES viewdef SoT
-- postcheck: ACTIVE naive=0, isolated=20 untouched, default 161 now()/99 none, idx 5 exact

COMMIT;
