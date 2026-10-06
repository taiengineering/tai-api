# DOCUMENT_LIST_READMODEL_SOURCE_MATRIX

조사일: 2026-10-07
WO: WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001
Source: 현재 DB + 소스 코드 근거만 사용
실행자: Claude Code

---

## 개요

DB view를 만들지 않는다. 현재 데이터에서 소비자 list에 필요한 field가 어디에서 오는지 source matrix만 기록한다.

---

## Field별 source matrix

| consumer field | current source table/column | direct available | derived | missing | ambiguity |
|---|---|---|---|---|---|
| document_key | 없음 (정의 안 됨) | NO | NO | YES | — |
| doc_id | document_forms.doc_id | YES | NO | — | — |
| doc_name | document_forms.doc_name | YES | NO | — | — |
| doc_type | document_type_mapping.doc_type | NO | YES | — | 30/260만 mapping 존재. 230건 missing |
| doc_detail | document_type_mapping.doc_detail | NO | YES | — | 30/260만. 14건만 non-null |
| availability | 없음 (정의 안 됨) | NO | NO | YES | — |
| runtime_schema_id | runtime_form_schema.id (source_trace.doc_id 역조회) | NO | YES | — | 260건만 doc_id 연결. 64건은 form_code 경로. 현재 resolver 없음 |
| working_document_id | runtime_document_data.id | NO | NO | YES | catalog↔runtime_document 연결 경로 없음 |
| working_status | runtime_document_data.status | NO | NO | YES | 연결 경로 없음 |
| confirmed_snapshot_id | runtime_document_archive (미구현) | NO | NO | YES | 테이블 없음 |
| last_saved_at | runtime_document_data.updated_at | NO | NO | YES | 연결 경로 없음 |
| last_confirmed_at | N/A | NO | NO | YES | — |
| supported_export_formats | document_type_registry 경유 파생 가능 | NO | YES | — | 30/260만 mapping→registry 경로. 230건 불가 |
| can_edit | 없음 (정의 안 됨) | NO | NO | YES | — |
| can_confirm | 없음 (정의 안 됨) | NO | NO | YES | — |
| can_export | 없음 (정의 안 됨) | NO | NO | YES | — |
| source_type | document_type_mapping.source_note 파생 가능 | NO | YES | — | 30/260만 가능 |

---

## 요약 수치

| 분류 | 건수 |
|---|---:|
| direct available | 2 (doc_id, doc_name) |
| derived (partial) | 5 (doc_type, doc_detail, runtime_schema_id, supported_export_formats, source_type) |
| missing (정의/연결 없음) | 10 (document_key, availability, working_document_id, working_status, confirmed_snapshot_id, last_saved_at, last_confirmed_at, can_edit, can_confirm, can_export) |
| **합계** | **17** |

---

## 핵심 gap 정리

### Gap 1 — runtime_schema_id resolver 없음
- 260건은 source_trace.doc_id → document_forms.doc_id 역조회로 파생 가능
- 64건은 form_code 경로만 있음 → catalog에 직접 연결 불가
- 현재 Python 코드에 doc_id → schema_id resolver 없음

### Gap 2 — working document 연결 경로 없음
- runtime_document_data는 runtime_form_schema_id를 FK로 보유하나 catalog와 직접 연결 없음
- list view에서 working_document_id, working_status, last_saved_at을 표시하려면 resolver 구현 필요

### Gap 3 — doc_type 커버리지 11.5%
- 소비자 목록의 doc_type 컬럼은 30/260에서만 가져올 수 있음
- 나머지 230건은 doc_type = NULL

### Gap 4 — 상태 컬럼 4개 정의 안 됨
- document_key, availability, can_edit, can_confirm, can_export: 현재 어떤 테이블에도 대응 컬럼 없음

---

## MUTATION

application code = 0 / DB write = 0
