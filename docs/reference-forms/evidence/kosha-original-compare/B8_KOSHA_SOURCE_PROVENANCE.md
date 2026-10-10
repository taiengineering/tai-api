---
wo: WO-REF01-060-B8-KOSHA-ORIGINAL-COMPARE-009
doc_type: KOSHA_SOURCE_PROVENANCE
date: 2026-10-10
base_head: 14f02992dd8e951643275c68fa09d17dd0eebc59
---

# B8 C029/C031/C033 — KOSHA 원본 출처 접근 기록

## 1. 조사 대상

| 서식 | TAI 제목 | KOSHA 대응 명칭 (page enumerated) | KOSHA 첨부 |
|------|---------|--------------------------------|-----------|
| C029 | 빈도·강도법 위험성평가표 | 위험성평가표(빈도강도법) (KOSHA #06) | 붙임2 HWP |
| C031 | 안전보건교육 실시일지 | 안전보건교육일지 서식(엑셀, 한글) (KOSHA #24) | 붙임5 ZIP |
| C033 | 도급업체 안전관리 이행점검표 | 도급·용역·위탁 업체 안전보건 수준 평가 (KOSHA #11) | 붙임2 HWP |

KOSHA 명칭 출처: OBJ-REF-01-KOSHA-24-FORMS-SOURCE-03.md (PAGE_ENUMERATED only — 필드 미검사).

---

## 2. 접근 시도 기록

### 2.1 대상 URL

```
https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view
```

게시일: 2025-02-07 (OBJ-REF-01-KOSHA-24-FORMS-SOURCE-03.md 기준).

### 2.2 시도 1 — 직접 WebFetch

| 항목 | 결과 |
|------|------|
| HTTP 상태 | 200 OK |
| 응답 본문 크기 | ~1,993 bytes |
| 응답 유형 | Vue.js SPA HTML shell |
| 실제 콘텐츠 로드 여부 | NO — JavaScript 실행 필요 |

Vue.js SPA: 모든 라우트가 동일한 HTML 쉘 반환. 실제 게시판 콘텐츠는 JS API 호출로 로드됨.

### 2.3 시도 2 — stdtboard API 구조 탐색

stdtboard 설정 파일: `/stdtboard/js/kosha-tboard-config.js`

```javascript
systemCd: "50"
chnlId:   "kosha24"
root:     "/api/compn24/auth"
process:  "/stdtboard/process.do"  → full: /api/compn24/auth/stdtboard/process.do
api:      "/stdtboard/api.do"      → full: /api/compn24/auth/stdtboard/api.do
filedown: "/stdtboard/fileDownload.do" → full: /api/compn24/auth/stdtboard/fileDownload.do
```

### 2.4 시도 3 — api.do POST 직접 호출

```
POST https://www.kosha.or.kr/api/compn24/auth/stdtboard/api.do
```

결과:
```json
{"code": "-101", "msg": "permission error"}
```

원인: Bearer JWT 토큰 필요. 브라우저 `sessionStorage`에서 `jwt-access-token` 또는 `ERP24_ACCESS_TOKEN_SESSION_STORAGE_KEY` 키로 조회.

### 2.5 시도 4 — process.do 직접 호출

```
POST https://www.kosha.or.kr/api/compn24/auth/stdtboard/process.do
```

결과: **WAF에 의한 connection reset**.

### 2.6 파일 다운로드 URL 구조 분석

tboard_common.js (555KB KOSHA 공통 JS 라이브러리) 분석 결과:

```
파일 다운로드 URL 패턴: ${root}${filedown}?data=<encrypted>&key=<encrypted>
```

- `data` 및 `key` 파라미터: 게시판 상세 조회 API 응답에서 반환되는 암호화된 첨부파일 토큰
- 게시판 상세 조회(`boardDetail` serviceId)도 JWT 인증 필요
- JWT 없이 토큰 값 획득 불가 → 파일 다운로드 URL 구성 불가

### 2.7 시도 5 — Web Archive (archive.org / Wayback Machine)

| 시도 | 결과 |
|------|------|
| web.archive.org | HTTP 429 Too Many Requests |
| wayback.archive.org | HTTP 429 Too Many Requests |

---

## 3. 접근 결론

```
KOSHA_PAGE_ACCESSIBLE              = YES (HTML 반환)
KOSHA_PAGE_CONTENT_READABLE        = NO (Vue.js SPA, JS 실행 필요)
KOSHA_API_ACCESSIBLE_WITHOUT_JWT   = NO (-101 permission error)
KOSHA_WAF_BYPASS_POSSIBLE          = NO (WAF connection reset)
KOSHA_FILE_DOWNLOAD_URL_DERIVABLE  = NO (암호화 토큰 — 상세 API 결과 필요)
WAYBACK_MACHINE_ACCESSIBLE         = NO (HTTP 429)

ATTACHMENT_2_STATUS = SOURCE_UNAVAILABLE_JWT_REQUIRED
ATTACHMENT_5_STATUS = SOURCE_UNAVAILABLE_JWT_REQUIRED

KOSHA_ACCESS_METHOD_EXHAUSTED      = YES
```

---

## 4. 접근 방법 소진 판정

JWT 토큰은 브라우저 로그인 세션에서만 획득 가능하며, 이 조사 컨텍스트에서는 브라우저 세션이 없음.

접근 재시도 가능 경로: 없음 (이 조사 컨텍스트 내에서).

---

## 5. 원본 비교 게이트 상태

WO-009 §12 지침: "원본을 확보하지 못하면 해당 서식의 원본 비교 게이트는 HOLD 또는 UNVERIFIED이며, 조사 실행만 완료된 것으로 기록한다."

| 서식 | 원본 비교 게이트 | 이유 |
|------|---------------|------|
| C029 | HOLD — SOURCE_UNAVAILABLE | 붙임2 HWP 미확보 (JWT 필요) |
| C031 | HOLD — SOURCE_UNAVAILABLE | 붙임5 ZIP 미확보 (JWT 필요) |
| C033 | HOLD — SOURCE_UNAVAILABLE | 붙임2 HWP 미확보 (JWT 필요) |

---

## 6. TAI 저작 이력 (git 기반 — 확보된 증거)

| 서식 | 최초 커밋 | WO | authoring_class |
|------|---------|-----|----------------|
| C029 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | TAI_ORIGINAL_DRAFT |
| C031 | 3c8f9bf6 (초기), e85c4187 (대체) | WO-BATCH-001, WO-VISUAL-REPAIR-005-PHASE2-CANONICAL-006 | TAI_ORIGINAL_DRAFT |
| C033 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | TAI_ORIGINAL_DRAFT |

모든 서식: `field_origin = TAI_PRACTICAL_PROPOSAL`, `source_document_access = NOT_CHECKED`.

TAI 저작 이력은 git 기반 사실이며, KOSHA 원본과의 유사도·독립성을 증명하지 않음.

---

```
SOURCE_PROVENANCE_STATUS   = EVIDENCE_COLLECTED
ATTACHMENT_2_STATUS        = SOURCE_UNAVAILABLE_JWT_REQUIRED
ATTACHMENT_5_STATUS        = SOURCE_UNAVAILABLE_JWT_REQUIRED
TAI_GIT_HISTORY            = CONFIRMED (3c8f9bf6)
FIELD_COMPARISON_STATUS    = IMPOSSIBLE_NO_SOURCE_ACCESS
ORIGINAL_COMPARE_GATE      = HOLD (3/3 서식)
```
