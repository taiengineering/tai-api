---
wo: WO-REF01-060-B8-KOSHA-ORIGINAL-COMPARE-009
evidence_type: KOSHA_ORIGINAL_COMPARE_009
status: EVIDENCE_COMPLETE_GPT_GATE_PENDING
date: 2026-10-10
base_head: 14f02992dd8e951643275c68fa09d17dd0eebc59
---

# REF01-B8-KOSHA-ORIGINAL-COMPARE-009-RESULT

WO-REF01-060-B8-KOSHA-ORIGINAL-COMPARE-009 증거 수집 결과.  
C029, C031, C033 vs KOSHA 공식 원본 비교 조사.

---

## 1. 프리플라이트

| 검증 항목 | 결과 |
|---------|------|
| BASE HEAD | `14f02992dd8e951643275c68fa09d17dd0eebc59` |
| 기준 HEAD 일치 | MATCH (git rev-parse HEAD 확인) |
| C029 JSON SHA | 78d98e840728fad23b8b01473151fc31f1136f5f (확인) |
| C031 JSON SHA | ea9c00d54af988e8f8616b81ab6101e1b3aabb12 (확인) |
| C033 JSON SHA | cb95eb99a73658577f61b1e4094b9884cdba3de9 (확인) |
| PRODUCTION_DB_WRITE | 0 |
| CANONICAL_JSON 변경 | 없음 |

---

## 2. KOSHA 원본 접근 시도 결과

### 접근 대상

```
https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view
```

### 접근 방법 소진

| 방법 | 결과 |
|------|------|
| WebFetch 직접 요청 | 200 OK — Vue.js SPA shell만 반환 (1,993 bytes) |
| stdtboard api.do POST | `{"code": "-101", "msg": "permission error"}` — JWT 필요 |
| process.do POST | WAF connection reset |
| Wayback Machine / archive.org | HTTP 429 Too Many Requests |
| 파일 다운로드 URL 직접 구성 | IMPOSSIBLE — 암호화 토큰 미확보 |

```
KOSHA_ACCESS_METHOD_EXHAUSTED  = YES
ATTACHMENT_2_STATUS            = SOURCE_UNAVAILABLE_JWT_REQUIRED
ATTACHMENT_5_STATUS            = SOURCE_UNAVAILABLE_JWT_REQUIRED
```

---

## 3. TAI 서식 구조 (JSON 확인)

| 서식 | 제목 | 주요 섹션 | 반복 테이블 컬럼 수 |
|------|------|---------|----------------|
| C029 | 빈도·강도법 위험성평가표 | S01 기본정보(4필드) + S02 평가표 + S03 안내 | 7열 |
| C031 | 안전보건교육 실시일지 | S01 기본정보(7필드) + S02 요약란 + S03 참석자표 + S04 안내 | 5열 |
| C033 | 도급업체 안전관리 이행점검표 | S01 기본정보(4필드) + S02 점검표 + S03 안내 | 6열 |

모든 서식: `authoring_class = TAI_ORIGINAL_DRAFT`, `field_origin = TAI_PRACTICAL_PROPOSAL`.

---

## 4. KOSHA 대응 명칭 (페이지 열거 기준)

출처: OBJ-REF-01-KOSHA-24-FORMS-SOURCE-03.md (PAGE_ENUMERATED only)

