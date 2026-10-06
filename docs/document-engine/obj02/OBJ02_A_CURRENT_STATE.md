# OBJ02_A_CURRENT_STATE

조사일: 2026-10-07
WO: WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001
실행자: Claude Code

---

## GIT

| 항목 | 값 |
|---|---|
| tai-api working branch | `docs/integrated-search-document-plan-20261007` |
| working branch HEAD | `7f3b5bf9a69c6bda25947da869fdf75c9db11d55` |
| tai-api origin/main | `d9ae49d05a4c35f19e842823d5cde9bebbd3f99a` |
| OBJ00 base SHA | `aa46bbb7ed07416784f3310681540c9fce7eef92` |
| document scope drift (OBJ01 이후) | NO |

---

## MUTATION

| 항목 | 건수 |
|---|---:|
| application code change | 0 |
| DB write | 0 |
| storage write | 0 |
| deploy | 0 |

---

## CATALOG

| 항목 | 값 |
|---|---|
| document_forms | 260 |
| doc_id unique | YES (260/260) |
| mapped (type_mapping) | 30 |
| unmapped | 230 |
| orphan mappings | 0 |
| coverage | 11.5% (30/260) |

---

## TYPE MAPPING

| 항목 | 값 |
|---|---|
| rows | 30 |
| doc_types | 8 (EQUIP/INSP/EDU/CHK/TBM/APPT/CONLOG/PPE) |
| doc_details (non-null) | 14 (EQUIP 전용: FIRE/ELEC/ELEV/ASBESTOS/HAZMAT×2/MACHINE×2/SCAFFOLD×2/CRANE/GUARD/GAS/BOILER/REFRIG) |
| PK | id (uuid) |
| UNIQUE | doc_id |
| FK to document_forms | 없음 |
| FK to runtime_form_schema | 없음 |
| Python consumer | 없음 |

---

## REGISTRY

| 항목 | 값 |
|---|---|
| rows | 8 |
| IMPLEMENTED | 5 (CHK/EQUIP/INSP/PPE/TBM) |
| PARTIAL | 0 |
| METADATA_ONLY | 1 (APPT) |
| MISSING | 2 (CONLOG/EDU) |

---

## RUNTIME SCHEMA

| 항목 | 값 |
|---|---|
| total | 324 |
| APPROVED_FOR_RUNTIME_USE | 1 |
| CANDIDATE | 323 |
| PK | id (uuid) |
| FK | schema_candidate_id → document_schema_candidate.id |

---

## SOURCE TRACE

| 항목 | 값 |
|---|---|
| doc_id non-null | 260 |
| form_code non-null | 64 |
| source_id non-null | 324 (전량) |
| source_table non-null | 324 (전량) |
| source_table distribution | document_forms=260 / document_form_master=64 |
| doc_id distinct | 260 (중복 없음) |
| 1 doc_id → 1 schema | YES (현재 데이터 기준) |
| exact source row identity | 324/324 (CORR-4: GPT 독립검증 추가 확인) |

CORR-4 상세:
- source_trace.source_id → document_forms.id = 260/260 MATCH
- source_trace.doc_id → document_forms.doc_id = 260/260 MATCH
- source_trace.source_id → document_form_master.id = 64/64 MATCH
- source_trace.form_code → document_form_master.form_code = 64/64 MATCH

---

## EXACT BINDING

| 분류 | 건수 |
|---|---:|
| EXPLICIT_DIRECT_BINDING | 0 |
| EXACT_DOC_ID_EVIDENCE (E1) | 260 |
| EXACT_SOURCE_ROW_EVIDENCE (E2) | 64 |
| EXACT_FORM_CODE_EVIDENCE (E3) | 64 |
| NO_EXACT_BINDING | 0 |
| AMBIGUOUS_EXACT_EVIDENCE | 0 |

E2와 E3는 동일 64건에 동시 적용 (document_form_master 기원).
E2/E3 64건은 catalog(document_forms)와 직접 연결 경로 없음.

---

## APPROVED SCHEMA

| 항목 | 값 |
|---|---|
| id | `dc79ac3c-388c-42dc-b029-3dd9bda54a47` |
| form_name | 점검 결과 기록서 (범용) |
| source_table | document_form_master |
| form_code | GEN-INSPECT-RESULT-001 |
| binding state | INDIRECT_EXACT_EVIDENCE_ONLY |
| catalog doc_id 연결 | NO |
| document_type_mapping 연결 | NO |
| document_type_registry 연결 | NO |

