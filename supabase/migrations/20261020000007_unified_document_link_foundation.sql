-- ============================================================
-- Migration: 20261020000007_unified_document_link_foundation.sql
-- WO-TAI-DOC-UNIFIED-LINK-MIGRATION-CORR-001 — CORR-B 버전 충돌 해소
--
-- Source DDL: WP01_UNIFIED_CATALOG/g3_schema_gate/unified_document_link_PROPOSED_DO_NOT_APPLY.sql
-- Source SHA256: 166954ea7ce1f54544d1444a89095663ce20ff91148e6823b8479b959e9b3b32
-- DESIGN IV: 5라운드 완료 (CORR-001 / CORR-002 / CORR-003 / FINAL-AUDIT-GUARD / PREAPPLY-CLOSE)
--
-- 목적: SAAS document_forms ↔ reference_forms 관계 레지스트리
-- 상태: MIGRATION PENDING — Owner 스테이징 승인 후 적용
--
-- DB 쓰기: 이 파일 작성 단계에서 0건 (로컬 테스트 전용)
-- 스테이징 적용: Owner 별도 승인 필요
-- 운영 적용: BLOCKED
--
-- FK 타겟 확인:
--   - document_forms.id  : UUID PK (확인: 20261006193021_catalog_schema_binding_b1.sql)
--   - reference_forms.id : UUID PK (확인: 20261011120000_reference_forms_core.sql)
-- ============================================================

-- ─────────────────────────────────────────────────────────────
-- 1. MAIN TABLE: unified_document_link
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.unified_document_link (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- FK: SAAS 카탈로그 문서 (document_forms.id)
    -- ON DELETE RESTRICT: 원본 삭제 시 링크 먼저 RETIRED 처리 필요
    saas_catalog_id     UUID        NOT NULL
                                    REFERENCES public.document_forms(id) ON DELETE RESTRICT,

    -- FK: 참고서식 (reference_forms.id)
    reference_form_id   UUID        NOT NULL
                                    REFERENCES public.reference_forms(id) ON DELETE RESTRICT,

    -- 관계 유형 (불변: INSERT 후 APPROVED 전까지만 수정 가능; APPROVED 후 immutability 트리거가 차단)
    -- RELATED_FORM: 두 문서는 별개 canonical identity 유지 (병합 없음)
    -- SAME_DOCUMENT_VERIFIED + review_state=APPROVED 조합만 카탈로그 병합 표시
    relation_type       TEXT        NOT NULL CHECK (relation_type IN (
                            'SAME_DOCUMENT_VERIFIED',
                            'SAME_DOCUMENT_CANDIDATE',
                            'RELATED_FORM',
                            'SUPERSEDES',
                            'SUPERSEDED_BY'
                        )),

    -- 검토 상태 (상태 전환 규칙: LINK_SCHEMA_APPROVAL_AUDIT_CONTRACT.md Section 1 참조)
    -- INSERT는 PROPOSED만 허용 (insert_guard 트리거가 강제)
    review_state        TEXT        NOT NULL DEFAULT 'PROPOSED' CHECK (review_state IN (
                            'PROPOSED',
                            'UNDER_REVIEW',
                            'APPROVED',
                            'REJECTED',
                            'RETIRED'
                        )),

    -- 증거 노트: match_basis, similarity_score, GPT 검토 결과 등
    -- 이 컬럼은 서버 측에서만 노출 (anon/authenticated에 직접 노출 금지)
    evidence_note       TEXT        NOT NULL,

    -- 검토자 (Owner 또는 위임받은 담당자)
    reviewed_by         TEXT,
    reviewed_at         TIMESTAMPTZ,

    -- Owner 승인 참조: WO 식별자 (예: WO-TAI-DOC-UNIFIED-LINK-APPROVE-001)
    -- 문자열 존재만으로 Owner 승인이 증명되지 않음
    -- 서버 측 API가 이 값의 유효성을 WO 레코드 또는 별도 승인 시스템에서 검증해야 함
    -- APPROVED→RETIRED 전환 시에는 기존 값과 다른 새 값 필요 (state_guard가 강제)
    owner_approval_ref  TEXT,

    -- 낙관적 버전: UPDATE마다 fn_udl_version_bump 트리거가 자동 증가
    version             INTEGER     NOT NULL DEFAULT 1,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- [P0-2 CORR-001] SAME_DOCUMENT_CANDIDATE는 APPROVED 상태가 될 수 없음
    -- (검증 미완료 후보를 승인으로 처리하는 것을 DB 레벨에서 차단)
    CONSTRAINT no_candidate_approval CHECK (
        NOT (relation_type = 'SAME_DOCUMENT_CANDIDATE' AND review_state = 'APPROVED')
    ),

    -- APPROVED 전환 조건: reviewed_by + reviewed_at + owner_approval_ref 모두 필요
    -- owner_approval_ref의 유효성은 DB가 아닌 서버 측 API에서 검증
    CONSTRAINT approval_requires_owner_gate CHECK (
        review_state != 'APPROVED'
        OR (reviewed_by IS NOT NULL
            AND reviewed_at IS NOT NULL
            AND owner_approval_ref IS NOT NULL)
    )

    -- [P0-4 CORR-001] UNIQUE 제약 제거 — 조건부 UNIQUE INDEX(uq_udl_active_pair)로 대체
    -- REJECTED/RETIRED 쌍의 재제안을 허용하기 위함 (아래 Section 10 참조)
);

