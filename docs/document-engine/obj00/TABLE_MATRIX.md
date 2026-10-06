# TABLE_MATRIX

조사일: 2026-10-07
DB: Supabase vwlahtguyggrhvslabax

---

## document_forms (260행)

| 항목 | 값 |
|---|---|
| PK | id (uuid) |
| 식별자 | doc_id (text, NOT NULL, e.g. DOC-BLD-001) |
| 컬럼 수 | 43 |
| RLS | 확인 안 됨 (SELECT 가능) |
| API consumer | routers/document_forms.py, routers/document_generate.py (간접) |
| 주요 컬럼 | doc_id, doc_name, sector, category, law_ref, tai_grade, tai_auto, tai_method, doc_format, is_active, file_url, required_fields(jsonb), has_legal_form |
| is_active=true | 260 (전체) |
| source_trace 참조 | runtime_form_schema.source_trace->>'doc_id'로 260건 연결 |

---

## form_templates (11행)

| 항목 | 값 |
|---|---|
| PK | id (uuid) |
| 주요 식별자 | form_code (text) |
| 용도 | 법정 별지 (LEGAL type) |
| API consumer | routers/engine_document.py |
| runtime_form_schema 연결 | schema_candidate_id JOIN = 0건 |

---

## document_form_master (64행)

| 항목 | 값 |
|---|---|
| PK | id (uuid) |
| 주요 식별자 | form_code (text) |
| 용도 | 표준/자유서식 (STANDARD/FREE type) |
| API consumer | routers/engine_document.py |
| runtime_form_schema 연결 | schema_candidate_id JOIN = 0건 (직접 FK 없음) |
| source_trace 참조 | runtime_form_schema.source_trace->>'source_table'='document_form_master' 64건 |

---

## document_type_registry (8행)

| 항목 | 값 |
|---|---|
| PK | doc_type (text) |
| 주요 컬럼 | type_label, template_file, fetcher_key, fetcher_status, note |
| API consumer | routers/document_generate.py, services/document_engine/generator.py |
| fetcher_status 분포 | EXISTING=5, NEW_NEEDED=2, NO_SOURCE=1 |

---

## runtime_form_schema (324행)

| 항목 | 값 |
|---|---|
| PK | id (uuid) |
| 컬럼 수 | 13 |
| 주요 컬럼 | schema_candidate_id, document_family, form_name, form_type, status, version, field_count, checklist_count, evidence_count, source_trace(jsonb) |
| status 분포 | APPROVED_FOR_RUNTIME_USE=1, CANDIDATE=323 |
| form_type 분포 | OFFICIAL=287, CUSTOM=32, INTERNAL=5 |
| document_family 분포 | 21개 고유값 (일상=98, 정기=72, UNRESOLVED=36, 작업시=24, 착공전=23, 사고시=22, 변경시=15, DOCUMENT=11, 기타) |
| source_trace 구조 | {doc_id, form_code, source_id, source_table} |
| API consumer | routers/document_engine_api.py (schemas 엔드포인트) |

---

## runtime_field (1,308행)

| 항목 | 값 |
|---|---|
| 주요 FK | schema_id → runtime_form_schema.id |
| API consumer | routers/document_engine_api.py (schema detail, document update) |

---

## runtime_checklist_item (802행)

| 항목 | 값 |
|---|---|
| 주요 FK | schema_id → runtime_form_schema.id |
| API consumer | routers/document_engine_api.py (schema detail, confirm) |

---

## runtime_evidence_field (202행)

| 항목 | 값 |
|---|---|
| 주요 FK | schema_id → runtime_form_schema.id |
| API consumer | routers/document_engine_api.py (schema detail, document update) |

---

## runtime_document_data (1행)

| 항목 | 값 |
|---|---|
| PK | id (uuid) |
| status | DRAFT (1건) |
| API consumer | routers/document_engine_api.py |

---

## runtime_document_approval (0행)

| 항목 | 값 |
|---|---|
| 용도 | APPROVED_BY_HUMAN 전이 시 기록 |
| API consumer | routers/document_engine_api.py (status 전이 route) |

---

## runtime_lifecycle_audit_log (3행)

| 항목 | 값 |
|---|---|
| 용도 | 상태 전이 감사 로그 |
| API consumer | routers/document_engine_api.py (audit-log 엔드포인트) |

---

## runtime_state_transition_rule (23행)

| 항목 | 값 |
|---|---|
| 용도 | 허용된 상태 전이 규칙 정의 |
| API consumer | routers/document_engine_api.py (transitions 엔드포인트) |

---

## generated_document (1,544행)

| 항목 | 값 |
|---|---|
| PK | id (uuid) |
| 컬럼 수 | 22 |
| 주요 컬럼 | runtime_document_id, form_schema_id, export_type, storage_path, bucket_id, status, flow_key, trace_id, tenant_id, factory_id, actor_id, form_code, document_name, version, download_url, snapshot_id, pdf_hash, generator_version, failure_reason |
| status 분포 | GENERATED=9, PENDING=1,527, FAILED=4, TEMPLATE_MISSING=4 |
| storage_path not null | 0 (전체 NULL) |
| download_url not null | 0 (전체 NULL) |
| failure_reason not null | 0 (전체 NULL) |
| runtime_document_id not null | 2 |
| export_type 분포 | PDF=1,543, HTML=1 |
| bucket_id default | form-outputs |

---

## evidence_vault_link (0행)

| 항목 | 값 |
|---|---|
| 용도 | 증빙 첨부 연결 |
| API consumer | routers/document_engine_api.py (evidence 엔드포인트) |

---

## documents (4행)

| 항목 | 값 |
|---|---|
| PK | id (uuid) |
| 컬럼 수 | 32 |
| 주요 컬럼 | company_id, factory_id, category(enum), source(enum), file_name, storage_path, bucket_id, file_size, mime_type, generated_by, generation_params, uploaded_by, deleted_at, is_active, retention_years |
| 현재 4건 모두 | generated_by=member_quote_pdf_v1, category=general, source=AUTO_GENERATED, mime_type=application/pdf |
| bucket_id | company-docs |
| 문서 모듈 문서 | 0건 (문서 모듈 미사용 — 견적서 PDF만 존재) |
