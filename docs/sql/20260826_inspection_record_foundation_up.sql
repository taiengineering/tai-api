-- WP-INSPECTION-OPS-01 / OBJ-01 INSPECTION RECORD / STEP-1A
-- ADDITIVE FOUNDATION — UP
--
-- ARTIFACT ONLY. This file is NOT applied to production in STEP-1A.
-- Absolutely additive: no ALTER/UPDATE/DELETE on safety_inspections or
-- safety_inspection_results. Base ledger is never mutated here.
--
-- Objects created:
--   table   safety_inspection_record_journal   (append-only change journal)
--   table   safety_inspection_command_receipt  (idempotency receipt)
--   func    fn_reject_inspection_record_mutation (trigger fn)
--   trig    trg_sirj_append_only / trg_sicr_append_only
--   func    fn_resolve_inspection_record(uuid)  (READ-ONLY effective record)
--   func    fn_apply_inspection_record_command(...) (SECURITY DEFINER txn)

BEGIN;

-- ==========================================================================
-- 1) JOURNAL TABLE (append-only)
-- ==========================================================================
CREATE TABLE IF NOT EXISTS public.safety_inspection_record_journal (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    inspection_id     uuid NOT NULL
                        REFERENCES public.safety_inspections(id) ON DELETE RESTRICT,
    revision          bigint NOT NULL,
    event_type        text NOT NULL,
    target_result_id  uuid NULL
                        REFERENCES public.safety_inspection_results(id) ON DELETE RESTRICT,
    before_snapshot   jsonb NOT NULL,
    after_snapshot    jsonb NOT NULL,
    changed_fields    text[] NOT NULL,
    actor_type        text NOT NULL,
    actor_id          uuid NULL,
    reason            text NULL,
    command_id        uuid NOT NULL,
    source            text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_sirj_revision_positive CHECK (revision > 0),
    CONSTRAINT chk_sirj_event_type CHECK (
        event_type IN (
            'INSPECTION_CORRECTION',
            'RESULT_CORRECTION',
            'STATUS_CHANGE',
            'INSPECTION_DEACTIVATION',
            'RESULT_DEACTIVATION'
        )
    ),
    CONSTRAINT chk_sirj_target_result CHECK (
        (event_type IN ('RESULT_CORRECTION','RESULT_DEACTIVATION') AND target_result_id IS NOT NULL)
        OR
        (event_type NOT IN ('RESULT_CORRECTION','RESULT_DEACTIVATION') AND target_result_id IS NULL)
    ),
    CONSTRAINT uq_sirj_inspection_revision UNIQUE (inspection_id, revision),
    CONSTRAINT uq_sirj_inspection_command  UNIQUE (inspection_id, command_id)
);

CREATE INDEX IF NOT EXISTS ix_sirj_inspection_rev
    ON public.safety_inspection_record_journal (inspection_id, revision);

-- ==========================================================================
-- 2) COMMAND RECEIPT TABLE (idempotency only)
-- ==========================================================================
CREATE TABLE IF NOT EXISTS public.safety_inspection_command_receipt (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    inspection_id     uuid NOT NULL
                        REFERENCES public.safety_inspections(id) ON DELETE RESTRICT,
    command_id        uuid NOT NULL,
    command_type      text NOT NULL,
    request_hash      text NOT NULL,
    request_payload   jsonb NOT NULL,
    response_snapshot jsonb NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_sicr_inspection_command UNIQUE (inspection_id, command_id)
);

-- ==========================================================================
-- 3) ACCESS CONTROL — no direct client/service mutation; RPC-only writes
-- ==========================================================================
ALTER TABLE public.safety_inspection_record_journal  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.safety_inspection_command_receipt ENABLE ROW LEVEL SECURITY;

-- Neutralize Supabase default grants; grant SELECT-only to service_role.
REVOKE ALL ON TABLE public.safety_inspection_record_journal  FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.safety_inspection_command_receipt FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.safety_inspection_record_journal  TO service_role;
GRANT SELECT ON TABLE public.safety_inspection_command_receipt TO service_role;
-- No policies for anon/authenticated -> RLS default deny. No INSERT/UPDATE/DELETE
-- grant to anyone: only the SECURITY DEFINER apply function (owner) writes.

-- ==========================================================================
-- 4) APPEND-ONLY GUARD (journal + receipt): deny UPDATE/DELETE even to owner
-- ==========================================================================
CREATE OR REPLACE FUNCTION public.fn_reject_inspection_record_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $reject$
BEGIN
    RAISE EXCEPTION 'append-only: % on % is not permitted', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'raise_exception';