-- ─────────────────────────────────────────────────────────────
-- 2. INSERT GUARD TRIGGER (P0-1 CORR-001 신규)
-- 최초 INSERT는 반드시 PROPOSED 상태만 허용
-- SECURITY DEFINER + search_path 고정으로 schema injection 방지
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.fn_udl_insert_guard()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF NEW.review_state != 'PROPOSED' THEN
        RAISE EXCEPTION
            'New unified_document_link rows must start in PROPOSED state. Got: %. '
            'Direct insertion in APPROVED/UNDER_REVIEW/REJECTED/RETIRED is not permitted.',
            NEW.review_state;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.fn_udl_insert_guard() FROM PUBLIC;

CREATE TRIGGER trg_udl_insert_guard
    BEFORE INSERT ON public.unified_document_link
    FOR EACH ROW EXECUTE FUNCTION public.fn_udl_insert_guard();

-- ─────────────────────────────────────────────────────────────
-- 3. VERSION BUMP + UPDATED_AT TRIGGER
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.fn_udl_version_bump()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    NEW.version    := OLD.version + 1;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.fn_udl_version_bump() FROM PUBLIC;

CREATE TRIGGER trg_udl_version_bump
    BEFORE UPDATE ON public.unified_document_link
    FOR EACH ROW EXECUTE FUNCTION public.fn_udl_version_bump();

