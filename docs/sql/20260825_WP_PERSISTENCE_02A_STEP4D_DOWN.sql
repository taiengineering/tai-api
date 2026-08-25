-- =====================================================================
-- WP-PERSISTENCE-02A STEP-4D — DOWN / PROMOTION ROLLBACK SQL (§14, §15)
-- =====================================================================
-- !!! NOT EXECUTED — 별도 명시 승인 없이 실행 금지 !!!
-- 목적: STEP-4D 승격만 원복. STEP-4B materialized 8 rows 는 삭제하지 않는다.
--   schema APPROVED_FOR_RUNTIME_USE → CANDIDATE
--   field ×5 APPROVED_BY_HUMAN → CANDIDATE, required_status target → CANDIDATE_ONLY
--   (DELETE 없음. master/candidate/schema/field row 유지.)
--   AUDIT (A-2): promotion audit 삭제 안 함(역사 보존). rollback_available true→false +
--                ROLLBACK_RUNTIME_PROMOTION audit 1건 추가.
-- 대상 schema UUID: dc79ac3c-388c-42dc-b029-3dd9bda54a47
-- 원자성: 단일 DO 블록. 실패 시 전체 롤백.
-- =====================================================================

DO $$
DECLARE
  v_schema_id uuid := 'dc79ac3c-388c-42dc-b029-3dd9bda54a47';
  v_cnt       integer;
  v_ref       integer;
  v_audit_cnt integer;
  v_before    jsonb;
  v_after     jsonb;
