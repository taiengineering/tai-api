# WO-TAI-DOC-LEG-VERSION-DRIFT-001 — 법령 버전 드리프트 영향 조사

**작성일**: 2026-10-21  
**작업 유형**: READ-ONLY / IMPACT CHECK  
**기준 커밋**: c9c7ccbc / 25d0293d (LEG-9 원본·R1)

---

## 1. SOURCE_VERSION_MATRIX

| 법령 | tai-api DB law_key | tai-api 시행일 | LEG SoT 시행일 | 드리프트 |
|------|-------------------|--------------|--------------|---------|
| 산업안전보건법 | `001766_276853` | 2025-10-01 | 2026-08-01 (`001766_283449`) | **DRIFT** |
| 산업안전보건법 시행령 | `003786_284771` | 2026-03-24 | 2026-08-01 | **DRIFT** |
| 산업안전보건법 시행규칙 | `007364_271485` | 2025-06-01 | 2025-06-01 | SAME (LEG 기준) |
| 산업안전보건기준에 관한 규칙 | `007363_273603` | 2025-09-01 | 2025-12-01 | **DRIFT** |

**비고**:
- 시행규칙은 tai-api=LEG SoT 동일(2025-06-01)이나, 국가법령정보센터에는 2026-08-01 시행본 존재. LEG 수집 파이프라인이 해당 버전을 미수집 상태로 추정 → LEG 파이프라인 별도 검토 대상.
- 안전보건기준에 관한 규칙은 2025-12-01 시행본에서 제619조의2④항 신설(측정결과 기록·3년 보존). tai-api DB에는 해당 조항 미반영.

---

## 2. CONFIRMED_DRIFT 상세

### 산업안전보건법 (2버전 드리프트)
- tai-api: 001766_276853 (2025-10-01, is_active=true)
- LEG SoT: 001766_283449 (2026-08-01)
- 본 조사에서 확인한 조문(제24·29·38·41·52·64조)은 구버전 기준. 현행 버전 직접 대조 미완료.

### 산업안전보건법 시행령 (1버전 드리프트)
- tai-api: 003786_284771 (2026-03-24, is_active=true)
- LEG SoT: 2026-08-01 시행본
- 이번 R1에서 직접 조회한 시행령 제34조·제37조는 구버전(2026-03-24) 기준.

### 산업안전보건기준에 관한 규칙 (1버전 드리프트)
- tai-api: 007363_273603 (2025-09-01, is_active=true)
- LEG SoT: 2025-12-01 시행본
- **핵심 차이**: 제619조의2④항 신설(2025-12-01) — 측정자 성명·일시·장소·결과 기록 및 3년 보존 의무. tai-api DB에는 ①②③항만 존재.

### 산업안전보건법 시행규칙 (LEG 기준 SAME)
- tai-api = LEG SoT = 2025-06-01
- 외부 국가법령정보센터에 2026-08-01 시행본 존재 → LEG 파이프라인 별도 검토 필요.

---

## 3. AFFECTED_DOCUMENTS — law_ref 오류

DB 조회 결과: `law_ref LIKE '%제41조%'` 전수 확인

| doc_id | doc_name | law_ref | 오류 여부 |
|--------|----------|---------|---------|
| DOC-OSH-045 | 보호구 지급대장 | 산안법 제41조 | ❌ **오류** (제41조 = 고객응대 건강장해) |
| DOC-OSH-046 | 보호구 착용 점검기록 | 산안법 제41조 | ❌ **오류** (동일 원인) |
| DOC-CHEM-004 | 장외영향평가서 | 화학물질관리법 제41조 | 화학물질관리법 조항. 별도 검증 필요. |

**DOC-OSH-046 추가 확인**: DOC-OSH-045와 동일한 오류. 보호구 착용 점검기록도 산안법 제41조를 참조하고 있으나, 현행 제41조는 고객의 폭언 등 건강장해 예방조치로 보호구와 무관.

