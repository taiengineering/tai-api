-- WP-INSPECTION-OPS-01 / OBJ-01 INSPECTION RECORD / KNOT-3B
-- WORKER ONE-SHOT RECORD CREATION - UP
--
-- Adds the atomic worker one-shot creation path:
--   table  safety_inspection_creation_receipt  (append-only, base creation idempotency)
--   func   fn_create_worker_inspection_record(...) RETURNS jsonb
--          (SECURITY DEFINER, service_role EXECUTE only; base header + results +
--           creation receipt in ONE transaction; NO journal, NO command receipt)
--
-- The existing command receipt (safety_inspection_command_receipt) is for
-- post-creation revision-command idempotency and is NOT reused here. Creation
-- idempotency needs a receipt that keys on submission_id BEFORE an inspection
-- exists, hence a separate table.
--
-- Foundation objects (STEP-1A) are never mutated here.

BEGIN;

-- ---------------------------------------------------------------------------
-- creation receipt (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE public.safety_inspection_creation_receipt (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id     uuid NOT NULL UNIQUE,
    inspection_id     uuid NOT NULL REFERENCES public.safety_inspections(id) ON DELETE RESTRICT,
    source            text NOT NULL,
    request_hash      text NOT NULL,
    request_payload   jsonb NOT NULL,
    response_snapshot jsonb NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- RLS on, zero policies (service_role bypasses; anon/authenticated blocked)
ALTER TABLE public.safety_inspection_creation_receipt ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.safety_inspection_creation_receipt FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.safety_inspection_creation_receipt FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.safety_inspection_creation_receipt TO service_role;

-- append-only: reuse the foundation reject function (blocks physical UPDATE/DELETE)
CREATE TRIGGER trg_sicreation_append_only
    BEFORE UPDATE OR DELETE ON public.safety_inspection_creation_receipt
    FOR EACH ROW EXECUTE FUNCTION public.fn_reject_inspection_record_mutation();

-- ---------------------------------------------------------------------------
-- atomic worker one-shot creation RPC
-- ---------------------------------------------------------------------------
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

    -- 2) creation receipt replay check (before any mutation)
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

    -- 3) serialize per schedule
    SELECT * INTO v_sched
    FROM public.work_schedules
    WHERE id = p_schedule_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'WORK_SCHEDULE_NOT_FOUND', 'detail', p_schedule_id::text);
    END IF;

    -- 4) factory match
    IF v_sched.factory_id IS DISTINCT FROM p_factory_id THEN
        RETURN jsonb_build_object('ok', false, 'error', 'FACTORY_MISMATCH',
                                  'detail', 'schedule.factory_id != p_factory_id');
    END IF;

    -- 5) duplicate schedule inspection check (under lock)
    SELECT count(*) INTO v_count
    FROM public.safety_inspections
    WHERE assignment_id = p_schedule_id;
    IF v_count > 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'INSPECTION_ALREADY_EXISTS_FOR_SCHEDULE',
                                  'detail', p_schedule_id::text);
    END IF;

    -- 6) canonical result validation + aggregate
    FOR v_elem IN SELECT value FROM jsonb_array_elements(p_results) AS value
    LOOP
        v_code := upper(coalesce(v_elem->>'result_code', ''));
        IF v_code NOT IN ('NORMAL','ABNORMAL','HOLD') THEN
            RETURN jsonb_build_object('ok', false, 'error', 'RESULT_CODE_UNRESOLVED',
                                      'detail', coalesce(v_elem->>'result_code',''));
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
        (id, assignment_id, inspector_id, inspection_date, status_code, factory_id, submitted_by)
    VALUES
        (v_inspection_id, p_schedule_id, p_inspector_id, p_submitted_at, 'COMPLETED', p_factory_id, p_inspector_id);

    -- 9) results INSERT (checked_at = submitted_at; canonical result_code)
    INSERT INTO public.safety_inspection_results
        (inspection_id, inspection_set_item_id, item_name, result_code, note, photo_urls, value_text, value_number, checked_at)
    SELECT
        v_inspection_id,
        nullif(e->>'inspection_set_item_id', '')::uuid,
        e->>'item_name',
        upper(e->>'result_code'),
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

REVOKE ALL ON FUNCTION public.fn_create_worker_inspection_record(uuid, text, text, uuid, uuid, uuid, timestamptz, jsonb, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_create_worker_inspection_record(uuid, text, text, uuid, uuid, uuid, timestamptz, jsonb, jsonb) TO service_role;

COMMIT;
