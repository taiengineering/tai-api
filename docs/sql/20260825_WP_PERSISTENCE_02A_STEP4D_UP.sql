-- =====================================================================
-- WP-PERSISTENCE-02A STEP-4D — UP SQL (HUMAN APPROVAL / RUNTIME PROMOTION)
-- =====================================================================
-- !!! NOT EXECUTED — STEP-4D 명시적 승인 전 실행 금지 !!!
-- 목적: GEN-INSPECT-RESULT-001 을 CANDIDATE → APPROVED_BY_HUMAN
--       → APPROVED_FOR_RUNTIME_USE 로 승격 (시스템 최초 APPROVED runtime schema).
-- 대상 schema UUID: dc79ac3c-388c-42dc-b029-3dd9bda54a47
-- 원자성: 단일 DO 블록. 실패 시 전체 롤백. 부분 승격 없음.
-- candidate.status = 건드리지 않음 (§3, enum 에 승격값 없음).
--
-- ★ AUDIT 정책 (대표 결정 A = A-2 확정):
--   status 승격 + runtime_form_audit_log 에 audit row 1건 INSERT.
--   reviewer_id=NULL (nullable 확인, 결정 B-1). action='PROMOTE_TO_RUNTIME_USE'.
-- 보강(2차): total field count=5 guard / preexisting promotion audit=0 guard /
--   audit INSERT rowcount=1 / final promotion audit count=1 assertion.
-- =====================================================================

DO $$
DECLARE
  v_schema_id  uuid := 'dc79ac3c-388c-42dc-b029-3dd9bda54a47';
  v_before     jsonb;
  v_after      jsonb;
  v_cnt        integer;
