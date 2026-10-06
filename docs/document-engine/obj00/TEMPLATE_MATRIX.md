# TEMPLATE_MATRIX

조사일: 2026-10-07
대상: templates/documents/ (taiengineering/tai-api main aa46bbb7)

---

## 전수 파일 목록

| 파일명 | doc_type | registry 연결 | 필수 Jinja2 변수 | fetcher | 테스트 | 상태 |
|---|---|---|---|---|---|---|
| DOC-OSH-056.html | TBM (doc_type=TBM) | YES — routers/document_engine.py _FETCHERS hardcode + document_type_registry | company_name, factory_name, factory_address, work_date, work_location, conductor_name, attendee_count, work_description, weather.*, risk_items[], safety_items[], attendees[], previous_issues, today_notice, manager_name, conductor_signature | TbmFetcher | NONE | READY (2경로에서 실제 사용 중) |
| DOC-INSP.html | INSP | document_type_registry row 필요 (template_file=DOC-INSP.html, fetcher_key=inspection) | company_name, company_logo, factory_name, factory_address, inspection_date, inspector_name, asset_name, asset_location, total_count, normal_count, issue_count, hold_count, items[], issue_items[], manager_name | InspectionFetcher | NONE | PARTIAL |
| DOC-CHK.html | CHK | document_type_registry row 필요 (fetcher_key=inspection) | company_name, company_logo, factory_name, factory_address, inspection_date, inspector_name, asset_name, asset_location, total_count, normal_count, issue_count, items[], manager_name | InspectionFetcher | NONE | PARTIAL |
| DOC-EQUIP.html | EQUIP | document_type_registry row 필요 (fetcher_key=inspection) | company_name, company_logo, factory_name, factory_address, asset_name, asset_code, asset_location, inspection_date, inspector_name, status_code, total_count, normal_count, issue_count, hold_count, items[], issue_items[], manager_name | InspectionFetcher | NONE | PARTIAL |
| DOC-PPE.html | PPE | document_type_registry row 필요 (fetcher_key=inspection) | company_name, company_logo, factory_name, factory_address, inspection_date, inspector_name, asset_name, asset_location, total_count, normal_count, issue_count, items[], manager_name | InspectionFetcher | NONE | PARTIAL |
| DOC-COMPLIANCE-REPORT.html | N/A (compliance_report.py 전용) | YES — routers/compliance_report.py hardcode | company_name, factory_name, factory_address, manager_name, period_from, period_to, generated_at, compliance.*, escalation.*, education.*, tbm.* | NONE (inline assembly) | NONE | READY (compliance_report.py에서 직접 사용) |
| _base.css | (shared styles) | 템플릿에서 link 참조 | N/A | NONE | NONE | READY (asset) |
| inspection_base.html | (base template) | DOC-INSP/CHK/EQUIP/PPE에서 extends 또는 참조 가능 | UNCLEAR | NONE | NONE | UNKNOWN |

### document_type_registry에 template_file 등록되었으나 templates/documents/에 없는 파일

| doc_type | template_file | exists_in_templates | 상태 |
|---|---|---|---|
| APPT | DOC-APPT.html | NOT FOUND | MISSING |
| CONLOG | DOC-CONLOG.html | NOT FOUND | MISSING |
| EDU | DOC-EDU.html | NOT FOUND | MISSING |

---

## 상태 요약

| 상태 | 파일 수 | 해당 파일 |
|---|---|---|
| READY | 3 | DOC-OSH-056.html, DOC-COMPLIANCE-REPORT.html, _base.css |
| PARTIAL | 4 | DOC-INSP.html, DOC-CHK.html, DOC-EQUIP.html, DOC-PPE.html |
| MISSING | 3 | DOC-APPT.html, DOC-CONLOG.html, DOC-EDU.html |
| UNKNOWN | 1 | inspection_base.html |

---

## 비고

- `templates/diagnosis_report_paid.html`, `diagnosis_report_paid_v2.html` — document engine 외부 경로 (routers/diagnosis_report.py 전용, 별도 inline Gotenberg)
- `templates/forms/OSHACT_FORM_002.html` — document engine renderer와 무관한 별도 경로
- TBM 문서(DOC-OSH-056.html)만 실제 production PDF 생성 경로 2개에서 모두 READY 상태
