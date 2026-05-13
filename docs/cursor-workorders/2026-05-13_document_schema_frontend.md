# [Cursor 작업지시서] 문서엔진 프론트엔드 통합

* 날짜: 2026-05-13
* 대상 레포: tai-api (main.py만) + tai-admin (프론트엔드)
* 서버: admin.taieng.co.kr / safe.taieng.co.kr

---

## TASK 0: main.py 라우터 등록 (tai-api)

### 파일: `tai-api/main.py`

기존 `document_engine_api_router` 등록 블록(v5.41.0 문서엔진 API) 바로 아래에 추가:

```python
from routers.document_schema import router as document_schema_router
from routers.document_runtime import router as document_runtime_router

app.include_router(document_schema_router, prefix="/api/v1")
app.include_router(document_runtime_router, prefix="/api/v1")
```

등록 후 최종 API 경로:

**Document Schema (구조 조회):**
- `GET /api/v1/document-schema/list`
- `GET /api/v1/document-schema/{document_type}`
- `GET /api/v1/document-schema/render-structure/{document_type}`
- `GET /api/v1/document-schema/field-mapping/{document_type}`
- `GET /api/v1/document-schema/integrity/{document_type}`

**Document Runtime (동적 바인딩):**
- `GET /api/v1/document-runtime/{document_type}?facility_id=`
- `POST /api/v1/document-runtime/render`
- `GET /api/v1/document-runtime/completeness/{document_type}`
- `GET /api/v1/document-runtime/evidence-binding/{document_type}`
- `GET /api/v1/document-runtime/integrity/{document_type}`

---

## TASK 1: Admin 문서스키마 콘솔 (tai-admin)

### 가장 중요한 원칙

이 화면은 ❌ 문서 편집기가 아니다.
"문서 내부 구조와 completeness rule을 시각적으로 검증"하는 governance console이다.

### 신규 페이지

경로: `/html/admin/document-schema.html`
메뉴: Admin → 문서엔진 → 문서스키마

### API 연동

```javascript
const API = 'https://api.taieng.co.kr/api/v1';

// 문서 유형 목록
const list = await fetch(`${API}/document-schema/list`).then(r => r.json());

// 특정 문서 스키마 상세
const schema = await fetch(`${API}/document-schema/OSHACT_FORM_001`).then(r => r.json());

// 무결성 점검
const integrity = await fetch(`${API}/document-schema/integrity/OSHACT_FORM_001`).then(r => r.json());
```

### A. 상단 Summary Card

API: `GET /document-schema/list`

| 카드 | 값 |
|---|---|
| 문서 유형 수 | `total_document_types` (97개) |
| 총 섹션 | 428개 |
| 총 필드 | 3,873개 |
| MANDATORY 필드 | mandatory_fields 합계 |
| RECOMMENDED 필드 | recommended_fields 합계 |

Vuexy card component 사용. 아이콘: ri-file-list-3-line, ri-checkbox-circle-line 등.

### B. 좌측 패널 — Document Type Explorer

`list.document_types` 배열을 목록으로 표시.
검색 input 상단 배치. 클릭 시 우측에 schema detail 로드.

각 항목 표시:
```
OSHACT_FORM_001
  필드 21 | 섹션 5 | MANDATORY 3
```

### C. 우측 — Section Structure Visualization

API: `GET /document-schema/{document_type}`

응답의 `sections` 배열을 tree view로 표시:

```
통합 산업재해 현황 조사표
├── 기본정보 (BASIC_INFO)
│   ├── 사업장명 [MANDATORY] [text-input]
│   ├── 사업자등록번호 [RECOMMENDED] [text-input]
│   └── 소재지 [RECOMMENDED] [text-input]
├── 재해현황 (ACCIDENT_STATS)
│   ├── 사고사망자 수 [OPTIONAL] [number-input]
│   └── 질병사망자 수 [OPTIONAL] [number-input]
├── 서명 (SIGNATURE)
│   └── (서명 또는 인) [MANDATORY] [signature-pad]
└── 제출 (SUBMISSION)
    └── 고용노동부 귀하 [OPTIONAL] [text-input]
```

collapsible section 사용. 각 필드 옆에:
- MANDATORY: 빨강 badge
- RECOMMENDED: 노랑 badge
- OPTIONAL: 회색 badge

### D. Field Detail Grid

section 클릭 시 하단에 DataTable 표시:

| 컬럼 | 소스 |
|---|---|
| field_code | `fields[].field_code` |
| field_label | `fields[].field_label` |
| field_type | `fields[].field_type` |
| required_level | badge 색상 표시 |
| source_mapping | `fields[].source_mapping` 또는 "미연결" |
| validation_rule | JSON 요약 |
| render_component | `fields[].render_component` |
| status | CANDIDATE / CONFIRMED |

### E. Schema Integrity Panel

API: `GET /document-schema/integrity/{document_type}`

