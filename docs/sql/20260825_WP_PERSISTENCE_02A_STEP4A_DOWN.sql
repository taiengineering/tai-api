-- =====================================================================
-- WP-PERSISTENCE-02A STEP-4A — DOWN / ROLLBACK SQL (§24)
-- =====================================================================
-- !!! NOT EXECUTED — 별도 명시 승인 없이 실행 금지 !!!
-- 목적: STEP-4B materialization 을 정확한 UUID chain 기준으로 안전 제거.
-- 원칙:
--   (1) form_code 광범위 DELETE 금지 → materialize 된 정확한 UUID chain 기준.
--   (2) FK 역순 삭제: runtime_field → runtime_form_schema
--       → document_schema_candidate → document_form_master
--   (3) 삭제 전 외부 FK reference = 0 확인 (runtime_document_data / bridge / 기타).
--       참조가 하나라도 있으면 RAISE EXCEPTION 후 전체 롤백(아무것도 삭제 안 함).
--   (4) 단일 DO 블록 = 원자적. 부분 삭제 없음.
-- 주: GEN-INSPECT-RESULT-001 은 유일 식별자이나, 안전을 위해 실제 삭제 대상은
--     "그 form_code 로 materialize 된 master 1건과 그 하위 chain"으로 한정한다.
-- =====================================================================

-- 실측 FK (2026-08-25):
--   runtime_form_schema(form_schema_id) 참조:
--     company_form_mapping, generated_document, rendered_form,
--     runtime_checklist_item, runtime_document_data, runtime_evidence_field, runtime_field
--   document_schema_candidate(schema_candidate_id) 참조:
--     checklist_item_candidate, evidence_field_candidate, field_candidate, runtime_form_schema
--   + semantic: runtime_inspection_bridge.runtime_form_schema_id (FK 아님, guard 대상)
-- 자기 소유 하위(우리가 만든 runtime_field / 우리 candidate 를 가리키는 우리 schema)는
-- 정상 삭제 대상이므로 guard 에서 제외. 그 외 참조가 하나라도 있으면 전체 중단.

DO $$
DECLARE
  v_master_id    uuid;
  v_candidate_id uuid;
  v_schema_id    uuid;
  v_master_cnt   integer;
  v_cand_cnt     integer;
  v_schema_cnt   integer;
  v_field_cnt    integer;
  v_field_exact  integer;
  v_ref          integer;
BEGIN
  -- ---------------------------------------------------------------
  -- 대상 UUID chain 확보 + 각 단계 count = exactly 1 확인 (아니면 STOP)
  -- ---------------------------------------------------------------
  SELECT count(*) INTO v_master_cnt
  FROM document_form_master WHERE form_code = 'GEN-INSPECT-RESULT-001';
  IF v_master_cnt = 0 THEN
    RAISE NOTICE 'DOWN: no GEN-INSPECT-RESULT-001 master. nothing to do.';
    RETURN;
  END IF;
  IF v_master_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN: master count = % (expected 1). manual review.', v_master_cnt;
  END IF;
  SELECT id INTO v_master_id
  FROM document_form_master WHERE form_code = 'GEN-INSPECT-RESULT-001';

  SELECT count(*) INTO v_cand_cnt
  FROM document_schema_candidate
  WHERE source_table='document_form_master' AND source_id = v_master_id
    AND form_code = 'GEN-INSPECT-RESULT-001';
  IF v_cand_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN: candidate count = % (expected 1). manual review.', v_cand_cnt;
  END IF;
  SELECT id INTO v_candidate_id
  FROM document_schema_candidate
  WHERE source_table='document_form_master' AND source_id = v_master_id
    AND form_code = 'GEN-INSPECT-RESULT-001';

  SELECT count(*) INTO v_schema_cnt
  FROM runtime_form_schema WHERE schema_candidate_id = v_candidate_id;
  IF v_schema_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN: runtime schema count = % (expected 1). manual review.', v_schema_cnt;
  END IF;
  SELECT id INTO v_schema_id
  FROM runtime_form_schema WHERE schema_candidate_id = v_candidate_id;

  -- runtime_field 정확히 5건 + 정확한 5 field_key 확인 (예상 밖 필드 있으면 STOP)
  SELECT count(*) INTO v_field_cnt
  FROM runtime_field WHERE form_schema_id = v_schema_id;
  IF v_field_cnt <> 5 THEN
    RAISE EXCEPTION 'ABORT DOWN: runtime_field count = % (expected 5). manual review.', v_field_cnt;
  END IF;
  SELECT count(*) INTO v_field_exact
  FROM runtime_field
  WHERE form_schema_id = v_schema_id
    AND field_key IN ('inspection_subject','inspected_at','inspection_title',
                      'inspector_display','inspection_results');
  IF v_field_exact <> 5 THEN
    RAISE EXCEPTION 'ABORT DOWN: unexpected field_key present (exact match=%/5). manual review.', v_field_exact;
  END IF;

  -- ---------------------------------------------------------------
  -- FK REFERENCE GUARD — schema 를 참조하는 모든 테이블 (자기 소유 runtime_field 제외)
  --   하나라도 참조 있으면 전체 중단(삭제 0).
  -- ---------------------------------------------------------------
  SELECT
    (SELECT count(*) FROM company_form_mapping   WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM generated_document     WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM rendered_form          WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM runtime_checklist_item WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM runtime_document_data  WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM runtime_evidence_field WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM runtime_inspection_bridge WHERE runtime_form_schema_id = v_schema_id)
  INTO v_ref;
  IF v_ref <> 0 THEN
    RAISE EXCEPTION 'ABORT DOWN: schema referenced elsewhere (total refs=%). rollback unsafe.', v_ref;
  END IF;

  -- candidate 를 참조하는 모든 테이블 (자기 소유 runtime_form_schema 제외)
  SELECT
    (SELECT count(*) FROM field_candidate            WHERE schema_candidate_id = v_candidate_id)
  + (SELECT count(*) FROM checklist_item_candidate   WHERE schema_candidate_id = v_candidate_id)
  + (SELECT count(*) FROM evidence_field_candidate   WHERE schema_candidate_id = v_candidate_id)
  INTO v_ref;
  IF v_ref <> 0 THEN
    RAISE EXCEPTION 'ABORT DOWN: candidate referenced by *_candidate (refs=%). rollback unsafe.', v_ref;
  END IF;

  -- ---------------------------------------------------------------
  -- FK 역순 삭제 (UUID chain 한정)
  -- ---------------------------------------------------------------
  DELETE FROM runtime_field             WHERE form_schema_id = v_schema_id;
  DELETE FROM runtime_form_schema       WHERE id = v_schema_id;
  DELETE FROM document_schema_candidate WHERE id = v_candidate_id;
  DELETE FROM document_form_master      WHERE id = v_master_id;

  RAISE NOTICE 'DOWN OK: removed chain master=% candidate=% schema=% fields=5',
    v_master_id, v_candidate_id, v_schema_id;
END $$;

-- =====================================================================
-- END DOWN SQL — NOT EXECUTED.
-- 실행 조건: (1) 별도 명시 승인, (2) runtime_document_data/bridge 참조 0 확인 후.
-- =====================================================================
