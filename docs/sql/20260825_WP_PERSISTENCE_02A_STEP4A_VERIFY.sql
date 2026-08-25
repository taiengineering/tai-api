-- =====================================================================
-- WP-PERSISTENCE-02A STEP-4A — VERIFY SQL (POST-APPLY, §17)
-- =====================================================================
-- !!! NOT EXECUTED — STEP-4B(UP) 실행 성공 직후 STEP-4C 에서 SELECT-only 실행 !!!
-- 목적: 8-row invariant + provenance + sector NULL + multi_row + status 검증
-- 단일 SELECT 로 전 항목 PASS/FAIL 판정. mutation 0.
-- required_status = CANDIDATE_ONLY 5/5 를 검증한다. 해석 B 확정.
-- =====================================================================

WITH m AS (
  SELECT id, form_code, sector, form_type, form_category
  FROM document_form_master
  WHERE form_code = 'GEN-INSPECT-RESULT-001'
),
c AS (
  SELECT id, source_table, source_id, sector, status, field_count, checklist_count, evidence_count
  FROM document_schema_candidate
  WHERE form_code = 'GEN-INSPECT-RESULT-001'
),
s AS (
  SELECT rfs.id, rfs.schema_candidate_id, rfs.form_type, rfs.document_family,
         rfs.field_count, rfs.checklist_count, rfs.evidence_count, rfs.status,
         rfs.source_trace
  FROM runtime_form_schema rfs
  WHERE rfs.source_trace->>'form_code' = 'GEN-INSPECT-RESULT-001'
),
f AS (
  SELECT rf.form_schema_id,
         count(*) AS field_cnt,
         count(DISTINCT rf.field_key) AS distinct_key_cnt,
         count(*) FILTER (WHERE rf.field_candidate_id IS NULL) AS null_candidate_cnt,
         count(*) FILTER (WHERE rf.field_key='inspection_results' AND rf.input_type='multi_row') AS multirow_cnt,
         count(*) FILTER (WHERE rf.status='CANDIDATE') AS candidate_status_cnt,
         count(*) FILTER (WHERE rf.required_status='CANDIDATE_ONLY') AS req_candidate_only_cnt,
         -- exact key/type/order 5건 (하나라도 어긋나면 5 미만)
         count(*) FILTER (WHERE
              (rf.field_key='inspection_subject' AND rf.input_type='text'      AND rf.field_order=1)
           OR (rf.field_key='inspected_at'       AND rf.input_type='datetime'  AND rf.field_order=2)
           OR (rf.field_key='inspection_title'   AND rf.input_type='text'      AND rf.field_order=3)
           OR (rf.field_key='inspector_display'  AND rf.input_type='text'      AND rf.field_order=4)
           OR (rf.field_key='inspection_results' AND rf.input_type='multi_row' AND rf.field_order=5)
         ) AS exact_contract_cnt,
         min(rf.field_order) AS min_order,
         max(rf.field_order) AS max_order,
         count(*) FILTER (WHERE rf.status NOT IN
           ('CANDIDATE','NEEDS_HUMAN_REVIEW','APPROVED_BY_HUMAN','REJECTED_BY_HUMAN')) AS bad_status_cnt
  FROM runtime_field rf
  JOIN s ON s.id = rf.form_schema_id
  GROUP BY rf.form_schema_id
),
ev AS (
  SELECT count(*) AS evidence_field_cnt
  FROM runtime_evidence_field ref
  JOIN s ON s.id = ref.form_schema_id
)
SELECT
  -- MASTER
  (SELECT count(*) FROM m)                               AS master_cnt,          -- expect 1
  (SELECT bool_and(sector IS NULL) FROM m)               AS master_sector_null,  -- expect true
  (SELECT bool_and(form_type='STANDARD' AND form_category='DOCUMENT') FROM m) AS master_type_ok, -- true
  -- CANDIDATE
  (SELECT count(*) FROM c)                               AS candidate_cnt,       -- expect 1
  (SELECT bool_and(source_table='document_form_master') FROM c) AS cand_srctable_ok, -- true
  (SELECT bool_and(source_id = (SELECT id FROM m)) FROM c)      AS cand_provenance_ok, -- true
  (SELECT bool_and(sector IS NULL) FROM c)               AS cand_sector_null,    -- true
  (SELECT bool_and(status='CANDIDATE') FROM c)           AS cand_status_ok,      -- true
  -- RUNTIME SCHEMA
  (SELECT count(*) FROM s)                               AS schema_cnt,          -- expect 1
  (SELECT bool_and(schema_candidate_id=(SELECT id FROM c)) FROM s) AS schema_provenance_ok, -- true
  (SELECT bool_and(form_type='CUSTOM' AND document_family='DOCUMENT') FROM s) AS schema_type_ok, -- true
  (SELECT bool_and(field_count=5 AND checklist_count=0 AND evidence_count=0) FROM s) AS schema_counts_ok, -- true
  (SELECT bool_and(status='CANDIDATE') FROM s)           AS schema_status_ok,    -- true
  (SELECT bool_and(source_trace->>'source_id' = (SELECT id::text FROM m)) FROM s) AS schema_trace_ok, -- true
  -- RUNTIME FIELD
  (SELECT field_cnt FROM f)                              AS field_cnt,           -- expect 5
  (SELECT distinct_key_cnt FROM f)                       AS distinct_key_cnt,    -- expect 5
  (SELECT null_candidate_cnt FROM f)                     AS field_null_candidate_cnt, -- expect 5
  (SELECT multirow_cnt FROM f)                           AS multirow_cnt,        -- expect 1
  (SELECT candidate_status_cnt FROM f)                   AS field_candidate_status_cnt, -- expect 5
  (SELECT req_candidate_only_cnt FROM f)                 AS field_req_candidate_only_cnt, -- expect 5
  (SELECT exact_contract_cnt FROM f)                     AS field_exact_contract_cnt, -- expect 5
  (SELECT min_order FROM f)                              AS field_min_order,     -- expect 1
  (SELECT max_order FROM f)                              AS field_max_order,     -- expect 5
  (SELECT bad_status_cnt FROM f)                         AS field_bad_status_cnt,-- expect 0
  -- EVIDENCE
  (SELECT evidence_field_cnt FROM ev)                    AS evidence_field_cnt,  -- expect 0
  -- TOTAL
  ((SELECT count(*) FROM m)+(SELECT count(*) FROM c)+(SELECT count(*) FROM s)+(SELECT field_cnt FROM f))
                                                         AS total_new_rows;      -- expect 8

-- =====================================================================
-- PASS 기준 (STEP-4C):
--   master_cnt=1, master_sector_null=true, master_type_ok=true
--   candidate_cnt=1, cand_srctable_ok=true, cand_provenance_ok=true,
--     cand_sector_null=true, cand_status_ok=true
--   schema_cnt=1, schema_provenance_ok=true, schema_type_ok=true,
--     schema_counts_ok=true, schema_status_ok=true, schema_trace_ok=true
--   field_cnt=5, distinct_key_cnt=5, field_null_candidate_cnt=5,
--     multirow_cnt=1, field_candidate_status_cnt=5,
--     field_req_candidate_only_cnt=5,   <- required_status=CANDIDATE_ONLY 5/5 (해석 B)
--     field_exact_contract_cnt=5,       <- exact key/type/order 5/5 (하나라도 다르면 <5)
--     field_min_order=1, field_max_order=5, field_bad_status_cnt=0
--   evidence_field_cnt=0
--   total_new_rows=8
-- 하나라도 불일치 → MATERIALIZATION_MISMATCH → STEP-4D 금지.
-- =====================================================================
