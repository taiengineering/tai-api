-- WP-INSPECTION-OPS-01 / OBJ-01 INSPECTION RECORD / KNOT-3C1
-- SAFE START ATOMIC + IDEMPOTENT CREATOR - UP
--
-- Replaces the SAFE start writer's two-step, non-atomic, unguarded creation
--   (router: work_schedules UPDATE  ->  safety_inspections INSERT)
-- with one transactional RPC:
--   fn_start_safe_inspection_record(...) RETURNS jsonb
--     (SECURITY DEFINER, service_role EXECUTE only)
--     schedule pair lock -> existing inspection cardinality check ->
--     schedule in_progress -> base header IN_PROGRESS, all in ONE transaction.
--
-- Idempotency key = (work_schedule_id, factory_id). A repeated start returns the
-- existing inspection (replayed) with ZERO mutation; it does NOT create a second
-- base row. This is a lifecycle-start creator, so there is NO submission/creation
-- receipt (unlike the worker one-shot path), NO journal, NO command receipt, NO
-- results insert.
--
-- The PAIR UNIQUE constraint (assignment_id, factory_id) is intentionally NOT in
-- this migration; it is a separate KNOT-3C2 migration. Foundation objects are
-- never mutated here.

BEGIN;

CREATE OR REPLACE FUNCTION public.fn_start_safe_inspection_record(
    p_schedule_id    uuid,
    p_factory_id     uuid,
    p_started_at     timestamptz,
    p_inspector_name text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_sched         record;
    v_existing      record;
    v_count         integer;
    v_inspection_id uuid;
    v_snapshot      jsonb;
BEGIN
    -- S1) input validation (fail-closed)
    IF p_schedule_id IS NULL OR p_factory_id IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'INVALID_START_INPUT',
                                  'detail', 'schedule_id/factory_id required');
    END IF;
    IF p_started_at IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'START_TIMESTAMP_INVALID',
                                  'detail', 'started_at required');
    END IF;

    -- S2) parent pair lock (identity = (id, factory_id); no factory fallback)
    SELECT * INTO v_sched
    FROM public.work_schedules
    WHERE id = p_schedule_id AND factory_id = p_factory_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'WORK_SCHEDULE_NOT_FOUND',
                                  'detail', p_schedule_id::text);
    END IF;

    -- S3) existing inspection cardinality under lock, keyed on the schedule pair
    SELECT count(*) INTO v_count
    FROM public.safety_inspections
    WHERE assignment_id = p_schedule_id AND factory_id = p_factory_id;

    IF v_count > 1 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'INSPECTION_CARDINALITY_VIOLATION',
                                  'detail', p_schedule_id::text);
    ELSIF v_count = 1 THEN
        -- idempotent replay: return the existing inspection, ZERO mutation.
        -- start is idempotent on (schedule_id, factory_id) regardless of lifecycle.
        SELECT * INTO v_existing
        FROM public.safety_inspections
        WHERE assignment_id = p_schedule_id AND factory_id = p_factory_id
        LIMIT 1;
        v_snapshot := jsonb_build_object(
            'inspection_id',     v_existing.id,
            'work_schedule_id',  p_schedule_id,
            'factory_id',        p_factory_id,
            'inspection_status', v_existing.status_code,
            'started_at',        v_existing.inspection_date,
            'inspector_name',    p_inspector_name
        );
        RETURN jsonb_build_object('ok', true, 'replayed', true, 'data', v_snapshot);
    END IF;

    -- S4) schedule mutation (only on a fresh create)
    UPDATE public.work_schedules
    SET status_code = 'in_progress', inspector_name = p_inspector_name
    WHERE id = p_schedule_id AND factory_id = p_factory_id;

    -- S5) base header create (canonical uppercase IN_PROGRESS; no submitted_by,
    --     no journal, no command receipt, no creation receipt, no results)
    v_inspection_id := gen_random_uuid();
    INSERT INTO public.safety_inspections
        (id, assignment_id, inspector_id, inspection_date, status_code, factory_id)
    VALUES
        (v_inspection_id, p_schedule_id, NULL, p_started_at, 'IN_PROGRESS', p_factory_id);

    -- S6) response (revision 0 from the resolver's perspective)
    v_snapshot := jsonb_build_object(
        'inspection_id',     v_inspection_id,
        'work_schedule_id',  p_schedule_id,
        'factory_id',        p_factory_id,
        'inspection_status', 'IN_PROGRESS',
        'started_at',        p_started_at,
        'inspector_name',    p_inspector_name
    );
    RETURN jsonb_build_object('ok', true, 'replayed', false, 'data', v_snapshot);
END;
$fn$;

REVOKE ALL ON FUNCTION public.fn_start_safe_inspection_record(uuid, uuid, timestamptz, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_start_safe_inspection_record(uuid, uuid, timestamptz, text) TO service_role;

COMMIT;