-- ─────────────────────────────────────────────────────────────
-- 4. IMMUTABILITY GUARD TRIGGER (P0-3 CORR-001 신규, CORR-002 강화, CORR-003 완결)
-- APPROVED 이후 (상태 전환 포함) 핵심 필드 변경 차단
-- CORR-002-A: OLD.review_state = 'APPROVED' 조건만으로 검사
--   → APPROVED→RETIRED 전환과 동시에 relation_type/reviewed_by/reviewed_at 변경 불가
-- CORR-002-B1: RETIRED/REJECTED 터미널 상태 필드 전면 잠금
-- CORR-003-②: created_at 전역 불변 추가; version/updated_at 시스템 관리 필드로 명시
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.fn_udl_immutability_guard()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    -- 페어 식별자: INSERT 후 영원히 불변
    IF OLD.saas_catalog_id IS DISTINCT FROM NEW.saas_catalog_id THEN
        RAISE EXCEPTION 'saas_catalog_id is immutable after row creation.';
    END IF;
    IF OLD.reference_form_id IS DISTINCT FROM NEW.reference_form_id THEN
        RAISE EXCEPTION 'reference_form_id is immutable after row creation.';
    END IF;

    -- [CORR-003-②] created_at: 생성 이후 변경 불가
    IF OLD.created_at IS DISTINCT FROM NEW.created_at THEN
        RAISE EXCEPTION 'created_at is immutable after row creation.';
    END IF;

    -- [CORR-002-A] APPROVED 이후 — 상태 전환 여부와 무관하게 핵심 승인 증거 필드 불변
    IF OLD.review_state = 'APPROVED' THEN
        IF OLD.relation_type IS DISTINCT FROM NEW.relation_type THEN
            RAISE EXCEPTION
                'relation_type is immutable once review_state reaches APPROVED. '
                'RETIRE the link and create a new PROPOSED row to change the relation type.';
        END IF;
        IF OLD.reviewed_by IS DISTINCT FROM NEW.reviewed_by THEN
            RAISE EXCEPTION
                'reviewed_by is immutable once review_state reaches APPROVED.';
        END IF;
        IF OLD.reviewed_at IS DISTINCT FROM NEW.reviewed_at THEN
            RAISE EXCEPTION
                'reviewed_at is immutable once review_state reaches APPROVED.';
        END IF;
        -- owner_approval_ref: APPROVED 상태 유지 시만 불변
        -- APPROVED→RETIRED 전환 시 신규 값 필수 (P0-5 CORR-001); 전환 시 변경 허용
        IF NEW.review_state = 'APPROVED'
           AND OLD.owner_approval_ref IS DISTINCT FROM NEW.owner_approval_ref THEN
            RAISE EXCEPTION
                'owner_approval_ref is immutable while review_state remains APPROVED. '
                'It may only change as part of an APPROVED → RETIRED transition.';
        END IF;
    END IF;

    -- [CORR-002-B1] RETIRED/REJECTED 터미널 상태: review_state 변경만 허용, 나머지 필드 불변
    IF OLD.review_state IN ('RETIRED', 'REJECTED') THEN
        IF OLD.relation_type IS DISTINCT FROM NEW.relation_type
           OR OLD.reviewed_by IS DISTINCT FROM NEW.reviewed_by
           OR OLD.reviewed_at IS DISTINCT FROM NEW.reviewed_at
           OR OLD.owner_approval_ref IS DISTINCT FROM NEW.owner_approval_ref
           OR OLD.evidence_note IS DISTINCT FROM NEW.evidence_note THEN
            RAISE EXCEPTION
                'Fields are immutable once review_state is RETIRED or REJECTED. '
                'Current state: %. '
                'Only REJECTED → RETIRED transition is permitted. '
                'Create a new PROPOSED row to propose a different link.',
                OLD.review_state;
        END IF;

        -- [FINAL-AUDIT-GUARD-P0-A] review_state 변경 없는 UPDATE 전면 차단
        IF OLD.review_state = NEW.review_state THEN
            RAISE EXCEPTION
                'UPDATE on a % row without review_state transition is not permitted. '
                'A no-op UPDATE would silently increment version without an audit record. '
                'Only REJECTED → RETIRED state transition is allowed for terminal state rows.',
                OLD.review_state;
        END IF;
    END IF;

    -- [PREAPPLY-CLOSE-G1] 비터미널 상태(PROPOSED/UNDER_REVIEW/APPROVED)에서
    -- 업무 필드 미변경 no-op UPDATE 차단.
    IF OLD.review_state NOT IN ('RETIRED', 'REJECTED') THEN
        IF OLD.review_state IS NOT DISTINCT FROM NEW.review_state
           AND OLD.relation_type IS NOT DISTINCT FROM NEW.relation_type
           AND OLD.reviewed_by IS NOT DISTINCT FROM NEW.reviewed_by
           AND OLD.reviewed_at IS NOT DISTINCT FROM NEW.reviewed_at
           AND OLD.owner_approval_ref IS NOT DISTINCT FROM NEW.owner_approval_ref
           AND OLD.evidence_note IS NOT DISTINCT FROM NEW.evidence_note THEN
            RAISE EXCEPTION
                'UPDATE without any business field change is not permitted in state %. '
                'A no-op UPDATE would silently increment version without an audit record. '
                'Modify at least one business field or transition review_state.',
                OLD.review_state;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.fn_udl_immutability_guard() FROM PUBLIC;

