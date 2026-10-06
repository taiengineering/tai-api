# OBJ00_CURRENT_STATE_EVIDENCE

조사일: 2026-10-07
WO: WO-DOC-OBJ00-READONLY-DISCOVERY-001
실행자: Claude Code

---

## GIT

| 레포 | SHA |
|---|---|
| tai-api local main | `aa46bbb7ed07416784f3310681540c9fce7eef92` |
| tai-api origin/main | `939ef60ba3c43f2ac0ff6a0256a787ebf05bd1aa` (local과 diverged) |
| tai-admin main | `94f2491c468df73d2a50e50551a51a5a6de44224` |
| 45cminc/doc main | `218091f6adc0895294ac6c9da74f565e557084ea` |

모든 anchor = master plan 기대값과 일치.

---

## MUTATION

| 항목 | 건수 |
|---|---:|
| code write | 0 |
| DB write | 0 |
| production deploy | 0 |
| storage write | 0 |

---

## CATALOG

| 테이블 | 건수 |
|---|---:|
| document_forms | 260 |
| form_templates | 11 |
| document_form_master | 64 |

---

## RUNTIME

| 항목 | 건수 |
|---|---:|
| runtime_form_schema | 324 |
| APPROVED_FOR_RUNTIME_USE | 1 |
| CANDIDATE | 323 |
| runtime_field | 1,308 |
| runtime_checklist_item | 802 |
| runtime_evidence_field | 202 |

---

## GENERATION

| 항목 | 건수 |
|---|---:|
| document_type_registry | 8 |
| actual template files | 6 (DOC-OSH-056 / DOC-INSP / DOC-CHK / DOC-EQUIP / DOC-PPE / DOC-COMPLIANCE-REPORT) |
| missing template files | 3 (DOC-APPT / DOC-CONLOG / DOC-EDU) |
| actual fetchers | 2 (inspection_fetcher.py / tbm_fetcher.py) |
| generated_document | 1,544 |
| PENDING | 1,527 |
| GENERATED | 9 |
| FAILED | 4 |
| TEMPLATE_MISSING | 4 |

---

## DOCUMENT LIBRARY

| 항목 | 건수 |
|---|---:|
| documents | 4 (전부 견적서 PDF, 문서 모듈 산출물 없음) |
| storage bucket(s) | company-docs (현재 사용), form-outputs (default값, 실제 object 없음) |

---

## ROUTES

| 항목 | 값 |
|---|---|
| mounted document routes | 37개 (7개 라우터 파일에서) |
| NOT mounted document routers | 3개 (routers/documents.py, document_runtime.py, document_schema.py) |

### generation path 불일치 (사실)

| 경로 | PDF bytes | storage write | generated_document INSERT | 실제 완성 |
|---|---|---|---|---|
| POST /document-engine/documents/{id}/generate | NO | NO | YES (PENDING) | NO (stub) |
| POST /documents/{doc_type}/generate | YES | NO | NO | YES (if fetcher exists) |
| POST /document-forms/{doc_id}/generate (TBM) | YES | YES (documents) | NO | YES (TBM only) |

---

## FRONTEND

| 항목 | 값 |
|---|---|
| document-forms route | FOUND (vue3/src/pages/document-forms/index.vue) |
| engine-document route | FOUND (vue3/src/pages/engine-document/index.vue) |
| compliance-report route | FOUND (vue3/src/pages/compliance-report/index.vue) |
| backend contract mismatch evidence | FOUND (4건) |

### 주요 mismatch (사실)

1. `POST /document-engine/documents/{id}/generate` → 응답에 pdf_url 없음 (PENDING만 반환). frontend extractPdfUrl() = '' → silent fail.
2. `GET /document-forms?per_page=200` → backend는 `size` 파라미터 사용. per_page 무시.
3. `GET /engine/forms/{form_code}/download` → backend 엔드포인트 미구현 (404).
4. `GET /document-forms` 응답 → form_schema_id 필드 없음. frontend POST /document-engine/documents body에서 form_schema_id=undefined.

