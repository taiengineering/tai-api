-- ============================================================
-- Migration: 20261021000001_udl_write_rpc.sql
-- WO-TAI-DOC-WP03B-IMPLEMENT-001 + CORR-001 + CORR-002
--
-- 목적: unified_document_link 쓰기 경로 RPC 함수
--   fn_udl_propose    — PROPOSED 행 신규 생성
--   fn_udl_transition — 상태 전환 (허용 전환만 처리)
--
-- OWNER_GATE_BLOCKED 정책 (CORR-001/002):
--   Owner 신원·승인 증거 SoT가 구축되기 전까지
--   Owner 결정이 필요한 모든 전환은 DB 레벨에서도 차단한다.
--   허용 전환: PROPOSED → UNDER_REVIEW (심사 접수)만 허용.
--   차단 전환: →REJECTED, →APPROVED, →RETIRED 전부 OWNER_GATE_BLOCKED.
--
-- DB 쓰기: RPC 함수 정의만 (테이블/스키마 변경 없음)
-- 의존: 20261020000007_unified_document_link_foundation.sql
-- Source/schema mutations: 0 (함수 정의만)
-- ============================================================

-- ─────────────────────────────────────────────────────────────
-- 1. fn_udl_propose
--    PROPOSED 상태로 신규 unified_document_link 행 생성.
--    audit 트리거가 app.actor 세션 변수를 읽으므로
--    INSERT 전에 set_config로 actor를 바인딩한다.
--    NULL 또는 빈 p_actor_id는 거부한다.
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.fn_udl_propose(
    p_actor_id          TEXT,
    p_saas_catalog_id   UUID,
    p_reference_form_id UUID,
    p_relation_type     TEXT,
    p_evidence_note     TEXT
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_row  public.unified_document_link;
    v_err  TEXT;
BEGIN
    -- CORR-002: NULL/빈 actor_id 거부 — 'system' 자동 대체 제거
    IF p_actor_id IS NULL OR trim(p_actor_id) = '' THEN
        RETURN json_build_object(
            'ok',     false,
            'error',  'ACTOR_REQUIRED',
            'detail', 'p_actor_id must not be null or empty'
        );
    END IF;

    PERFORM set_config('app.actor', p_actor_id, true);

    BEGIN
        INSERT INTO public.unified_document_link(
            saas_catalog_id,
            reference_form_id,
            relation_type,
            review_state,
            evidence_note
        )
        VALUES (
            p_saas_catalog_id,
            p_reference_form_id,
            p_relation_type,
            'PROPOSED',
            p_evidence_note
        )
        RETURNING * INTO v_row;
    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS v_err = MESSAGE_TEXT;
            RETURN json_build_object(
                'ok',     false,
                'error',  'DUPLICATE_ACTIVE_PAIR',
                'detail', v_err
            );
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_err = MESSAGE_TEXT;
            RETURN json_build_object(
                'ok',     false,
                'error',  'CONSTRAINT_VIOLATION',
                'detail', v_err
            );
        WHEN raise_exception THEN
            GET STACKED DIAGNOSTICS v_err = MESSAGE_TEXT;
            RETURN json_build_object(
                'ok',     false,
                'error',  'GUARD_REJECTED',
                'detail', v_err
            );
    END;

    RETURN json_build_object(
        'ok',   true,
        'data', row_to_json(v_row)
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.fn_udl_propose(TEXT, UUID, UUID, TEXT, TEXT) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.fn_udl_propose(TEXT, UUID, UUID, TEXT, TEXT) TO service_role;

-- ─────────────────────────────────────────────────────────────
-- 2. fn_udl_transition
--    허용된 상태 전환을 수행한다.
--    허용 전환 (CORR-002 적용):
--      PROPOSED → UNDER_REVIEW  (심사 접수) — 허용
--    차단 전환 (OWNER_GATE_BLOCKED):
--      PROPOSED/UNDER_REVIEW → REJECTED  — Owner 결정, 차단
--      UNDER_REVIEW          → APPROVED  — Owner 결정, 차단
--      APPROVED              → RETIRED   — Owner 결정, 차단
--      REJECTED              → RETIRED   — Owner 결정, 차단
--    NULL/빈 p_actor_id 거부.
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.fn_udl_transition(
    p_actor_id           TEXT,
    p_link_id            UUID,
    p_new_state          TEXT,
    p_owner_approval_ref TEXT DEFAULT NULL
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
    -- CORR-002: NULL/빈 actor_id 거부 — 'system' 자동 대체 제거
    IF p_actor_id IS NULL OR trim(p_actor_id) = '' THEN
        RETURN json_build_object(
            'ok',     false,
            'error',  'ACTOR_REQUIRED',
            'detail', 'p_actor_id must not be null or empty'
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
        -- 허용 전환: PROPOSED → UNDER_REVIEW
        IF v_old.review_state = 'PROPOSED' AND p_new_state = 'UNDER_REVIEW' THEN
            UPDATE public.unified_document_link
            SET review_state = 'UNDER_REVIEW',
                reviewed_by  = p_actor_id,
                reviewed_at  = now()
            WHERE id = p_link_id
            RETURNING * INTO v_row;

        -- CORR-002: Owner 결정 전환 — OWNER_GATE_BLOCKED
        ELSIF p_new_state IN ('REJECTED', 'APPROVED', 'RETIRED') THEN
            RETURN json_build_object(
                'ok',     false,
                'error',  'OWNER_GATE_BLOCKED',
                'detail', format(
                    'Transition %s→%s is blocked: Owner identity and approval evidence SoT '
                    'are not established. Only PROPOSED→UNDER_REVIEW is permitted.',
                    v_old.review_state, p_new_state
                )
            );

        ELSE
            RETURN json_build_object(
                'ok',     false,
                'error',  'INVALID_TRANSITION',
                'detail', format(
                    'Cannot transition from %s to %s. '
                    'Only PROPOSED→UNDER_REVIEW is permitted.',
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

REVOKE EXECUTE ON FUNCTION public.fn_udl_transition(TEXT, UUID, TEXT, TEXT) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.fn_udl_transition(TEXT, UUID, TEXT, TEXT) TO service_role;

-- ─────────────────────────────────────────────────────────────
-- ROLLBACK (스테이징 환경에서만; 프로덕션 롤백은 Owner 서면 승인 필요):
--
-- DROP FUNCTION IF EXISTS public.fn_udl_transition(TEXT, UUID, TEXT, TEXT);
-- DROP FUNCTION IF EXISTS public.fn_udl_propose(TEXT, UUID, UUID, TEXT, TEXT);
-- ─────────────────────────────────────────────────────────────
