# M004 본선 최종 완결 보고서

> WO: WO-TAI-M004-MAINLINE-FINAL-CLOSEOUT-001  
> 작성일: 2026-10-23  
> 교정일: 2026-10-23 (CORR-001 — WEB47→WEB48, 68→86, E2/E3 증거 범위 교정)  
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
| DOC-CON-044 | `APPROVED_FOR_RUNTIME_USE` | **True** | E2E PASS (63DOC SQL 제외 — 별도 완료) |
| WEB48 (63DOC SQL 대상) | `CANDIDATE` | **False** | 63DOC SQL 미실행 |
| INSP15 (15종) | `CANDIDATE` | **False** | 별도 AUTO_SOURCE 경로 |

> **교정 (CORR-001):** 초판 "WEB47"은 오기. DOC-CON-044는 63DOC SQL에 포함되지 않으므로 SQL 대상 WEB 분류는 48종 전부 미활성화.

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
| file_url 보유 건수 | **86/260** | API 실측 (law.go.kr/LSW/flDownload.do) |
| URL 미보유 | 174/260 | — |

> **교정 (CORR-001):** 초판 68건은 `M004_SERVICE_MODE_MATRIX.csv` 기준. 운영 DB API 실측 결과 86건.  
> `WO-TAI-M004-PRODUCTION-FINAL-E2E-001`에서 대표 URL HTTP 200 + HWP 바이너리 반환 확인 (E5 PASS).

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
| E1 | 회원 → 문서검색 → 빈양식 다운로드 | **DEFECT** | API file_url 86건 존재 + 실제 HWP 응답 확인. UI 미연결 (vue3 file_url 미사용) |
| E2 | 회원 → 사업장 → 자동작성 → PDF | **UNVERIFIED** | DOC-CON-044는 수동 웹작성 E2E. 자동작성 별도 증거 없음 (CORR-001) |
| E3 | SaaS 점검데이터 → 점검일지 생성 | **UNVERIFIED** | DOC-CON-044는 수동 웹작성 E2E. 점검데이터 연동 별도 증거 없음 (CORR-001) |
| E4 | TBM → PDF → 문서함 → 재다운로드 | **PARTIAL** | TBM 생성·문서함·signed URL 경로 구현 확인. 실제 demo E2E 미수행 |
| E5 | 공식 별지 → 원본 다운로드 | **PASS** | HTTP 200 + Content-Type=application/hwp + OLE2 bytes 확인 |
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
RELEASE_PENDING_OWNER_APPROVAL = 48 (WEB48 — 63DOC SQL 미실행)  ← CORR-001 교정
RELEASE_SEPARATE_TRACK = 15 (INSP15 — AUTO_SOURCE_ONLY)
ORIGINAL_DOWNLOAD_URL_COUNT = 86 (law.go.kr, E5 PASS)  ← CORR-001 교정

ACTUAL_DEFECTS:
  DEF-001 = E1 — file_url UI 미연결 (vue3 document-forms에서 file_url 미사용)
  DEF-002 = E2/E3 — 자동작성·점검데이터 기반 생성 경로 미검증 (수동 웹작성과 다른 경로)

REMAINING_WORK:
  R1 = 63DOC SQL Owner 최종 승인 (WEB48 동시 활성화)
  R2 = DEF-001 교정: vue3 UI에 file_url 다운로드 링크 연결
  R3 = E4 (문서함 저장·재다운로드) 실제 demo E2E 수행
  R4 = E2/E3 자동작성 경로 별도 검증 또는 NOT_IN_SCOPE 확정
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
| **R1** | 63DOC SQL 실행 승인 (WEB48) | 실행 즉시 전체 고객 노출. DEF-001 교정 후 실행 권고. |
| **R2** | DEF-001 교정 승인 | file_url 86건 UI 연결. 소규모 vue3 변경. |
| **R5** | INSP15 WEB 포함 여부 | YES=15종 추가 WEB 노출 / NO=현행 AUTO_SOURCE_ONLY 유지 (GPT 권고=NO) |

**DEF-001 교정 우선:** vue3 document-forms UI에 file_url이 있는 문서 대상 "원본 다운로드" 버튼/링크를 추가.  
법제처 URL로 직접 연결 (이미 HTTP 200 + HWP 반환 확인). 소규모 UI 변경으로 E1 차단 해소 가능.
