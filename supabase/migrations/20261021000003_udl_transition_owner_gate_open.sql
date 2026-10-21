-- ============================================================
-- Migration: 20261021000003_udl_transition_owner_gate_open.sql
-- WO-TAI-DOC-WP03B-SIMPLIFY-001 작업 B — Owner 승인 경로 활성화
-- WO-TAI-DOC-WP03B-FINAL-GATE-001 — review_note 검토 근거 append
--
-- 변경: fn_udl_transition 4-param → 6-param
--        p_final_relation_type (5번): APPROVE 시 관계 유형 재지정
--        p_review_note          (6번): PROPOSED→UNDER_REVIEW 시 evidence_note에 append
--      Owner 결정 전환 활성화 (OWNER_GATE_BLOCKED 제거)
--      API 레이어가 Owner 신원 + 검토 근거 존재 여부를 확인한 후 호출.
--
-- 운영 적용: 별도 Owner 승인 필요 (작업 A 운영 확인 후)
-- ============================================================

-- 기존 4-param 버전 제거 (6-param 버전으로 교체)
DROP FUNCTION IF EXISTS public.fn_udl_transition(TEXT, UUID, TEXT, TEXT);

CREATE OR REPLACE FUNCTION public.fn_udl_transition(
    p_actor_id            TEXT,
    p_link_id             UUID,
    p_new_state           TEXT,
    p_owner_approval_ref  TEXT DEFAULT NULL,
    p_final_relation_type TEXT DEFAULT NULL,
    p_review_note         TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row  public.unified_document_link;
    v_old  public.unified_document_link;
    v_err  TEXT;
BEGIN
    IF p_actor_id IS NULL OR trim(p_actor_id) = '' THEN
        RETURN json_build_object(
            'ok',     false,
            'error',  'ACTOR_REQUIRED',
            'detail', 'p_actor_id must not be null or empty'
        );
    END IF;

    -- PROPOSED→UNDER_REVIEW 시 p_review_note 공백 거부 (API 레이어 방어 이중화)
    IF p_new_state = 'UNDER_REVIEW' AND trim(COALESCE(p_review_note, '')) = '' THEN
        RETURN json_build_object(
            'ok',     false,
            'error',  'REVIEW_NOTE_REQUIRED',
            'detail', 'p_review_note must not be null or blank for PROPOSED→UNDER_REVIEW'
        );
    END IF;

    PERFORM set_config('app.actor', p_actor_id, true);

    SELECT * INTO v_old FROM public.unified_document_link WHERE id = p_link_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN json_build_object(
            'ok',     false,
            'error',  'LINK_NOT_FOUND',
            'detail', format('Link %s not found', p_link_id)
        );
    END IF;

    BEGIN
        IF v_old.review_state = 'PROPOSED' AND p_new_state = 'UNDER_REVIEW' THEN
            UPDATE public.unified_document_link
            SET review_state = 'UNDER_REVIEW',
                reviewed_by  = p_actor_id,
                reviewed_at  = now(),
                evidence_note = evidence_note
                    || E'\n[REVIEWED:' || p_actor_id
                    || ':' || to_char(now(), 'YYYYMMDD"T"HH24MISS"Z"') || '] '
                    || COALESCE(trim(p_review_note), '')
            WHERE id = p_link_id
            RETURNING * INTO v_row;

        ELSIF v_old.review_state = 'UNDER_REVIEW' AND p_new_state = 'APPROVED' THEN
            UPDATE public.unified_document_link
            SET review_state       = 'APPROVED',
                reviewed_by        = p_actor_id,
                reviewed_at        = now(),
                owner_approval_ref = p_owner_approval_ref,
                relation_type      = COALESCE(p_final_relation_type, relation_type)
            WHERE id = p_link_id
            RETURNING * INTO v_row;

        ELSIF p_new_state = 'REJECTED'
              AND v_old.review_state IN ('PROPOSED', 'UNDER_REVIEW') THEN
            UPDATE public.unified_document_link
            SET review_state = 'REJECTED'
            WHERE id = p_link_id
            RETURNING * INTO v_row;

        ELSIF p_new_state = 'RETIRED'
              AND v_old.review_state = 'APPROVED' THEN
            UPDATE public.unified_document_link
            SET review_state       = 'RETIRED',
                owner_approval_ref = p_owner_approval_ref
            WHERE id = p_link_id
            RETURNING * INTO v_row;

        ELSIF p_new_state = 'RETIRED'
              AND v_old.review_state = 'REJECTED' THEN
            UPDATE public.unified_document_link
            SET review_state = 'RETIRED'
            WHERE id = p_link_id
            RETURNING * INTO v_row;

        ELSE
            RETURN json_build_object(
                'ok',     false,
                'error',  'INVALID_TRANSITION',
                'detail', format(
                    'Cannot transition from %s to %s.',
                    v_old.review_state, p_new_state
                )
            );
        END IF;

    EXCEPTION
        WHEN raise_exception THEN
            GET STACKED DIAGNOSTICS v_err = MESSAGE_TEXT;
            RETURN json_build_object(
                'ok',     false,
                'error',  'GUARD_REJECTED',
                'detail', v_err
            );
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_err = MESSAGE_TEXT;
            RETURN json_build_object(
                'ok',     false,
                'error',  'CONSTRAINT_VIOLATION',
                'detail', v_err
            );
    END;

    RETURN json_build_object(
        'ok',   true,
        'data', row_to_json(v_row)
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.fn_udl_transition(TEXT, UUID, TEXT, TEXT, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.fn_udl_transition(TEXT, UUID, TEXT, TEXT, TEXT, TEXT) TO service_role;
