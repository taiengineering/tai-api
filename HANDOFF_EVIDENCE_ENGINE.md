# 법령엔진 v3.0 — 증거 기반 파싱 파이프라인 핸드오프

## 작업 일시
2026-05-10 ~ 2026-05-11

## 작업 요약
기존 sub_type/if_pattern 분류 방식 **전면 폐기** 후, 증거 기반(Evidence-based) 파싱 파이프라인으로 전환.
4단계 파이프라인 구축 완료. 143,549건 법령 조항 전체 실행 완료.

---

## 핵심 원칙
- **"의미를 저장하지 말고 증거를 저장한다"**
- LLM 의미 해석 금지
- 모든 토큰은 원문 span(start, end) 필수
- "관리하여야 한다" 전체 저장 ("관리"로 줄이면 안 됨)
- UNKNOWN/UNRESOLVED 허용 — 억지 분류 금지
- 100% 매핑 (토큰 없어도 원문 링크 유지)
- 모든 출력은 CANDIDATE 상태 — 확정 Rule 생성 금지

---

## 파이프라인 구조

```
law_article_part (143,549)
    ↓ Stage 1: Evidence Token 추출
evidence_token (237,097)
    ↓ Stage 2: 정규화 (Canonical + Family)
evidence_normalized (282,232)
    ↓ Stage 3: Family Grouping
family_candidate (284,579) + family_relation (16,974)
    ↓ Stage 4: Constraint Graph
constraint_node (284,579) + constraint_edge (16,974)
```

---

## Stage 1: Evidence Token 추출

### 파일
- `engine/evidence_extractor.py` (v3)

### 토큰 타입 (13종)
OBLIGATION_TOKEN, PROHIBITION_TOKEN, AUTHORITY_TOKEN, DEFINITION_TOKEN,
DELEGATION_TOKEN, CONDITION_TOKEN, EXCEPTION_TOKEN, FREQUENCY_TOKEN,
DEADLINE_TOKEN, REFERENCE_TOKEN, ATTACHMENT_TOKEN, ACTOR_TOKEN, TARGET_TOKEN

### 추출 방식
- 정규식 기반 전체 표현 보전 (예: `[가-힣]{1,30}하여야\s*한다`)
- 「법률명」 내부는 보호 영역 → 토큰 추출 제외
- 겹치는 span → 긴 매칭 우선
- 빈 텍스트 → UNKNOWN 후보로 100% 매핑 유지

### DB 테이블
- `evidence_token` — span 기반 추출 토큰
- `evidence_candidate` — 토큰에서 생성한 후보
- `evidence_relation` — 주체-행위-대상 관계 후보
- `evidence_validation` — 조항별 검증 결과
- `evidence_issue` — 검증 실패 이슈

### 실행 결과
| 토큰 타입 | 건수 |
|---|---|
| REFERENCE | 76,304 |
| ACTOR | 43,432 |
| OBLIGATION | 27,589 |
| CONDITION | 22,163 |
| DEFINITION | 14,069 |
| DELEGATION | 13,506 |
| AUTHORITY | 10,611 |
| ATTACHMENT | 9,160 |
| EXCEPTION | 7,579 |
| DEADLINE | 5,685 |
| TARGET | 4,166 |
| FREQUENCY | 2,571 |
| PROHIBITION | 1,057 |
| **합계** | **237,097** |

---

## Stage 2: 정규화 (Normalizer)

### 파일
- `engine/evidence_normalizer.py`

### 처리 로직
1. 동사+어미 분리: "통보해야 한다" → canonical "통보" + "해야 한다" (stem 2자 이상만)
2. 주체 조사 제거: "소방서장은" → canonical "소방서장"
3. 그 외: 원문 그대로 IDENTITY
4. Registry 조회 → 있으면 CANDIDATE, 없으면 UNRESOLVED

### DB 테이블
- `token_family_registry` — canonical → family 매핑 (75개 초기 데이터)
- `evidence_normalized` — 정규화 결과

### 실행 결과
- 282,232건 정규화
- CANDIDATE: 64,574건 (22.9%)
- UNRESOLVED: 217,658건 (77.1%)

### Registry Family 분포 (CANDIDATE 상위)
| Family | 건수 |
|---|---|
| MANDATORY_FAMILY | 21,080 |
| PERMISSIVE_FAMILY | 9,677 |
| REPORT_FAMILY | 5,933 |
| DEFINITION_FAMILY | 4,809 |
| MANDATORY_ITEM_FAMILY | 4,701 |
| INSTALL_FAMILY | 3,191 |
| WITHIN_FAMILY | 3,056 |
| EXECUTE_FAMILY | 1,490 |
| IMMEDIATE_FAMILY | 1,256 |

---

## Stage 3: Family Grouping

### 파일
- `engine/family_grouper.py`

### 처리 로직
1. Registry 기반 Multi-Family 매칭 (1토큰 → 여러 Family 허용)
2. Context Restriction (주변 문맥으로 범위 축소, 확정 아님)
3. Family Relation 생성 (Family 간 관계 후보)
4. Validation (raw_token/canonical_token 존재 여부)
5. Semantic Expansion 탐지

### DB 테이블
- `family_candidate` — Family 후보 (CANDIDATE/AMBIGUOUS/CONTEXT_RESTRICTED/UNRESOLVED)
- `family_relation` — Family 간 관계 후보

### 실행 결과
- 284,579 Family Candidate
  - CANDIDATE: 59,380
  - CONTEXT_RESTRICTED_CANDIDATE: 2,808 (Multi-Family 토큰)
  - UNRESOLVED: 222,391
