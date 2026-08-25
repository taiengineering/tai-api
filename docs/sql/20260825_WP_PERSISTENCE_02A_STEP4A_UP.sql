-- =====================================================================
-- WP-PERSISTENCE-02A STEP-4A — UP SQL (MATERIALIZATION DRAFT)
-- =====================================================================
-- !!! NOT EXECUTED — STEP-4B 명시적 승인 전 실행 금지 !!!
-- 목적: GENERAL_INSPECTION_RESULT v1 을 8 row atomic materialize
--   document_form_master 1 + document_schema_candidate 1
--   + runtime_form_schema 1 + runtime_field 5 = 8 rows
-- 원자성: 단일 DO 블록. 내부 예외 시 블록 전체 롤백. 부분 materialization 없음.
-- provenance: document_form_master -> candidate(source_table=document_form_master,
--             source_id=master.id) -> runtime(source_trace.source_id=master.id)
-- sector: master.sector=NULL / candidate.sector=NULL 명시 (default BUILDING 오염 방지)
-- status: 전부 CANDIDATE (승인 전). APPROVED_FOR_RUNTIME_USE 는 STEP-4D.
-- required_status: 전건 CANDIDATE_ONLY (해석 B 확정). REQUIRED_BY_HUMAN/NOT_REQUIRED 는
--                  4D 사람 승인 후의 target contract (STEP-3 SEALED = 4D target).
-- field_candidate_id: NULL (nullable 계약 사용, field_candidate INSERT 0)
-- =====================================================================

DO $$
DECLARE
  v_master_id    uuid;
  v_candidate_id uuid;
  v_schema_id    uuid;
  v_field_cnt    integer;
  v_master_cnt   integer;
  v_candidate_cnt integer;
  v_runtime_cnt  integer;
