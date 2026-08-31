-- TAI TIME PHASE 2 STEP D artifact. EXECUTE = 0.
-- Reverse of UP. Isolated 20 columns must remain untouched.
-- Direct 236 reverse ALTERs require ACTIVE manifest columns[].

BEGIN;

DROP VIEW public.v_equipment_unified;
DROP VIEW public.v_payments_list;
DROP VIEW public.v_process_unified;

ALTER TABLE public.work_schedules
  ALTER COLUMN reviewed_at TYPE timestamp without time zone
  USING reviewed_at AT TIME ZONE 'Asia/Seoul';

-- 236 × TYPE timestamp without time zone USING <col> AT TIME ZONE 'Asia/Seoul'
-- 3 view EXACT recreate from SoT viewdef

COMMIT;