| TAI 서식 | KOSHA 명칭 (verbatim) | KOSHA 첨부 | 이름 유사도 |
|---------|---------------------|-----------|-----------|
| C029 | 위험성평가표(빈도강도법) (KOSHA #06) | 붙임2 HWP | HIGH |
| C031 | 안전보건교육일지 서식(엑셀, 한글) (KOSHA #24) | 붙임5 ZIP | HIGH |
| C033 | 도급·용역·위탁 업체 안전보건 수준 평가 (KOSHA #11) | 붙임2 HWP | PARTIAL |

KOSHA 명칭 = 페이지 열거만 확인. 필드·레이아웃은 UNVERIFIED.

---

## 5. 원본 비교 결과

| 서식 | 필드 비교 | 레이아웃 비교 | 유사도 | 독립성 | 게이트 상태 |
|------|---------|------------|------|------|----------|
| C029 | IMPOSSIBLE | IMPOSSIBLE | UNVERIFIED | UNVERIFIED | HOLD |
| C031 | IMPOSSIBLE | IMPOSSIBLE | UNVERIFIED | UNVERIFIED | HOLD |
| C033 | IMPOSSIBLE | IMPOSSIBLE | UNVERIFIED | UNVERIFIED | HOLD |

원인: KOSHA 원본 파일(HWP/ZIP) 미확보. JWT 인증 장벽.

---

## 6. 라이선스 증거

| 항목 | 내용 |
|------|------|
| KOSHA 게시 안내 | "사업장 상황에 맞게 수정 가능" — 내부 업무 사용 맥락 |
| 상업적 재배포 명시 허가 | 없음 |
| KOGL 유형 | UNVERIFIED (페이지 접근 불가) |
| 원본 파일 내 저작권 표기 | UNVERIFIED (파일 미확보) |

```
COMMERCIAL_REDISTRIBUTION_AUTHORIZED = NO (3/3)
RIGHTS_STATUS                        = RIGHTS_UNVERIFIED (3/3)
```

---

## 7. TAI 저작 이력 (git 기반 사실)

| 서식 | 최초 커밋 | WO | authoring_class |
|------|---------|-----|----------------|
| C029 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | TAI_ORIGINAL_DRAFT |
| C031 | 3c8f9bf6 → e85c4187 (대체) | WO-BATCH-001, WO-VISUAL-REPAIR-005-PHASE2-CANONICAL-006 | TAI_ORIGINAL_DRAFT |
| C033 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | TAI_ORIGINAL_DRAFT |

주의: git 저작 이력은 TAI 독자 설계 역사를 기록하나, KOSHA 원본과의 유사도 및 독립성을 증명하지 않음.

---

## 8. 변경 파일

| 파일 | 내용 |
|------|------|
| `evidence/kosha-original-compare/B8_KOSHA_SOURCE_PROVENANCE.md` | KOSHA 접근 시도 기록 (신규) |
| `evidence/kosha-original-compare/B8_C029_C031_C033_COMPARISON_MATRIX.json` | 비교 매트릭스 (신규) |
| `evidence/kosha-original-compare/B8_KOSHA_LICENSE_EVIDENCE.md` | 라이선스 증거 (신규) |
| `evidence/kosha-original-compare/REF01_B8_KOSHA_ORIGINAL_COMPARE_RESULT.md` | 본 결과 문서 (신규) |

정규 JSON 14종·PDF 14종·DOCX 14종·공통 엔진·DB 스키마·행 변경 없음.

---

## 9. 요약 카운트

| 항목 | 값 |
|------|---|
| 조사 대상 서식 | 3 (C029, C031, C033) |
| KOSHA 원본 파일 확보 | 0/3 |
| 필드 비교 완료 | 0/3 |
| 유사도 확인 | 0/3 |
| 독립성 확인 | 0/3 |
| 원본 비교 게이트 HOLD | 3/3 |
| 상업적 재배포 승인 | 0/3 |
| KOGL 유형 확인 | 0/3 |
| TAI git 이력 확인 | 3/3 (TAI_ORIGINAL_DRAFT) |

---

## 10. 상태

```
WO                                   = WO-REF01-060-B8-KOSHA-ORIGINAL-COMPARE-009
BASE_HEAD                            = 14f02992dd8e951643275c68fa09d17dd0eebc59
FORMS_INVESTIGATED                   = 3 (C029, C031, C033)
KOSHA_SOURCE_OBTAINED                = 0/3
KOSHA_ACCESS_METHOD_EXHAUSTED        = YES
ATTACHMENT_2_STATUS                  = SOURCE_UNAVAILABLE_JWT_REQUIRED
ATTACHMENT_5_STATUS                  = SOURCE_UNAVAILABLE_JWT_REQUIRED
FIELD_COMPARISON_STATUS              = IMPOSSIBLE (3/3)
SIMILARITY_VERDICT                   = UNVERIFIED (3/3)
INDEPENDENCE_VERDICT                 = UNVERIFIED (3/3)
ORIGINAL_COMPARE_GATE                = HOLD (3/3)
RIGHTS_STATUS                        = RIGHTS_UNVERIFIED (3/3)
COMMERCIAL_REDISTRIBUTION_AUTHORIZED = NO
TAI_GIT_HISTORY                      = CONFIRMED (TAI_ORIGINAL_DRAFT)
PRODUCTION_DB_WRITE                  = 0
CHANGED_FILES                        = 4 (evidence files only, new directory)
B8_CLOSED_FINAL                      = NO
PR_MERGE                             = BLOCKED
DEPLOY                               = BLOCKED
PUBLICATION                          = INTERNAL_POC_ONLY
NEXT_GATE                            = GPT_INDEPENDENT_KOSHA_COMPARE_009_REVIEW
```