END;
$reject$;

DROP TRIGGER IF EXISTS trg_sirj_append_only ON public.safety_inspection_record_journal;
CREATE TRIGGER trg_sirj_append_only
    BEFORE UPDATE OR DELETE ON public.safety_inspection_record_journal
    FOR EACH ROW EXECUTE FUNCTION public.fn_reject_inspection_record_mutation();

DROP TRIGGER IF EXISTS trg_sicr_append_only ON public.safety_inspection_command_receipt;
CREATE TRIGGER trg_sicr_append_only
    BEFORE UPDATE OR DELETE ON public.safety_inspection_command_receipt
    FOR EACH ROW EXECUTE FUNCTION public.fn_reject_inspection_record_mutation();

-- ==========================================================================
-- 5) RESOLVER — base ledger + journal folding -> current effective record
--    READ-ONLY. Returns the effective-record jsonb on success, or
--    {"error":"<CODE>","detail":...} on a fail-closed condition.
-- ==========================================================================
CREATE OR REPLACE FUNCTION public.fn_resolve_inspection_record(p_inspection_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $resolve$
DECLARE
    v_insp    public.safety_inspections%ROWTYPE;
    v_status  text;
    v_results jsonb := '[]'::jsonb;
    v_bad     text;
    v_record  jsonb;
    v_overall text;
    v_max_rev bigint := 0;
    v_seq_ok  boolean;
    v_after   jsonb;
BEGIN
    SELECT * INTO v_insp FROM public.safety_inspections WHERE id = p_inspection_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('error','INSPECTION_NOT_FOUND','detail',p_inspection_id::text);
    END IF;

    -- legacy inspection status normalization (STEP-1A contract)
    v_status := CASE
        WHEN v_insp.status_code IN ('in_progress','IN_PROGRESS') THEN 'IN_PROGRESS'
        WHEN v_insp.status_code IN ('completed','COMPLETED','ISSUE','HOLD') THEN 'COMPLETED'
        ELSE 'LEGACY_STATUS_UNRESOLVED'
    END;
    IF v_status = 'LEGACY_STATUS_UNRESOLVED' THEN
        RETURN jsonb_build_object('error','LEGACY_STATUS_UNRESOLVED','detail',COALESCE(v_insp.status_code,'(null)'));
    END IF;

    -- base results with result_code normalization; fail-closed on unresolved
    SELECT
        COALESCE(jsonb_agg(
            jsonb_build_object(
                'result_id', r.id,
                'is_active', true,
                'inspection_set_item_id', r.inspection_set_item_id,
                'item_name', r.item_name,
                'result_code', norm.code,
                'value_text', r.value_text,
                'value_number', r.value_number,
                'note', r.note,
                'checked_at', r.checked_at,
                'photo_url', r.photo_url,
                'photo_urls', r.photo_urls,
                'created_at', r.created_at
            )
            ORDER BY r.created_at NULLS LAST, r.id
        ), '[]'::jsonb),
        max(CASE WHEN norm.code = 'RESULT_CODE_UNRESOLVED' THEN r.id::text END)
    INTO v_results, v_bad
    FROM public.safety_inspection_results r
    CROSS JOIN LATERAL (
        SELECT CASE
            WHEN lower(COALESCE(r.result_code,'')) IN ('normal','ok','pass') THEN 'NORMAL'
            WHEN lower(COALESCE(r.result_code,'')) = 'hold' THEN 'HOLD'
            WHEN lower(COALESCE(r.result_code,'')) IN ('abnormal','bad','fail','issue','ng') THEN 'ABNORMAL'
            ELSE 'RESULT_CODE_UNRESOLVED'
        END AS code
    ) norm
    WHERE r.inspection_id = p_inspection_id;

    IF v_bad IS NOT NULL THEN
        RETURN jsonb_build_object('error','RESULT_CODE_UNRESOLVED','detail',v_bad);
    END IF;

    -- base effective record (revision 0, all active)
    v_record := jsonb_build_object(
        'inspection_id', v_insp.id,
        'revision', 0,
        'is_active', true,
        'inspection_status', v_status,
        'legacy_raw_status_code', v_insp.status_code,
        'assignment_id', v_insp.assignment_id,
        'asset_id', v_insp.asset_id,
        'inspector_id', v_insp.inspector_id,
        'inspection_date', v_insp.inspection_date,
        'submitted_by', v_insp.submitted_by,
        'factory_id', v_insp.factory_id,
        'results', v_results
    );

    -- journal folding: revision ASC contiguity; effective = latest after_snapshot
    SELECT max(revision) INTO v_max_rev
      FROM public.safety_inspection_record_journal WHERE inspection_id = p_inspection_id;
    IF v_max_rev IS NULL THEN
        v_max_rev := 0;
    ELSE
        SELECT (count(*) = v_max_rev
                AND min(revision) = 1
                AND max(revision) = v_max_rev
                AND count(DISTINCT revision) = v_max_rev)
          INTO v_seq_ok
          FROM public.safety_inspection_record_journal WHERE inspection_id = p_inspection_id;
        IF NOT COALESCE(v_seq_ok, false) THEN
            RETURN jsonb_build_object('error','JOURNAL_REVISION_GAP','detail',p_inspection_id::text);
        END IF;
        SELECT after_snapshot INTO v_after
          FROM public.safety_inspection_record_journal
         WHERE inspection_id = p_inspection_id AND revision = v_max_rev;
        v_record := v_after;
    END IF;

    -- overall_result from ACTIVE results only
    SELECT CASE
        WHEN count(*) FILTER (WHERE active) = 0 THEN NULL
        WHEN count(*) FILTER (WHERE active AND code = 'ABNORMAL') > 0 THEN 'ABNORMAL'
        WHEN count(*) FILTER (WHERE active AND code = 'HOLD') > 0 THEN 'HOLD'
        ELSE 'NORMAL'
    END
    INTO v_overall
    FROM (
        SELECT e->>'result_code' AS code,
               COALESCE((e->>'is_active')::boolean, true) AS active
        FROM jsonb_array_elements(v_record->'results') e
    ) s;

    v_record := jsonb_set(v_record, '{revision}', to_jsonb(v_max_rev));
    v_record := jsonb_set(v_record, '{overall_result}', COALESCE(to_jsonb(v_overall), 'null'::jsonb));
    RETURN v_record;
END;
$resolve$;

-- ==========================================================================
-- 6) APPLY COMMAND — single-transaction, revision-guarded, idempotent
-- ==========================================================================
CREATE OR REPLACE FUNCTION public.fn_apply_inspection_record_command(
    p_inspection_id     uuid,
    p_expected_revision bigint,
    p_command_id        uuid,
    p_event_type        text,
    p_target_result_id  uuid,
    p_changes           jsonb,
    p_actor_type        text,
    p_actor_id          uuid,
    p_reason            text,
    p_source            text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $apply$
DECLARE
    v_lock_id  uuid;
    v_req      jsonb;
    v_hash     text;
    v_receipt  public.safety_inspection_command_receipt%ROWTYPE;
    v_current  jsonb;
    v_cur_rev  bigint;
    v_before   jsonb;
    v_after    jsonb;
    v_changed  text[] := ARRAY[]::text[];
    v_new_rev  bigint;
    v_event_id uuid;
    v_target   jsonb;
    v_found    boolean;
    v_results  jsonb;
    v_key      text;
    v_allowed  text[];
    v_overall  text;
    v_resp     jsonb;
    v_to       text;
BEGIN
    v_req := jsonb_build_object(
        'expected_revision', p_expected_revision,
        'event_type', p_event_type,
        'target_result_id', p_target_result_id,
        'changes', p_changes,
        'actor_type', p_actor_type,
        'actor_id', p_actor_id,
        'reason', p_reason,
        'source', p_source
    );
    v_hash := md5(v_req::text);

    -- 1) lock base inspection row (locking read; not a data mutation)
    SELECT id INTO v_lock_id FROM public.safety_inspections WHERE id = p_inspection_id FOR UPDATE;
    -- 2) existence
    IF v_lock_id IS NULL THEN
        RETURN jsonb_build_object('ok',false,'error','INSPECTION_NOT_FOUND','detail',p_inspection_id::text);
    END IF;

    -- 3) receipt lookup
    SELECT * INTO v_receipt FROM public.safety_inspection_command_receipt
     WHERE inspection_id = p_inspection_id AND command_id = p_command_id;
    IF FOUND THEN
        IF v_receipt.request_hash = v_hash THEN
            RETURN v_receipt.response_snapshot;         -- 4-A idempotent replay
        ELSE
            RETURN jsonb_build_object('ok',false,'error','COMMAND_ID_REUSE_CONFLICT','detail',p_command_id::text);
        END IF;
    END IF;

    -- 5) resolve current effective state
    v_current := public.fn_resolve_inspection_record(p_inspection_id);
    IF v_current ? 'error' THEN
        RETURN jsonb_build_object('ok',false,'error', v_current->>'error','detail', v_current->>'detail');
    END IF;
    v_cur_rev := (v_current->>'revision')::bigint;

    -- 6) revision check
    IF p_expected_revision IS DISTINCT FROM v_cur_rev THEN
        RETURN jsonb_build_object('ok',false,'error','REVISION_CONFLICT',
            'detail', format('expected=%s current=%s', p_expected_revision, v_cur_rev));
    END IF;

    -- 7) inactive inspection guard (all events rejected once inactive)
    IF COALESCE((v_current->>'is_active')::boolean, true) = false THEN
        RETURN jsonb_build_object('ok',false,'error','INSPECTION_INACTIVE','detail',p_inspection_id::text);
    END IF;

    v_before := v_current;
    v_after  := v_current;

    -- 8/9/10) per-event validation + after_snapshot computation
    IF p_event_type = 'INSPECTION_CORRECTION' THEN
        IF p_changes IS NULL OR p_changes = '{}'::jsonb THEN
            RETURN jsonb_build_object('ok',false,'error','INVALID_CHANGE_FIELD','detail','empty');
        END IF;
        v_allowed := ARRAY['inspection_date','inspector_id'];
        FOR v_key IN SELECT jsonb_object_keys(p_changes) LOOP
            IF NOT (v_key = ANY(v_allowed)) THEN
                RETURN jsonb_build_object('ok',false,'error','INVALID_CHANGE_FIELD','detail',v_key);
            END IF;
            v_after   := jsonb_set(v_after, ARRAY[v_key], p_changes->v_key);
            v_changed := v_changed || ('inspection.' || v_key);
        END LOOP;

    ELSIF p_event_type = 'RESULT_CORRECTION' THEN
        IF p_target_result_id IS NULL THEN
            RETURN jsonb_build_object('ok',false,'error','INVALID_CHANGE_FIELD','detail','target_result_id required');
        END IF;
        SELECT e, true INTO v_target, v_found
          FROM jsonb_array_elements(v_before->'results') e
         WHERE e->>'result_id' = p_target_result_id::text
         LIMIT 1;
        IF NOT COALESCE(v_found, false) THEN
            RETURN jsonb_build_object('ok',false,'error','RESULT_NOT_FOUND','detail',p_target_result_id::text);
        END IF;
        IF p_changes IS NULL OR p_changes = '{}'::jsonb THEN
            RETURN jsonb_build_object('ok',false,'error','INVALID_CHANGE_FIELD','detail','empty');
        END IF;
        v_allowed := ARRAY['result_code','value_text','value_number','note','checked_at','photo_url','photo_urls'];
        IF (v_target->>'inspection_set_item_id') IS NULL THEN
            v_allowed := v_allowed || 'item_name';   -- legacy/manual row only
        END IF;
        FOR v_key IN SELECT jsonb_object_keys(p_changes) LOOP
            IF NOT (v_key = ANY(v_allowed)) THEN
                RETURN jsonb_build_object('ok',false,'error','INVALID_CHANGE_FIELD','detail',v_key);
            END IF;
        END LOOP;
        IF p_changes ? 'result_code'
           AND NOT ((p_changes->>'result_code') IN ('NORMAL','ABNORMAL','HOLD')) THEN
            RETURN jsonb_build_object('ok',false,'error','INVALID_CHANGE_FIELD',
                'detail','result_code:' || COALESCE(p_changes->>'result_code','null'));
        END IF;
        SELECT jsonb_agg(
            CASE WHEN e->>'result_id' = p_target_result_id::text THEN e || p_changes ELSE e END
        ) INTO v_results FROM jsonb_array_elements(v_before->'results') e;
        v_after := jsonb_set(v_after, '{results}', v_results);
        FOR v_key IN SELECT jsonb_object_keys(p_changes) LOOP
            v_changed := v_changed || ('results.' || p_target_result_id::text || '.' || v_key);
        END LOOP;

    ELSIF p_event_type = 'STATUS_CHANGE' THEN
        v_to := p_changes->>'to_status';
        IF v_to IS NULL THEN
            RETURN jsonb_build_object('ok',false,'error','INVALID_STATUS_TRANSITION','detail','to_status required');
        END IF;
        IF NOT ((v_before->>'inspection_status') = 'IN_PROGRESS' AND v_to = 'COMPLETED') THEN
            RETURN jsonb_build_object('ok',false,'error','INVALID_STATUS_TRANSITION',
                'detail', format('%s -> %s', v_before->>'inspection_status', v_to));
        END IF;
        v_after   := jsonb_set(v_after, '{inspection_status}', to_jsonb('COMPLETED'::text));
        v_changed := v_changed || 'inspection_status';

    ELSIF p_event_type = 'INSPECTION_DEACTIVATION' THEN
        -- already-inactive is handled by the step-7 guard (INSPECTION_INACTIVE)
        v_after   := jsonb_set(v_after, '{is_active}', to_jsonb(false));
        v_changed := v_changed || 'is_active';

    ELSIF p_event_type = 'RESULT_DEACTIVATION' THEN
        IF p_target_result_id IS NULL THEN
            RETURN jsonb_build_object('ok',false,'error','INVALID_CHANGE_FIELD','detail','target_result_id required');
        END IF;
        SELECT e, true INTO v_target, v_found
          FROM jsonb_array_elements(v_before->'results') e
         WHERE e->>'result_id' = p_target_result_id::text
         LIMIT 1;
        IF NOT COALESCE(v_found, false) THEN
            RETURN jsonb_build_object('ok',false,'error','RESULT_NOT_FOUND','detail',p_target_result_id::text);
        END IF;
        IF COALESCE((v_target->>'is_active')::boolean, true) = false THEN
            RETURN jsonb_build_object('ok',false,'error','RESULT_INACTIVE','detail',p_target_result_id::text);
        END IF;
        SELECT jsonb_agg(
            CASE WHEN e->>'result_id' = p_target_result_id::text
                 THEN jsonb_set(e, '{is_active}', to_jsonb(false)) ELSE e END
        ) INTO v_results FROM jsonb_array_elements(v_before->'results') e;
        v_after   := jsonb_set(v_after, '{results}', v_results);
        v_changed := v_changed || ('results.' || p_target_result_id::text || '.is_active');

    ELSE
        RETURN jsonb_build_object('ok',false,'error','INVALID_CHANGE_FIELD',
            'detail','unknown event_type ' || COALESCE(p_event_type,'null'));
    END IF;

    -- recompute overall_result in after from active results
    SELECT CASE
        WHEN count(*) FILTER (WHERE active) = 0 THEN NULL
        WHEN count(*) FILTER (WHERE active AND code = 'ABNORMAL') > 0 THEN 'ABNORMAL'
        WHEN count(*) FILTER (WHERE active AND code = 'HOLD') > 0 THEN 'HOLD'
        ELSE 'NORMAL'
    END
    INTO v_overall
    FROM (
        SELECT e->>'result_code' AS code,
               COALESCE((e->>'is_active')::boolean, true) AS active
        FROM jsonb_array_elements(v_after->'results') e
    ) s;

    v_new_rev := v_cur_rev + 1;
    v_after := jsonb_set(v_after, '{revision}', to_jsonb(v_new_rev));
    v_after := jsonb_set(v_after, '{overall_result}', COALESCE(to_jsonb(v_overall), 'null'::jsonb));

    -- 12) journal append
    INSERT INTO public.safety_inspection_record_journal(
        inspection_id, revision, event_type, target_result_id,
        before_snapshot, after_snapshot, changed_fields,
        actor_type, actor_id, reason, command_id, source
    ) VALUES (
        p_inspection_id, v_new_rev, p_event_type, p_target_result_id,
        v_before, v_after, v_changed,
        p_actor_type, p_actor_id, p_reason, p_command_id, p_source
    ) RETURNING id INTO v_event_id;

    -- 13) response
    v_resp := jsonb_build_object('ok',true,'data', jsonb_build_object(
        'inspection_id', p_inspection_id,
        'revision', v_new_rev,
        'event_id', v_event_id,
        'command_id', p_command_id
    ));

    -- 14) receipt append (same transaction)
    INSERT INTO public.safety_inspection_command_receipt(
        inspection_id, command_id, command_type, request_hash, request_payload, response_snapshot
    ) VALUES (
        p_inspection_id, p_command_id, p_event_type, v_hash, v_req, v_resp
    );

    -- 15) return
    RETURN v_resp;
END;
$apply$;

-- ==========================================================================
-- 7) FUNCTION EXECUTE GRANTS — backend (service_role) only
-- ==========================================================================
REVOKE ALL ON FUNCTION public.fn_resolve_inspection_record(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_resolve_inspection_record(uuid) TO service_role;

REVOKE ALL ON FUNCTION public.fn_apply_inspection_record_command(
    uuid, bigint, uuid, text, uuid, jsonb, text, uuid, text, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_apply_inspection_record_command(
    uuid, bigint, uuid, text, uuid, jsonb, text, uuid, text, text
) TO service_role;

COMMIT;
