# M004 본선 최종 완결 보고서

> WO: WO-TAI-M004-MAINLINE-FINAL-CLOSEOUT-001  
> 작성일: 2026-10-23  
> 작성자: Claude Code — GPT 독립검증 대기  
> 전제: 기존 완료 작업 인수 / 신규 수집·설계·엔진 제작 금지 / PROD_DB_WRITE=0 (별도 승인 전)

---

## 인수 기준선

기존 완료 작업을 재검증 없이 인수한다.

| 항목 | 상태 | 근거 |
|---|---|---|
| 공공데이터 API 수집 | **INHERITED** | law_master/law_article DB 보유 |
| 법령·원본서식 연결 | **INHERITED** | form_templates 11종 + document_forms 260종 |
| 서비스 모드 분류 | **INHERITED** | M004_SERVICE_MODE_MATRIX.csv 확정 |
| 런타임 구현 | **INHERITED** | runtime_form_schema 324종 / runtime_field 1,308개 |
| DOC-CON-044 E2E | **INHERITED** | LIVE E2E PASS (2026-10-22, test_doc=22ea1d3a, PDF 140KB) |

---

## C1. 고객 SaaS 서비스 경로 현황

### 웹작성 (WEB_WRITING)

```
고객 UI (vue3/src/pages/document-forms/)
  ↓
GET /document-engine/catalog/{catalog_document_id}
  → availability = "READY_FOR_EDIT" | "PREPARING" | "NO_SCHEMA"
  → can_create = (availability == "READY_FOR_EDIT")
  ↓ (can_create=True일 때만)
POST /document-engine/documents
  ↓
PATCH /document-engine/documents/{id}
  ↓
POST /document-engine/documents/{id}/generate
  ↓ Gotenberg
PDF 바이너리 반환
```

| 항목 | 상태 | 파일 |
|---|---|---|
| API 경로 | **IMPLEMENTED** | `routers/document_engine_api.py` |
| HTML 렌더링 | **IMPLEMENTED** | `services/document_engine_svc.py:render_document_html()` |
| PDF 생성 | **IMPLEMENTED** | Gotenberg `html_to_pdf()` |
| 고객 UI | **IMPLEMENTED** | `vue3/src/pages/document-forms/` |
| catalog_resolver | **IMPLEMENTED** | `services/document_engine/catalog_resolver.py` |
| can_create 게이트 | **IMPLEMENTED** | `APPROVED_FOR_RUNTIME_USE`일 때만 `can_create=True` |

**현재 can_create 상태:**

| 문서 | schema 상태 | can_create | 사유 |
|---|---|---|---|
| DOC-CON-044 | `APPROVED_FOR_RUNTIME_USE` | **True** | E2E PASS |
| WEB47 (나머지 47종) | `CANDIDATE` | **False** | 63DOC SQL 미실행 |
| INSP15 (15종) | `CANDIDATE` | **False** | 별도 AUTO_SOURCE 경로 |

---

### 자동작성 (AUTO_WRITING)

| 항목 | 상태 | 설명 |
|---|---|---|
| source_inspection_id 연결 | **IMPLEMENTED** | `document_engine_api.py:138-195` 멱등성 구현 |
| InspectionFetcher 경로 | **PARTIAL** | fetcher 구현됨, 15종 NOT_VERIFIED |
| TBM 자동생성 | **IMPLEMENTED** | `POST /document-forms/DOC-OSH-056/generate` + TbmFetcher |
| auto-fill (자동 필드 주입) | **NOT_IMPLEMENTED** | 설계 금지 — "auto fill, auto approve, inferred default 절대 금지" |

INSP15의 서비스 의도: `OVERALL_STATUS=AUTO_SOURCE_ONLY` (WEB_EDIT 아닌 자동생성 경로).  
63DOC SQL에 INSP15 포함 시 WEB can_create도 True가 되나 자동생성 경로의 별도 연결은 미검증.

---

### 원본서식 다운로드 (ORIGINAL_DOWNLOAD)

| 항목 | 상태 | 설명 |
|---|---|---|
| 법정서식 file_url 목록 제공 | **IMPLEMENTED** | `GET /document-forms` → `file_url` 반환 |
| 다운로드 클라이언트 연결 | **IMPLEMENTED** | `window.open(file_url, '_blank')` |
| URL 존재 건수 | 68/260 | `DOWNLOAD_FORM_STATUS=URL_EXISTS_DOWNLOAD_NOT_IMPLEMENTED` |
| URL 미존재 | 173/260 | `NOT_IN_SCOPE` |
| 공식원본 전용 | 19/260 | `BLOCKED_ORIGINAL_ONLY` |

`URL_EXISTS_DOWNLOAD_NOT_IMPLEMENTED` 68건: file_url은 DB에 존재하나 실제 파일 다운로드 구현 상태 미확인.  
63종 대상 중 해당 건수 별도 확인 필요.

---

### 문서함 (DOCUMENT_LIBRARY)

| 항목 | 상태 | 파일 |
|---|---|---|
| 생성 → documents 저장 | **IMPLEMENTED** | `document_svc.register_generated()` |
| Signed URL 발급 | **IMPLEMENTED** | `GET /documents/{id}/download` |
| 문서 목록 조회 | **IMPLEMENTED** | `GET /documents` |
| E4 E2E (생성→저장→재다운로드) | **UNVERIFIED** | 기존 증거 없음 |

---

## C2. OBJ12 E2E 경로별 현황

