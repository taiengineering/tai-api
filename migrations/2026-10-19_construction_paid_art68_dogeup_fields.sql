-- migration: 2026-10-19_construction_paid_art68_dogeup_fields.sql
-- WO-LEGAL-ADDITIONAL-INPUT-2FRONT-GAP-CLOSURE-001 Phase B
-- GAP-A: CONSTRUCTION PAID diagnosis_input_fields에 ART68(산안법 제68조) 도급관계 4개 필드 추가
--
-- 근거:
--   - tai-api /legal-engine/diagnose/construction-leg → SafeConstructionConsumerInput에 4개 명시
--   - tai-api clients/leg_runtime_client.py _LEG_INPUT_FIELDS에 4개 등록 (lines 416-419)
--   - tai-admin construction-extraction validateArt68Gate() + constructionExtractionLogic.ts 정상 구현
--   - tai-www paid-diagnosis-detail.astro: /diagnosis/fields API 응답 기반 화면 구성
--     → DB에 없으면 유료진단 화면에 미노출 → form_data 미포함 → LEG 전달 불가
--
-- 설계 계약 (WO 지시서 조건):
--   1. contracts_construction_work_at_site: 항상 표시(visibility_condition NULL)
--   2. 자식 3개: parent=true일 때만 표시 (visibility_condition)
--   3. parent=false 이면 자식 3개 payload 제외 → 유료진단 isFieldVisible() fail-closed 처리
--   4. 미입력(NULL)과 false 구분 → boolean field_type, missing≠false
--   5. same_site_contracted_construction_work_count: number (0 이상 정수, 0≠누락)
--   6. 기존 visibility_condition {"field_code","op":"eq","value"} 계약 재사용
--   7. 그룹 "도급관계" 신규 (협력업체 sort_order=200 다음, 210-240)
--   8. 기존 필드 변경 없음
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
    -- [1/4] 부모 필드 — 항상 표시
    (
        'CONSTRUCTION', 'PAID', '도급관계',
        'contracts_construction_work_at_site',
        '귀사가 이 공사현장에서 건설공사를 도급받아 시공합니까?',
        'boolean',
        false, 210, true,
        NULL
    ),
    -- [2/4] 자식: 시공 주도·총괄·관리 여부 — parent=true일 때만
    (
        'CONSTRUCTION', 'PAID', '도급관계',
        'leads_and_manages_construction_execution',
        '귀사가 건설공사의 시공을 주도·총괄하거나 관리합니까?',
        'boolean',
        false, 220, true,
        '{"field_code":"contracts_construction_work_at_site","op":"eq","value":true}'::jsonb
    ),
    -- [3/4] 자식: 재도급 여부 — parent=true일 때만
    (
        'CONSTRUCTION', 'PAID', '도급관계',
        'recontracts_received_construction_work',
        '귀사가 도급받은 건설공사를 다시 도급(재도급)합니까?',
        'boolean',
        false, 230, true,
        '{"field_code":"contracts_construction_work_at_site","op":"eq","value":true}'::jsonb
    ),
    -- [4/4] 자식: 같은 현장 도급 건설공사 건수 (0 이상 정수) — parent=true일 때만
    (
        'CONSTRUCTION', 'PAID', '도급관계',
        'same_site_contracted_construction_work_count',
        '이 공사현장에서 귀사가 도급한 건설공사 건수 (0 이상 정수)',
        'number',
        false, 240, true,
        '{"field_code":"contracts_construction_work_at_site","op":"eq","value":true}'::jsonb
    );

COMMIT;

-- 검증 쿼리 (적용 후 실행):
-- SELECT field_code, field_name, sort_order, visibility_condition
-- FROM diagnosis_input_fields
-- WHERE sector = 'CONSTRUCTION'
--   AND tier = 'PAID'
--   AND field_group = '도급관계'
--   AND is_active = true
-- ORDER BY sort_order;
-- → 4개 행 반환 기대
