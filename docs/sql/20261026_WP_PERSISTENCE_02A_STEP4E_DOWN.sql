-- =====================================================================
-- WP-PERSISTENCE-02A STEP-4E — DOWN / PROMOTION ROLLBACK SQL
-- =====================================================================
-- !!! NOT EXECUTED — 별도 명시 Owner 승인 없이 실행 금지 !!!
-- 목적: STEP-4E Evidence 포함 승격 원복
--   runtime_form_schema    APPROVED_FOR_RUNTIME_USE → CANDIDATE
--   runtime_evidence_field APPROVED_BY_HUMAN → CANDIDATE
--   runtime_field          불변 (STEP4E_UP이 변경하지 않음 — G3 승인 보존)
-- 계약 기준: WO-027-EVIDENCE-CONTRACT-C2-FINAL.md §4-4 (P0-4 정합화 반영)
-- 불변: evidence_field_candidate.status = 변경 없음 (독립 결정 보존)
-- 불변: runtime_field.status = 변경 없음 (STEP4E_UP 변경 범위 외)
-- 대상 schema UUID: 4e07df2e-904a-4fe6-ad18-cecc0f5e57f3
-- 원자성: 단일 DO 블록. 실패 시 전체 롤백. 성공 Audit = 동일 TX 커밋.
-- 실패 시: DO 블록 자동 롤백 → 파일 하단 실패 Audit SQL을 별도 TX로 실행
-- =====================================================================

DO $$
DECLARE
  v_schema_id       uuid := '4e07df2e-904a-4fe6-ad18-cecc0f5e57f3';
  v_cnt             integer;
  v_ref             integer;
  v_audit_cnt       integer;
  v_rollback_cnt    integer;
  v_field_cnt       integer;
  v_evidence_cnt    integer;
  v_before          jsonb;
  v_after           jsonb;