- 16,974 Family Relation

### Multi-Family 토큰
| canonical | Family 1 | Family 2 | 건수 |
|---|---|---|---|
| 확인 | INSPECT_FAMILY | VERIFY_FAMILY | 660 |
| 신고 | REPORT_FAMILY | NOTIFY_FAMILY | 471 |
| 검사 | INSPECT_FAMILY | TEST_INSPECT_FAMILY | 118 |
| 수리 | MAINTAIN_FAMILY | REPAIR_FAMILY | 76 |

---

## Stage 4: Constraint Graph

### 파일
- `engine/constraint_builder.py`

### 처리 로직
1. Family Candidate → Constraint Node 변환
2. 같은 part 내 노드 쌍 → Constraint Edge 생성
3. 관계 유형 10종 (ACTOR_ACTION, ACTION_FREQUENCY 등)
4. Validation (cross-part 관계 탐지)
5. 모든 출력 CANDIDATE — Rule 생성 없음

### DB 테이블
- `constraint_node` — Graph 노드
- `constraint_edge` — Graph 엣지 (연결 후보)

### 실행 결과

**Node 분포**
| node_type | 건수 | 비율 |
|---|---|---|
| UNKNOWN | 222,528 | 78.2% |
| OBLIGATION | 35,928 | 12.6% |
| ACTION | 18,482 | 6.5% |
| DEFINITION | 4,809 | 1.7% |
| DEADLINE | 1,270 | 0.4% |
| FREQUENCY | 1,084 | 0.4% |
| CONDITION | 478 | 0.2% |

**Edge 분포**
| relation_type | 건수 |
|---|---|
| ACTION_TRIGGER_RELATION | 15,883 |
| ACTION_DEADLINE_RELATION | 591 |
| ACTION_FREQUENCY_RELATION | 494 |
| ACTION_CONDITION_RELATION | 6 |

---

## 스크립트 파일

| 파일 | 용도 |
|---|---|
| `scripts/run_evidence_sample.py` | Stage 1+2 샘플 테스트 |
| `scripts/run_evidence_full.py` | Stage 1+2 전체 실행 (143,549건) |
| `scripts/run_family_full.py` | Stage 3 전체 실행 |
| `scripts/run_constraint_full.py` | Stage 4 전체 실행 |

---

## 알려진 이슈

### 1. UNKNOWN 78.2% (222,528건)
- 원인: 참조(제N조), 주체(소방서장), 대상(성능위주설계) 등이 token_family_registry에 family가 없음
- 영향: Constraint Graph에서 UNKNOWN 노드로 남아 Edge 연결 불가
- 조치: ACTOR/TARGET/REFERENCE용 registry 보강 필요 (현재 ACTION/OBLIGATION/FREQUENCY/DEADLINE만 75개)

### 2. Constraint Edge가 4종만 생성
- 원인: ACTOR/TARGET 노드가 UNKNOWN이라 ACTOR_ACTION_RELATION, ACTION_TARGET_RELATION 생성 불가
- 조치: 이슈 #1 해결 시 자동 해소

### 3. 비정규화 법령 미처리 (11,366건)
- 대상: article_type ≠ '조문' (본칙/항/전문/조/절/목/장)
- 원인: law_article_part가 없는 구조 (NFTC/KEC 기술기준)
- 조치: 별도 파이프라인 필요

### 4. Tier 1 부분 수집 법령 (14개, 1,448 조문)
- 대상: 도로교통법, 자동차관리법, 형법, 민법 등
- 원인: law_article은 있으나 law_article_part가 없음 (인용 매칭용 부분 수집)
- 조치: 전체 수집 완료 시 자동 해소

### 5. Context Restriction 정밀도
- 현재: 단순 prefix 10자 확인
- 개선: 복합어 사전 기반 또는 Kiwi 형태소 분석 적용 가능

---

## DB 테이블 전체 목록 (이번 작업에서 생성)

| 테이블 | 건수 | 역할 |
|---|---|---|
| evidence_token | 237,097 | Stage 1 원문 토큰 |
| evidence_candidate | ~237,000 | Stage 1 후보 |
| evidence_relation | ~25,000 | Stage 1 관계 후보 |
| evidence_validation | 143,549 | Stage 1 검증 결과 |
| evidence_issue | 0 | Stage 1 이슈 |
| token_family_registry | 90 | Registry (canonical → family) |
| evidence_normalized | 282,232 | Stage 2 정규화 |
| family_candidate | 284,579 | Stage 3 Family 후보 |
| family_relation | 16,974 | Stage 3 Family 관계 |
| constraint_node | 284,579 | Stage 4 Graph 노드 |
| constraint_edge | 16,974 | Stage 4 Graph 엣지 |

---

## 폐기된 작업

### Track A~E 순차 검증 엔진 (폐기)
- 기존 sub_type/if_pattern 기반 → 94.59% UNCLASSIFIED → 검증 불가
- Track B citation 매칭률 90% 기준 → 실제 평균 59.59% → 대부분 FAIL
- Track E 검증 정규식이 텍스트 변형 미커버 → 325/381 법령 FAIL
- **결론: 의미 분류 방식 자체가 법령 데이터에 부적합 → 증거 기반으로 전환**

### 관련 파일 (더 이상 사용 안 함)
- `engine/track_runner.py`
- `scripts/run_track_full.py`
- `scripts/run_track_by_article.py`
