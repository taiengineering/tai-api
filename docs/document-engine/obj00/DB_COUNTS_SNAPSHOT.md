# DB_COUNTS_SNAPSHOT

조사일: 2026-10-07
DB: Supabase project vwlahtguyggrhvslabax
조사방법: SELECT COUNT(*) via MCP execute_sql

---

## 테이블 카운트 (실측)

| 테이블 | 건수 | master plan 기대값 | 일치 |
|---|---:|---:|---|
| document_forms | 260 | 260 | YES |
| form_templates | 11 | 11 | YES |
| document_form_master | 64 | 64 | YES |
| document_type_registry | 8 | 8 | YES |
| runtime_form_schema | 324 | 324 | YES |
| runtime_field | 1,308 | 1,308 | YES |
| runtime_checklist_item | 802 | 802 | YES |
| runtime_evidence_field | 202 | 202 | YES |
| runtime_document_data | 1 | 1 | YES |
| runtime_document_approval | 0 | — | — |
| runtime_lifecycle_audit_log | 3 | — | — |
| runtime_state_transition_rule | 23 | — | — |
| generated_document | 1,544 | 1,544 | YES |
| evidence_vault_link | 0 | — | — |
| documents | 4 | 4 | YES |

---

## Status 분포

### runtime_form_schema
| status | 건수 |
|---|---:|
| APPROVED_FOR_RUNTIME_USE | 1 |
| CANDIDATE | 323 |

### generated_document
| status | 건수 |
|---|---:|
| GENERATED | 9 |
| PENDING | 1,527 |
| FAILED | 4 |
| TEMPLATE_MISSING | 4 |

### runtime_document_data
| status | 건수 |
|---|---:|
| DRAFT | 1 |

### document_forms
| is_active | 건수 |
|---|---:|
| true | 260 |
| false | 0 |

---

## document_type_registry 8건 전체

| doc_type | type_label | template_file | fetcher_key | fetcher_status |
|---|---|---|---|---|
| APPT | 선임 보고 | DOC-APPT.html | NULL | NO_SOURCE |
| CHK | 점검 체크리스트 | DOC-CHK.html | inspection | EXISTING |
| CONLOG | 공사일지 | DOC-CONLOG.html | construction | NEW_NEEDED |
| EDU | 교육일지 | DOC-EDU.html | education | NEW_NEEDED |
| EQUIP | 설비점검기록부 | DOC-EQUIP.html | inspection | EXISTING |
| INSP | 안전점검일지 | DOC-INSP.html | inspection | EXISTING |
| PPE | 보호구 착용 점검 | DOC-PPE.html | inspection | EXISTING |
| TBM | 작업 전 안전점검회의 | DOC-OSH-056.html | tbm | EXISTING |

### fetcher_status 분포
- EXISTING: 5 (CHK/EQUIP/INSP/PPE/TBM)
- NEW_NEEDED: 2 (CONLOG/EDU) — 구현 코드 없음
- NO_SOURCE: 1 (APPT) — fetcher_key NULL, fetcher 없음

---

## APPROVED_FOR_RUNTIME_USE 1건 상세

| 필드 | 값 |
|---|---|
| id | dc79ac3c-388c-42dc-b029-3dd9bda54a47 |
| form_name | 점검 결과 기록서 (범용) |
| form_type | CUSTOM |
| document_family | DOCUMENT |
| field_count | 5 |
| checklist_count | 0 |
| evidence_count | 0 |
| source_table | document_form_master |
| form_code | GEN-INSPECT-RESULT-001 |
| created_at | 2026-08-25 |
