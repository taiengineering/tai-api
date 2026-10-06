# CURRENT_LIST_VIEW_CONTRACT

조사일: 2026-10-07
WO: WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001
Source: tai-api HEAD 7f3b5bf9 (branch docs/integrated-search-document-plan-20261007)
실행자: Claude Code

---

## /document-forms 화면

| 항목 | 현재 소스 기준 사실 |
|---|---|
| list source API | `GET /document-forms` |
| list source table | `document_forms` (260행) |
| 지원 params | `page`, `per_page` (pagination 지원) |
| 노출 데이터 | doc_id, doc_name, sector, category, law_ref, tai_grade, obligation 등 document_forms 컬럼 |
| selected row key | doc_id |
| HTML editable view | 없음 — open 시 `create_document()` 호출 경로만 존재 |
| runtime_form_schema binding key 기대 | `form_schema_id` (composable pickFormSchemaId() 에서 tpl.form_schema_id \|\| tpl.runtime_form_schema_id \|\| tpl.schema_id 순서로 탐색) |
| form_schema_id 공급 여부 | **없음** — document_forms 테이블에 form_schema_id 컬럼 없음 |
| HTML edit/save chain | 없음 (구현 없음) |
| 현재 break point | pickFormSchemaId() 실행 → undefined → "이 서식에 연결된 form_schema_id가 없습니다" 에러 throw → create_document() 미호출 |

---

## /engine-document 화면

| 항목 | 현재 소스 기준 사실 |
|---|---|
| list source API | `GET /engine/forms` |
| list source table | `document_form_master` (64행, form_type/form_category/obligation_type/sector/is_active 필터) |
| 지원 params (backend) | form_type, form_category, obligation_type, sector (default=BUILDING), is_active (default=True) |
| frontend 전송 params | page, size, keyword, category — **MISMATCH** (pagination/keyword 미지원) |
| 노출 데이터 | form_code, form_name, form_type, 등 document_form_master 컬럼 |
| selected row key | form_code |
| HTML editable view | 없음 |
| runtime_form_schema binding key 기대 | 없음 (명시적 binding 코드 없음) |
| download endpoint | `GET /engine/forms/{form_code}/download` — **404 NOT IMPLEMENTED** |
| autoFill | "Phase 2" toast 반환 — 항상 미구현 |
| 현재 break point | 1. list params MISMATCH (keyword/pagination 미지원) 2. download 404 3. autoFill Phase 2 미구현 |

---

## 두 화면의 list→open→edit→save chain 실제 break point

### /document-forms

```
[catalog list] → select doc_id
  → pickFormSchemaId(tpl) → undefined (form_schema_id 컬럼 없음)
  → throw Error("이 서식에 연결된 form_schema_id가 없습니다")
  → create_document() 미호출 [BREAK]
```

### /engine-document

```
[form master list, keyword/pagination MISMATCH] → select form_code
  → click download → GET /engine/forms/{code}/download → 404 [BREAK]
  → autoFill → "Phase 2 준비 중" toast [BREAK]
```

---

## frontend에서 runtime_form_schema binding을 기대하는 key

| 화면 | 기대 key | 실제 공급 여부 |
|---|---|---|
| /document-forms | form_schema_id (tpl에서) | NO (document_forms에 없음) |
| /engine-document | 명시적 binding 없음 | N/A |

---

## MUTATION

application code = 0 / DB write = 0
