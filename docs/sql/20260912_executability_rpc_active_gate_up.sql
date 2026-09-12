-- STAGE1 EXECUTABILITY — atomic RPC active_yn fail-close
-- WO-SAFE-EXECUTABILITY-ACTIVE-GATE-STAGE1-001 / PATCH-R3
--
-- REGISTERED in supabase/migrations (guri-cf convention).
-- production APPLY = HUMAN ONLY (AI-003). NOT applied in this WO.
--
-- Authority sources (CREATE OR REPLACE on current applied semantics):
--   docs/sql/20260827_safe_inspection_start_atomic_up.sql
--   docs/sql/20260827_worker_inspection_pair_lock_patch_up.sql
--
-- Additive only: after parent lock (+ replay fast-paths), require
--   work_schedules.active_yn IS TRUE
-- before any schedule/inspection/result/receipt side-effect.
-- Error code: WORK_SCHEDULE_NOT_EXECUTABLE

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
        -- replay 는 저장된 사실만 반환한다: inspector_name 은 잠긴 work_schedules 행의
        -- 값(v_sched.inspector_name), started_at 은 기존 inspection_date. 두 번째 요청의
        -- p_inspector_name / p_started_at 은 replay 응답에 쓰지 않는다.
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
            'inspector_name',    v_sched.inspector_name
        );
        RETURN jsonb_build_object('ok', true, 'replayed', true, 'data', v_snapshot);
    END IF;

    -- S2b/S3b) Stage1 executability: active_yn exact TRUE before side-effects.
    -- Idempotent replay (v_count=1) already returned above with ZERO mutation.
    IF v_sched.active_yn IS DISTINCT FROM TRUE THEN
        RETURN jsonb_build_object('ok', false, 'error', 'WORK_SCHEDULE_NOT_EXECUTABLE',
                                  'detail', 'active_yn is not true');
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