---

## ENG:DOC (45cminc/doc)

| 항목 | 값 |
|---|---|
| digitize | ACTUAL (OCR + Docling + PaddleOCR) |
| pdf renderer | PLACEHOLDER (literal string, no actual PDF library) |
| docx renderer | PLACEHOLDER (literal string) |
| markdown renderer | ACTUAL |
| Gotenberg reference | NOT FOUND |
| Railway config | NOT FOUND (Dockerfile만 존재) |
| last updated | 2026-06-24 |

---

## FILES CREATED

```
docs/document-engine/obj00/
  OBJ00_CURRENT_STATE_EVIDENCE.md        (이 파일)
  GIT_DEPLOYMENT_IDENTITY.md
  ROUTE_MATRIX.md
  SERVICE_FETCHER_MATRIX.md
  TABLE_MATRIX.md
  DB_COUNTS_SNAPSHOT.md
  TEMPLATE_MATRIX.md
  FRONTEND_CONTRACT_MATRIX.md
  GENERATED_DOCUMENT_PROVENANCE.md
  DOCUMENT_LIBRARY_STORAGE_EVIDENCE.md
  RENDERER_INFRA_EVIDENCE.md
  ENG_DOC_BOUNDARY_EVIDENCE.md
  ACTIVE_LEGACY_MATRIX.md
  DOCUMENT_FORMS_260_SNAPSHOT.csv        (261줄 / 43컬럼)
  RUNTIME_FORM_SCHEMA_324_SNAPSHOT.csv   (325줄 / 13컬럼)
  CATALOG_RUNTIME_EXACT_MATCH_EVIDENCE.csv
```

---

## UNRESOLVED FACTS

1. **Railway deployment commit**: NOT_ACCESSIBLE — Railway API UNAUTHORIZED. origin/main = 939ef60b.
2. **Gotenberg Railway service**: NOT_ACCESSIBLE — Railway API UNAUTHORIZED. fallback hostname `gotenberg.railway.internal:3000` 존재가 service 실행을 보장하지 않음.
3. **form-outputs bucket**: GPT 독립검증으로 **object=0 CONFIRMED** (CORR-C 반영).
4. **GENERATED 9건 파일 실존**: storage_path=NULL — GPT 독립검증에서도 9건 전부 NULL CONFIRMED. 실제 파일 존재 여부 UNVERIFIED.
5. **anonymous 1,521건 PENDING 삽입 경로**: UNRESOLVED — 현재 코드와 다른 경로 가능성. 추정 금지 (CORR-F).
6. **tai-api local vs origin 차이**: 1 commit diff. document-engine scope 변경 없음 (GPT 독립검증 CONFIRMED).
7. **documents.py /documents endpoints**: routers/documents.py가 LEGACY 분류되었으나 `document_svc.py`는 다른 mounted router에서 사용 중 — documents.py와 document_svc.py는 별개 파일임.

## CLOSEOUT CORRECTION STATUS (CORR-A~F)

| CORR | 내용 | 상태 |
|---|---|---|
| CORR-A | 16개 파일 Git 반영 | 이 commit에서 완료 |
| CORR-B | GIT_DEPLOYMENT_IDENTITY 정정 주석 추가 | DONE |
| CORR-C | Storage 실증 수치 반영 (GPT verified) | DONE |
| CORR-D | frontend mismatch 표현 교정 (/engine/forms) | DONE |
| CORR-E | Railway/Gotenberg NOT_ACCESSIBLE 상세 기록 | DONE |
| CORR-F | PENDING provenance 분리 명확화 | DONE |

---

## OBJ00 EXECUTION = COMPLETE

GPT INDEPENDENT VERIFICATION = REQUIRED

NO ARCHITECTURE DECISION MADE
NO SEMANTIC MAPPING MADE
NO PRODUCTION MUTATION