BEGIN
  -- ─── 진입 조건 [D1~D5] ───────────────────────────────────────────

  -- [D1] rollback_available=true인 PROMOTE_TO_RUNTIME_USE_WITH_EVIDENCE audit 1건
  SELECT count(*) INTO v_audit_cnt
  FROM runtime_form_audit_log
  WHERE source_table = 'runtime_form_schema' AND source_id = v_schema_id
    AND action = 'PROMOTE_TO_RUNTIME_USE_WITH_EVIDENCE'
    AND rollback_available = true;
  IF v_audit_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT [D1]: rollback_available Audit 없음 (count=%). STOP.', v_audit_cnt;
  END IF;

  -- [D2] schema status = APPROVED_FOR_RUNTIME_USE
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = v_schema_id AND status = 'APPROVED_FOR_RUNTIME_USE') <> 1 THEN
    RAISE EXCEPTION 'ABORT [D2]: schema not APPROVED_FOR_RUNTIME_USE. STOP.';
  END IF;

  -- [D3] runtime_field 상태 확인 (APPROVED_BY_HUMAN 보존 검증 — 불변 확인용)
  -- STEP4E_UP이 runtime_field를 변경하지 않으므로 DOWN도 변경하지 않음.
  -- 그러나 APPROVED_BY_HUMAN이 아닌 행이 있으면 비정상 상태이므로 ABORT.
  SELECT count(*) INTO v_field_cnt
  FROM runtime_field WHERE form_schema_id = v_schema_id;

  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id AND status <> 'APPROVED_BY_HUMAN') > 0 THEN
    RAISE EXCEPTION 'ABORT [D3]: runtime_field 중 APPROVED_BY_HUMAN이 아닌 행 (비정상 상태). STOP.';
  END IF;

  -- [D4] runtime_evidence_field 전 행 APPROVED_BY_HUMAN
  SELECT count(*) INTO v_evidence_cnt
  FROM runtime_evidence_field WHERE form_schema_id = v_schema_id;

  IF (SELECT count(*) FROM runtime_evidence_field
      WHERE form_schema_id = v_schema_id AND status <> 'APPROVED_BY_HUMAN') > 0 THEN
    RAISE EXCEPTION 'ABORT [D4]: runtime_evidence_field 중 APPROVED_BY_HUMAN이 아닌 행. STOP.';
  END IF;

  -- [D5] 중복 롤백 차단 (이미 롤백 수행된 경우)
  SELECT count(*) INTO v_rollback_cnt
  FROM runtime_form_audit_log
  WHERE source_table = 'runtime_form_schema' AND source_id = v_schema_id
    AND action = 'ROLLBACK_FROM_RUNTIME_USE_WITH_EVIDENCE';
  IF v_rollback_cnt > 0 THEN
    RAISE EXCEPTION 'ABORT [D5]: 이미 STEP4E 롤백 수행됨 (중복 롤백 차단). STOP.';
  END IF;

  -- ─── 롤백 차단 [B1, B3] ────────────────────────────────────────────

  -- [B1] 승격 이후 참조 존재 → ABORT
  SELECT
    (SELECT count(*) FROM runtime_inspection_bridge WHERE runtime_form_schema_id = v_schema_id)
  + (SELECT count(*) FROM runtime_document_data      WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM generated_document         WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM rendered_form              WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM company_form_mapping       WHERE form_schema_id = v_schema_id)
  + (SELECT count(*) FROM runtime_checklist_item     WHERE form_schema_id = v_schema_id)
  INTO v_ref;
  IF v_ref > 0 THEN
    RAISE EXCEPTION 'ABORT [B1]: 승격 후 생성된 참조 %건 존재. PROMOTION_ROLLBACK_UNSAFE. STOP.', v_ref;
  END IF;

  -- [B3] Audit rollback_available=true 재확인 (B3 계약)
  IF (SELECT count(*) FROM runtime_form_audit_log
      WHERE source_table = 'runtime_form_schema' AND source_id = v_schema_id
        AND action = 'PROMOTE_TO_RUNTIME_USE_WITH_EVIDENCE'
        AND rollback_available = false) > 0 THEN
    RAISE EXCEPTION 'ABORT [B3]: rollback_available=false Audit 존재. 이미 롤백됨. STOP.';
  END IF;

  -- ─── 대상 행 잠금 (동시 변경 통제) ────────────────────────────────
  -- runtime_field는 변경하지 않으므로 잠금하지 않음

  PERFORM 1 FROM runtime_form_schema WHERE id = v_schema_id FOR UPDATE;
  PERFORM 1 FROM runtime_evidence_field WHERE form_schema_id = v_schema_id FOR UPDATE;

  -- ─── 롤백 전 snapshot ──────────────────────────────────────────────

  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'fields_preserved', jsonb_build_object(
      'count', v_field_cnt,
      'note', 'runtime_field unchanged (STEP4E_UP did not modify runtime_field)'),
    'evidence_fields', (SELECT jsonb_agg(jsonb_build_object(
                 'id', id, 'status', status,
                 'evidence_candidate_id', evidence_candidate_id))
               FROM runtime_evidence_field WHERE form_schema_id = v_schema_id)
  ) INTO v_before;

  -- ─── 롤백 순서 ───────────────────────────────────────────────────

  -- [1] runtime_form_schema → CANDIDATE
  UPDATE runtime_form_schema
  SET status = 'CANDIDATE', updated_at = now()
  WHERE id = v_schema_id AND status = 'APPROVED_FOR_RUNTIME_USE';
  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN [1]: schema revert % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  -- [2] runtime_evidence_field → CANDIDATE
  UPDATE runtime_evidence_field
  SET status = 'CANDIDATE'
  WHERE form_schema_id = v_schema_id AND status = 'APPROVED_BY_HUMAN';
  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> v_evidence_cnt THEN
    RAISE EXCEPTION 'ABORT DOWN [2]: evidence_field revert % rows (expected %). ROLLBACK.', v_cnt, v_evidence_cnt;
  END IF;

  -- ─── FINAL ASSERT ─────────────────────────────────────────────────

  IF (SELECT status FROM runtime_form_schema WHERE id = v_schema_id) <> 'CANDIDATE' THEN
    RAISE EXCEPTION 'ABORT DOWN FINAL: schema not CANDIDATE. ROLLBACK.';
  END IF;
  IF (SELECT count(*) FROM runtime_evidence_field
      WHERE form_schema_id = v_schema_id AND status = 'CANDIDATE') <> v_evidence_cnt THEN
    RAISE EXCEPTION 'ABORT DOWN FINAL: evidence_field not all CANDIDATE. ROLLBACK.';
  END IF;
  -- runtime_field는 변경하지 않았으므로 APPROVED_BY_HUMAN 유지 검증
  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id AND status = 'APPROVED_BY_HUMAN') <> v_field_cnt THEN
    RAISE EXCEPTION 'ABORT DOWN FINAL: runtime_field state changed unexpectedly. ROLLBACK.';
  END IF;

  -- ─── after snapshot ────────────────────────────────────────────────

  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'fields_preserved', jsonb_build_object(
      'count', v_field_cnt,
      'note', 'runtime_field unchanged (STEP4E_UP did not modify runtime_field)'),
    'evidence_fields', (SELECT jsonb_agg(jsonb_build_object(
                 'id', id, 'status', status))
               FROM runtime_evidence_field WHERE form_schema_id = v_schema_id)
  ) INTO v_after;

  -- ─── Audit: promotion rollback_available flip (C2-FINAL §4-4) ──────

  UPDATE runtime_form_audit_log
  SET rollback_available = false
  WHERE source_table = 'runtime_form_schema' AND source_id = v_schema_id
    AND action = 'PROMOTE_TO_RUNTIME_USE_WITH_EVIDENCE'
    AND rollback_available = true;
  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN: Audit rollback_available flip % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  -- ─── 성공 Audit INSERT (동일 TX — C2-FINAL §4-4 성공 경로) ──────────

  INSERT INTO runtime_form_audit_log
    (source_table, source_id, action, schema_version,
     before_state, after_state, reviewer_id, review_comment,
     rollback_snapshot, rollback_available)
  VALUES
    ('runtime_form_schema', v_schema_id,
     'ROLLBACK_FROM_RUNTIME_USE_WITH_EVIDENCE', 1,
     v_before, v_after, NULL,
     'STEP4E Evidence 포함 승격 롤백. evidence_field_candidate.status 불변. runtime_field 불변(STEP4E_UP 변경 범위 외, G3 승인 보존). C2-FINAL §4-4 P0-4 정합화.',
     NULL, false);

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT DOWN: rollback Audit INSERT % rows. ROLLBACK.', v_cnt;
  END IF;

  RAISE NOTICE 'STEP4E_DOWN OK: schema=% CANDIDATE evidence=% CANDIDATE — fields(%) APPROVED_BY_HUMAN 보존',
    v_schema_id, v_evidence_cnt, v_field_cnt;
END $$;

-- =====================================================================
-- 실패 Audit (C2-FINAL §4-4 실패 경로)
-- ─────────────────────────────────────────────────────────────────────
-- DO 블록에서 RAISE EXCEPTION 발생 시 트랜잭션 전체가 자동 롤백됩니다.
-- DB 상태는 롤백 시도 이전으로 복원됩니다.
-- 실패 Audit INSERT는 이 파일에 포함하지 않습니다.
-- → 실패 Audit을 기록하려면 별도 파일을 새 세션에서 실행하십시오:
--   20261026_WP_PERSISTENCE_02A_STEP4E_DOWN_FAIL_AUDIT.sql
-- =====================================================================
-- END STEP4E_DOWN SQL — NOT EXECUTED.
