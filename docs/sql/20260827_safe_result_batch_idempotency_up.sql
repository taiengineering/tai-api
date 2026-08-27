-- WP-INSPECTION-OPS / OBJ-01 INSPECTION RECORD / DEBT-W3-02
-- SAFE RESULT INITIAL-BATCH IDEMPOTENCY - UP
--
-- Makes POST /inspection/result/{inspection_id}/items DB-level race-safe and
-- idempotent WITHOUT a client idempotency key, a receipt table, or a per-item
-- unique index. The logical identity of a SAFE initial result batch is simply the
-- inspection_id (schedule cardinality is already 0..1, so an inspection has at most
-- one initial SAFE result batch).
--
-- fn_record_safe_inspection_result_batch(p_inspection_id, p_results):
--   1. validate incoming array + canonical result_code (NORMAL/ABNORMAL/HOLD)
--   2. lock the parent inspection FOR UPDATE (serialize concurrent submissions)
--   3. existing results = 0  -> INSERT the batch (single checked_at)  -> CREATED
--   4. existing results > 0  -> canonical, order-independent comparison of the
--        incoming batch vs the stored W3 batch:
--          equal   -> INSERT 0 -> REPLAY
--          differ  -> RESULT_INITIAL_BATCH_CONFLICT (base INSERT 0)
--
-- Compared business fields (W3 shape only): inspection_set_item_id, result_code,
-- note (missing -> ''), photo_url (missing/JSON-null -> NULL). id/checked_at/
-- created_at are server-generated and excluded. Rows are compared as STRUCTURED
-- jsonb tuples (jsonb_build_array), so no text separator can ever collide and NULL
-- stays distinct from ''. If any stored row for the inspection carries content W3
-- never writes (item_name / value_text / value_number / a non-empty photo_urls),
-- it is Worker-shaped and the request fails closed with the same conflict rather
-- than being mistaken for a W3 replay. An empty photo_urls ('[]', the column
-- default that W3 rows carry) is W3-compatible and does NOT trip the guard.
--
-- Physical-immutability compatible: INSERT-only. Later business change flows only
-- through the journal (RESULT_CORRECTION / RESULT_DEACTIVATION); this RPC never
-- UPDATEs or DELETEs a base row.

BEGIN;

CREATE OR REPLACE FUNCTION public.fn_record_safe_inspection_result_batch(
    p_inspection_id uuid,
    p_results       jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_insp        record;
    v_count       integer;
    v_nonw3       integer;
    v_n           integer;
    v_in_keys     jsonb[];
    v_ex_keys     jsonb[];
    v_checked_at  timestamptz;
    v_elem        jsonb;
    v_code        text;
BEGIN
    -- 1) input validation
    IF p_inspection_id IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'INVALID_RESULT_INPUT',
                                  'detail', 'inspection_id required');
    END IF;
    IF p_results IS NULL OR jsonb_typeof(p_results) <> 'array' OR jsonb_array_length(p_results) = 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'EMPTY_RESULTS', 'detail', 'results required');
    END IF;
    v_n := jsonb_array_length(p_results);

    -- 2) canonical result_code validation (service already normalizes to canonical)
    FOR v_elem IN SELECT value FROM jsonb_array_elements(p_results) AS value
    LOOP
        IF jsonb_typeof(v_elem->'result_code') <> 'string' THEN
            RETURN jsonb_build_object('ok', false, 'error', 'RESULT_CODE_UNRESOLVED',
                                      'detail', 'result_code not a string');
        END IF;
        v_code := v_elem->>'result_code';
        IF v_code NOT IN ('NORMAL','ABNORMAL','HOLD') THEN
            RETURN jsonb_build_object('ok', false, 'error', 'RESULT_CODE_UNRESOLVED',
                                      'detail', coalesce(v_code, ''));
        END IF;
    END LOOP;

    -- 3) parent inspection lock (serialize per inspection)
    SELECT id INTO v_insp
    FROM public.safety_inspections
    WHERE id = p_inspection_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'INSPECTION_NOT_FOUND',
                                  'detail', p_inspection_id::text);
    END IF;

    -- 4) existing result cardinality (under lock)
    SELECT count(*) INTO v_count
    FROM public.safety_inspection_results
    WHERE inspection_id = p_inspection_id;

    IF v_count = 0 THEN
        -- 4-A) fresh: INSERT the batch with a single transaction-time checked_at
        v_checked_at := now();
        INSERT INTO public.safety_inspection_results
            (inspection_id, inspection_set_item_id, result_code, note, photo_url, checked_at)
        SELECT
            p_inspection_id,
            nullif(e->>'inspection_set_item_id', '')::uuid,
            e->>'result_code',
            coalesce(e->>'note', ''),
            e->>'photo_url',
            v_checked_at
        FROM jsonb_array_elements(p_results) AS e;
        RETURN jsonb_build_object('ok', true, 'mode', 'CREATED', 'count', v_n,
                                  'data', jsonb_build_object('inspection_id', p_inspection_id, 'created', v_n));
    END IF;

    -- 4-B) existing present: any Worker-shaped row => fail closed (not a W3 replay).
    -- An empty photo_urls ('[]') is the W3 default and is NOT Worker content.
    SELECT count(*) INTO v_nonw3
    FROM public.safety_inspection_results
    WHERE inspection_id = p_inspection_id
      AND (item_name IS NOT NULL OR value_text IS NOT NULL
           OR value_number IS NOT NULL
           OR (photo_urls IS NOT NULL AND photo_urls <> '[]'::jsonb));
    IF v_nonw3 > 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'RESULT_INITIAL_BATCH_CONFLICT',
                                  'detail', 'existing results are not W3-shaped');
    END IF;

    -- canonical, order-independent multiset of STRUCTURED tuples. jsonb_build_array
    -- avoids any text-separator collision and keeps NULL distinct from '' (a missing
    -- or JSON-null photo_url is NULL, never the empty string).
    SELECT array_agg(t ORDER BY t) INTO v_in_keys
    FROM (
        SELECT jsonb_build_array(
                   nullif(e->>'inspection_set_item_id', '')::uuid,
                   e->>'result_code',
                   coalesce(e->>'note', ''),
                   CASE
                       WHEN NOT (e ? 'photo_url') OR jsonb_typeof(e->'photo_url') = 'null'
                       THEN NULL
                       ELSE e->>'photo_url'
                   END
               ) AS t
        FROM jsonb_array_elements(p_results) AS e
    ) s;

    SELECT array_agg(t ORDER BY t) INTO v_ex_keys
    FROM (
        SELECT jsonb_build_array(
                   inspection_set_item_id,
                   result_code,
                   coalesce(note, ''),
                   photo_url
               ) AS t
        FROM public.safety_inspection_results
        WHERE inspection_id = p_inspection_id
    ) s;

    IF v_in_keys IS NOT DISTINCT FROM v_ex_keys THEN
        -- same batch: replay, INSERT 0, external count = N
        RETURN jsonb_build_object('ok', true, 'mode', 'REPLAY', 'count', v_n,
                                  'data', jsonb_build_object('inspection_id', p_inspection_id, 'created', v_n));
    ELSE
        RETURN jsonb_build_object('ok', false, 'error', 'RESULT_INITIAL_BATCH_CONFLICT',
                                  'detail', 'incoming batch differs from stored batch');
    END IF;
END
$fn$;

REVOKE ALL ON FUNCTION public.fn_record_safe_inspection_result_batch(uuid, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_record_safe_inspection_result_batch(uuid, jsonb) TO service_role;

COMMIT;
