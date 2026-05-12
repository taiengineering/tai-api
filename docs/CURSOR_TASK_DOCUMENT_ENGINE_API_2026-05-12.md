# Cursor 작업지시서: TAI 문서엔진 API 구현
**작성일**: 2026-05-12
**브랜치**: dev
**레포**: taiengineering/tai-api

---

## 선행 규칙 (필수 준수)

- `docs/DEV_RULES_SERVICE_LAYER.md` 준수
- Router = HTTP만 (SQL 금지), Service = 비즈니스 로직 (FastAPI import 금지)
- 파일당 최대 400줄 / 15KB
- `from db.supabase_client import get_supabase`
- dev 브랜치에서 작업 → main으로 PR

---

## 절대 금지

1. missing field 자동 채우기
2. inferred default value 생성
3. auto approval
4. auto document finalize
5. Candidate를 Final로 변환
6. required 자동 확정
7. source trace 없는 필드 생성

---

## DB 테이블 (이미 존재 — DDL 건드리지 마라)

### 핵심 테이블

**runtime_form_schema** (323건)
```
id, schema_candidate_id, document_family, form_type(OFFICIAL|CUSTOM|INTERNAL),
form_name, field_count, checklist_count, evidence_count, source_trace,
status(CANDIDATE|NEEDS_HUMAN_REVIEW|APPROVED_BY_HUMAN|APPROVED_FOR_RUNTIME_USE|REJECTED_BY_HUMAN|ARCHIVED),
version, created_at, updated_at
```

**runtime_field** (1,303건)
```
id, form_schema_id(FK→runtime_form_schema), field_candidate_id, field_label,
field_key, input_type(text|textarea|number|date|datetime|checkbox|radio|select|file|image|signature|measurement|table|multi_row),
field_order, required_status(CANDIDATE_ONLY|NEEDS_HUMAN_REVIEW|REQUIRED_BY_HUMAN|NOT_REQUIRED),
default_value, placeholder, validation_rule, source_trace, status, created_at
```

**runtime_checklist_item** (802건)
```
id, form_schema_id(FK), checklist_candidate_id, raw_text,
input_type(CHECK|PASS_FAIL|VALUE_INPUT), item_order, source_trace, status, created_at
```

**runtime_evidence_field** (202건)
```
id, form_schema_id(FK), evidence_candidate_id, evidence_family,
upload_type(image_upload|attachment|measurement_input|signature|geo_location|timestamp_auto|inspector_identity),
evidence_label, source_trace, status, created_at
```

**runtime_document_data** (운영 — 현재 0건)
```
id, form_schema_id(FK), factory_id, company_id, runtime_data_json,
evidence_links, created_by, updated_by,
status(DRAFT|IN_PROGRESS|SUBMITTED_FOR_REVIEW|REVIEW_PENDING|APPROVED_BY_HUMAN|REJECTED_BY_HUMAN|RETURNED_FOR_EDIT|ARCHIVED),
created_at, updated_at, submitted_at, submitted_by,
reviewed_at, reviewed_by, review_comment, archived_at, version, parent_document_id
```
CHECK: APPROVED_BY_HUMAN 시 reviewed_by NOT NULL 필수

**runtime_state_transition_rule** (9건)
```
id, from_status, to_status, requires_reviewer, requires_comment, description
```

**runtime_document_review** (운영)
```
id, runtime_document_id(FK), review_reason, detail,
status(REVIEW_PENDING|APPROVED_BY_HUMAN|REJECTED_BY_HUMAN|RETURNED_FOR_EDIT),
reviewer_id, reviewed_at, review_action(APPROVE|REJECT|RETURN_FOR_EDIT|REQUEST_MORE_DATA),
review_comment, created_at
```
CHECK: status != REVIEW_PENDING 시 reviewer_id NOT NULL 필수

**runtime_document_approval** (운영)
```
id, runtime_document_id(FK), reviewer_id(NOT NULL), reviewed_at, review_action,
review_comment, source_trace_snapshot, runtime_snapshot, evidence_snapshot,
rollback_available, created_at
```

**evidence_vault_link** (운영)
```
id, document_data_id(FK→runtime_document_data), evidence_file_id,
evidence_type(IMAGE|PDF|HWP|EXCEL|MEASUREMENT_FILE|SIGNATURE_IMAGE|GEO_EVIDENCE|VIDEO|OTHER),
storage_path, bucket_id, status(LINKED|UNLINKED|EXPIRED),
linked_field_id, uploaded_by, uploaded_at, file_name, file_size, mime_type
```

**generated_document** (운영)
```
id, template_id, runtime_document_id(FK→runtime_document_data), form_schema_id,
export_type(HTML|PDF|XLSX|PRINT_VIEW|API_RESPONSE), storage_path, bucket_id,
status(GENERATED|SIGNED|SUBMITTED|ARCHIVED), created_at
```

**runtime_lifecycle_audit_log** (운영)
```
id, runtime_document_id(FK), action(CREATED|FIELD_EDIT|CHECKLIST_EDIT|EVIDENCE_UPLOAD|
STATUS_CHANGE|SUBMITTED|REVIEW_ACTION|APPROVAL|REJECTION|RETURN_FOR_EDIT|ARCHIVED|ROLLBACK|REVISION_CREATED),
actor_id, before_state, after_state, field_changes, rollback_available, created_at
```

---

## 파일 구조 (생성할 파일 4개)

```
schemas/
  document_engine_schema.py    (~150줄)
services/
  document_engine_svc.py       (~380줄)
routers/
  document_engine_api.py       (~350줄)
main.py                        (2줄 추가)
```

---

## API 엔드포인트 요약

| Method | Path | 역할 |
|--------|------|------|
| GET | /document-engine/schemas | Runtime Form Schema 목록 |
| GET | /document-engine/schemas/{id} | Schema 상세 (fields+checklists+evidence) |
| POST | /document-engine/documents | 문서 생성 (DRAFT) |
| GET | /document-engine/documents | 문서 목록 |
| GET | /document-engine/documents/{id} | 문서 상세 |
| PATCH | /document-engine/documents/{id} | 문서 수정 |
| POST | /document-engine/documents/{id}/status | 상태 전이 |
| GET | /document-engine/transitions | 전이 규칙 목록 |
| POST | /document-engine/documents/{id}/evidence | 증빙 업로드 |
| GET | /document-engine/documents/{id}/evidence | 증빙 목록 |
| POST | /document-engine/documents/{id}/generate | 문서 생성 |
| GET | /document-engine/documents/{id}/generated | 생성된 문서 목록 |
| GET | /document-engine/metrics | 전체 메트릭 |
| GET | /document-engine/metrics/factory/{id} | 시설별 메트릭 |
| GET | /document-engine/documents/{id}/audit-log | 감사 로그 |

---

## 검증 체크리스트

- [ ] GET /document-engine/schemas → 323건 반환
- [ ] GET /document-engine/schemas/{id} → fields + checklists + evidence 포함
- [ ] POST /document-engine/documents → DRAFT 생성, audit log 기록
- [ ] POST /document-engine/documents/{id}/status → 전이 규칙 검증
- [ ] 허용 안 된 전이 시도 → 400 에러
- [ ] APPROVED_BY_HUMAN 시 actor_id 없으면 → DB CHECK 위반 에러
- [ ] POST /document-engine/documents/{id}/evidence → 파일 업로드 + vault link
- [ ] ARCHIVED 문서 수정 시도 → 400 에러
- [ ] GET /document-engine/metrics → v_runtime_metrics 뷰 데이터

커밋 메시지: `feat: 문서엔진 API v1.0.0 (schema + service + router)`