---

## FRONTEND

| 항목 | 값 |
|---|---|
| /document-forms list source | GET /document-forms → document_forms |
| /engine-document list source | GET /engine/forms → document_form_master |
| open/edit source | 없음 (미구현) |
| /document-forms break point | form_schema_id undefined → create_document() 미호출 |
| /engine-document break point | download 404 + autoFill Phase 2 미구현 + list params MISMATCH |

---

## EXPORT (CORR-3: DB CHECK 반영)

`chk_gd_export` CHECK: HTML / PDF / XLSX / PRINT_VIEW / API_RESPONSE 허용. DOCX/HWP 없음.

| format | DB_ALLOWED | renderer | 판정 |
|---|---|---|---|
| PDF | YES | YES (Gotenberg) | ACTUAL — 견적서 경로 PRODUCTION_VERIFIED / 문서엔진 경로 UNVERIFIED |
| HTML | YES | YES (Jinja2) | ACTUAL |
| XLSX | YES | NO | DB_ALLOWED_BUT_NOT_IMPLEMENTED |
| PRINT_VIEW | YES | NO (별도 route 없음) | DB_ALLOWED_BUT_NOT_IMPLEMENTED |
| API_RESPONSE | YES | PARTIAL | DB_ALLOWED_PARTIAL |
| DOCX | NO | NO | NOT_ALLOWED_NOT_PRESENT |
| HWP | NO | NO | NOT_ALLOWED_NOT_PRESENT |

---

## BINDING FEASIBILITY

| 방안 | Required DDL | catalog coverage | Migration risk |
|---|---|---|---|
| A. mapping-column | ALTER TABLE document_type_mapping ADD COLUMN | 30/260 | LOW |
| B. binding-table | CREATE TABLE document_schema_binding + 260 INSERT | 260/260 | MEDIUM |
| C. source-trace-only | 없음 | 260/260 (doc_id 경로) | NONE |

NO RECOMMENDATION MADE

---

## FILES CREATED

```
docs/document-engine/obj02/
  OBJ02_A_CURRENT_STATE.md                       (이 파일)
  GIT_HISTORY_EVIDENCE.md
  DOCUMENT_CATALOG_CURRENT.csv                   (261줄 / 17컬럼)
  DOCUMENT_TYPE_MAPPING_CURRENT.csv              (31줄 / 7컬럼)
  CATALOG_TYPE_MAPPING_COVERAGE.csv              (261줄 / 6컬럼)
  TYPE_MAPPING_CENSUS.md
  TYPE_REGISTRY_RUNTIME_EVIDENCE.md
  RUNTIME_SCHEMA_CURRENT.csv                     (325줄 / 13컬럼)
  RUNTIME_SCHEMA_SOURCE_TRACE_CENSUS.md
  CATALOG_RUNTIME_EXACT_BINDING_EVIDENCE.csv     (325줄 / 9컬럼)
  APPROVED_SCHEMA_TRACE.md
  CANDIDATE_SCHEMA_CENSUS.md
  CURRENT_LIST_VIEW_CONTRACT.md
  DOCUMENT_LIST_READMODEL_SOURCE_MATRIX.md
  SCHEMA_BINDING_FEASIBILITY.md
  EXPORT_FORMAT_CAPABILITY.md
```

총 16개

---

## CORRECTIONS APPLIED

| CORR | 내용 | 파일 |
|---|---|---|
| CORR-1 | Template 실제 경로 수정 (`templates/documents/`) | TYPE_REGISTRY_RUNTIME_EVIDENCE.md |
| CORR-2 | Generic generation consumer 분리 (`document_generate.py` vs `document_engine.py`) | TYPE_REGISTRY_RUNTIME_EVIDENCE.md |
| CORR-3 | DB CHECK (`chk_gd_export`) 반영: XLSX=DB_ALLOWED_BUT_NOT_IMPLEMENTED, DOCX/HWP=NOT_ALLOWED | EXPORT_FORMAT_CAPABILITY.md, 이 파일 |
| CORR-4 | Source identity 추가 실증: 324/324 MATCH (GPT 독립검증 결과) | RUNTIME_SCHEMA_SOURCE_TRACE_CENSUS.md, 이 파일 |

---

## OBJ02-A = COMPLETE
GPT INDEPENDENT VERIFICATION = REQUIRED (FINAL REVERIFY)

NO ARCHITECTURE DECISION MADE
NO SEMANTIC MAPPING MADE
NO PRODUCTION MUTATION
