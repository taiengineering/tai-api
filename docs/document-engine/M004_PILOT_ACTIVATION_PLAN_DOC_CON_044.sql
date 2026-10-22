-- =====================================================================
-- WO-TAI-M004-WEB-ACTIVATION-PILOT-001-CORR-001 — PILOT ACTIVATION SQL
-- =====================================================================
-- !!! NOT EXECUTED — Owner + PRJ 운영 변경 승인 전 실행 금지 !!!
-- 목적: DOC-CON-044 소규모안전관리계획 스키마 활성화
--       runtime_field (4건): CANDIDATE/CANDIDATE_ONLY → APPROVED_BY_HUMAN/REQUIRED_BY_HUMAN
--       runtime_form_schema: CANDIDATE → APPROVED_BY_HUMAN → APPROVED_FOR_RUNTIME_USE
-- 기준 커밋: 16673da4 (WO-TAI-M004-WEB-REQUIREDNESS-GATE-001-CORR-001)
-- 작성: Claude Code (WO-TAI-M004-WEB-ACTIVATION-PILOT-001) 2026-10-22
-- 교정: Claude Code (WO-TAI-M004-WEB-ACTIVATION-PILOT-001-CORR-001) 2026-10-22
--
-- 대상 식별자:
--   schema_id           = 479a1881-3bec-47ac-a8bf-0f8ff8db2cf8
--   catalog_document_id = a795be1d-08a4-4291-aa68-57b7ff59519d  (document_forms.id)
--   schema_candidate_id = 6b74769f-8f0f-4804-ac5d-07b09556a7db
--
-- PRJ 승인 근거:
--   Step4D 패턴 (WP-PERSISTENCE-02A STEP-4D) 재사용.
--   단일 DO 블록 원자 실행. 실패 시 전체 롤백. 부분 승격 없음.
--
-- ── 고객 격리 근거 (CORR-001 CORR-1) ────────────────────────────────
-- ISOLATION_CONFIRMED_FRONTEND_NOT_WIRED:
--   모든 고객 접근 경로(tai-admin/admin-vue3 engine-document · document-forms 페이지)는
--   구 API(GET /document-forms, GET /document-forms/{id}) 전용이며
--   신 문서 엔진(POST /documents, GET /documents/catalog/{doc_id}) 미연결.
--   스키마 활성화 → can_create=True 는 API 계층 상태이나 현재 고객 UI 호출 경로 없음.
--   증거: useEngineDocumentList.ts:103 GET /document-forms 전용 /
--          useEngineDocumentDetail.ts:36 GET /document-forms/{id} 전용 /
--          admin-vue3 전 파일에서 POST /documents 호출 0건.
--   CUSTOMER_RELEASE=HOLD 사유: 신 문서 엔진 전용 UI 연결 · QA 없이 고객 노출 금지.
-- ─────────────────────────────────────────────────────────────────────
--
-- 활성화 후 기대 상태:
--   runtime_form_schema.status = APPROVED_FOR_RUNTIME_USE
--   runtime_field.status = APPROVED_BY_HUMAN (4건)
--   runtime_field.required_status = REQUIRED_BY_HUMAN (4건)
--   catalog API: availability=READY_FOR_EDIT, can_create=true
--
-- ── 복구 계획 (CORR-001 CORR-4 — conditional rollback guard) ─────────
-- before_state → runtime_form_audit_log.rollback_snapshot 저장됨.
-- 복구 실행 전 반드시 아래 전제조건 확인 후 DO 블록 실행:
--   전제조건:
--     runtime_document_data = 0건 (고객 데이터 없음)
--     runtime_inspection_bridge = 0건
--     runtime_form_schema.status = 'APPROVED_FOR_RUNTIME_USE' (중복 롤백 차단)
--     runtime_form_audit_log PROMOTE_TO_RUNTIME_USE 1건 존재
--   조건 불충족 시 DO 블록이 EXCEPTION 발생 → 전체 자동 롤백.
--   Owner 에스컬레이션 없이 복구 SQL 실행 금지.
--
-- 복구 DO 블록 (NOT EXECUTED):
-- DO $$
-- DECLARE v_cnt integer;
-- BEGIN
--   IF (SELECT count(*) FROM runtime_document_data
--       WHERE form_schema_id = '479a1881-3bec-47ac-a8bf-0f8ff8db2cf8') <> 0 THEN
--     RAISE EXCEPTION 'ROLLBACK_ABORT: runtime_document_data 참조 존재. Owner 에스컬레이션 필요.';
--   END IF;
--   IF (SELECT count(*) FROM runtime_inspection_bridge
--       WHERE runtime_form_schema_id = '479a1881-3bec-47ac-a8bf-0f8ff8db2cf8') <> 0 THEN
--     RAISE EXCEPTION 'ROLLBACK_ABORT: bridge 참조 존재. Owner 에스컬레이션 필요.';
--   END IF;
--   IF (SELECT status FROM runtime_form_schema
--       WHERE id = '479a1881-3bec-47ac-a8bf-0f8ff8db2cf8') <> 'APPROVED_FOR_RUNTIME_USE' THEN
--     RAISE EXCEPTION 'ROLLBACK_ABORT: schema 상태가 APPROVED_FOR_RUNTIME_USE 아님 (이미 롤백됐거나 불일치).';
--   END IF;
--   UPDATE runtime_form_schema SET status = 'CANDIDATE', updated_at = now()
--     WHERE id = '479a1881-3bec-47ac-a8bf-0f8ff8db2cf8';
--   UPDATE runtime_field
--     SET status = 'CANDIDATE', required_status = 'CANDIDATE_ONLY'
--     WHERE form_schema_id = '479a1881-3bec-47ac-a8bf-0f8ff8db2cf8';
--   GET DIAGNOSTICS v_cnt = ROW_COUNT;
--   IF v_cnt <> 4 THEN
--     RAISE EXCEPTION 'ROLLBACK_ABORT: field rollback affected % rows (expected 4).', v_cnt;
--   END IF;
--   RAISE NOTICE 'ROLLBACK OK: schema=479a1881-... → CANDIDATE, 4 fields → CANDIDATE/CANDIDATE_ONLY';
-- END $$;
-- ─────────────────────────────────────────────────────────────────────
--
-- 변경 후 검증 조건:
--   SELECT status FROM runtime_form_schema WHERE id='479a1881...' → APPROVED_FOR_RUNTIME_USE
--   SELECT count(*) FROM runtime_field WHERE form_schema_id='479a1881...' AND status='APPROVED_BY_HUMAN' → 4
--   SELECT count(*) FROM runtime_field WHERE form_schema_id='479a1881...' AND required_status='REQUIRED_BY_HUMAN' → 4
--   GET /documents/catalog/DOC-CON-044 → can_create=true
-- =====================================================================