CREATE TRIGGER trg_udl_immutability
    BEFORE UPDATE ON public.unified_document_link
    FOR EACH ROW EXECUTE FUNCTION public.fn_udl_immutability_guard();

-- ─────────────────────────────────────────────────────────────
-- 5. STATE TRANSITION GUARD TRIGGER
-- 허용 전환만 통과; 역방향·터미널 재활성화 차단
-- P0-5 CORR-001: APPROVED→RETIRED 시 신규(구별 가능한) owner_approval_ref 강제
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.fn_udl_state_guard()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_allowed_transitions TEXT[][] := ARRAY[
        ARRAY['PROPOSED',      'UNDER_REVIEW'],
        ARRAY['PROPOSED',      'REJECTED'],
        ARRAY['UNDER_REVIEW',  'APPROVED'],
        ARRAY['UNDER_REVIEW',  'REJECTED'],
        ARRAY['APPROVED',      'RETIRED'],
        ARRAY['REJECTED',      'RETIRED']
    ];
    v_pair TEXT[];
BEGIN
    IF OLD.review_state IS DISTINCT FROM NEW.review_state THEN
        FOREACH v_pair SLICE 1 IN ARRAY v_allowed_transitions LOOP
            IF v_pair[1] = OLD.review_state AND v_pair[2] = NEW.review_state THEN

                -- [P0-5 CORR-001] APPROVED→RETIRED: 폐기 결정에 대한 별도 Owner 승인참조 필수
                IF OLD.review_state = 'APPROVED' AND NEW.review_state = 'RETIRED' THEN
                    IF NEW.owner_approval_ref IS NULL THEN
                        RAISE EXCEPTION
                            'Transitioning APPROVED → RETIRED requires a new owner_approval_ref '
                            'for the retirement decision (cannot be NULL).';
                    END IF;
                    IF NEW.owner_approval_ref = OLD.owner_approval_ref THEN
                        RAISE EXCEPTION
                            'Transitioning APPROVED → RETIRED requires a distinct new owner_approval_ref. '
                            'The retirement decision must be separately authorized. '
                            'Current: %, Old: %', NEW.owner_approval_ref, OLD.owner_approval_ref;
                    END IF;
                END IF;

                RETURN NEW;
            END IF;
        END LOOP;

        RAISE EXCEPTION 'Invalid review_state transition: % → %. '
            'Allowed: PROPOSED→UNDER_REVIEW/REJECTED, UNDER_REVIEW→APPROVED/REJECTED, '
            'APPROVED→RETIRED, REJECTED→RETIRED.',
            OLD.review_state, NEW.review_state;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.fn_udl_state_guard() FROM PUBLIC;

CREATE TRIGGER trg_udl_state_guard
    BEFORE UPDATE ON public.unified_document_link
    FOR EACH ROW EXECUTE FUNCTION public.fn_udl_state_guard();

-- ─────────────────────────────────────────────────────────────
-- 6. DELETE GUARD TRIGGER
-- 링크 행 삭제 금지: RETIRED 전환으로 비파괴적 폐기
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.fn_udl_deny_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION
        'unified_document_link rows cannot be deleted. '
        'Transition to RETIRED via review_state instead. '
        'Audit integrity requires all link rows to be preserved.';
END;
$$;

REVOKE EXECUTE ON FUNCTION public.fn_udl_deny_delete() FROM PUBLIC;