BEGIN
  -- 존재 확인
  IF (SELECT count(*) FROM runtime_form_schema WHERE id = v_schema_id) <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN: schema not found (id=%). STOP.', v_schema_id;
  END IF;

  -- DOWN GUARD (§15): runtime-use 이후 생성 가능한 참조 = 0 확인.
  SELECT
    (SELECT count(*) FROM runtime_inspection_bridge WHERE runtime_form_schema_id = v_schema_id)
  + (SELECT count(*) FROM runtime_document_data     WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM generated_document        WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM rendered_form             WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM company_form_mapping      WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM runtime_checklist_item    WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM runtime_evidence_field    WHERE form_schema_id = v_schema_id)
  INTO v_ref;
  IF v_ref <> 0 THEN
    RAISE EXCEPTION 'ABORT DOWN: schema referenced after runtime-use (refs=%). PROMOTION_ROLLBACK_UNSAFE. STOP.', v_ref;
  END IF;

  -- 현재 상태 exact 확인 (승격된 상태일 때만 원복. 예상 밖이면 STOP)
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = v_schema_id AND status = 'APPROVED_FOR_RUNTIME_USE') <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN: schema not APPROVED_FOR_RUNTIME_USE (current not promoted). STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id AND status = 'APPROVED_BY_HUMAN') <> 5 THEN
    RAISE EXCEPTION 'ABORT DOWN: field not 5 APPROVED_BY_HUMAN. STOP.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND required_status='REQUIRED_BY_HUMAN') <> 3
     OR (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND required_status='NOT_REQUIRED') <> 2 THEN
    RAISE EXCEPTION 'ABORT DOWN: required_status not exact target (3/2). STOP.';
  END IF;

  -- AUDIT GUARD (A-2): 활성 PROMOTE audit 이 정확히 1건 + rollback_available=true 일 때만.
  SELECT count(*) INTO v_audit_cnt
  FROM runtime_form_audit_log
  WHERE source_table='runtime_form_schema' AND source_id = v_schema_id
    AND action='PROMOTE_TO_RUNTIME_USE' AND rollback_available = true;
  IF v_audit_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN: active PROMOTE audit count = % (expected 1, rollback_available=true). STOP.', v_audit_cnt;
  END IF;

  -- 원복 전 snapshot (rollback audit 용)
  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'fields', (SELECT jsonb_agg(jsonb_build_object(
                 'field_key', field_key, 'status', status, 'required_status', required_status)
                 ORDER BY field_order)
               FROM runtime_field WHERE form_schema_id = v_schema_id)
  ) INTO v_before;

  -- [1] schema 원복: APPROVED_FOR_RUNTIME_USE → CANDIDATE
  UPDATE runtime_form_schema
  SET status = 'CANDIDATE', updated_at = now()
  WHERE id = v_schema_id AND status = 'APPROVED_FOR_RUNTIME_USE';
  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN: schema revert affected % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  -- [2] field ×5 원복: APPROVED_BY_HUMAN → CANDIDATE, required_status → CANDIDATE_ONLY
  UPDATE runtime_field
  SET status = 'CANDIDATE', required_status = 'CANDIDATE_ONLY'
  WHERE form_schema_id = v_schema_id AND status = 'APPROVED_BY_HUMAN';
  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 5 THEN
    RAISE EXCEPTION 'ABORT DOWN: field revert affected % rows (expected 5). ROLLBACK.', v_cnt;
  END IF;

  -- FINAL ASSERT (원복 후 = STEP-4B 직후 상태와 동일해야)
  IF (SELECT status FROM runtime_form_schema WHERE id = v_schema_id) <> 'CANDIDATE' THEN
    RAISE EXCEPTION 'ABORT DOWN: schema not reverted to CANDIDATE. ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id
      AND status='CANDIDATE' AND required_status='CANDIDATE_ONLY') <> 5 THEN
    RAISE EXCEPTION 'ABORT DOWN: field not reverted to 5 CANDIDATE/CANDIDATE_ONLY. ROLLBACK.';
  END IF;
  -- 8 row 유지 확인 (삭제 없음)
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id) <> 5 THEN
    RAISE EXCEPTION 'ABORT DOWN: field row count changed (must stay 5, no delete). ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM document_form_master WHERE form_code='GEN-INSPECT-RESULT-001') <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN: master row changed (must stay 1, no delete). ROLLBACK.';
  END IF;

  -- AUDIT ROLLBACK 처리 (A-2): promotion audit 는 삭제하지 않는다(역사 보존).
  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'fields', (SELECT jsonb_agg(jsonb_build_object(
                 'field_key', field_key, 'status', status, 'required_status', required_status)
                 ORDER BY field_order)
               FROM runtime_field WHERE form_schema_id = v_schema_id)
  ) INTO v_after;

  UPDATE runtime_form_audit_log
  SET rollback_available = false
  WHERE source_table='runtime_form_schema' AND source_id = v_schema_id
    AND action='PROMOTE_TO_RUNTIME_USE' AND rollback_available = true;
  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN: promotion audit rollback_available flip affected % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  INSERT INTO runtime_form_audit_log
    (source_table, source_id, action, schema_version,
     before_state, after_state, reviewer_id, review_comment,
     rollback_snapshot, rollback_available)
  VALUES
    ('runtime_form_schema', v_schema_id, 'ROLLBACK_RUNTIME_PROMOTION', 1,
     v_before, v_after, NULL,
     'WP-PERSISTENCE-02A STEP-4D promotion rollback. Reverts schema/fields to CANDIDATE. Original PROMOTE audit preserved (rollback_available flipped to false).',
     NULL, false);

  RAISE NOTICE 'DOWN OK (promotion-only revert): schema=% back to CANDIDATE, fields=5 back to CANDIDATE/CANDIDATE_ONLY. 8 rows preserved. audit history preserved.', v_schema_id;
END $$;

-- =====================================================================
-- END DOWN SQL — NOT EXECUTED.
-- 실행 조건: (1) 별도 명시 승인, (2) runtime-use 이후 참조 0 확인 후.
-- 주: 이 DOWN 은 STEP-4D 승격만 원복. STEP-4B 8 rows 는 보존.
--     8 rows 자체 제거는 STEP-4A DOWN (tai-api@9c027595) 사용.
-- =====================================================================