CREATE OR REPLACE FUNCTION public.fn_create_worker_inspection_record(
    p_submission_id   uuid,
    p_request_hash    text,
    p_source          text,
    p_schedule_id     uuid,
    p_factory_id      uuid,
    p_inspector_id    uuid,
    p_submitted_at    timestamptz,
    p_results         jsonb,
    p_request_payload jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_existing    record;
    v_sched       record;
    v_count       integer;
    v_inspection_id uuid;
    v_elem        jsonb;
    v_code        text;
    v_normal      integer := 0;
    v_abnormal    integer := 0;
    v_hold        integer := 0;
    v_total       integer := 0;
    v_overall     text;
    v_issue_items jsonb := '[]'::jsonb;
    v_snapshot    jsonb;
BEGIN
    -- 1) input validation
    IF p_submission_id IS NULL OR p_request_hash IS NULL OR p_request_hash = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'INVALID_SUBMISSION_INPUT',
                                  'detail', 'submission_id/request_hash required');
    END IF;
    IF p_schedule_id IS NULL OR p_factory_id IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'INVALID_SUBMISSION_INPUT',
                                  'detail', 'schedule_id/factory_id required');
    END IF;
    IF p_submitted_at IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'WORKER_SUBMISSION_TIMESTAMP_INVALID',
                                  'detail', 'submitted_at required');
    END IF;
    IF p_results IS NULL OR jsonb_typeof(p_results) <> 'array' OR jsonb_array_length(p_results) = 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'EMPTY_RESULTS', 'detail', 'results required');
    END IF;

    -- 2) creation receipt replay check (fast path, before lock)
    SELECT * INTO v_existing
    FROM public.safety_inspection_creation_receipt
    WHERE submission_id = p_submission_id;
    IF FOUND THEN
        IF v_existing.request_hash = p_request_hash THEN
            -- exact replay: return stored snapshot, mutation 0
            RETURN jsonb_build_object('ok', true, 'replayed', true, 'data', v_existing.response_snapshot);
        ELSE
            RETURN jsonb_build_object('ok', false, 'error', 'SUBMISSION_ID_REUSE_CONFLICT',
                                      'detail', 'same submission_id, different request_hash');
        END IF;
    END IF;

    -- 3) serialize per schedule (pair identity: id + factory_id)
    SELECT * INTO v_sched
    FROM public.work_schedules
    WHERE id = p_schedule_id AND factory_id = p_factory_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'WORK_SCHEDULE_NOT_FOUND', 'detail', p_schedule_id::text);
    END IF;

    -- 3b) concurrency recheck (single recheck under lock, NOT a retry loop):
    -- a concurrent request holding the lock first may have created the receipt.
    SELECT * INTO v_existing
    FROM public.safety_inspection_creation_receipt
    WHERE submission_id = p_submission_id;
    IF FOUND THEN
        IF v_existing.request_hash = p_request_hash THEN
            RETURN jsonb_build_object('ok', true, 'replayed', true, 'data', v_existing.response_snapshot);
        ELSE
            RETURN jsonb_build_object('ok', false, 'error', 'SUBMISSION_ID_REUSE_CONFLICT',
                                      'detail', 'same submission_id, different request_hash');
        END IF;
    END IF;

    -- 4) factory match
    IF v_sched.factory_id IS DISTINCT FROM p_factory_id THEN
        RETURN jsonb_build_object('ok', false, 'error', 'FACTORY_MISMATCH',
                                  'detail', 'schedule.factory_id != p_factory_id');
    END IF;

    -- 4b) Stage1 executability: active_yn exact TRUE before side-effects.
    -- Creation-receipt replay (steps 2/3b) already returned above with ZERO mutation.
    IF v_sched.active_yn IS DISTINCT FROM TRUE THEN
        RETURN jsonb_build_object('ok', false, 'error', 'WORK_SCHEDULE_NOT_EXECUTABLE',
                                  'detail', 'active_yn is not true');
    END IF;

    -- 5) duplicate schedule inspection check (under lock; pair identity)
    SELECT count(*) INTO v_count
    FROM public.safety_inspections
    WHERE assignment_id = p_schedule_id AND factory_id = p_factory_id;
    IF v_count > 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'INSPECTION_ALREADY_EXISTS_FOR_SCHEDULE',
                                  'detail', p_schedule_id::text);
    END IF;

    -- 6) canonical result validation (EXACT, no normalization) + aggregate
    FOR v_elem IN SELECT value FROM jsonb_array_elements(p_results) AS value
    LOOP
        IF jsonb_typeof(v_elem->'result_code') <> 'string' THEN
            RETURN jsonb_build_object('ok', false, 'error', 'RESULT_CODE_UNRESOLVED', 'detail', 'result_code not a string');
        END IF;
        v_code := v_elem->>'result_code';
        IF v_code NOT IN ('NORMAL','ABNORMAL','HOLD') THEN
            RETURN jsonb_build_object('ok', false, 'error', 'RESULT_CODE_UNRESOLVED',
                                      'detail', coalesce(v_code, ''));
        END IF;
        v_total := v_total + 1;
        IF v_code = 'NORMAL' THEN
            v_normal := v_normal + 1;
        ELSIF v_code = 'ABNORMAL' THEN
            v_abnormal := v_abnormal + 1;
            v_issue_items := v_issue_items || jsonb_build_array(jsonb_build_object(
                'item_name', coalesce(v_elem->>'item_name', ''),
                'note',      coalesce(v_elem->>'note', ''),
                'photo_urls', coalesce(v_elem->'photo_urls', '[]'::jsonb)
            ));
        ELSE
            v_hold := v_hold + 1;
        END IF;
    END LOOP;

    IF v_abnormal > 0 THEN
        v_overall := 'ABNORMAL';
    ELSIF v_hold > 0 THEN
        v_overall := 'HOLD';
    ELSE
        v_overall := 'NORMAL';
    END IF;

    -- 7) server-side inspection UUID
    v_inspection_id := gen_random_uuid();

    -- 8) base header INSERT (lifecycle COMPLETED regardless of outcome)
    INSERT INTO public.safety_inspections
        (id, assignment_id, inspector_id, inspection_date, status_code, factory_id)
    VALUES
        (v_inspection_id, p_schedule_id, p_inspector_id, p_submitted_at, 'COMPLETED', p_factory_id);

    -- 9) results INSERT (checked_at = submitted_at; canonical result_code)
    INSERT INTO public.safety_inspection_results
        (inspection_id, inspection_set_item_id, item_name, result_code, note, photo_urls, value_text, value_number, checked_at)
    SELECT
        v_inspection_id,
        nullif(e->>'inspection_set_item_id', '')::uuid,
        e->>'item_name',
        e->>'result_code',
        e->>'note',
        coalesce(e->'photo_urls', '[]'::jsonb),
        e->>'value_text',
        nullif(e->>'value_number', '')::numeric,
        p_submitted_at
    FROM jsonb_array_elements(p_results) AS e;

    -- 10) response snapshot (facts; presentation alias is the router's job)
    v_snapshot := jsonb_build_object(
        'inspection_id',     v_inspection_id,
        'revision',          0,
        'inspection_status', 'COMPLETED',
        'overall_result',    v_overall,
        'normal_count',      v_normal,
        'abnormal_count',    v_abnormal,
        'hold_count',        v_hold,
        'total_count',       v_total,
        'issue_items',       v_issue_items,
        'inspector_id',      p_inspector_id
    );

    -- 11) creation receipt INSERT (same transaction as base + results)
    INSERT INTO public.safety_inspection_creation_receipt
        (submission_id, inspection_id, source, request_hash, request_payload, response_snapshot)
    VALUES
        (p_submission_id, v_inspection_id, coalesce(p_source, 'WORKER_PWA'),
         p_request_hash, coalesce(p_request_payload, '{}'::jsonb), v_snapshot);

    -- 12) return
    RETURN jsonb_build_object('ok', true, 'replayed', false, 'data', v_snapshot);
END;
$fn$;

REVOKE ALL ON FUNCTION public.fn_start_safe_inspection_record(uuid, uuid, timestamptz, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_start_safe_inspection_record(uuid, uuid, timestamptz, text) TO service_role;

REVOKE ALL ON FUNCTION public.fn_create_worker_inspection_record(uuid, text, text, uuid, uuid, uuid, timestamptz, jsonb, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_create_worker_inspection_record(uuid, text, text, uuid, uuid, uuid, timestamptz, jsonb, jsonb) TO service_role;

COMMIT;
