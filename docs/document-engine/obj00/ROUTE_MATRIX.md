# ROUTE_MATRIX

조사일: 2026-10-07
대상: taiengineering/tai-api (main aa46bbb7)
조사방법: router_registry/ + routers/ 전수 코드 조사

---

## MOUNTED 라우터 (router_registry/document_engine.py에 등록)

모든 아래 라우터는 `_load_all_modules()` 방식으로 main.py에서 로드됨.

### routers/document_forms.py

| method | path | purpose | backing_service | backing_table | output | auth | status |
|---|---|---|---|---|---|---|---|
| GET | /document-forms | 서식 목록 조회 | document_forms_service.list_document_forms | document_forms | JSON | NONE | ACTIVE |
| GET | /document-forms/stats | 서식 통계 | document_forms_service.get_document_forms_stats | document_forms | JSON | NONE | ACTIVE |
| GET | /document-forms/{doc_id} | 서식 상세 | document_forms_service.get_document_form | document_forms | JSON | NONE | ACTIVE |

### routers/document_engine.py

| method | path | purpose | backing_service | backing_table | output | auth | status |
|---|---|---|---|---|---|---|---|
| GET | /document-forms/{doc_id}/preview | HTML 미리보기 (TBM 전용) | TbmFetcher + render_document_html | tbm_meetings, tbm_attendees, factories | HTML | NONE | ACTIVE |
| POST | /document-forms/{doc_id}/generate | PDF 생성 → bytes + register_generated | TbmFetcher + generate_document_pdf + document_svc.register_generated | tbm_meetings, factories, documents | application/pdf (bytes) | NONE | ACTIVE |

**주의:** `/document-forms/{doc_id}` prefix를 document_forms.py와 공유함. preview/generate는 engine.py, 목록/상세는 forms.py.

### routers/document_engine_api.py

| method | path | purpose | backing_service | backing_table | output | auth | status |
|---|---|---|---|---|---|---|---|
| GET | /document-engine/schemas | Runtime Form Schema 목록 | document_engine_svc.list_form_schemas | runtime_form_schema | JSON | NONE | ACTIVE |
| GET | /document-engine/schemas/{schema_id} | Schema 상세 + fields | document_engine_svc.get_form_schema_detail | runtime_form_schema, runtime_field, runtime_checklist_item, runtime_evidence_field | JSON | NONE | ACTIVE |
| POST | /document-engine/documents | 문서 생성 (DRAFT) | document_engine_svc.create_document | runtime_document_data, runtime_form_schema | JSON | NONE | ACTIVE |
| GET | /document-engine/documents | 문서 목록 | document_engine_svc.list_documents | runtime_document_data | JSON | NONE | ACTIVE |
| GET | /document-engine/documents/{doc_id} | 문서 상세 | document_engine_svc.get_document | runtime_document_data | JSON | NONE | ACTIVE |
| PATCH | /document-engine/documents/{doc_id} | 문서 데이터 수정 | document_engine_svc.update_document | runtime_document_data, runtime_field, runtime_evidence_field | JSON | NONE | ACTIVE |
| POST | /document-engine/documents/{doc_id}/status | 상태 전이 | svc.change_status OR confirm_document_atomic | runtime_document_data, runtime_state_transition_rule, runtime_lifecycle_audit_log, runtime_document_approval | JSON | JWT (get_current_user) | ACTIVE |
| GET | /document-engine/transitions | 허용 전이 규칙 목록 | document_engine_svc.get_transitions | runtime_state_transition_rule | JSON | NONE | ACTIVE |
| POST | /document-engine/documents/{doc_id}/evidence | 증빙 등록 | document_engine_svc.link_evidence | evidence_vault_link | JSON | NONE | ACTIVE |
| GET | /document-engine/documents/{doc_id}/evidence | 증빙 목록 | document_engine_svc.list_evidence | evidence_vault_link | JSON | NONE | ACTIVE |
| POST | /document-engine/documents/{doc_id}/generate | 생성 레코드 삽입 (PENDING만) | document_engine_svc.generate_document | generated_document | JSON | NONE | ACTIVE |
| GET | /document-engine/documents/{doc_id}/generated | 생성 목록 | document_engine_svc.list_generated | generated_document | JSON | NONE | ACTIVE |
| GET | /document-engine/metrics | 전체 메트릭 | document_engine_svc.get_metrics | v_runtime_metrics | JSON | NONE | ACTIVE |
| GET | /document-engine/metrics/factory/{factory_id} | 시설별 메트릭 | document_engine_svc.get_metrics_by_factory | v_runtime_metrics_by_factory | JSON | NONE | ACTIVE |
| GET | /document-engine/documents/{doc_id}/audit-log | 감사 로그 | document_engine_svc.get_audit_log | runtime_lifecycle_audit_log | JSON | NONE | ACTIVE |

### routers/engine_document.py