| E2E | 내용 | 상태 | 근거 |
|---|---|---|---|
| E1 | 회원 → 문서검색 → 빈양식 다운로드 | **UNVERIFIED** | 기존 증거 없음 |
| E2 | 회원 → 사업장 → 자동작성 → PDF | **PASS** | DOC-CON-044 E2E 인수 |
| E3 | SaaS 점검데이터 → 점검일지 생성 | **PASS** | DOC-CON-044 E2E 인수 |
| E4 | TBM → PDF → 문서함 → 재다운로드 | **UNVERIFIED** | 기존 증거 없음 |
| E5 | 공식 별지 → 원본 다운로드 | **UNVERIFIED** | 기존 증거 없음 |
| E6 | GPT 보조필드 → Human confirm → 생성 | **NOT_IN_SCOPE** | GPT 보조작성 미구현 |
| E7 | 다른 회사 문서 접근 차단 | **PASS** | WO-TAI-SEC02/SEC03/SEC04 완료 |
| E8 | 템플릿 누락 fail-close | **PASS** | catalog_resolver NO_SCHEMA 처리 확인 |
| E9 | renderer 장애 시 FAILED 기록 | **PARTIAL** | error handling 구현됨, E2E 미확인 |
| E10 | 동일 요청 retry idempotency | **PASS** | source_inspection_id 멱등성 구현 확인 |
| E11 | frozen snapshot 동일 hash | **NOT_IN_SCOPE** | archive 경로 구현됨, 현 단계 외 |
| E12 | Search → Document → SaaS CTA | **NOT_IN_SCOPE** | OBJ11 별도 WO |

---

## C3. 출시 범위 확정

### 현재 출시 가능

| 문서 | 서비스 경로 | 근거 |
|---|---|---|
| **DOC-CON-044** | 웹작성 + PDF | E2E PASS + APPROVED_FOR_RUNTIME_USE |

### 63DOC SQL 실행 후 출시 가능 (Owner 승인 전제)

| 그룹 | 건수 | 서비스 경로 | 선결 조건 |
|---|---|---|---|
| WEB47 | 47 | 웹작성 + PDF | 63DOC SQL Owner 승인 |
| INSP15 | 15 | AUTO_SOURCE 별도 경로 | D2 결정 (WEB 포함 여부) |

### 활성화 방식 확인

63DOC SQL은 WEB47 schema 상태를 `CANDIDATE` → `APPROVED_FOR_RUNTIME_USE`로 변경한다.  
실행 즉시:
- catalog_resolver: `PREPARING` → `READY_FOR_EDIT`
- `can_create=True`
- 모든 고객 사업장에서 API 수준 문서 생성 가능

**기술적 격리 없음. SQL 실행 = 즉시 전체 고객 노출.**

---

## 완료 보고

```
WO = WO-TAI-M004-MAINLINE-FINAL-CLOSEOUT-001

ORIGINAL_SOURCE_WORK = INHERITED
FORM_MERGE_WORK = INHERITED
SERVICE_CLASSIFICATION = INHERITED (M004_SERVICE_MODE_MATRIX.csv)

WEB_WRITING =
  ROUTE_IMPLEMENTED = YES
  UI_CONNECTED = YES (vue3/src/pages/document-forms/)
  CURRENT_ACTIVE = 1 (DOC-CON-044)
  BLOCKED = 47 (WEB47 — schema CANDIDATE)

AUTO_WRITING =
  SOURCE_INSPECTION_LINK = PARTIAL (멱등성 구현, 15종 NOT_VERIFIED)
  TBM_AUTO = IMPLEMENTED (DOC-OSH-056 + TbmFetcher)
  AUTO_FILL = NOT_IMPLEMENTED (설계 금지 항목)

ORIGINAL_DOWNLOAD =
  FILE_URL_LIST = IMPLEMENTED (form_templates 기반)
  URL_EXISTS = 68/260
  E5_E2E = UNVERIFIED

DOCUMENT_LIBRARY =
  STORAGE_ROUTE = IMPLEMENTED (register_generated + signed URL)
  E4_E2E = UNVERIFIED

CUSTOMER_SAAS_ROUTE = CONNECTED (DOC-CON-044 E2E 기준)
SECURITY_SCOPE = PASS (WO-TAI-SEC 시리즈 완료)
DEPLOYMENT_STATUS = feat/m004-auto-web-mainline-integration PR#683

RELEASE_READY_DOCS = 1 (DOC-CON-044)
RELEASE_PENDING_OWNER_APPROVAL = 47 (WEB47 — 63DOC SQL 미실행)
RELEASE_SEPARATE_TRACK = 15 (INSP15 — AUTO_SOURCE_ONLY)
ACTUAL_DEFECTS = 미확인 (E1/E4/E5 UNVERIFIED)

REMAINING_WORK:
  R1 = 63DOC SQL Owner 최종 승인 (WEB47 48종 동시 활성화)
  R2 = E1 (빈양식 다운로드) E2E 확인
  R3 = E4 (문서함 저장·재다운로드) E2E 확인
  R4 = E5 (공식별지 원본 다운로드 68건) E2E 확인
  R5 = INSP15 D2 결정 (WEB 포함 vs AUTO_SOURCE 별도 유지)

NEW_SOURCE_COLLECTION = 0
NEW_LEGAL_DESIGN = 0
NEW_ENGINE_DESIGN = 0

PROD_DB_WRITE = 0 (별도 승인 전)
GPT_IV = PENDING
```

---

## Owner 결정 사항

| # | 결정 | 영향 |
|---|---|---|
| **R1** | 63DOC SQL 실행 승인 | WEB47 즉시 전체 고객 노출. 실행 전 E1/E4/E5 E2E 확인 권고. |
| **R5** | INSP15 WEB 포함 여부 | YES=15종 추가 노출(AUTO_SOURCE별도경로 병행) / NO=현행 AUTO_SOURCE_ONLY 유지 |

E1/E4/E5 UNVERIFIED 항목은 실제 결함이 존재하면 수정 후 R1 실행 권고.  
결함이 없으면 R1 바로 진행 가능.
