-- =====================================================================
-- WO-TAI-M004-WEB-ACTIVATION-PILOT-001-CORR-002 — PILOT ACTIVATION SQL
-- =====================================================================
-- !!! NOT EXECUTED — Owner + PRJ 운영 변경 승인 전 실행 금지 !!!
-- 목적: DOC-CON-044 소규모안전관리계획 스키마 활성화
--       runtime_field (4건): CANDIDATE/CANDIDATE_ONLY → APPROVED_BY_HUMAN/REQUIRED_BY_HUMAN
--       runtime_form_schema: CANDIDATE → APPROVED_BY_HUMAN → APPROVED_FOR_RUNTIME_USE
-- 기준 커밋: 16673da4 (WO-TAI-M004-WEB-REQUIREDNESS-GATE-001-CORR-001)
-- 작성: Claude Code (WO-TAI-M004-WEB-ACTIVATION-PILOT-001) 2026-10-22
-- 교정: Claude Code (WO-TAI-M004-WEB-ACTIVATION-PILOT-001-CORR-001) 2026-10-22
-- 교정: Claude Code (WO-TAI-M004-WEB-ACTIVATION-PILOT-001-CORR-002) 2026-10-22
--
-- 대상 식별자:
--   schema_id           = 479a1881-3bec-47ac-a8bf-0f8ff8db2cf8
--   catalog_document_id = a795be1d-08a4-4291-aa68-57b7ff59519d  (document_forms.id)
--   schema_candidate_id = 6b74769f-8f0f-4804-ac5d-07b09556a7db
--   schema_version      = 1  (runtime_form_schema.version, DB 실증값)
--
-- PRJ 승인 근거:
--   Step4D 패턴 원문: docs/sql/20260825_WP_PERSISTENCE_02A_STEP4D_UP.sql
--   단일 DO 블록 원자 실행. 실패 시 전체 롤백. 부분 승격 없음.
--
-- ── 고객 격리 근거 (CORR-002 — CORR-001 격리 주장 교정) ──────────────
-- ISOLATION_CONFIRMED_FORM_SCHEMA_ID_NOT_WIRED:
--   고객 SaaS 프론트(tai-admin/vue3/src/pages/document-forms/)는
--   POST /document-engine/documents를 실제로 호출하나 (CORR-001 주장 "FRONTEND_NOT_WIRED" 교정),
--   document_forms 테이블에 form_schema_id / runtime_form_schema_id / schema_id 컬럼 없음 (DB 확인).
--   증거:
--     document_forms 컬럼 조회: id, doc_id, is_active 만 반환 — form_schema_id 없음.
--     document-formsFormat.ts:219 pickFormSchemaId(tpl) → tpl.form_schema_id || tpl.runtime_form_schema_id || tpl.schema_id || ''
--     → DOC-CON-044 선택 시 모두 undefined → '' 반환.
--     useDocumentFormsGenerate.ts:71 if (!formSchemaId) throw '이 서식에 연결된 form_schema_id가 없습니다.'
--     → POST /document-engine/documents API 호출 자체 미발생.
--   DOC-CON-044는 고객 서식 목록(GET /document-forms)에 표시(is_active=true)되나
--   문서 생성 시도 시 프론트 에러로 차단.
--   스키마 활성화(CANDIDATE→APPROVED_FOR_RUNTIME_USE)가 이 고객 차단 메커니즘을 변경하지 않음.
--   CAVEAT: 스키마 UUID 직접 API 호출 시 우회 가능 — 인증+factory scope 필요.
--   CUSTOMER_RELEASE=HOLD 사유: document_forms.form_schema_id 매핑 + 전용 UI QA 없이 고객 노출 금지.
-- ─────────────────────────────────────────────────────────────────────
--
-- 활성화 후 기대 상태:
--   runtime_form_schema.status = APPROVED_FOR_RUNTIME_USE
--   runtime_field.status = APPROVED_BY_HUMAN (4건)
--   runtime_field.required_status = REQUIRED_BY_HUMAN (4건)
--   catalog API: availability=READY_FOR_EDIT, can_create=true
--
-- ── 복구 계획 (CORR-002 — conditional rollback guard 강화) ───────────
-- before_state → runtime_form_audit_log.rollback_snapshot 저장됨.
-- 복구 실행 전 반드시 아래 DO 블록으로 전제조건 확인 후 복구:
--   전제조건:
--     runtime_document_data = 0건 (고객 데이터 없음)
--     runtime_inspection_bridge = 0건
--     runtime_form_schema.status = 'APPROVED_FOR_RUNTIME_USE' (중복 롤백 차단)
--     runtime_form_audit_log PROMOTE_TO_RUNTIME_USE = 1건 존재 (CORR-002 추가)
--   조건 불충족 시 DO 블록이 EXCEPTION → 전체 자동 롤백.
--   !! 감사기록(runtime_form_audit_log)은 복구 후에도 삭제하지 않는다. 이력 보존 필수. !!
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
--   -- CORR-002: 승격 감사기록 1건 존재 확인 (감사기록은 롤백 후에도 삭제하지 않는다)
--   IF (SELECT count(*) FROM runtime_form_audit_log
--       WHERE source_table = 'runtime_form_schema'
--         AND source_id = '479a1881-3bec-47ac-a8bf-0f8ff8db2cf8'
--         AND action = 'PROMOTE_TO_RUNTIME_USE') <> 1 THEN
--     RAISE EXCEPTION 'ROLLBACK_ABORT: 승격 감사기록이 정확히 1건 없음. Owner 에스컬레이션 필요.';
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
--   -- 감사기록 삭제 금지 — 이력 보존 필수. rollback_snapshot은 audit row에 보존됨.
-- END $$;
-- ─────────────────────────────────────────────────────────────────────
--
-- 변경 후 검증 조건:
--   SELECT status FROM runtime_form_schema WHERE id='479a1881...' → APPROVED_FOR_RUNTIME_USE
--   SELECT count(*) FROM runtime_field WHERE form_schema_id='479a1881...' AND status='APPROVED_BY_HUMAN' → 4
--   SELECT count(*) FROM runtime_field WHERE form_schema_id='479a1881...' AND required_status='REQUIRED_BY_HUMAN' → 4
--   GET /document-engine/catalog/DOC-CON-044 → can_create=true
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

  -- P4B: exact field_label (CORR-002 — DB 실증값 4건 재확인)
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND
        ( (field_key = 'construction_project_overview'      AND field_label = '건설공사 개요')
       OR (field_key = 'construction_procedure'             AND field_label = '시공 절차')
       OR (field_key = 'construction_precautions'           AND field_label = '시공 시 주의사항')
       OR (field_key = 'hazardous_work_and_safety_measures' AND field_label = '위험공종 및 안전관리 대책') )
      ) <> 4 THEN
    RAISE EXCEPTION 'ABORT: P4B field_label exact contract mismatch. STOP.';
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

  -- P8: source provenance — catalog_document_id + schema_candidate_id 동시 일치
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = v_schema_id
        AND catalog_document_id = v_catalog_id
        AND schema_candidate_id = v_cand_id) <> 1 THEN
    RAISE EXCEPTION 'ABORT: P8 source provenance mismatch (catalog_document_id or schema_candidate_id). STOP.';
  END IF;

  -- P9: schema version = 1 (CORR-002 — 실행시점 버전 불변 확인)
  IF (SELECT version FROM runtime_form_schema WHERE id = v_schema_id) <> 1 THEN
    RAISE EXCEPTION 'ABORT: P9 schema version != 1. STOP.';
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

  -- G4: document_schema_candidate CANDIDATE 불변 확인 (승격 전 소스 상태)
  IF (SELECT status FROM document_schema_candidate WHERE id = v_cand_id) <> 'CANDIDATE' THEN
    RAISE EXCEPTION 'ABORT: G4 document_schema_candidate.status != CANDIDATE (source drift detected). STOP.';
  END IF;

  -- G5: document_forms.required_fields 원본 계약 재확인 (CORR-002)
  --     4건 전부 is_mandatory=true 검증 (field_key + is_mandatory 교차확인)
  IF (SELECT count(*) FROM document_forms
      WHERE id = v_catalog_id
        AND jsonb_array_length(required_fields) = 4) <> 1 THEN
    RAISE EXCEPTION 'ABORT: G5 required_fields count != 4. STOP.';
  END IF;
  IF (SELECT count(*) FROM jsonb_array_elements(
        (SELECT required_fields FROM document_forms WHERE id = v_catalog_id)
      ) AS elem
      WHERE (elem->>'is_mandatory')::boolean = TRUE) <> 4 THEN
    RAISE EXCEPTION 'ABORT: G5 not all 4 required_fields.is_mandatory=true. STOP.';
  END IF;

  -- ── BEFORE STATE SNAPSHOT ──────────────────────────────────────────
  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'schema_version', (SELECT version FROM runtime_form_schema WHERE id = v_schema_id),
    'fields', (SELECT jsonb_agg(jsonb_build_object(
                 'field_key', field_key, 'field_label', field_label,
                 'status', status, 'required_status', required_status)
                 ORDER BY field_order)
               FROM runtime_field WHERE form_schema_id = v_schema_id)
  ) INTO v_before;

  -- ── [1] runtime_field ×4: CANDIDATE→APPROVED_BY_HUMAN + CANDIDATE_ONLY→REQUIRED_BY_HUMAN ──
  -- 근거: document_forms.required_fields 전 4건 is_mandatory=true (G5 실행시점 재확인)
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
  -- F4: source provenance 불변
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = v_schema_id
        AND catalog_document_id = v_catalog_id
        AND schema_candidate_id = v_cand_id) <> 1 THEN
    RAISE EXCEPTION 'ABORT: F4 final source provenance mismatch. ROLLBACK.';
  END IF;
  -- F5: schema version 불변 (CORR-002)
  IF (SELECT version FROM runtime_form_schema WHERE id = v_schema_id) <> 1 THEN
    RAISE EXCEPTION 'ABORT: F5 schema version changed after promotion. ROLLBACK.';
  END IF;

  -- ── AFTER STATE SNAPSHOT ───────────────────────────────────────────
  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'schema_version', (SELECT version FROM runtime_form_schema WHERE id = v_schema_id),
    'fields', (SELECT jsonb_agg(jsonb_build_object(
                 'field_key', field_key, 'field_label', field_label,
                 'status', status, 'required_status', required_status)
                 ORDER BY field_order)
               FROM runtime_field WHERE form_schema_id = v_schema_id)
  ) INTO v_after;

  -- ── AUDIT LOG ──────────────────────────────────────────────────────
  -- reviewer_id=NULL: Step4D B-1 계약 (nullable 허용, 별도 reviewer identity 계약 없음).
  -- CORR-002: PRJ_STEP4D_REFERENCE = docs/sql/20260825_WP_PERSISTENCE_02A_STEP4D_UP.sql
  INSERT INTO runtime_form_audit_log
    (source_table, source_id, action, schema_version,
     before_state, after_state, reviewer_id, review_comment,
     rollback_snapshot, rollback_available)
  VALUES
    ('runtime_form_schema', v_schema_id, 'PROMOTE_TO_RUNTIME_USE', 1,
     v_before, v_after, NULL,
     'WO-TAI-M004-WEB-ACTIVATION-PILOT-001-CORR-002: DOC-CON-044 NON_LEGAL pilot activation. has_legal_form=FALSE. reviewer_id=NULL per Step4D B-1 contract (docs/sql/20260825_WP_PERSISTENCE_02A_STEP4D_UP.sql). Execution requires explicit Owner+PRJ authorization before running this SQL.',
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
--   SELECT status, version FROM runtime_form_schema WHERE id = '479a1881-3bec-47ac-a8bf-0f8ff8db2cf8';
--   SELECT field_key, field_label, status, required_status FROM runtime_field
--     WHERE form_schema_id = '479a1881-3bec-47ac-a8bf-0f8ff8db2cf8' ORDER BY field_order;
--   GET /document-engine/catalog/DOC-CON-044 → {"can_create": true, "availability": "READY_FOR_EDIT"}
-- =====================================================================
