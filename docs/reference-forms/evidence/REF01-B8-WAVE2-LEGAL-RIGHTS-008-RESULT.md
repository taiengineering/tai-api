---
wo: WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008
evidence_type: LEGAL_RIGHTS_EVIDENCE_008
status: EVIDENCE_COMPLETE_GPT_GATE_PENDING
date: 2026-10-10
base_head: 9864b9ac2039086747b68d0ff31507ac40806a27
---

# REF01-B8-WAVE2-LEGAL-RIGHTS-008-RESULT

WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008 증거 수집 결과.  
14종 B8 서식 법령 적용성·출처·재배포 권한 증거 추적.

---

## 1. 프리플라이트 검증

| 검증 항목 | 결과 |
|---------|------|
| 원격 HEAD | `9864b9ac2039086747b68d0ff31507ac40806a27` |
| 기준 HEAD 일치 | MATCH |
| PR #564 | OPEN / DRAFT / UNMERGED |
| 워킹 트리 | CLEAN |
| WO-007B-R1 | PASS (런타임 증거, COMMIT=NONE) |
| output 72파일 SHA baseline | 캡처 완료 (engine.py be4899da / engine.cjs 375250c7) |
| canonical JSON 14종 법령 관련 필드 | legal_review_status=PENDING / rights_status=RIGHTS_UNVERIFIED / publication_status=INTERNAL_POC_ONLY — 14/14 확인 |
| PRODUCTION_DB_WRITE | 0 |

---

## 2. 법령 RPC 조회 결과

### GOVERNANCE_SOURCE_OF_TRUTH.md

전체 저장소 검색 결과: **NOT FOUND** (node_modules 제외).

### governance DB 실제 접근 결과 (WO-008A 정정)

45cm-prj-db (`iapzwbysfzootqnldtan`) `governance` 스키마 RPC 호출 실시:  
`governance.get_active_items_for_scope('LEG', NULL)` — **호출 성공**  
반환값 = AI 거버넌스 규칙 16건 (AI-001~AI-016); **산업안전보건법 조문 데이터 없음**  
이 DB는 45CM 개발 거버넌스 전용 — 산업 법령 SoT 아님.

### LEG 런타임 경로

`clients/leg_runtime_client.py` 확인:  
접근 방식 = `POST {LEG_RUNTIME_URL}/evaluate` (HTTP REST).  
이 조사 컨텍스트에서 `LEG_RUNTIME_URL` 미설정 → 법령 조회 불가.

```
GOVERNANCE_RPC_ACCESSIBLE  = YES
GOVERNANCE_RPC_LAW_CONTENT = NONE
LEGAL_RPC_ROUTE            = LEGAL_RPC_CONTRACT_UNRESOLVED
```

### 연구 문서 내 법령 인용 (2차 증거만)

| 서식 | 연구 문서 인용 조문 | 분류 |
|------|-----------------|------|
| GOV-01 | 산업안전보건법 제24조 (report 15 S1) — 적용 사업장 조건부 회의록 의무 | ACTIVITY_DUTY_CONFIRMED_CONDITIONAL |
| C026-C029 | 산업안전보건법 제36조 (report 02 S4 snippet) — 위험성평가 의무, 방법별 법정 서식 여부 미확인 | REVIEW_REQUIRED |
| C031 | 법 제29조 교육 의무 + KOSHA 붙임5 유사명 (report 03) | REVIEW_REQUIRED |
| C033 | 법 제63조 도급 의무 + KOSHA 붙임2 유사명 (report 03) | REVIEW_REQUIRED |
| C039-C044 | 산업안전보건법·화학물질관리법 관련 조항 추정 (report 10) | REVIEW_REQUIRED |
| C037 | 근로자 참여 관련 조항 미특정 | REVIEW_REQUIRED |

**판정:**
```
LEGAL_RPC_EVIDENCED_COUNT = 0
REVIEW_REQUIRED_COUNT     = 13
CONDITIONAL_COUNT         = 1 (GOV-01)
```

---

## 3. 출처·원본 유사도 증거

### 원본 파일 검사 현황

```
SOURCE_FILE_INSPECTED = 0/14
SIMILARITY_VERIFIED   = 0/14
```

모든 14종: `source_document_access=NOT_CHECKED`, `source_match=NOT_VERIFIED`.

### 출처 유형별 주요 발견

**TAI_PROPOSED (7종: C026, C027, C028, C029, C031, C033, C037):**
- 독자 워크플로우 후보화 (report 09/13 기반)
- C029, C031, C033: KOSHA 24종 내 유사명 서식 존재 → **원본 HWP/ZIP 검사 전 유사도 판단 불가**
- C026, C027, C028, C037: KOSHA 24종 직접 대응 미발견 — 단, TAI 독자성도 증거 미확인