BEGIN
  -- PRECONDITION ASSERT (승격 전 현재 상태 exact 재확인, 아니면 STOP)
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = v_schema_id AND status = 'CANDIDATE'
        AND form_type='CUSTOM' AND document_family='DOCUMENT'
        AND field_count=5 AND checklist_count=0 AND evidence_count=0) <> 1 THEN
    RAISE EXCEPTION 'ABORT: schema precondition mismatch (not CANDIDATE/exact). STOP.';
  END IF;

  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id
        AND status='CANDIDATE' AND required_status='CANDIDATE_ONLY') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field precondition mismatch (not 5 CANDIDATE/CANDIDATE_ONLY). STOP.';
  END IF;

  -- 전체 runtime_field count = 5 (예상 밖 6번째 field 방지)
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id) <> 5 THEN
    RAISE EXCEPTION 'ABORT: total runtime_field count <> 5. STOP.';
  END IF;

  -- exact key/type/order 5/5
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND
        ( (field_key='inspection_subject' AND input_type='text'      AND field_order=1)
       OR (field_key='inspected_at'       AND input_type='datetime'  AND field_order=2)
       OR (field_key='inspection_title'   AND input_type='text'      AND field_order=3)
       OR (field_key='inspector_display'  AND input_type='text'      AND field_order=4)
       OR (field_key='inspection_results' AND input_type='multi_row' AND field_order=5) )
      ) <> 5 THEN
    RAISE EXCEPTION 'ABORT: field exact contract mismatch. STOP.';
  END IF;

  -- bridge / runtime_document 참조 0 (승격 전 아직 사용 안 됨)
  IF (SELECT count(*) FROM runtime_inspection_bridge WHERE runtime_form_schema_id = v_schema_id) <> 0 THEN
    RAISE EXCEPTION 'ABORT: bridge already references schema. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_document_data WHERE form_schema_id = v_schema_id) <> 0 THEN
    RAISE EXCEPTION 'ABORT: runtime_document_data already references schema. STOP.';
  END IF;

  -- preexisting promotion audit = 0 (실행 순간 재확인, STEP-4A 패턴)
  IF (SELECT count(*) FROM runtime_form_audit_log
      WHERE source_table = 'runtime_form_schema' AND source_id = v_schema_id
        AND action = 'PROMOTE_TO_RUNTIME_USE') <> 0 THEN
    RAISE EXCEPTION 'ABORT: preexisting promotion audit found. STOP.';
  END IF;

  -- before_state snapshot (audit / rollback 용)
  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'fields', (SELECT jsonb_agg(jsonb_build_object(
                 'field_key', field_key, 'status', status, 'required_status', required_status)
                 ORDER BY field_order)
               FROM runtime_field WHERE form_schema_id = v_schema_id)
  ) INTO v_before;

  -- [1] runtime_field ×5: CANDIDATE→APPROVED_BY_HUMAN + required_status→target
  UPDATE runtime_field
  SET status = 'APPROVED_BY_HUMAN',
      required_status = CASE field_key
        WHEN 'inspection_subject'  THEN 'REQUIRED_BY_HUMAN'
        WHEN 'inspected_at'        THEN 'REQUIRED_BY_HUMAN'
        WHEN 'inspection_results'  THEN 'REQUIRED_BY_HUMAN'
        WHEN 'inspection_title'    THEN 'NOT_REQUIRED'
        WHEN 'inspector_display'   THEN 'NOT_REQUIRED'
      END
  WHERE form_schema_id = v_schema_id
    AND status = 'CANDIDATE' AND required_status = 'CANDIDATE_ONLY';

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 5 THEN
    RAISE EXCEPTION 'ABORT: field UPDATE affected % rows (expected 5). ROLLBACK.', v_cnt;
  END IF;

  -- ASSERT field exact (승격 후)
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND status='APPROVED_BY_HUMAN') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field not all APPROVED_BY_HUMAN. ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND required_status='REQUIRED_BY_HUMAN') <> 3 THEN
    RAISE EXCEPTION 'ABORT: REQUIRED_BY_HUMAN <> 3. ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND required_status='NOT_REQUIRED') <> 2 THEN
    RAISE EXCEPTION 'ABORT: NOT_REQUIRED <> 2. ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND required_status='CANDIDATE_ONLY') <> 0 THEN
    RAISE EXCEPTION 'ABORT: CANDIDATE_ONLY still present. ROLLBACK.';
  END IF;
  -- exact field_key ↔ required_status 매핑 검증
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND
        ( (field_key='inspection_subject'  AND required_status='REQUIRED_BY_HUMAN')
       OR (field_key='inspected_at'        AND required_status='REQUIRED_BY_HUMAN')
       OR (field_key='inspection_results'  AND required_status='REQUIRED_BY_HUMAN')
       OR (field_key='inspection_title'    AND required_status='NOT_REQUIRED')
       OR (field_key='inspector_display'   AND required_status='NOT_REQUIRED') )
      ) <> 5 THEN
    RAISE EXCEPTION 'ABORT: field_key↔required_status target mismatch. ROLLBACK.';
  END IF;

  -- [2] runtime_form_schema: CANDIDATE→APPROVED_BY_HUMAN (1차)
  UPDATE runtime_form_schema
  SET status = 'APPROVED_BY_HUMAN', updated_at = now()
  WHERE id = v_schema_id AND status = 'CANDIDATE';
  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT: schema APPROVED_BY_HUMAN UPDATE affected % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  -- GATE ASSERT (§8 G1~G10 승격 전 최종 게이트, 실측 기반)
  -- G1: CUSTOM + sector NULL + 법령 미종속 (law_article 포함)
  IF NOT EXISTS (
    SELECT 1 FROM runtime_form_schema s
    JOIN document_form_master m ON m.form_code = 'GEN-INSPECT-RESULT-001'
    WHERE s.id = v_schema_id AND s.form_type='CUSTOM'
      AND m.sector IS NULL AND m.law_name IS NULL
      AND m.law_article IS NULL AND m.legal_basis IS NULL
  ) THEN
    RAISE EXCEPTION 'ABORT: G1 fail (form_type/sector/law). ROLLBACK.';
  END IF;
  -- G2: source_inspection_id 필드 부재
  IF EXISTS (SELECT 1 FROM runtime_field WHERE form_schema_id = v_schema_id AND field_key='source_inspection_id') THEN
    RAISE EXCEPTION 'ABORT: G2 fail (source_inspection_id in fields). ROLLBACK.';
  END IF;
  -- G10: 금지 필드 부재 + counts
  IF EXISTS (SELECT 1 FROM runtime_field WHERE form_schema_id = v_schema_id
             AND field_key IN ('overall_result','corrective_summary','evidence_files')) THEN
    RAISE EXCEPTION 'ABORT: G10 fail (forbidden field present). ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_evidence_field WHERE form_schema_id = v_schema_id) <> 0 THEN
    RAISE EXCEPTION 'ABORT: evidence <> 0. ROLLBACK.';
  END IF;

  -- [3] runtime_form_schema: APPROVED_BY_HUMAN→APPROVED_FOR_RUNTIME_USE (2차)
  UPDATE runtime_form_schema
  SET status = 'APPROVED_FOR_RUNTIME_USE', updated_at = now()
  WHERE id = v_schema_id AND status = 'APPROVED_BY_HUMAN';
  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT: schema APPROVED_FOR_RUNTIME_USE UPDATE affected % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  -- FINAL ASSERT (§12 COMMIT 전 전수 검증)
  IF (SELECT status FROM runtime_form_schema WHERE id = v_schema_id) <> 'APPROVED_FOR_RUNTIME_USE' THEN
    RAISE EXCEPTION 'ABORT: final schema status not APPROVED_FOR_RUNTIME_USE. ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND status='APPROVED_BY_HUMAN') <> 5 THEN
    RAISE EXCEPTION 'ABORT: final field status not 5 APPROVED_BY_HUMAN. ROLLBACK.';
  END IF;
  -- candidate 불변 확인 (건드리지 않았음)
  IF (SELECT status FROM document_schema_candidate
      WHERE form_code='GEN-INSPECT-RESULT-001') <> 'CANDIDATE' THEN
    RAISE EXCEPTION 'ABORT: candidate.status changed (must stay CANDIDATE). ROLLBACK.';
  END IF;
  -- schema 헤더 불변 (form_type/document_family/counts)
  IF (SELECT count(*) FROM runtime_form_schema WHERE id = v_schema_id
      AND form_type='CUSTOM' AND document_family='DOCUMENT'
      AND field_count=5 AND checklist_count=0 AND evidence_count=0) <> 1 THEN
    RAISE EXCEPTION 'ABORT: schema header drift. ROLLBACK.';
  END IF;

  -- after_state snapshot
  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'fields', (SELECT jsonb_agg(jsonb_build_object(
                 'field_key', field_key, 'status', status, 'required_status', required_status)
                 ORDER BY field_order)
               FROM runtime_field WHERE form_schema_id = v_schema_id)
  ) INTO v_after;

  -- [AUDIT] runtime_form_audit_log 기록 (A-2 / reviewer_id=NULL B-1)
  INSERT INTO runtime_form_audit_log
    (source_table, source_id, action, schema_version,
     before_state, after_state, reviewer_id, review_comment,
     rollback_snapshot, rollback_available)
  VALUES
    ('runtime_form_schema', v_schema_id, 'PROMOTE_TO_RUNTIME_USE', 1,
     v_before, v_after, NULL,
     'Human approval explicitly authorized under WP-PERSISTENCE-02A STEP-4D governance. reviewer_id is NULL because no canonical schema-governance reviewer identity contract currently exists.',
     v_before, true);

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT: promotion audit INSERT affected % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  -- final: promotion audit 정확히 1건
  IF (SELECT count(*) FROM runtime_form_audit_log
      WHERE source_table = 'runtime_form_schema' AND source_id = v_schema_id
        AND action = 'PROMOTE_TO_RUNTIME_USE') <> 1 THEN
    RAISE EXCEPTION 'ABORT: promotion audit count <> 1. ROLLBACK.';
  END IF;

  RAISE NOTICE 'PROMOTED OK: schema=% status=APPROVED_FOR_RUNTIME_USE fields=5 APPROVED_BY_HUMAN', v_schema_id;
END $$;

-- =====================================================================
-- END UP SQL — NOT EXECUTED.
-- 실행 승인(STEP-4D) 시: 이 파일 전체를 단일 execute_sql 호출로 실행.
-- 실행 직후 VERIFY.sql 로 승격 결과 확인.
-- =====================================================================
