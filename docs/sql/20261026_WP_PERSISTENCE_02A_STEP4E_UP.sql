-- =====================================================================
-- WP-PERSISTENCE-02A STEP-4E — UP SQL (Evidence 포함 서식 승격)
-- =====================================================================
-- !!! NOT EXECUTED — G4 승격 별도 Owner 승인 전 실행 금지 !!!
-- 목적: DOC-CON-048 (재하도급 승낙 통보서) evidence 포함 서식 승격
--       CANDIDATE → APPROVED_BY_HUMAN → APPROVED_FOR_RUNTIME_USE
-- 계약 기준: WO-027-EVIDENCE-CONTRACT-C2-FINAL.md §4-2
-- 대상 식별자 (C2-FINAL §10):
--   runtime_form_schema.id      = 4e07df2e-904a-4fe6-ad18-cecc0f5e57f3
--   document_schema_candidate   = 2f41ab16-4748-4bf7-84a3-55a20f74efda
--   runtime_evidence_field.id   = 948088d5-627f-4825-a906-2b86a3d27de5
--   evidence_field_candidate.id = 5e5687b3-e62f-480c-ad75-1efc41706e3b
-- 원자성: 단일 DO 블록. 실패 시 전체 롤백. 부분 승격 없음.
-- STEP4D 차이: evidence_count ≥ 1 허용, evidence 상태 전이 포함.
-- ※ 실행 전: v_reviewer_id를 G4 승격 승인자 UUID로 교체할 것 (NULL 금지 — C2-FINAL §4-3)
-- =====================================================================

DO $$
DECLARE
  v_schema_id        uuid := '4e07df2e-904a-4fe6-ad18-cecc0f5e57f3';
  v_candidate_id     uuid := '2f41ab16-4748-4bf7-84a3-55a20f74efda';
  v_reviewer_id      uuid := NULL;   -- ★ 실행 전 G4 승격 승인자 UUID로 교체 필수 (C2-FINAL §4-3)
  v_before           jsonb;
  v_after            jsonb;
  v_cnt              integer;
  v_field_cnt        integer;
  v_evidence_cnt     integer;