DO $$
DECLARE
  v_schema_id  uuid := '479a1881-3bec-47ac-a8bf-0f8ff8db2cf8';
  v_catalog_id uuid := 'a795be1d-08a4-4291-aa68-57b7ff59519d';
  v_cand_id    uuid := '6b74769f-8f0f-4804-ac5d-07b09556a7db';
  v_before     jsonb;
  v_after      jsonb;
  v_cnt        integer;
BEGIN
  -- ── PRECONDITION ASSERTS ───────────────────────────────────────────

  -- P1: schema 현재 상태 exact 재확인
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = v_schema_id
        AND status = 'CANDIDATE'
        AND form_type = 'OFFICIAL'
        AND document_family = '착공전'
        AND field_count = 4
        AND checklist_count = 0
        AND evidence_count = 0) <> 1 THEN
    RAISE EXCEPTION 'ABORT: P1 schema precondition mismatch. STOP.';
  END IF;

  -- P2: 4 필드 모두 CANDIDATE/CANDIDATE_ONLY
  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id
        AND status = 'CANDIDATE'
        AND required_status = 'CANDIDATE_ONLY') <> 4 THEN
    RAISE EXCEPTION 'ABORT: P2 field precondition mismatch (expected 4 CANDIDATE/CANDIDATE_ONLY). STOP.';
  END IF;

  -- P3: total field count = 4 (예상 밖 필드 차단)
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id) <> 4 THEN
    RAISE EXCEPTION 'ABORT: P3 total runtime_field count <> 4. STOP.';
  END IF;

  -- P4: exact field_key + input_type + field_order (계약 재확인)
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND
        ( (field_key = 'construction_project_overview'      AND input_type = 'text'     AND field_order = 1)
       OR (field_key = 'construction_procedure'             AND input_type = 'text'     AND field_order = 2)
       OR (field_key = 'construction_precautions'           AND input_type = 'textarea' AND field_order = 3)
       OR (field_key = 'hazardous_work_and_safety_measures' AND input_type = 'text'     AND field_order = 4) )
      ) <> 4 THEN
    RAISE EXCEPTION 'ABORT: P4 field exact contract mismatch (key/type/order). STOP.';
  END IF;

  -- P5: 기존 문서 참조 없음 (초기 상태 보장)
  IF (SELECT count(*) FROM runtime_document_data WHERE form_schema_id = v_schema_id) <> 0 THEN
    RAISE EXCEPTION 'ABORT: P5 runtime_document_data already references schema. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_inspection_bridge WHERE runtime_form_schema_id = v_schema_id) <> 0 THEN
    RAISE EXCEPTION 'ABORT: P5 runtime_inspection_bridge already references schema. STOP.';
  END IF;

  -- P6: 기존 승격 audit 없음 (중복 실행 차단)
  IF (SELECT count(*) FROM runtime_form_audit_log
      WHERE source_table = 'runtime_form_schema'
        AND source_id = v_schema_id
        AND action = 'PROMOTE_TO_RUNTIME_USE') <> 0 THEN
    RAISE EXCEPTION 'ABORT: P6 promotion audit already exists (duplicate run). STOP.';
  END IF;

  -- P7: catalog_document_id에 기존 APPROVED 스키마 없음 (unique constraint 보강)
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE catalog_document_id = v_catalog_id
        AND status = 'APPROVED_FOR_RUNTIME_USE') <> 0 THEN
    RAISE EXCEPTION 'ABORT: P7 existing APPROVED_FOR_RUNTIME_USE schema for catalog_document_id. STOP.';
  END IF;

  -- P8: source provenance — catalog_document_id + schema_candidate_id 동시 일치 (CORR-001 CORR-2)
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = v_schema_id
        AND catalog_document_id = v_catalog_id
        AND schema_candidate_id = v_cand_id) <> 1 THEN
    RAISE EXCEPTION 'ABORT: P8 source provenance mismatch (catalog_document_id or schema_candidate_id). STOP.';
  END IF;

  -- ── GATE ASSERTS ───────────────────────────────────────────────────

  -- G1: NON_LEGAL 확인 — has_legal_form=FALSE
  IF (SELECT count(*) FROM document_forms
      WHERE id = v_catalog_id
        AND has_legal_form = FALSE
        AND doc_id = 'DOC-CON-044') <> 1 THEN
    RAISE EXCEPTION 'ABORT: G1 NON_LEGAL gate fail (has_legal_form != FALSE or doc_id mismatch). STOP.';
  END IF;

  -- G2: 증빙 필드 없음
  IF (SELECT count(*) FROM runtime_evidence_field WHERE form_schema_id = v_schema_id) <> 0 THEN
    RAISE EXCEPTION 'ABORT: G2 evidence_fields present (expected 0). STOP.';
  END IF;

  -- G3: 체크리스트 없음
  IF (SELECT count(*) FROM runtime_checklist_item WHERE form_schema_id = v_schema_id) <> 0 THEN
    RAISE EXCEPTION 'ABORT: G3 checklists present (expected 0). STOP.';
  END IF;

  -- G4: document_schema_candidate CANDIDATE 불변 확인 (승격 전 소스 상태 — CORR-001 CORR-2)
  IF (SELECT status FROM document_schema_candidate WHERE id = v_cand_id) <> 'CANDIDATE' THEN
    RAISE EXCEPTION 'ABORT: G4 document_schema_candidate.status != CANDIDATE (source drift detected). STOP.';
  END IF;

  -- ── BEFORE STATE SNAPSHOT ──────────────────────────────────────────
  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'fields', (SELECT jsonb_agg(jsonb_build_object(
                 'field_key', field_key, 'status', status, 'required_status', required_status)
                 ORDER BY field_order)
               FROM runtime_field WHERE form_schema_id = v_schema_id)
  ) INTO v_before;

  -- ── [1] runtime_field ×4: CANDIDATE→APPROVED_BY_HUMAN + CANDIDATE_ONLY→REQUIRED_BY_HUMAN ──
  -- 근거: document_forms.required_fields 전 4건 is_mandatory=True (FIELD_REQUIREDNESS_GATE.csv 검증)
  UPDATE runtime_field
  SET status = 'APPROVED_BY_HUMAN',
      required_status = 'REQUIRED_BY_HUMAN'
  WHERE form_schema_id = v_schema_id
    AND status = 'CANDIDATE'
    AND required_status = 'CANDIDATE_ONLY';

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 4 THEN
    RAISE EXCEPTION 'ABORT: [1] field UPDATE affected % rows (expected 4). ROLLBACK.', v_cnt;
  END IF;

  -- POST-ASSERT: 필드 전환 검증
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND status = 'APPROVED_BY_HUMAN') <> 4 THEN
    RAISE EXCEPTION 'ABORT: [1] not all 4 fields APPROVED_BY_HUMAN. ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND required_status = 'REQUIRED_BY_HUMAN') <> 4 THEN
    RAISE EXCEPTION 'ABORT: [1] not all 4 fields REQUIRED_BY_HUMAN. ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND required_status = 'CANDIDATE_ONLY') <> 0 THEN
    RAISE EXCEPTION 'ABORT: [1] CANDIDATE_ONLY still present. ROLLBACK.';
  END IF;

  -- ── [2] runtime_form_schema: CANDIDATE→APPROVED_BY_HUMAN (1차) ────
  UPDATE runtime_form_schema
  SET status = 'APPROVED_BY_HUMAN', updated_at = now()
  WHERE id = v_schema_id AND status = 'CANDIDATE';
  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT: [2] schema APPROVED_BY_HUMAN UPDATE affected % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  -- ── [3] runtime_form_schema: APPROVED_BY_HUMAN→APPROVED_FOR_RUNTIME_USE (2차) ──
  UPDATE runtime_form_schema
  SET status = 'APPROVED_FOR_RUNTIME_USE', updated_at = now()
  WHERE id = v_schema_id AND status = 'APPROVED_BY_HUMAN';
  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT: [3] schema APPROVED_FOR_RUNTIME_USE UPDATE affected % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  -- ── FINAL ASSERTS ──────────────────────────────────────────────────

  -- F1: schema APPROVED_FOR_RUNTIME_USE
  IF (SELECT status FROM runtime_form_schema WHERE id = v_schema_id) <> 'APPROVED_FOR_RUNTIME_USE' THEN
    RAISE EXCEPTION 'ABORT: F1 final schema status not APPROVED_FOR_RUNTIME_USE. ROLLBACK.';
  END IF;
  -- F2: schema_candidate 불변 (CANDIDATE 유지)
  IF (SELECT status FROM document_schema_candidate WHERE id = v_cand_id) <> 'CANDIDATE' THEN
    RAISE EXCEPTION 'ABORT: F2 schema_candidate.status changed (must stay CANDIDATE). ROLLBACK.';
  END IF;
  -- F3: schema 헤더 불변
  IF (SELECT count(*) FROM runtime_form_schema WHERE id = v_schema_id
      AND form_type = 'OFFICIAL' AND document_family = '착공전'
      AND field_count = 4 AND checklist_count = 0 AND evidence_count = 0) <> 1 THEN
    RAISE EXCEPTION 'ABORT: F3 schema header drift detected. ROLLBACK.';
  END IF;
  -- F4: source provenance 불변 (CORR-001 CORR-2)
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = v_schema_id
        AND catalog_document_id = v_catalog_id
        AND schema_candidate_id = v_cand_id) <> 1 THEN
    RAISE EXCEPTION 'ABORT: F4 final source provenance mismatch. ROLLBACK.';
  END IF;

  -- ── AFTER STATE SNAPSHOT ───────────────────────────────────────────
  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'fields', (SELECT jsonb_agg(jsonb_build_object(
                 'field_key', field_key, 'status', status, 'required_status', required_status)
                 ORDER BY field_order)
               FROM runtime_field WHERE form_schema_id = v_schema_id)
  ) INTO v_after;

  -- ── AUDIT LOG ──────────────────────────────────────────────────────
  -- reviewer_id=NULL: Step4D B-1 계약 (nullable 허용, 별도 reviewer identity 계약 없음).
  -- CORR-001 CORR-3: review_comment 는 실행 전 승인 요건을 명시 (완료 사실 주장 금지).
  INSERT INTO runtime_form_audit_log
    (source_table, source_id, action, schema_version,
     before_state, after_state, reviewer_id, review_comment,
     rollback_snapshot, rollback_available)
  VALUES
    ('runtime_form_schema', v_schema_id, 'PROMOTE_TO_RUNTIME_USE', 1,
     v_before, v_after, NULL,
     'WO-TAI-M004-WEB-ACTIVATION-PILOT-001-CORR-001: DOC-CON-044 NON_LEGAL pilot activation. has_legal_form=FALSE. reviewer_id=NULL per Step4D B-1 contract. Execution requires explicit Owner+PRJ authorization before running this SQL.',
     v_before, true);

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT: audit INSERT affected % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  -- Final audit count assert
  IF (SELECT count(*) FROM runtime_form_audit_log
      WHERE source_table = 'runtime_form_schema'
        AND source_id = v_schema_id
        AND action = 'PROMOTE_TO_RUNTIME_USE') <> 1 THEN
    RAISE EXCEPTION 'ABORT: final promotion audit count <> 1. ROLLBACK.';
  END IF;

  RAISE NOTICE 'PROMOTED OK: schema=% APPROVED_FOR_RUNTIME_USE | fields=4 APPROVED_BY_HUMAN REQUIRED_BY_HUMAN', v_schema_id;
END $$;

-- =====================================================================
-- END — !!! NOT EXECUTED. PRJ+Owner 운영 변경 승인 후 단일 execute_sql 호출로 실행. !!!
-- 실행 직후 VERIFY:
--   SELECT status FROM runtime_form_schema WHERE id = '479a1881-3bec-47ac-a8bf-0f8ff8db2cf8';
--   SELECT field_key, status, required_status FROM runtime_field
--     WHERE form_schema_id = '479a1881-3bec-47ac-a8bf-0f8ff8db2cf8' ORDER BY field_order;
--   GET /documents/catalog/DOC-CON-044 → {"can_create": true, "availability": "READY_FOR_EDIT"}
-- =====================================================================