integrity_status = "CLEAN" → 초록 배너
integrity_status = "HAS_ISSUES" → 빨강 배너 + issues 테이블

issues 테이블 컬럼:
- field_code
- issue (missing_render_component / mandatory_without_validation / unconfirmed_candidate)

### 금지 사항

- drag/drop 문서 빌더 금지
- no-code editor 느낌 금지
- AI 문서 생성 느낌 금지
- 이 화면은 "schema inspector" + "governance console"이어야 함

---

## TASK 2: Runtime Document HTML Viewer (tai-admin)

### 가장 중요한 원칙

이 화면은 ❌ PDF 미리보기가 아니다.
"현재 runtime 상태를 실시간으로 보여주는 문서 projection"이다.

### 신규 페이지

경로: `/html/runtime/document-viewer.html`

### API 연동

```javascript
const API = 'https://api.taieng.co.kr/api/v1';

// runtime document (facility_id 필요)
const doc = await fetch(`${API}/document-runtime/OSHACT_FORM_001?facility_id=${facilityId}`)
  .then(r => r.json());

// completeness만
const comp = await fetch(`${API}/document-runtime/completeness/OSHACT_FORM_001?facility_id=${facilityId}`)
  .then(r => r.json());

// evidence binding
const ev = await fetch(`${API}/document-runtime/evidence-binding/OSHACT_FORM_001?facility_id=${facilityId}`)
  .then(r => r.json());
```

### A. 상단 Completeness Summary

API 응답의 `completeness` 객체:

```
creatable: true/false → 상단 CRITICAL alert (false일 때)
mandatory: 80% (4/5 pass)  → 프로그레스 바
recommended: 60% (3/5 pass) → 프로그레스 바
total_fields: 21
```

creatable=false → 빨강 배너: "필수 항목 미완료 — 문서 생성 불가"
creatable=true → 초록 배너: "문서 생성 가능"

### B. Document Runtime View

sections → fields 구조로 렌더:

각 section은 collapsible card:
```
[기본정보]
  사업장명: 홍길동산업 ✅
  사업자등록번호: 123-45-67890 ✅
  근로자 수: (미입력) ⚠️ RECOMMENDED
  
[재해현황]
  사고사망자 수: (미입력) ℹ️
  질병사망자 수: (미입력) ℹ️

[서명]
  (서명 또는 인): (미서명) ❌ MANDATORY
```

### completeness 표시 규칙

| completeness.status | 아이콘 | 색상 |
|---|---|---|
| PASS | ✅ | 초록 |
| WARNING | ⚠️ | 노랑 |
| FAIL | ❌ | 빨강 |
| UNSUPPORTED | ❔ | 회색 |

FAIL 필드는 field label + value 영역 빨강 border.

### C. Dynamic Section Rendering

`fields[].visible = false` → 해당 필드 숨김 (DOM에서 제거하지 말고 `display: none`)
조건 미충족 section은 접힌 상태 + 회색 처리:

```
[전기안전관리자 정보] (조건 미충족: 전기용량 300kVA 미만)
```

### D. Evidence Binding Viewer

field_type이 "image" 또는 "evidence_ref"인 필드:
- evidence_bound = true → 사진 thumbnail 표시 + 개수 badge
- evidence_bound = false → "증빙 미첨부" 표시

### E. Runtime Explainability Panel

각 필드 옆에 ℹ️ 아이콘. 클릭 시 tooltip 또는 side panel:

```
필드: 사업장명
소스: facility.facility_name
추출 근거: HWP 원문 추출: ① 사업장명
상태: CANDIDATE (미확정)
```

source_mapping, source_trace, source_reason 표시.

### F. Export Button (선택)

우상단 "PDF 내보내기" 버튼.
현재 runtime payload를 서버로 전송 → Gotenberg PDF 생성.

PDF는 truth가 아니라 "현재 runtime snapshot의 artifact".

### 금지 사항

- static template 느낌 금지
- PDF mimic 중심 설계 금지
- hardcoded layout 금지
- 이 화면은 "structured document runtime projection"이어야 함

---

## UI 공통 규칙

- Bootstrap 5 + Vuexy 테마 사용
- 네이비 컬러 스킴 (`tai-brand.css`, `#1565c0`)
- 반응형: 모바일 최우선
- API base URL: `https://api.taieng.co.kr/api/v1`
- 에러 처리: fetch 실패 시 toast 알림
- 로딩: skeleton loader 사용

---

## 데이터 현황 (참고)

- document_schema_registry: 3,873 필드 (97개 문서 유형)
- document_schema_section: 428 섹션
- 전부 status = 'CANDIDATE' (Human Review 전)
- source_mapping: 대부분 NULL (PHASE C 데이터 미적재)
- conditional_rule: 전부 NULL (PHASE D 데이터 미적재)

---

## 작업 완료 후 보고

```json
{
  "main_py_router_registered": true,
  "document_schema_console_created": true,
  "runtime_document_viewer_created": true,
  "illegal_ai_decision_count": 0
}
```