**올바른 근거**: 안전보건기준에 관한 규칙 제32조(보호구의 지급 등) — 직접 조회 완료. 지급 및 착용 의무 규정. 단, 지급대장·점검기록 자체의 작성·보존 의무는 제32조에 명시 없음 (별도 규정 확인 필요).

---

## 4. LAW_REF_045_IMPACT — 오류의 실제 영향 범위

### 영향 있는 경로

| 경로 | 영향 내용 |
|------|---------|
| `GET /document-forms` (list) | `select("*")` — law_ref 포함. 사용자 문서 목록에 "산안법 제41조" 표시. |
| `GET /document-forms/{doc_id}` (detail) | 상세 응답에 `law_ref: "산안법 제41조"` 노출. |
| `GET /document-forms?search=제41조` | 검색 결과에 DOC-OSH-045, DOC-OSH-046 포함. 제41조로 검색한 사용자에게 PPE 문서 표시. |
| `services/document_link_review_read.py:140` | `columns=...law_ref,...` — 관리자 문서 링크 리뷰 화면에 law_ref 포함. WP03-B 리뷰 UI에 오류 값 표시. |

### 영향 없는 경로

| 경로 | 근거 |
|------|------|
| 진단 결과 (`routers/diagnosis_result_web.py`) | `law_ref`는 LEG 진단 결과의 `law_name`+`law_article`에서 조합. `document_forms.law_ref` 미사용. |
| 자동작성 엔진 workspace_readmodel | `_SELECT_COLUMNS = "id,doc_id,doc_name,sector,category,is_active,priority"` — law_ref 미포함. |
| 문서 자동작성 필드 생성 | FETCHER 로직은 law_ref 참조 없이 DB 조회 (inspection/TBM 데이터 직접 조회). |
| LEG 진단·의무 판정 | LEG 파이프라인은 tai-api의 document_forms.law_ref 독립. |

**결론**: 오류의 영향은 SaaS UI 표시 오류 + 관리자 리뷰 화면에 한정. 진단 결과·자동작성·LEG 의무판정에는 영향 없음.

---

## 5. EXISTING_SYNC_PIPELINE

### tai-api 법령 수집 파이프라인

`routers/law_collector.py` v3.0:
- 소스: data.go.kr API (Railway IP 제한 없음). 폴백: law.go.kr.
- 엔드포인트: `POST /law-collector/check-updates-v2` (크론 전용).
- 기능: 법령 개정 감지 → `law_master`·`law_article` 업데이트 → 개정 시 law_rule_drafts APPROVED → NEEDS_REVIEW 자동 표시.
- DB 쓰기: 있음 (운영 DB). 실행 시 Owner 승인 필요.

### LEG 업데이트 추적 파이프라인

`routers/admin_law_updates.py`:
- `LEG_SUPABASE_URL` + `LEG_SUPABASE_SERVICE_ROLE_KEY` 환경변수 사용 (LEG SoT 직접 접근).
- 기능: LEG의 `law_update_tracking` 테이블 읽기 전용 + Slack 알림.
- DB 쓰기: 0 (Slack 타임스탬프만).
- 목적: 법령 개정 케이스 관리자 확인용. 실제 tai-api DB 법령 버전 동기화와 별개.

### 버전 드리프트 해소 방법 (기존 절차)

| 방법 | 조건 |
|------|------|
| `POST /law-collector/check-updates-v2` 실행 | Owner 승인 + 크론 또는 수동 트리거. 운영 DB 쓰기 발생. |
| 특정 법령 수동 재수집 | `law_collector.py` 의 법령별 수집 엔드포인트 사용. Owner 승인 필요. |

**시행규칙 2026-08-01 외부 버전**: LEG 파이프라인이 2026-08-01 시행본 미수집 상태. LEG 파이프라인 owner가 수집 대상 버전 범위를 확인해야 함. tai-api 단독으로 처리 불가.

---

## 6. REQUIRED_CORRECTION_SCOPE