BEGIN
  -- ---------------------------------------------------------------
  -- GUARD: 3단계 전부 중복 검사 (§11 DUPLICATE STOP)
  --   4A에서 0이었어도 4B 실행 순간 재확인. 하나라도 선존하면 STOP.
  -- ---------------------------------------------------------------
  SELECT count(*) INTO v_master_cnt
  FROM document_form_master WHERE form_code = 'GEN-INSPECT-RESULT-001';
  IF v_master_cnt <> 0 THEN
    RAISE EXCEPTION 'ABORT: GENERAL master already exists (count=%). PREEXISTING_GENERAL_SCHEMA_FOUND.', v_master_cnt;
  END IF;

  SELECT count(*) INTO v_candidate_cnt
  FROM document_schema_candidate WHERE form_code = 'GEN-INSPECT-RESULT-001';
  IF v_candidate_cnt <> 0 THEN
    RAISE EXCEPTION 'ABORT: GENERAL candidate already exists (count=%). PREEXISTING_GENERAL_SCHEMA_FOUND.', v_candidate_cnt;
  END IF;

  SELECT count(*) INTO v_runtime_cnt
  FROM runtime_form_schema WHERE source_trace->>'form_code' = 'GEN-INSPECT-RESULT-001';
  IF v_runtime_cnt <> 0 THEN
    RAISE EXCEPTION 'ABORT: GENERAL runtime schema already exists (count=%). PREEXISTING_GENERAL_SCHEMA_FOUND.', v_runtime_cnt;
  END IF;

  -- ---------------------------------------------------------------
  -- [1] document_form_master (sector=NULL 명시, 법령 미기입)
  -- ---------------------------------------------------------------
  INSERT INTO document_form_master
    (form_code, form_name, form_type, form_category, sector,
     required_fields, template_fields, is_active, sort_order)
  VALUES
    ('GEN-INSPECT-RESULT-001',
     '점검 결과 기록서 (범용)',
     'STANDARD',
     'DOCUMENT',
     NULL,                                   -- ★ sector NULL 명시
     '["점검 대상","점검 일시","점검 세트/제목","점검자(표시)","점검 항목별 결과"]'::jsonb,
     NULL,                                   -- template_fields
     true,
     0)
  RETURNING id INTO v_master_id;

  -- ---------------------------------------------------------------
  -- [2] document_schema_candidate (source_table=document_form_master, sector=NULL)
  -- ---------------------------------------------------------------
  INSERT INTO document_schema_candidate
    (source_table, source_id, doc_id, doc_name, form_code, form_type,
     category, sector, field_count, checklist_count, evidence_count, status)
  VALUES
    ('document_form_master',                 -- CHECK 허용값
     v_master_id,                            -- provenance: master.id
     NULL,                                   -- doc_id
     '점검 결과 기록서 (범용)',
     'GEN-INSPECT-RESULT-001',
     'STANDARD',
     'DOCUMENT',
     NULL,                                   -- ★ sector NULL 명시
     5, 0, 0,
     'CANDIDATE')
  RETURNING id INTO v_candidate_id;

  -- ---------------------------------------------------------------
  -- [3] runtime_form_schema (form_type=CUSTOM, document_family=DOCUMENT)
  -- ---------------------------------------------------------------
  INSERT INTO runtime_form_schema
    (schema_candidate_id, document_family, form_type, form_name,
     field_count, checklist_count, evidence_count, source_trace, status, version)
  VALUES
    (v_candidate_id,
     'DOCUMENT',                             -- 기존 값 재사용
     'CUSTOM',
     '점검 결과 기록서 (범용)',
     5, 0, 0,
     jsonb_build_object(
       'doc_id', NULL,
       'form_code', 'GEN-INSPECT-RESULT-001',
       'source_id', v_master_id::text,
       'source_table', 'document_form_master'),
     'CANDIDATE',
     1)
  RETURNING id INTO v_schema_id;

  -- ---------------------------------------------------------------
  -- [4] runtime_field ×5
  --   required_status = CANDIDATE_ONLY (해석 B 확정 — 기존 1303건 전건 관례와 일치).
  --   status = CANDIDATE / field_candidate_id = NULL.
  --   최종 target(4D 사람 승인 후 UPDATE): subject/inspected_at/results=REQUIRED_BY_HUMAN,
  --   title/inspector_display=NOT_REQUIRED. (STEP-3 SEALED = 4D target, 4B initial 아님)
  -- ---------------------------------------------------------------
  INSERT INTO runtime_field
    (form_schema_id, field_candidate_id, field_label, field_key,
     input_type, field_order, required_status, source_trace, status)
  VALUES
    (v_schema_id, NULL, '점검 대상',        'inspection_subject', 'text',     1,
     'CANDIDATE_ONLY',
     jsonb_build_object('source_table','document_form_master','form_code','GEN-INSPECT-RESULT-001'),
     'CANDIDATE'),
    (v_schema_id, NULL, '점검 일시',        'inspected_at',      'datetime', 2,
     'CANDIDATE_ONLY',
     jsonb_build_object('source_table','document_form_master','form_code','GEN-INSPECT-RESULT-001'),
     'CANDIDATE'),
    (v_schema_id, NULL, '점검 세트/제목',   'inspection_title',  'text',     3,
     'CANDIDATE_ONLY',
     jsonb_build_object('source_table','document_form_master','form_code','GEN-INSPECT-RESULT-001'),
     'CANDIDATE'),
    (v_schema_id, NULL, '점검자(표시)',     'inspector_display', 'text',     4,
     'CANDIDATE_ONLY',
     jsonb_build_object('source_table','document_form_master','form_code','GEN-INSPECT-RESULT-001'),
     'CANDIDATE'),
    (v_schema_id, NULL, '점검 항목별 결과', 'inspection_results','multi_row',5,
     'CANDIDATE_ONLY',
     jsonb_build_object('source_table','document_form_master','form_code','GEN-INSPECT-RESULT-001'),
     'CANDIDATE');

  -- ---------------------------------------------------------------
  -- IN-TRANSACTION ASSERTION (§12 step 8) — EXACT CONTRACT. 실패 시 전체 롤백.
  -- 4C 가 "처음 발견하는 검사"가 아니라 독립 재검증이 되도록, COMMIT 전 exact 확인.
  -- ---------------------------------------------------------------

  -- (a) MASTER exact
  IF (SELECT count(*) FROM document_form_master
      WHERE id = v_master_id AND form_code = 'GEN-INSPECT-RESULT-001'
        AND form_type = 'STANDARD' AND form_category = 'DOCUMENT' AND sector IS NULL) <> 1 THEN
    RAISE EXCEPTION 'ABORT: master exact contract mismatch. ROLLBACK.';
  END IF;

  -- (b) CANDIDATE exact (provenance + sector NULL + status)
  IF (SELECT count(*) FROM document_schema_candidate
      WHERE id = v_candidate_id AND source_table = 'document_form_master'
        AND source_id = v_master_id AND form_code = 'GEN-INSPECT-RESULT-001'
        AND sector IS NULL AND status = 'CANDIDATE'
        AND field_count = 5 AND checklist_count = 0 AND evidence_count = 0) <> 1 THEN
    RAISE EXCEPTION 'ABORT: candidate exact contract mismatch. ROLLBACK.';
  END IF;

  -- (c) RUNTIME SCHEMA exact
  IF (SELECT count(*) FROM runtime_form_schema
      WHERE id = v_schema_id AND schema_candidate_id = v_candidate_id
        AND form_type = 'CUSTOM' AND document_family = 'DOCUMENT'
        AND field_count = 5 AND checklist_count = 0 AND evidence_count = 0
        AND status = 'CANDIDATE'
        AND source_trace->>'source_id' = v_master_id::text
        AND source_trace->>'source_table' = 'document_form_master'
        AND source_trace->>'form_code' = 'GEN-INSPECT-RESULT-001') <> 1 THEN
    RAISE EXCEPTION 'ABORT: runtime schema exact contract mismatch. ROLLBACK.';
  END IF;

  -- (d) RUNTIME FIELD count exact
  SELECT count(*) INTO v_field_cnt
  FROM runtime_field WHERE form_schema_id = v_schema_id;
  IF v_field_cnt <> 5 THEN
    RAISE EXCEPTION 'ABORT: runtime_field count = % (expected 5). ROLLBACK.', v_field_cnt;
  END IF;

  IF (SELECT count(DISTINCT field_key) FROM runtime_field WHERE form_schema_id = v_schema_id) <> 5 THEN
    RAISE EXCEPTION 'ABORT: distinct field_key <> 5. ROLLBACK.';
  END IF;

  -- (e) RUNTIME FIELD exact key/type/order (5건 전수, 하나라도 다르면 롤백)
  IF (SELECT count(*) FROM runtime_field WHERE form_schema_id = v_schema_id AND
        ( (field_key='inspection_subject' AND input_type='text'      AND field_order=1)
       OR (field_key='inspected_at'       AND input_type='datetime'  AND field_order=2)
       OR (field_key='inspection_title'   AND input_type='text'      AND field_order=3)
       OR (field_key='inspector_display'  AND input_type='text'      AND field_order=4)
       OR (field_key='inspection_results' AND input_type='multi_row' AND field_order=5) )
      ) <> 5 THEN
    RAISE EXCEPTION 'ABORT: runtime_field exact key/type/order mismatch. ROLLBACK.';
  END IF;

  -- (f) required_status = CANDIDATE_ONLY 5/5 (해석 B 확정)
  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id AND required_status = 'CANDIDATE_ONLY') <> 5 THEN
    RAISE EXCEPTION 'ABORT: required_status not CANDIDATE_ONLY 5/5. ROLLBACK.';
  END IF;

  -- (g) status = CANDIDATE 5/5
  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id AND status = 'CANDIDATE') <> 5 THEN
    RAISE EXCEPTION 'ABORT: field status not CANDIDATE 5/5. ROLLBACK.';
  END IF;

  -- (h) field_candidate_id NULL 5/5
  IF (SELECT count(*) FROM runtime_field
      WHERE form_schema_id = v_schema_id AND field_candidate_id IS NULL) <> 5 THEN
    RAISE EXCEPTION 'ABORT: field_candidate_id not NULL 5/5. ROLLBACK.';
  END IF;

  -- (i) evidence = 0
  IF (SELECT count(*) FROM runtime_evidence_field WHERE form_schema_id = v_schema_id) <> 0 THEN
    RAISE EXCEPTION 'ABORT: runtime_evidence_field <> 0. ROLLBACK.';
  END IF;

  RAISE NOTICE 'MATERIALIZED OK (exact): master=% candidate=% schema=% fields=5 required=CANDIDATE_ONLY status=CANDIDATE',
    v_master_id, v_candidate_id, v_schema_id;
END $$;

-- =====================================================================
-- END UP SQL — NOT EXECUTED.
-- 실행 승인(STEP-4B) 시: 이 파일 전체를 단일 execute_sql 호출로 실행.
-- 실행 직후 VERIFY.sql 로 8-row invariant 확인.
-- =====================================================================
