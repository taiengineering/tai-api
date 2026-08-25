-- =====================================================================
-- WP-PERSISTENCE-02A STEP-4D — VERIFY SQL (POST-PROMOTION, §13)
-- =====================================================================
-- !!! NOT EXECUTED — STEP-4D(UP) 실행 성공 직후 SELECT-only 실행 !!!
-- 목적: 승격 결과 검증. schema=APPROVED_FOR_RUNTIME_USE, field 5 APPROVED_BY_HUMAN,
--       required_status target(3 REQUIRED / 2 NOT_REQUIRED / 0 CANDIDATE_ONLY),
--       candidate 불변(CANDIDATE), bridge/document ref 0, audit 1.
-- 단일 SELECT. mutation 0.
-- 대상 schema UUID: dc79ac3c-388c-42dc-b029-3dd9bda54a47
-- 보강(2차): audit source_table exact / gate CASE 에 field_count=5 + schema_header_ok 편입.
-- =====================================================================

WITH s AS (
  SELECT id, status, form_type, document_family, field_count, checklist_count, evidence_count
  FROM runtime_form_schema
  WHERE id = 'dc79ac3c-388c-42dc-b029-3dd9bda54a47'
),
f AS (
  SELECT
    count(*) AS field_cnt,
    count(*) FILTER (WHERE status='APPROVED_BY_HUMAN') AS field_approved_cnt,
    count(*) FILTER (WHERE required_status='REQUIRED_BY_HUMAN') AS req_by_human_cnt,
    count(*) FILTER (WHERE required_status='NOT_REQUIRED') AS not_required_cnt,
    count(*) FILTER (WHERE required_status='CANDIDATE_ONLY') AS candidate_only_cnt,
    count(*) FILTER (WHERE
         (field_key='inspection_subject'  AND input_type='text'      AND field_order=1 AND required_status='REQUIRED_BY_HUMAN' AND status='APPROVED_BY_HUMAN')
      OR (field_key='inspected_at'        AND input_type='datetime'  AND field_order=2 AND required_status='REQUIRED_BY_HUMAN' AND status='APPROVED_BY_HUMAN')
      OR (field_key='inspection_title'    AND input_type='text'      AND field_order=3 AND required_status='NOT_REQUIRED'      AND status='APPROVED_BY_HUMAN')
      OR (field_key='inspector_display'   AND input_type='text'      AND field_order=4 AND required_status='NOT_REQUIRED'      AND status='APPROVED_BY_HUMAN')
      OR (field_key='inspection_results'  AND input_type='multi_row' AND field_order=5 AND required_status='REQUIRED_BY_HUMAN' AND status='APPROVED_BY_HUMAN')
    ) AS exact_field_contract_cnt
  FROM runtime_field WHERE form_schema_id = 'dc79ac3c-388c-42dc-b029-3dd9bda54a47'
),
aud AS (
  SELECT count(*) AS audit_cnt
  FROM runtime_form_audit_log
  WHERE source_table = 'runtime_form_schema'
    AND source_id = 'dc79ac3c-388c-42dc-b029-3dd9bda54a47'
    AND action = 'PROMOTE_TO_RUNTIME_USE'
)
SELECT
  (SELECT id FROM s)                                     AS schema_id,
  (SELECT status FROM s)                                 AS schema_status,          -- expect APPROVED_FOR_RUNTIME_USE
  (SELECT bool_and(form_type='CUSTOM' AND document_family='DOCUMENT'
                   AND field_count=5 AND checklist_count=0 AND evidence_count=0) FROM s) AS schema_header_ok, -- true
  (SELECT field_cnt FROM f)                              AS field_count,            -- expect 5
  (SELECT field_approved_cnt FROM f)                     AS field_approved_count,   -- expect 5
  (SELECT req_by_human_cnt FROM f)                       AS field_required_by_human_count, -- expect 3
  (SELECT not_required_cnt FROM f)                       AS field_not_required_count,      -- expect 2
  (SELECT candidate_only_cnt FROM f)                     AS field_candidate_only_count,    -- expect 0
  (SELECT exact_field_contract_cnt FROM f)               AS exact_field_contract_count,    -- expect 5
  (SELECT status FROM document_schema_candidate WHERE form_code='GEN-INSPECT-RESULT-001') AS candidate_status, -- expect CANDIDATE
  (SELECT count(*) FROM runtime_inspection_bridge WHERE runtime_form_schema_id='dc79ac3c-388c-42dc-b029-3dd9bda54a47') AS bridge_ref_count, -- expect 0
  (SELECT count(*) FROM runtime_document_data WHERE form_schema_id='dc79ac3c-388c-42dc-b029-3dd9bda54a47') AS runtime_document_ref_count, -- expect 0
  (SELECT audit_cnt FROM aud)                            AS audit_log_count,        -- A-2: expect 1
  CASE WHEN
    (SELECT status FROM s) = 'APPROVED_FOR_RUNTIME_USE'
    AND (SELECT bool_and(form_type='CUSTOM' AND document_family='DOCUMENT'
                         AND field_count=5 AND checklist_count=0 AND evidence_count=0) FROM s) = true
    AND (SELECT field_cnt FROM f) = 5
    AND (SELECT field_approved_cnt FROM f) = 5
    AND (SELECT req_by_human_cnt FROM f) = 3
    AND (SELECT not_required_cnt FROM f) = 2
    AND (SELECT candidate_only_cnt FROM f) = 0
    AND (SELECT exact_field_contract_cnt FROM f) = 5
    AND (SELECT status FROM document_schema_candidate WHERE form_code='GEN-INSPECT-RESULT-001') = 'CANDIDATE'
    AND (SELECT count(*) FROM runtime_inspection_bridge WHERE runtime_form_schema_id='dc79ac3c-388c-42dc-b029-3dd9bda54a47') = 0
    AND (SELECT count(*) FROM runtime_document_data WHERE form_schema_id='dc79ac3c-388c-42dc-b029-3dd9bda54a47') = 0
    AND (SELECT audit_cnt FROM aud) = 1
  THEN 'PASS' ELSE 'FAIL' END                            AS promotion_state_gate_status; -- expect PASS

-- =====================================================================
-- PASS 기준 (§13):
--   schema_status = APPROVED_FOR_RUNTIME_USE
--   schema_header_ok = true (form_type/document_family/counts 5/0/0)  <- gate 편입
--   field_count = 5                                                   <- gate 편입(전체 count)
--   field_approved_count = 5
--   field_required_by_human_count = 3
--   field_not_required_count = 2
--   field_candidate_only_count = 0
--   exact_field_contract_count = 5   (5필드 전부 key+input_type+order+required+status 일치)
--   candidate_status = CANDIDATE (불변)
--   bridge_ref_count = 0
--   runtime_document_ref_count = 0
--   audit_log_count = 1              (A-2, source_table+source_id+action exact)
--   promotion_state_gate_status = PASS
--     주: 이 gate 는 DB structural 상태(G1/G2/G3/G4/G8/G9/G10 중 DB로 입증 가능한 부분) +
--         승격 상태를 검증. G5~G7(raw_code/value·note/photo 보존)은 STEP-3 SEALED payload
--         contract 에 의존하며 이 SELECT 로 재입증하지 않는다.
-- 하나라도 불일치 → PROMOTION_MISMATCH → 결과 제출 후 STOP.
-- =====================================================================
