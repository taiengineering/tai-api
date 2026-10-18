-- migration: 2026-10-19_construction_paid_art68_dogeup_fields.sql
-- WO-LEGAL-ADDITIONAL-INPUT-2FRONT-GAP-CLOSURE-001 Phase B
-- CORRECTION-001: 부모 질문 의미 교정 + is_required=true + 필드 수 정정(44→48)
-- GAP-A: CONSTRUCTION PAID diagnosis_input_fields에 ART68(산안법 제68조) 도급관계 4개 필드 추가
--
-- 근거:
--   - tai-api /legal-engine/diagnose/construction-leg → SafeConstructionConsumerInput에 4개 명시
--   - tai-api clients/leg_runtime_client.py _LEG_INPUT_FIELDS에 4개 등록 (lines 416-419)
--   - tai-admin construction-extraction/index.vue validateArt68Gate() + 레이블 원문 확인
--   - tai-www paid-diagnosis-detail.astro: /diagnosis/fields API 응답 기반 화면 구성
--     → DB에 없으면 유료진단 화면에 미노출 → form_data 미포함 → LEG 전달 불가
--
-- 설계 계약 (CORRECTION-001 적용):
--   1. contracts_construction_work_at_site: 항상 표시(visibility_condition NULL), is_required=true
--   2. 자식 3개: parent=true일 때만 표시 (visibility_condition), is_required=true
--      → isFieldVisible() 숨김 시 missingIn() 에서 skip → 조건부 필수
--   3. parent=false이면 자식 3개 payload 제외 → applyVisibilityAfterParentChange() fail-closed
--   4. 미입력(NULL)과 false 구분 → boolean field_type, missing≠false
--   5. same_site_contracted_construction_work_count: number (0 이상 정수, 0≠누락)
--   6. 기존 visibility_condition {"field_code","op":"eq","value"} 계약 재사용
--   7. 그룹 "도급관계" 신규 (협력업체 sort_order=200 다음, 210-240)
--   8. 기존 필드 변경 없음
--   9. field_name: tai-admin construction-extraction/index.vue 레이블 원문과 동일
--  10. 필드 수: 운영 DB CONSTRUCTION/PAID 활성 44개 → 적용 후 48개
--
-- UNIQUE 제약: (field_code, sector, tier) 고유 — 중복 적용 시 오류 반환(정상)
--
-- 적용: Draft PR 병합 + Owner 승인 후 운영 DB 적용
-- 금지: 이 파일을 직접 운영 DB에 실행하지 않는다

BEGIN;

INSERT INTO diagnosis_input_fields (
    sector, tier, field_group,
    field_code, field_name, field_type,
    is_required, sort_order, is_active,
    visibility_condition
)
VALUES
    -- [1/4] 부모 필드 — 항상 표시, 필수
    (
        'CONSTRUCTION', 'PAID', '도급관계',
        'contracts_construction_work_at_site',
        '이 현장에서 건설공사를 외부 업체에 도급하고 있습니까?',
        'boolean',
        true, 210, true,
        NULL
    ),
    -- [2/4] 자식: 시공 주도·총괄·관리 여부 — parent=true일 때만 (조건부 필수)
    (
        'CONSTRUCTION', 'PAID', '도급관계',
        'leads_and_manages_construction_execution',
        '해당 건설공사의 시공을 귀사가 주도하여 총괄·관리하고 있습니까?',
        'boolean',
        true, 220, true,
        '{"field_code":"contracts_construction_work_at_site","op":"eq","value":true}'::jsonb
    ),
    -- [3/4] 자식: 재도급 여부 — parent=true일 때만 (조건부 필수)
    (
        'CONSTRUCTION', 'PAID', '도급관계',
        'recontracts_received_construction_work',
        '다른 자에게 도급받은 건설공사를 다시 도급하는 경우입니까?',
        'boolean',
        true, 230, true,
        '{"field_code":"contracts_construction_work_at_site","op":"eq","value":true}'::jsonb
    ),
    -- [4/4] 자식: 같은 현장 도급 건설공사 건수 (0 이상 정수) — parent=true일 때만 (조건부 필수)
    (
        'CONSTRUCTION', 'PAID', '도급관계',
        'same_site_contracted_construction_work_count',
        '같은 장소에서 귀사가 도급한 건설공사는 몇 건입니까?',
        'number',
        true, 240, true,
        '{"field_code":"contracts_construction_work_at_site","op":"eq","value":true}'::jsonb
    );

COMMIT;

-- 검증 쿼리 (적용 후 실행):
-- SELECT field_code, field_name, is_required, sort_order, visibility_condition
-- FROM diagnosis_input_fields
-- WHERE sector = 'CONSTRUCTION'
--   AND tier = 'PAID'
--   AND field_group = '도급관계'
--   AND is_active = true
-- ORDER BY sort_order;
-- → 4개 행 반환 기대
--
-- 전체 활성 필드 수 검증:
-- SELECT COUNT(*) FROM diagnosis_input_fields
-- WHERE sector = 'CONSTRUCTION' AND tier = 'PAID' AND is_active = true;
-- → 48개 기대 (적용 전 44개 + 4개)