BEGIN
  -- [P0] reviewer_id NULL 가드 (C2-FINAL §4-3: NULL 불허)
  IF v_reviewer_id IS NULL THEN
    RAISE EXCEPTION 'ABORT [P0]: v_reviewer_id가 NULL입니다. 승인자 UUID를 설정한 후 재실행하십시오.';
  END IF;
  -- ─── PRECONDITION 검증 [P1~P4] ────────────────────────────────────

  -- [P1] schema status = CANDIDATE
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = v_schema_id AND status = 'CANDIDATE') <> 1 THEN
    RAISE EXCEPTION 'ABORT [P1]: runtime_form_schema.status != CANDIDATE. STOP.';
  END IF;

  -- [P2] runtime_field 전 행 status = APPROVED_BY_HUMAN (G3 통과 확인)
  SELECT count(*) INTO v_field_cnt
  FROM runtime_field WHERE form_schema_id = v_schema_id;

  IF v_field_cnt = 0 THEN
    RAISE EXCEPTION 'ABORT [P2]: runtime_field 0건. 서식 구조 오류.';
  END IF;

  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id
        AND status <> 'APPROVED_BY_HUMAN') > 0 THEN
    RAISE EXCEPTION 'ABORT [P2]: runtime_field 중 APPROVED_BY_HUMAN이 아닌 행 존재 (G3 미완). STOP.';
  END IF;

  -- [P3] runtime_field required_status = CANDIDATE_ONLY 행 0개
  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id
        AND required_status = 'CANDIDATE_ONLY') > 0 THEN
    RAISE EXCEPTION 'ABORT [P3]: CANDIDATE_ONLY 필드 존재. Packet A 실행 후 재시도. STOP.';
  END IF;

  -- [P4] evidence_count ≥ 1 (STEP4D와 차이: evidence 없으면 STEP4D 사용)
  SELECT count(*) INTO v_evidence_cnt
  FROM runtime_evidence_field WHERE form_schema_id = v_schema_id;

  IF v_evidence_cnt = 0 THEN
    RAISE EXCEPTION 'ABORT [P4]: evidence_count = 0. evidence 없는 서식은 STEP4D_UP 사용. STOP.';
  END IF;

  -- 중복 승격 방지 (preexisting promotion audit = 0)
  IF (SELECT count(*) FROM runtime_form_audit_log
      WHERE source_table = 'runtime_form_schema' AND source_id = v_schema_id
        AND action = 'PROMOTE_TO_RUNTIME_USE_WITH_EVIDENCE') <> 0 THEN
    RAISE EXCEPTION 'ABORT: 이미 STEP4E 승격 Audit 존재. 중복 실행 차단. STOP.';
  END IF;

  -- ─── 대상 행 잠금 (동시 변경 통제) ────────────────────────────────

  PERFORM 1 FROM runtime_form_schema WHERE id = v_schema_id FOR UPDATE;
  PERFORM 1 FROM runtime_field WHERE form_schema_id = v_schema_id FOR UPDATE;
  PERFORM 1 FROM runtime_evidence_field WHERE form_schema_id = v_schema_id FOR UPDATE;

  -- ─── before_state snapshot ─────────────────────────────────────────

  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'fields', (SELECT jsonb_agg(jsonb_build_object(
                 'id', id, 'field_key', field_key,
                 'status', status, 'required_status', required_status)
                 ORDER BY field_order)
               FROM runtime_field WHERE form_schema_id = v_schema_id),
    'evidence_fields', (SELECT jsonb_agg(jsonb_build_object(
                 'id', id, 'status', status,
                 'evidence_candidate_id', evidence_candidate_id))
               FROM runtime_evidence_field WHERE form_schema_id = v_schema_id)
  ) INTO v_before;

  -- ─── STEP 1: evidence_field_candidate 검증 [S1] ────────────────────

  -- [S1-2] 각 evidence_field의 evidence_field_candidate.status = APPROVED_BY_HUMAN
  IF EXISTS (
    SELECT 1
    FROM runtime_evidence_field ev
    JOIN evidence_field_candidate efc ON efc.id = ev.evidence_candidate_id
    WHERE ev.form_schema_id = v_schema_id
      AND efc.status <> 'APPROVED_BY_HUMAN'
  ) THEN
    RAISE EXCEPTION 'ABORT [S1-2]: evidence_field_candidate 미승인 행 존재 (G-EFC 미완). STOP.';
  END IF;

  -- [S1-3] schema_candidate_id 일치 확인 (R2-C2)
  IF EXISTS (
    SELECT 1
    FROM runtime_evidence_field ev
    JOIN evidence_field_candidate efc ON efc.id = ev.evidence_candidate_id
    WHERE ev.form_schema_id = v_schema_id
      AND efc.schema_candidate_id <> v_candidate_id
  ) THEN
    RAISE EXCEPTION 'ABORT [S1-3]: evidence_field_candidate.schema_candidate_id 불일치 (R2-C2). STOP.';
  END IF;

  -- [S1-4] FK 유효성 (evidence_candidate_id NULL 차단)
  IF EXISTS (
    SELECT 1 FROM runtime_evidence_field
    WHERE form_schema_id = v_schema_id
      AND evidence_candidate_id IS NULL
  ) THEN
    RAISE EXCEPTION 'ABORT [S1-4]: evidence_candidate_id NULL 행 존재. FK 무결성 불가. STOP.';
  END IF;

  -- ─── STEP 2: runtime_evidence_field → APPROVED_BY_HUMAN [S2] ────────

  -- [S2-1] 전 행 status = CANDIDATE 확인
  IF (SELECT count(*) FROM runtime_evidence_field
      WHERE form_schema_id = v_schema_id AND status <> 'CANDIDATE') > 0 THEN
    RAISE EXCEPTION 'ABORT [S2-1]: runtime_evidence_field 중 CANDIDATE가 아닌 행 존재. STOP.';
  END IF;

  UPDATE runtime_evidence_field
  SET status = 'APPROVED_BY_HUMAN'
  WHERE form_schema_id = v_schema_id AND status = 'CANDIDATE';

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  -- [S2-3] UPDATE 행 수 = evidence_count 일치
  IF v_cnt <> v_evidence_cnt THEN
    RAISE EXCEPTION 'ABORT [S2-3]: runtime_evidence_field UPDATE % rows (expected %). ROLLBACK.', v_cnt, v_evidence_cnt;
  END IF;

  -- ─── STEP 3: runtime_form_schema → APPROVED_BY_HUMAN [S3] ───────────

  UPDATE runtime_form_schema
  SET status = 'APPROVED_BY_HUMAN', updated_at = now()
  WHERE id = v_schema_id AND status = 'CANDIDATE';

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT [S3]: schema APPROVED_BY_HUMAN UPDATE % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  -- ─── STEP 4: Gate 검증 [G-EV, G-EFC, G-FK, G-FLD, G-FLD2] ──────────

  -- [G-EV] runtime_evidence_field 전 행 APPROVED_BY_HUMAN
  IF (SELECT count(*) FROM runtime_evidence_field
      WHERE form_schema_id = v_schema_id AND status <> 'APPROVED_BY_HUMAN') > 0 THEN
    RAISE EXCEPTION 'ABORT [G-EV]: runtime_evidence_field 미승인 행 존재. ROLLBACK.';
  END IF;

  -- [G-EFC] evidence_field_candidate 전 행 APPROVED_BY_HUMAN
  IF EXISTS (
    SELECT 1
    FROM runtime_evidence_field ev
    JOIN evidence_field_candidate efc ON efc.id = ev.evidence_candidate_id
    WHERE ev.form_schema_id = v_schema_id
      AND efc.status <> 'APPROVED_BY_HUMAN'
  ) THEN
    RAISE EXCEPTION 'ABORT [G-EFC]: evidence_field_candidate 미승인 행 존재. ROLLBACK.';
  END IF;

  -- [G-FK] FK chain 유효성
  IF (SELECT count(*) FROM runtime_evidence_field ev
      LEFT JOIN evidence_field_candidate efc ON efc.id = ev.evidence_candidate_id
      WHERE ev.form_schema_id = v_schema_id AND efc.id IS NULL) > 0 THEN
    RAISE EXCEPTION 'ABORT [G-FK]: evidence_candidate_id FK 단절 행 존재. ROLLBACK.';
  END IF;

  -- [G-FLD] runtime_field 전 행 APPROVED_BY_HUMAN (재확인)
  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id AND status <> 'APPROVED_BY_HUMAN') > 0 THEN
    RAISE EXCEPTION 'ABORT [G-FLD]: runtime_field 미승인 행 존재. ROLLBACK.';
  END IF;

  -- [G-FLD2] CANDIDATE_ONLY = 0 (재확인)
  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id AND required_status = 'CANDIDATE_ONLY') > 0 THEN
    RAISE EXCEPTION 'ABORT [G-FLD2]: CANDIDATE_ONLY 필드 존재. ROLLBACK.';
  END IF;

  -- ─── STEP 5: runtime_form_schema → APPROVED_FOR_RUNTIME_USE [S5] ────

  UPDATE runtime_form_schema
  SET status = 'APPROVED_FOR_RUNTIME_USE', updated_at = now()
  WHERE id = v_schema_id AND status = 'APPROVED_BY_HUMAN';

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT [S5]: schema APPROVED_FOR_RUNTIME_USE UPDATE % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  -- ─── FINAL ASSERT ─────────────────────────────────────────────────

  IF (SELECT status FROM runtime_form_schema WHERE id = v_schema_id)
      <> 'APPROVED_FOR_RUNTIME_USE' THEN
    RAISE EXCEPTION 'ABORT FINAL: schema 최종 상태 불일치. ROLLBACK.';
  END IF;

  IF (SELECT count(*) FROM runtime_evidence_field
      WHERE form_schema_id = v_schema_id AND status = 'APPROVED_BY_HUMAN')
      <> v_evidence_cnt THEN
    RAISE EXCEPTION 'ABORT FINAL: runtime_evidence_field 최종 상태 불일치. ROLLBACK.';
  END IF;

  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id AND status = 'APPROVED_BY_HUMAN')
      <> v_field_cnt THEN
    RAISE EXCEPTION 'ABORT FINAL: runtime_field 최종 상태 불일치. ROLLBACK.';
  END IF;

  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id AND required_status = 'CANDIDATE_ONLY') <> 0 THEN
    RAISE EXCEPTION 'ABORT FINAL: CANDIDATE_ONLY 잔존. ROLLBACK.';
  END IF;

  -- ─── after_state snapshot ──────────────────────────────────────────

  SELECT jsonb_build_object(
    'schema_status', (SELECT status FROM runtime_form_schema WHERE id = v_schema_id),
    'fields', (SELECT jsonb_agg(jsonb_build_object(
                 'id', id, 'field_key', field_key,
                 'status', status, 'required_status', required_status)
                 ORDER BY field_order)
               FROM runtime_field WHERE form_schema_id = v_schema_id),
    'evidence_fields', (SELECT jsonb_agg(jsonb_build_object(
                 'id', id, 'status', status,
                 'evidence_candidate_id', evidence_candidate_id))
               FROM runtime_evidence_field WHERE form_schema_id = v_schema_id)
  ) INTO v_after;

  -- ─── Audit INSERT (C2-FINAL §4-3) ─────────────────────────────────

  INSERT INTO runtime_form_audit_log
    (source_table, source_id, action, schema_version,
     before_state, after_state, reviewer_id, review_comment,
     rollback_snapshot, rollback_available)
  VALUES
    ('runtime_form_schema', v_schema_id,
     'PROMOTE_TO_RUNTIME_USE_WITH_EVIDENCE', 1,
     v_before, v_after,
     v_reviewer_id,  -- NULL 불허 (C2-FINAL §4-3: STEP4D와 차이)
     'STEP4E evidence-included promotion. DOC-CON-048 재하도급 승낙 통보서. C2-FINAL §4 계약 기준.',
     v_before, true);

  GET DIAGNOSTICS v_cnt = ROW_COUNT;
  IF v_cnt <> 1 THEN
    RAISE EXCEPTION 'ABORT: Audit INSERT % rows (expected 1). ROLLBACK.', v_cnt;
  END IF;

  RAISE NOTICE 'STEP4E_UP OK: schema=% APPROVED_FOR_RUNTIME_USE fields=% evidence=%',
    v_schema_id, v_field_cnt, v_evidence_cnt;
END $$;

-- =====================================================================
-- END STEP4E_UP SQL — NOT EXECUTED.
-- G4 승격 Owner 승인 시: 이 파일 전체를 단일 execute_sql 호출로 실행.