CREATE TRIGGER trg_udl_no_delete
    BEFORE DELETE ON public.unified_document_link
    FOR EACH ROW EXECUTE FUNCTION public.fn_udl_deny_delete();

-- ─────────────────────────────────────────────────────────────
-- 7. AUDIT TABLE: unified_document_link_audit
-- Append-only 이벤트 로그 (reference_form_events 패턴 적용)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.unified_document_link_audit (
    id                BIGSERIAL   PRIMARY KEY,
    link_id           UUID        NOT NULL
                                  REFERENCES public.unified_document_link(id) ON DELETE RESTRICT,
    event_type        TEXT        NOT NULL DEFAULT 'STATE_CHANGE' CHECK (event_type IN (
                          'INITIAL_PROPOSE',
                          'STATE_CHANGE',
                          'FIELD_CHANGE'
                      )),
    actor             TEXT        NOT NULL,
    from_state        TEXT,
    to_state          TEXT        NOT NULL,
    changed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    change_note       TEXT,
    old_evidence_note TEXT,
    old_value         TEXT,
    new_value         TEXT
);

-- ─────────────────────────────────────────────────────────────
-- 8. AUDIT TRIGGER FUNCTION
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.fn_udl_audit_state_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_actor TEXT;
    v_note  TEXT;
BEGIN
    v_actor := COALESCE(
        NULLIF(current_setting('app.actor', true), ''),
        'system'
    );

    IF TG_OP = 'INSERT' THEN
        INSERT INTO public.unified_document_link_audit
            (link_id, event_type, actor, from_state, to_state, change_note)
        VALUES
            (NEW.id, 'INITIAL_PROPOSE', v_actor, NULL, NEW.review_state,
             LEFT('initial PROPOSE: ' || NEW.evidence_note, 500));

    ELSIF TG_OP = 'UPDATE' THEN

        -- 상태 전환: 항상 기록
        IF OLD.review_state IS DISTINCT FROM NEW.review_state THEN
            IF OLD.review_state = 'APPROVED' AND NEW.review_state = 'RETIRED' THEN
                v_note := 'state: APPROVED → RETIRED'
                          || '; original_approval_ref: '
                          || COALESCE(OLD.owner_approval_ref, 'none')
                          || '; retirement_ref: '
                          || COALESCE(NEW.owner_approval_ref, 'none');
            ELSE
                v_note := 'state: ' || OLD.review_state || ' → ' || NEW.review_state
                          || '; ref: ' || COALESCE(NEW.owner_approval_ref, 'none');
            END IF;
            INSERT INTO public.unified_document_link_audit
                (link_id, event_type, actor, from_state, to_state, change_note)
            VALUES
                (NEW.id, 'STATE_CHANGE', v_actor, OLD.review_state, NEW.review_state,
                 LEFT(v_note, 500));
        END IF;

        -- [CORR-003-①] 필드 변경 감사: 상태 전환 여부와 무관하게 항상 독립 검사
        IF OLD.evidence_note IS DISTINCT FROM NEW.evidence_note THEN
            v_note := 'field_change: evidence_note (v' || NEW.version::text || ')';
            INSERT INTO public.unified_document_link_audit
                (link_id, event_type, actor, from_state, to_state,
                 change_note, old_evidence_note)
            VALUES
                (NEW.id, 'FIELD_CHANGE', v_actor, OLD.review_state, NEW.review_state,
                 LEFT(v_note, 500), OLD.evidence_note);
        END IF;

        IF OLD.relation_type IS DISTINCT FROM NEW.relation_type THEN
            v_note := 'field_change: relation_type (v' || NEW.version::text || ')';
            INSERT INTO public.unified_document_link_audit
                (link_id, event_type, actor, from_state, to_state,
                 change_note, old_value, new_value)
            VALUES
                (NEW.id, 'FIELD_CHANGE', v_actor, OLD.review_state, NEW.review_state,
                 LEFT(v_note, 500), OLD.relation_type, NEW.relation_type);
        END IF;

        IF OLD.reviewed_by IS DISTINCT FROM NEW.reviewed_by THEN
            v_note := 'field_change: reviewed_by (v' || NEW.version::text || ')';
            INSERT INTO public.unified_document_link_audit
                (link_id, event_type, actor, from_state, to_state,
                 change_note, old_value, new_value)
            VALUES
                (NEW.id, 'FIELD_CHANGE', v_actor, OLD.review_state, NEW.review_state,
                 LEFT(v_note, 500), OLD.reviewed_by, NEW.reviewed_by);
        END IF;

        IF OLD.reviewed_at IS DISTINCT FROM NEW.reviewed_at THEN
            v_note := 'field_change: reviewed_at (v' || NEW.version::text || ')';
            INSERT INTO public.unified_document_link_audit
                (link_id, event_type, actor, from_state, to_state,
                 change_note, old_value, new_value)
            VALUES
                (NEW.id, 'FIELD_CHANGE', v_actor, OLD.review_state, NEW.review_state,
                 LEFT(v_note, 500),
                 OLD.reviewed_at::text, NEW.reviewed_at::text);
        END IF;

        IF OLD.owner_approval_ref IS DISTINCT FROM NEW.owner_approval_ref THEN
            v_note := 'field_change: owner_approval_ref (v' || NEW.version::text || ')';
            INSERT INTO public.unified_document_link_audit
                (link_id, event_type, actor, from_state, to_state,
                 change_note, old_value, new_value)
            VALUES
                (NEW.id, 'FIELD_CHANGE', v_actor, OLD.review_state, NEW.review_state,
                 LEFT(v_note, 500),
                 OLD.owner_approval_ref, NEW.owner_approval_ref);
        END IF;

    END IF;

    RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.fn_udl_audit_state_change() FROM PUBLIC;

