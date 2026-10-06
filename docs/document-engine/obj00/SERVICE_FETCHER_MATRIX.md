# SERVICE_FETCHER_MATRIX

조사일: 2026-10-07
대상: taiengineering/tai-api (main aa46bbb7)

---

## 서비스 목록

| 서비스 파일 | 역할 | 주요 callers | DB 의존 | storage 의존 | external 의존 | 테스트 | dead/legacy |
|---|---|---|---|---|---|---|---|
| services/document_engine_svc.py | Runtime Document Engine CRUD, state machine, audit | routers/document_engine_api.py | runtime_document_data, runtime_form_schema, runtime_field, runtime_checklist_item, runtime_evidence_field, runtime_state_transition_rule, runtime_lifecycle_audit_log, runtime_document_approval, evidence_vault_link, generated_document, v_runtime_metrics, v_runtime_metrics_by_factory | NONE | NONE | test_document_engine_status_auth.py, test_document_confirm_authz.py, test_document_confirm_svc.py | NO |
| services/document_engine/renderer.py | Jinja2 HTML render + Gotenberg PDF | routers/document_engine.py, routers/compliance_report.py, services/document_engine/generator.py | NONE (파일 I/O) | NONE (template 파일 읽기) | Gotenberg (httpx async) | NONE | NO |
| services/document_engine/generator.py | doc_type registry → fetcher dispatch → render | routers/document_generate.py | document_type_registry | NONE | Gotenberg (via renderer) | NONE | NO |
| services/document_svc.py | 파일 upload/download/metadata, signed URL | routers/documents.py(미탑재), routers/document_engine.py, routers/inspection_record_read.py, routers/contract_kmong.py, routers/diagnosis_report.py, routers/diagnosis_proposal.py, services/member_quote_pdf_svc.py | documents | Supabase storage bucket `company-docs` | NONE | test_member_quote_pdf.py, test_inspection_record_photos.py, test_paid_result_pdf_router_v1.py | NO — 광범위 사용 |
| services/document_forms_service.py | Document forms catalog list/detail/stats | routers/document_forms.py | document_forms | NONE | NONE | NONE | NO |
| services/document_schema_renderer.py | Deterministic HTML renderer (confirm seal WP-05A) | services/document_confirm_svc.py (document_confirm_svc → document_engine_api) | NONE (순수 함수) | NONE | NONE | test_document_schema_renderer.py | NO |
| services/document_confirm_svc.py | confirm_document_atomic — APPROVED_BY_HUMAN transaction | routers/document_engine_api.py (status 전이 route) | runtime_document_data(SELECT FOR UPDATE), runtime_form_schema, runtime_field, runtime_checklist_item | NONE | NONE | test_document_confirm_svc.py, test_document_confirm_authz.py | NO |
| services/runtime_document_context.py | runtime context dict 구성 (facility_condition + runtime_facility_profile) | 발견 안 됨 — 어느 router/service에서도 import 없음 | facility_condition, runtime_facility_profile | NONE | NONE | NONE | LEGACY |
| services/document_snapshot_integrity.py | Snapshot integrity 검증 (Q4 hash) | services/document_confirm_svc.py → routers/document_engine_api.py (간접) | UNCLEAR | NONE | NONE | test_document_snapshot_integrity.py | NO (active chain) |
| services/gotenberg_svc.py | 동기 Gotenberg PDF renderer (strict, no fallback) | services/member_quote_pdf_svc.py → routers/member_quotes.py, routers/admin_quotes.py | NONE | NONE | Gotenberg (httpx sync) | test_member_quote_pdf.py | NO |

---

## Fetcher 목록 (services/document_engine/fetchers/)

| 파일 | exists | fetcher_key | 실제 사용 | callers | 사용 테이블 |
|---|---|---|---|---|---|
| base_fetcher.py | YES | (ABC base) | YES | 모든 fetcher가 상속 | NONE |
| inspection_fetcher.py | YES | `"inspection"` | YES | services/document_engine/generator.py FETCHER_MAP | equipment_assets, factories, companies, users, safety_inspections |
| tbm_fetcher.py | YES | `"tbm"` | YES | services/document_engine/generator.py FETCHER_MAP + routers/document_engine.py _FETCHERS dict | tbm_meetings, tbm_attendees, factories |
| APPT fetcher | NOT FOUND | N/A | NO | NONE | NONE |
| CHK fetcher (별도) | NOT FOUND | N/A | NO — inspection_fetcher로 커버 | NONE | NONE |
| CONLOG fetcher | NOT FOUND | N/A | NO — document_type_registry.fetcher_status=NEW_NEEDED | NONE | NONE |
| EDU fetcher | NOT FOUND | N/A | NO — document_type_registry.fetcher_status=NEW_NEEDED | NONE | NONE |
| EQUIP fetcher (별도) | NOT FOUND | N/A | NO — inspection_fetcher로 커버 | NONE | NONE |
| INSP fetcher (별도) | NOT FOUND | N/A | NO — inspection_fetcher로 커버 | NONE | NONE |
| PPE fetcher (별도) | NOT FOUND | N/A | NO — inspection_fetcher로 커버 | NONE | NONE |

### FETCHER_MAP (generator.py 실제 코드)
```python
FETCHER_MAP = {
    "inspection": InspectionFetcher,
    "tbm": TbmFetcher,
}
```

### Fetcher gap 요약

document_type_registry에는 8개 doc_type이 있으나 실제 구현된 fetcher는 2개 (inspection, tbm).

| doc_type | fetcher_key | fetcher_file_exists | 실행 가능 |
|---|---|---|---|
| APPT | NULL | NO | NO |
| CHK | inspection | NO (inspection_fetcher.py 재사용) | YES (inspection_fetcher 사용 시) |
| CONLOG | construction | NO | NO |
| EDU | education | NO | NO |
| EQUIP | inspection | NO (inspection_fetcher.py 재사용) | YES (inspection_fetcher 사용 시) |
| INSP | inspection | NO (inspection_fetcher.py 재사용) | YES (inspection_fetcher 사용 시) |
| PPE | inspection | NO (inspection_fetcher.py 재사용) | YES (inspection_fetcher 사용 시) |
| TBM | tbm | YES (tbm_fetcher.py) | YES |

---

## Gotenberg 통합 분포 (3개)

| 위치 | env var | fallback | transport | 사용 경로 |
|---|---|---|---|---|
| services/document_engine/renderer.py | GOTENBERG_URL | `http://gotenberg.railway.internal:3000` | httpx async | document_generate + compliance_report + document_engine |
| services/gotenberg_svc.py | GOTENBERG_URL | NONE (strict, fail-closed) | httpx sync | member_quotes + admin_quotes |
| routers/diagnosis_report.py (inline) | GOTENBERG_URL | `http://tai-gotenberg.internal:3000` | httpx async inline | diagnosis PDF |

**env var 이름**: 3곳 모두 `GOTENBERG_URL` (일치)
**fallback 호스트명**: renderer.py ≠ diagnosis_report.py (불일치)
**.env.example**: `GOTENBERG_URL` 미문서화
