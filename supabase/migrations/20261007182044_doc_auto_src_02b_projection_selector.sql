-- AUTO-SRC-02B: Deterministic Projection Selector
-- inspection_set_projection_binding (child table for explicit projection specialization)
-- document_equipment_projection_map (canonical equipment code → EQUIP doc_detail, GAP-02C resolver)
-- fn_create_worker_inspection_record: asset_id carry from v_sched (v1.1)

BEGIN;

-- ============================================================
-- TABLE 1: inspection_set_projection_binding
-- ============================================================
CREATE TABLE IF NOT EXISTS public.inspection_set_projection_binding (
    id                  uuid        NOT NULL DEFAULT gen_random_uuid(),
    inspection_set_id   uuid        NOT NULL REFERENCES public.inspection_sets(id) ON DELETE RESTRICT,
    projection_type     text        NOT NULL,
    projection_detail   text,
    binding_source      text        NOT NULL,
    is_active           boolean     NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id)
);

-- unique: one row per (inspection_set, projection_type, detail-or-placeholder)
CREATE UNIQUE INDEX IF NOT EXISTS inspection_set_projection_binding_unique_idx
    ON public.inspection_set_projection_binding
        (inspection_set_id, projection_type, COALESCE(projection_detail, '-'));

CREATE INDEX IF NOT EXISTS inspection_set_projection_binding_set_id_idx
    ON public.inspection_set_projection_binding (inspection_set_id);

ALTER TABLE public.inspection_set_projection_binding ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.inspection_set_projection_binding FROM anon;
REVOKE ALL ON TABLE public.inspection_set_projection_binding FROM authenticated;
REVOKE ALL ON TABLE public.inspection_set_projection_binding FROM service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.inspection_set_projection_binding TO service_role;

-- ============================================================
-- TABLE 2: document_equipment_projection_map (GAP-02C resolver)
-- 40-row seed: 35 RESOLVED + 5 UNRESOLVED
-- Source: system_codes(category=equipment_type) + WO-DOC-AUTO-SRC-02B Section 16-18
-- ============================================================
CREATE TABLE IF NOT EXISTS public.document_equipment_projection_map (
    equipment_type_code text        NOT NULL,
    projection_detail   text,
    mapping_status      text        NOT NULL,
    mapping_basis       text        NOT NULL,
    note                text,
    is_active           boolean     NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (equipment_type_code)
);

ALTER TABLE public.document_equipment_projection_map ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.document_equipment_projection_map FROM anon;
REVOKE ALL ON TABLE public.document_equipment_projection_map FROM authenticated;
REVOKE ALL ON TABLE public.document_equipment_projection_map FROM service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.document_equipment_projection_map TO service_role;

-- ============================================================
-- SEED: document_equipment_projection_map v1
-- GPT-FROZEN mapping per WO-DOC-AUTO-SRC-02B Sections 16-18
-- 35 RESOLVED codes + 5 UNRESOLVED(NULL)
-- ELEC: 001-010, MACHINE: 011/012/013/016/017/018/023/024/038
-- BOILER: 014, REFRIG: 019/020/039, CRANE: 021/022
-- ELEV: 025/026, GAS: 027/028, HAZMAT: 029/030, FIRE: 031/032/033/034
-- UNRESOLVED: 015/035/036/037/040
-- ============================================================
INSERT INTO public.document_equipment_projection_map
    (equipment_type_code, projection_detail, mapping_status, mapping_basis, note)
VALUES
    -- ELEC (변압기, 차단기, 피뢰기, 전력퓨즈, 전선케이블, 배전반, 발전기, 전동기, 인버터, 비상발전기)
    ('001', 'ELEC', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '변압기'),
    ('002', 'ELEC', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '차단기'),
    ('003', 'ELEC', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '피뢰기'),
    ('004', 'ELEC', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '전력퓨즈'),
    ('005', 'ELEC', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '전선케이블'),
    ('006', 'ELEC', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '배전반'),
    ('007', 'ELEC', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '발전기'),
    ('008', 'ELEC', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '전동기'),
    ('009', 'ELEC', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '인버터'),
    ('010', 'ELEC', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '비상발전기'),
    -- MACHINE (펌프, 압축기, 열교환기, 반응기, 혼합기, 원심분리기, 프레스, 컨베이어, 압력용기)
    ('011', 'MACHINE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '펌프'),
    ('012', 'MACHINE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '압축기'),
    ('013', 'MACHINE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '열교환기'),
    ('016', 'MACHINE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '반응기'),
    ('017', 'MACHINE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '혼합기'),
    ('018', 'MACHINE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '원심분리기'),
    ('023', 'MACHINE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '프레스'),
    ('024', 'MACHINE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '컨베이어'),
    ('038', 'MACHINE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '압력용기'),
    -- BOILER
    ('014', 'BOILER', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '보일러'),
    -- REFRIG (냉동기, 냉각탑, 냉동창고)
    ('019', 'REFRIG', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '냉동기'),
    ('020', 'REFRIG', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '냉각탑'),
    ('039', 'REFRIG', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '냉동창고'),
    -- CRANE (크레인, 호이스트)
    ('021', 'CRANE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '크레인'),
    ('022', 'CRANE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '호이스트'),
    -- ELEV (승강기, 에스컬레이터)
    ('025', 'ELEV', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '승강기'),
    ('026', 'ELEV', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '에스컬레이터'),
    -- GAS (가스저장탱크, 가스배관)
    ('027', 'GAS', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '가스저장탱크'),
    ('028', 'GAS', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '가스배관'),
    -- HAZMAT (화학물질탱크, 폐수처리설비)
    ('029', 'HAZMAT', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '화학물질탱크'),
    ('030', 'HAZMAT', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '폐수처리설비'),
    -- FIRE (스프링클러, 자동화재탐지, 소화기, 소화전)
    ('031', 'FIRE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '스프링클러'),
    ('032', 'FIRE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '자동화재탐지'),
    ('033', 'FIRE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '소화기'),
    ('034', 'FIRE', 'RESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', '소화전'),
    -- UNRESOLVED (no canonical AUTO EQUIP doc_detail mapping; fail-closed)
    ('015', NULL, 'UNRESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', NULL),
    ('035', NULL, 'UNRESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', NULL),
    ('036', NULL, 'UNRESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', NULL),
    ('037', NULL, 'UNRESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', NULL),
    ('040', NULL, 'UNRESOLVED', 'WO-DOC-AUTO-SRC-02B-v1', NULL)
ON CONFLICT (equipment_type_code) DO NOTHING;

-- ============================================================
-- FUNCTION UPDATE: fn_create_worker_inspection_record v1.1
-- Only change: Step 8 INSERT adds asset_id = v_sched.asset_id
-- v_sched is already locked (FOR UPDATE, Step 3) — no extra query needed
-- ============================================================
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

    -- 8) base header INSERT (v1.1: asset_id carried from v_sched — locked in step 3)
    INSERT INTO public.safety_inspections
        (id, assignment_id, inspector_id, inspection_date, status_code, factory_id, asset_id)
    VALUES
        (v_inspection_id, p_schedule_id, p_inspector_id, p_submitted_at, 'COMPLETED', p_factory_id,
         v_sched.asset_id);

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

REVOKE ALL ON FUNCTION public.fn_create_worker_inspection_record(uuid, text, text, uuid, uuid, uuid, timestamptz, jsonb, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_create_worker_inspection_record(uuid, text, text, uuid, uuid, uuid, timestamptz, jsonb, jsonb) TO service_role;

COMMIT;
