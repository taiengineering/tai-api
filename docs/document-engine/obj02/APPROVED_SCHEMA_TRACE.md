# APPROVED_SCHEMA_TRACE

조사일: 2026-10-07
WO: WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001
DB: Supabase vwlahtguyggrhvslabax
실행자: Claude Code

---

## APPROVED_FOR_RUNTIME_USE Schema 기본 정보

| 항목 | 값 |
|---|---|
| id | `dc79ac3c-388c-42dc-b029-3dd9bda54a47` |
| schema_candidate_id | `167a9e43-5244-4793-bc4a-11e640391065` |
| document_family | DOCUMENT |
| form_type | CUSTOM |
| form_name | 점검 결과 기록서 (범용) |
| status | APPROVED_FOR_RUNTIME_USE |
| version | 1 |
| field_count | 5 |
| checklist_count | 0 |
| evidence_count | 0 |

---

## source_trace

```json
{
  "doc_id": null,
  "form_code": "GEN-INSPECT-RESULT-001",
  "source_id": "4236fb68-a620-4804-8951-7064ad908cd4",
  "source_table": "document_form_master"
}
```

---

## source row 확인

| 항목 | 값 |
|---|---|
| source_table | document_form_master |
| source_id | 4236fb68-a620-4804-8951-7064ad908cd4 |
| source row 실존 여부 | YES (E2 exact source_row 확인: 64건 중 포함) |
| form_code 일치 여부 | YES (E3 exact form_code 확인: document_form_master.form_code = GEN-INSPECT-RESULT-001) |
| document_form_master.doc_id 컬럼 | 없음 (doc_id 컬럼 존재하지 않음) |

---

## 관련 runtime_field (5건)

| field_order | field_key | field_label | input_type | required_status |
|---:|---|---|---|---|
| 1 | inspection_subject | 점검 대상 | text | REQUIRED_BY_HUMAN |
| 2 | inspected_at | 점검 일시 | datetime | REQUIRED_BY_HUMAN |
| 3 | inspection_title | 점검 세트/제목 | text | NOT_REQUIRED |
| 4 | inspector_display | 점검자(표시) | text | NOT_REQUIRED |
| 5 | inspection_results | 점검 항목별 결과 | multi_row | REQUIRED_BY_HUMAN |

---

## catalog doc_id 직접 연결 여부

| 확인 항목 | 결과 |
|---|---|
| source_trace.doc_id | null |
| document_forms에 직접 연결 | NO |
| document_type_mapping 연결 | NO (document_type_mapping에 form_code=GEN-INSPECT-RESULT-001 행 없음) |
| document_type_registry 연결 | NO (doc_type이 없으므로 registry row와 연결 불가) |
| frontend /document-forms 선택 가능 여부 | NO (catalog 목록에서 선택 → form_schema_id 미확인 경로) |

---

## 판정

**INDIRECT_EXACT_EVIDENCE_ONLY**

근거:
- source_id → document_form_master PK 정확히 일치 (E2)
- form_code → document_form_master.form_code 정확히 일치 (E3)
- document_forms.doc_id와의 직접 연결 없음 (doc_id = null)
- document_type_mapping, document_type_registry에 대응 행 없음
- 현재 frontend /document-forms 에서 이 schema를 통해 문서를 생성하는 경로 없음

---

## MUTATION

application code = 0 / DB write = 0