CREATE TRIGGER trg_udl_audit
    AFTER INSERT OR UPDATE ON public.unified_document_link
    FOR EACH ROW EXECUTE FUNCTION public.fn_udl_audit_state_change();

-- ─────────────────────────────────────────────────────────────
-- 9. AUDIT DELETE/UPDATE GUARD
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.fn_udl_audit_deny_mutate()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION
        'unified_document_link_audit is append-only. '
        'UPDATE and DELETE are not permitted.';
END;
$$;

REVOKE EXECUTE ON FUNCTION public.fn_udl_audit_deny_mutate() FROM PUBLIC;

CREATE TRIGGER trg_udl_audit_no_update
    BEFORE UPDATE ON public.unified_document_link_audit
    FOR EACH ROW EXECUTE FUNCTION public.fn_udl_audit_deny_mutate();

CREATE TRIGGER trg_udl_audit_no_delete
    BEFORE DELETE ON public.unified_document_link_audit
    FOR EACH ROW EXECUTE FUNCTION public.fn_udl_audit_deny_mutate();

-- ─────────────────────────────────────────────────────────────
-- 10. ROW LEVEL SECURITY
-- ─────────────────────────────────────────────────────────────

ALTER TABLE public.unified_document_link       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.unified_document_link_audit ENABLE ROW LEVEL SECURITY;

-- 메인 테이블: anon/authenticated 직접 접근 전면 차단
CREATE POLICY udl_anon_deny ON public.unified_document_link
    FOR SELECT TO anon USING (false);

CREATE POLICY udl_authenticated_deny ON public.unified_document_link
    FOR SELECT TO authenticated USING (false);

CREATE POLICY udl_service_all ON public.unified_document_link
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- 감사 테이블: anon/authenticated 전면 차단
CREATE POLICY udl_audit_anon_deny ON public.unified_document_link_audit
    FOR SELECT TO anon USING (false);

CREATE POLICY udl_audit_authenticated_deny ON public.unified_document_link_audit
    FOR SELECT TO authenticated USING (false);