**MIXED (6종: C039~C044):**
- 화학물질관리법·산업안전보건법 관련 의무 참조 존재
- KOSHA MSDS 시스템(report 10 S2): **상업적 재사용 저작권 침해 가능 명시 경고**
- 원본 서식 파일: 미검사

**OFFICIAL_PROCESS_AND_TAI_HYPOTHESIS (1종: GOV-01):**
- 법 제24조 절차 기반; 법정 별지 없음
- TAI 열 구조 독자 제안 — 원본 복제 없음 추정, 증거 미확보

---

## 4. 재배포 권한 조사

### KOSHA 게시 안내 (report 03)

"게시된 참고서식은 사업장 상황에 맞게 수정 가능"  
→ **내부 사용 문구; 상업적 SaaS 배포·유료 다운로드 허가 아님**

### KOGL(공공누리) 유형 확인

해당 KOSHA 게시물 대상 KOGL 유형 미확인 — 유형 1(자유이용), 2(비영리), 3(변경금지), 4(비영리+변경금지) 중 어느 것인지 검사 불가.

### KOSHA MSDS 시스템 경고 (report 10 S2)

공식 페이지 직접 경고: 외부 상업적 이용 시 저작권 침해 가능 → C039-C044 관련 소재 상업적 재배포 **BLOCKED**.

### 판정 요약

```
RIGHTS_CLEAR_COUNT              = 0/14
RIGHTS_UNVERIFIED_COUNT         = 14/14
COMMERCIAL_REDISTRIBUTION       = UNVERIFIED for all 14
PUBLICATION_AUTHORIZED          = false (14/14)
COMMERCIAL_REDISTRIBUTION_AUTHORIZED = NO
```

---

## 5. 변경 파일

| 파일 | 내용 |
|------|------|
| `evidence/legal-rights-008/REF01_B8_14_LEGAL_RIGHTS_MATRIX.json` | 14행 추적 매트릭스 (신규) |
| `evidence/legal-rights-008/REF01_B8_14_SOURCE_LICENSE_TRACE.md` | 출처·라이선스 추적 (신규) |
| `evidence/legal-rights-008/REF01_B8_14_LEGAL_RPC_TRACE.md` | 법령 RPC 조회 추적 (신규) |
| `evidence/REF01-B8-WAVE2-LEGAL-RIGHTS-008-RESULT.md` | 본 증거 문서 (신규) |

정규 JSON 14종·PDF 14종·DOCX 14종·공통 엔진·DB 스키마·행 변경 없음.

---

## 6. 요약 카운트

| 항목 | 값 |
|------|---|
| 대상 서식 수 | 14/14 |
| 법령 의무 RPC 확인 | 0 (LEGAL_SOT_UNAVAILABLE) |
| 조건부 활동의무 (2차 증거) | 1 (GOV-01) |
| REVIEW_REQUIRED | 13 |
| 원본 파일 검사 완료 | 0/14 |
| 유사도 확인 | 0/14 |
| 권리 확인 | 0/14 |
| 상업적 재배포 승인 | 0/14 |
| 법률 전문가 검토 필요 | 14/14 |
| 제3자 유사성 위험 (주의) | 3 (C029, C031, C033 — KOSHA 유사명 서식 존재) |

---

## 7. 상태

```
WO                             = WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008
BASE_HEAD                      = 9864b9ac2039086747b68d0ff31507ac40806a27
NEW_HEAD                       = 84e8461af7e51139d1e165f484991434945f4d92 (WO-008 커밋)
REMOTE_HEAD                    = 6440d28700b01c9ce541dff459d159bac342a97f (WO-008A 이후 최신)
PR_564                         = OPEN / DRAFT / UNMERGED
FORMS                          = 14/14
LEGAL_RPC_ROUTE                = LEGAL_RPC_CONTRACT_UNRESOLVED
GOVERNANCE_RPC_ACCESSIBLE      = YES (산업안전 법령 데이터 없음)
LEGAL_RPC_RESULTS              = EVIDENCED=0 / REVIEW_REQUIRED=13 / CONDITIONAL=1
SOURCE_TRACE                   = EVIDENCED=0 / UNVERIFIED=14
RIGHTS_TRACE                   = SPECIFIC_PERMISSION=0 / UNVERIFIED=14
COMMERCIAL_REDISTRIBUTION_AUTHORIZED = NO
QA_ENGINE_OUTPUT_SHA           = be4899da / 375250c7 (UNCHANGED)
PRODUCTION_DB_WRITE            = 0
CHANGED_FILES                  = 4 (evidence files only, approved scope)
B8_CLOSED_FINAL                = NO
PR_MERGE                       = BLOCKED
DEPLOY                         = BLOCKED
PUBLICATION                    = INTERNAL_POC_ONLY
NEXT_GATE                      = GPT_INDEPENDENT_LEGAL_RIGHTS_EVIDENCE_REVIEW
```