| method | path | purpose | backing_service | backing_table | output | auth | status |
|---|---|---|---|---|---|---|---|
| GET | /engine/forms | 서식 목록 (LEGAL/STANDARD/FREE) | direct supabase | form_templates, document_form_master | JSON | NONE | ACTIVE |
| GET | /engine/forms/summary | 보관현황 요약 | direct supabase | form_templates, document_form_master | JSON | NONE | ACTIVE |
| GET | /engine/forms/{form_code} | 서식 상세 | direct supabase | form_templates, document_form_master | JSON | NONE | ACTIVE |
| PATCH | /engine/forms/{form_code} | 서식 수정 (admin) | direct supabase | form_templates, document_form_master | JSON | NONE | ACTIVE |

**주의:** frontend engine-document 페이지가 `/engine/forms/{form_code}/download`를 호출하나, 이 엔드포인트는 존재하지 않음 (404).

### routers/document_monitoring.py

| method | path | purpose | backing_table | auth |
|---|---|---|---|---|
| GET | /document-monitoring/summary | 감시 요약 | document_requirement_rule, engine_integrity_event | role check (request.state.user_role) |
| GET | /document-monitoring/completeness-drift | 완전성 드리프트 | engine_integrity_event | role check |
| GET | /document-monitoring/rule-drift | 룰 드리프트 | engine_integrity_event | role check |
| GET | /document-monitoring/mandatory-drift | 필수 드리프트 | engine_integrity_event | role check |
| GET | /document-monitoring/render-drift | 렌더 드리프트 | engine_integrity_event | role check |
| GET | /document-monitoring/pdf-artifact | PDF 불일치 | engine_integrity_event | role check |
| GET | /document-monitoring/explainability-audit | 설명가능성 감사 | engine_integrity_event | role check |
| GET | /document-monitoring/unsupported-document | 미지원 문서 | engine_integrity_event | role check |
| GET | /document-monitoring/requirement-rules | 요구사항 룰 목록 | document_requirement_rule | role check |
| GET | /document-monitoring/status | 상태 (hardcoded) | none | NONE |

### routers/compliance_report.py

| method | path | purpose | backing_service | output | auth |
|---|---|---|---|---|---|
| POST | /compliance-report/generate | 증빙 이행 리포트 PDF | generate_document_pdf (renderer) + inline data assembly | application/pdf (streaming) | NONE |

### routers/document_generate.py

| method | path | purpose | backing_service | backing_table | output | auth | status |
|---|---|---|---|---|---|---|---|
| GET | /documents/{doc_type}/registry | 유형 등록 정보 | generator.get_registry | document_type_registry | JSON | NONE | ACTIVE |
| POST | /documents/{doc_type}/preview | HTML 미리보기 | generator.render_html | document_type_registry + fetcher | HTML | NONE | ACTIVE |
| POST | /documents/{doc_type}/generate | PDF 생성 (streaming) | generator.render_pdf → generate_document_pdf | document_type_registry + fetcher | application/pdf (streaming) | NONE | ACTIVE |

---

## NOT MOUNTED 라우터 (파일 존재, router_registry 미등록)

| 파일 | prefix | endpoints 수 | last commit | consumers | 분류 |
|---|---|---|---|---|---|
| routers/documents.py | /documents | 10 (upload/download/delete/list 포함) | `03e13509 fix(documents): 문서 API에 인증·회사 스코프를 붙인다` | document_svc에서 사용하나 HTTP 라우터는 미탑재 | LEGACY |
| routers/document_runtime.py | /document-runtime | 5 | `b29b5411 feat: Runtime Data Binding Engine — PHASE A~I 구현` | 없음 | LEGACY |
| routers/document_schema.py | /document-schema | 5 | `bf487e3d feat: Document Schema Layer — registry 적재 스크립트 + API 라우터` | 없음 | LEGACY |

---

## 생성 경로 특이점 (두 경로 독립 추적)

### PATH 1: `POST /document-engine/documents/{doc_id}/generate`
- **router**: routers/document_engine_api.py
- **service**: document_engine_svc.generate_document
- **동작**: `generated_document` 테이블에 status=`PENDING` INSERT만 수행
- **Gotenberg 호출**: NONE
- **PDF bytes 반환**: NONE — JSON 반환
- **storage write**: NONE
- **status transition**: runtime_document_data 상태 미변경
- **코드 주석**: "GENERATED 승격은 Q5 계약에서" — 구현 STUB
- **결과**: 1,527건의 PENDING 누적 원인

### PATH 2: `POST /documents/{doc_type}/generate`
- **router**: routers/document_generate.py
- **service**: generator.render_pdf → generator._build() → document_type_registry lookup → fetcher.fetch() → generate_document_pdf
- **동작**: document_type_registry에서 template_file/fetcher_key 조회 → fetcher.fetch() → Jinja2 render → Gotenberg POST → PDF bytes 반환
- **Gotenberg 호출**: YES — `{GOTENBERG_URL}/forms/chromium/convert/html`
- **PDF bytes 반환**: YES — StreamingResponse (application/pdf)
- **storage write**: NONE
- **metadata insert**: NONE (documents 테이블 미삽입)
- **status transition**: NONE
- **실제 동작 조건**: document_type_registry에 doc_type row + fetcher_key=`inspection` 또는 `tbm` 필수