-- [P1 CORR-001] 감사 테이블: service_role SELECT만 (INSERT는 REVOKE — 트리거 전용)
CREATE POLICY udl_audit_service_select ON public.unified_document_link_audit
    FOR SELECT TO service_role USING (true);

-- ─────────────────────────────────────────────────────────────
-- 11. GRANTS
-- ─────────────────────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE ON public.unified_document_link TO service_role;
REVOKE ALL ON public.unified_document_link FROM anon, authenticated;

-- [P1 CORR-001] 감사 테이블: service_role SELECT만
GRANT SELECT ON public.unified_document_link_audit TO service_role;
REVOKE INSERT, UPDATE, DELETE ON public.unified_document_link_audit FROM service_role;
REVOKE ALL ON public.unified_document_link_audit FROM anon, authenticated;

-- ─────────────────────────────────────────────────────────────
-- 12. INDEXES
-- ─────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_udl_saas_id
    ON public.unified_document_link(saas_catalog_id);

CREATE INDEX IF NOT EXISTS idx_udl_ref_id
    ON public.unified_document_link(reference_form_id);

CREATE INDEX IF NOT EXISTS idx_udl_review_state
    ON public.unified_document_link(review_state);

-- [P0-4 CORR-001] 조건부 UNIQUE INDEX — REJECTED/RETIRED 쌍의 재제안 허용
CREATE UNIQUE INDEX IF NOT EXISTS uq_udl_active_pair
    ON public.unified_document_link(saas_catalog_id, reference_form_id)
    WHERE review_state NOT IN ('REJECTED', 'RETIRED');

CREATE INDEX IF NOT EXISTS idx_udl_audit_link_id
    ON public.unified_document_link_audit(link_id);

CREATE INDEX IF NOT EXISTS idx_udl_audit_changed
    ON public.unified_document_link_audit(changed_at DESC);

CREATE INDEX IF NOT EXISTS idx_udl_audit_event_type
    ON public.unified_document_link_audit(event_type, changed_at DESC);

-- ─────────────────────────────────────────────────────────────
-- ROLLBACK (스테이징 환경에서만; 프로덕션 롤백은 Owner 서면 승인 필요):
--
-- DROP TRIGGER IF EXISTS trg_udl_audit_no_delete   ON public.unified_document_link_audit;
-- DROP TRIGGER IF EXISTS trg_udl_audit_no_update   ON public.unified_document_link_audit;
-- DROP TRIGGER IF EXISTS trg_udl_audit             ON public.unified_document_link;
-- DROP TRIGGER IF EXISTS trg_udl_no_delete         ON public.unified_document_link;
-- DROP TRIGGER IF EXISTS trg_udl_state_guard       ON public.unified_document_link;
-- DROP TRIGGER IF EXISTS trg_udl_immutability      ON public.unified_document_link;
-- DROP TRIGGER IF EXISTS trg_udl_version_bump      ON public.unified_document_link;
-- DROP TRIGGER IF EXISTS trg_udl_insert_guard      ON public.unified_document_link;
-- DROP FUNCTION IF EXISTS public.fn_udl_audit_deny_mutate();
-- DROP FUNCTION IF EXISTS public.fn_udl_audit_state_change();
-- DROP FUNCTION IF EXISTS public.fn_udl_deny_delete();
-- DROP FUNCTION IF EXISTS public.fn_udl_state_guard();
-- DROP FUNCTION IF EXISTS public.fn_udl_immutability_guard();
-- DROP FUNCTION IF EXISTS public.fn_udl_version_bump();
-- DROP FUNCTION IF EXISTS public.fn_udl_insert_guard();
-- DROP INDEX IF EXISTS public.uq_udl_active_pair;
-- DROP TABLE IF EXISTS public.unified_document_link_audit;
-- DROP TABLE IF EXISTS public.unified_document_link;
-- ─────────────────────────────────────────────────────────────
