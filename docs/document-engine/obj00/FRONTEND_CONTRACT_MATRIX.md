# FRONTEND_CONTRACT_MATRIX

조사일: 2026-10-07
대상: taiengineering/tai-admin (main 94f2491c)

---

## 페이지 목록

### 1. engine-document/index.vue — 서식관리

| 항목 | 값 |
|---|---|
| 파일 경로 | vue3/src/pages/engine-document/index.vue |
| route_path | /engine-document (VFS 라우팅) |
| menu_visible | YES (API /menus catalog, group_code=DOC) |
| auth | useTaiApi() composable (JWT Bearer) |

**호출 API:**

| 엔드포인트 | 기대 응답 |
|---|---|
| GET /engine/forms/summary | `{data: {total, active, expiring, expired}}` |
| GET /engine/forms?form_type=&page=&size=&keyword= | `{data: {items: [...], total: number}}` |
| GET /engine/forms/{form_code} | form row (form_code, form_name, legal_basis, use_case, submit_agency, submit_method, submit_timing, submit_url, penalty, retention_years, required_fields, form_type) |
| GET /engine/forms/{form_code}/download | blob download |

**download_mechanism:** api.download() → blob → `<a download>` anchor trigger

---

### 2. document-forms/index.vue — 서식 작성

| 항목 | 값 |
|---|---|
| 파일 경로 | vue3/src/pages/document-forms/index.vue |
| route_path | /document-forms (VFS 라우팅) |
| menu_visible | YES (API /menus catalog) |
| auth | useTaiApi() + raw fetch (generate 시) |

**호출 API:**

| 엔드포인트 | 기대 응답 |
|---|---|
| GET /document-forms?per_page=200 | array with: `doc_id\|id\|template_id\|uuid`, `doc_name\|name\|title\|form_name`, `form_schema_id\|runtime_form_schema_id\|schema_id` |
| GET /document-forms/{id} | template detail with `fields\|form_fields\|field_schema\|form_json\|required_fields` |
| GET /factories/{id} | `{factory_name, factory_code, address\|address_line1\|road_address, company_name, ksic_code, ksic_name}` |
| POST /document-engine/documents | body: `{form_schema_id, factory_id, company_id, created_by}` → `{data: {id: ...}}` |
| PATCH /document-engine/documents/{doc_id} | body: `{runtime_data_json, updated_by}` |
| POST /document-engine/documents/{doc_id}/generate | body: `{export_type: "pdf"}` → 기대: `{data: {pdf_url\|file_url\|url\|signed_url\|download_url\|storage_url\|output_url}}` |

**download_mechanism:** `window.open(url, '_blank')` (PDF), iframe (preview modal)
**generate auth:** raw fetch, AbortController 90s, 401 → localStorage clear + window.location.replace(LOGIN_PATH)

---

### 3. compliance-report/index.vue — 증빙 이행 리포트

| 항목 | 값 |
|---|---|
| 파일 경로 | vue3/src/pages/compliance-report/index.vue |
| route_path | /compliance-report (VFS 라우팅) |
| menu_visible | YES (API /menus catalog) |
| auth | raw fetch (Authorization: Bearer {localStorage}) |

**호출 API:**

| 엔드포인트 | 기대 응답 |
|---|---|
| GET /factories?company_id= | `[{id, factory_name}]` |
| POST /compliance-report/generate | binary blob (PDF) |

**download_mechanism:** raw fetch → blob → URL.createObjectURL → `<a download>` (파일명: `증빙이행리포트_{date_from}_{date_to}.pdf`)

---

## FRONTEND_BACKEND_MISMATCH_EVIDENCE

### Mismatch 1 — 심각: generate 응답에 PDF URL 없음

| 항목 | 내용 |
|---|---|
| 경로 | POST /document-engine/documents/{doc_id}/generate |
| Frontend 기대 | `body.pdf_url` \| `body.file_url` \| `body.url` \| `body.signed_url` \| `body.download_url` \| `body.storage_url` \| `body.output_url` (extractPdfUrl 함수) |
| Backend 실제 응답 | `{runtime_document_id, form_schema_id, export_type, status: "PENDING", id, created_at, ...}` — PDF URL 없음 |
| 코드 주석 | "실제 완료는 output/snapshot 계약(Q5)에서 GENERATED 승격" |
| 결과 | extractPdfUrl() = `''`. iframe preview + window.open() 모두 silent fail |

### Mismatch 2 (CORR-D 교정): /engine/forms pagination/search 계약 불일치

| 항목 | 내용 |
|---|---|
| 경로 | GET /engine/forms |
| Frontend 전송 params | form_type, page, size, keyword, category |
| Backend 실제 지원 params | form_type, form_category, obligation_type, sector, is_active (코드 실측: routers/engine_document.py 41~44행) |
| 불일치 항목 | page — backend 미지원 (no pagination, all rows 반환) |
| | size — backend 미지원 |
| | keyword — backend 미지원 (no search) |
| | category — frontend 전송명. backend는 form_category (다른 param명) |
| Frontend 기대 응답 | `{data: {items: [...], total: number}}` (pagination 포함) |
| Backend 실제 응답 | raw list (pagination wrapper 없음) |
| 결과 | page/size/keyword 무시, category는 form_category로 전달 필요 |

참고: `/document-forms?per_page=200`는 별도. backend `/document-forms` list 엔드포인트의 pagination 지원 여부는 routers/document_forms.py 기준 — 이 항목과 별개.

### 구 Mismatch 2 원문 정정

기존 보고 "per_page vs size 파라미터 불일치" (document-forms 경로)는 GPT 독립검증에서 MATCH로 정정됨.
정확한 mismatch는 위의 `/engine/forms` pagination/search contract임.

### Mismatch 3: /engine/forms/{form_code}/download 미구현

| 항목 | 내용 |
|---|---|
| 경로 | GET /engine/forms/{form_code}/download |
| Frontend 호출 | engine-document 페이지에서 api.download() |
| Backend 존재 | routers/engine_document.py에 /download path 없음 |
| 결과 | 404 |

### Mismatch 4: form_schema_id 필드 응답 여부

| 항목 | 내용 |
|---|---|
| 경로 | GET /document-forms?per_page=200 |
| Frontend 기대 | 응답 아이템에 `form_schema_id` \| `runtime_form_schema_id` \| `schema_id` 중 하나 |
| Backend 실제 응답 | document_forms 테이블 컬럼 (doc_id, doc_name, sector, category, tai_grade, ...) — form_schema_id 컬럼 없음 |
| 결과 | form_schema_id = undefined. 이후 POST /document-engine/documents body의 form_schema_id = undefined |