| 항목 | 유형 | 범위 | 승인 조건 |
|------|------|------|---------|
| DOC-OSH-045 `law_ref` 정정 | 운영 DB UPDATE | `document_forms` 1행 | Owner 승인 + 올바른 조항 확정 후 실행 |
| DOC-OSH-046 `law_ref` 정정 | 운영 DB UPDATE | `document_forms` 1행 | Owner 승인 + 올바른 조항 확정 후 실행 |
| 보호구 관련 법정 근거 확정 | READ-ONLY 조사 | 안전보건기준에 관한 규칙 별도 조항 | 지급대장 보존 의무 조항 특정 필요 |
| 법령 버전 동기화 (3개 법령) | 운영 DB 쓰기 | tai-api law_master · law_article | Owner 승인 + law_collector 실행 |
| 시행규칙 2026-08-01 수집 | LEG 파이프라인 | LEG SoT 별도 | LEG 파이프라인 Owner 승인 |

**NOT IN SCOPE** (이번 WO에서 처리 안 함):
- 9쌍 문서 관계 자동 등록
- 자동작성 엔진 수정
- 82쌍 재분석
- Migration·신규 기능 개발

---

## 7. 종료 보고

```
WO = WO-TAI-DOC-LEG-VERSION-DRIFT-001

SOURCE_VERSION_MATRIX:
  산업안전보건법:         tai-api 2025-10-01  | LEG SoT 2026-08-01  → DRIFT
  산업안전보건법 시행령:  tai-api 2026-03-24  | LEG SoT 2026-08-01  → DRIFT
  산업안전보건법 시행규칙: tai-api 2025-06-01 | LEG SoT 2025-06-01  → SAME (외부 2026-08-01 미수집)
  안전보건기준에 관한 규칙: tai-api 2025-09-01 | LEG SoT 2025-12-01 → DRIFT

CONFIRMED_DRIFT:
  3개 법령 드리프트 확정.
  안전보건기준 규칙: 619조의2④항 2025-12-01 신설 — tai-api DB 미반영.

AFFECTED_DOCUMENTS:
  DOC-OSH-045 보호구 지급대장:    law_ref=산안법 제41조 ❌ 오류
  DOC-OSH-046 보호구 착용 점검기록: law_ref=산안법 제41조 ❌ 오류
  (DOC-CHEM-004 화학물질관리법 제41조: 별도 검증 필요)

LAW_REF_045_IMPACT:
  영향 있음: SaaS UI (GET /document-forms list/detail), 검색, 관리자 리뷰 화면.
  영향 없음: LEG 진단결과, 자동작성 엔진, 의무판정.

EXISTING_SYNC_PIPELINE:
  tai-api: law_collector.py v3.0 (POST /law-collector/check-updates-v2, 크론).
  LEG → tai-api 직접 동기화 파이프라인: 없음.
           admin_law_updates는 읽기 전용 추적.
  법령 재수집: Owner 승인 후 law_collector 실행으로 가능.

REQUIRED_CORRECTION_SCOPE:
  [P1] DOC-OSH-045·046 law_ref 정정 → Owner 승인 + 올바른 조항 확정 후 실행.
  [P2] 3개 법령 버전 동기화 → Owner 승인 후 law_collector 실행.
  [P3] 시행규칙 2026-08-01 → LEG 파이프라인 Owner 별도 검토.

PRODUCTION_WRITE = 0
NEW_DEVELOPMENT = 0

RESULT = READY_FOR_GPT_IV
```

---

**조회 소스 식별자**:
- document_forms: vwlahtguyggrhvslabax DB 2026-10-21 (DOC-OSH-045, 046, law_ref 조회)
- law_master: vwlahtguyggrhvslabax DB 2026-10-21 (4개 법령 버전 확인)
- 코드 조회: tai-api 커밋 25d0293d (law_ref 노출 경로 분석)
- LEG SoT 버전 정보: GPT 독립검증 판정(WO-TAI-DOC-UNIFICATION-LEG-9-001-IV-CORRECTION) 기준
