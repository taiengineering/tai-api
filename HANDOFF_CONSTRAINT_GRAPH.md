# Constraint Graph IR 완성 — 핸드오프 문서

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 "Family Relation & Constraint Builder" 17단계 전체 실행 완료.
UNKNOWN 78.2% → 3.2% 해소, Edge 4종 → 10종 완성, Subtype 분류 완료.

---

## 핵심 원칙 (준수 확인)

- ✅ Family Candidate 수정 없음 (1단계)
- ✅ 의미 추론/확정 없음
- ✅ Rule 생성 없음
- ✅ Semantic Expansion 미발생
- ✅ 모든 출력 CANDIDATE 상태
- ✅ 패턴 미매칭 → UNRESOLVED 유지 (억지 확정 없음)

---

## 실행 스크립트

| 파일 | 용도 |
|---|---|
| `scripts/run_constraint_enrich.py` | Phase 1: UNKNOWN 노드 타입 복원 + Phase 2: 누락 Edge 생성 |
| `scripts/run_constraint_subtype.py` | 3~10단계: Subtype 분류 + ACTION_SCOPE_RELATION 생성 |

실행 방법:
```bash
cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
railway run python3 scripts/run_constraint_enrich.py
railway run python3 scripts/run_constraint_subtype.py
```

---

## 파이프라인 실행 결과

### Phase 1: UNKNOWN 노드 타입 복원

evidence_token.token_type (Stage 1 정규식 결과)을 증거로 사용.

| token_type | → node_type | 건수 |
|---|---|---|
| REFERENCE_TOKEN | REFERENCE | 76,304 |
| ACTOR_TOKEN | ACTOR | 43,432 |
| CONDITION_TOKEN | CONDITION | 22,163 |
| DEFINITION_TOKEN | DEFINITION | 16,444 |
| OBLIGATION_TOKEN | OBLIGATION | 14,849 |
| DELEGATION_TOKEN | DELEGATION | 13,506 |
| ATTACHMENT_TOKEN | EVIDENCE | 9,160 |
| EXCEPTION_TOKEN | EXCEPTION | 7,579 |
| DEADLINE_TOKEN | DEADLINE | 4,429 |
| TARGET_TOKEN | TARGET | 4,166 |
| FREQUENCY_TOKEN | FREQUENCY | 1,487 |
| **소계** | | **213,519** |
| AUTHORITY_TOKEN | UNKNOWN 유지 | 7,486 |
| PROHIBITION_TOKEN | UNKNOWN 유지 | 1,523 |

UNKNOWN: 222,528 → 9,009 (96% 해소)

### Phase 2: 누락 Edge 생성

| relation_type | 신규 건수 |
|---|---|
| ACTOR_ACTION_RELATION | 12,604 |
| ACTION_REFERENCE_RELATION | 10,638 |
| ACTION_CONDITION_RELATION | 7,128 |
| ACTION_EVIDENCE_RELATION | 3,043 |
| ACTION_EXCEPTION_RELATION | 2,118 |
| ACTION_TARGET_RELATION | 1,023 |
| **소계** | **36,554** |

### Phase 3: Subtype 분류 (프롬프트 3~10단계)

#### [3단계] TARGET → SCOPE

| scope_family | 건수 |
|---|---|
| FACILITY_SCOPE | 1,151 |
| EQUIPMENT_SCOPE | 970 |
| PROCESS_SCOPE | 189 |
| UNRESOLVED_SCOPE | 1,856 |

#### [4단계] CONDITION family_name 세분

| condition_family | 건수 |
|---|---|
| IF_AFTER_INSTALL | 1,060 |
| IF_OVER_THRESHOLD | 1,038 |
| IF_ON_CHANGE | 650 |
| IF_OPERATIONAL | 447 |
| IF_ON_ACCIDENT | 335 |
| IF_EXISTS | 17 |
| CONDITIONAL_FAMILY (기존) | 478 |
| UNRESOLVED_CONDITION | 18,616 |

#### [5단계] CONDITION → TRIGGER

0건 변환. "~경우" 조건문은 이벤트 시점이 아니므로 TRIGGER 전환하지 않음.

#### [6단계] FREQUENCY

| family_name | 건수 |
|---|---|
| ANNUAL_FAMILY | 789 |
| PERIODIC_FAMILY | 176 |
| AD_HOC_FAMILY | 89 |
| QUARTERLY_FAMILY | 21 |
| SEMI_ANNUAL_FAMILY | 9 |
| UNRESOLVED_FREQUENCY | 1,487 |

#### [7단계] DEADLINE

| family_name | 건수 |
|---|---|
| IMMEDIATE_FAMILY | 1,256 |
| WITHIN_FAMILY | 9 |
| BY_FAMILY | 5 |
| UNRESOLVED_DEADLINE | 4,429 |

#### [8단계] EVIDENCE

| family_name | 건수 |
|---|---|
| ATTACHMENT_TABLE_FAMILY | 4,779 |
| ATTACHMENT_FORM_FAMILY | 4,381 |

100% 분류 완료.

#### [9단계] EXCEPTION

| family_name | 건수 |
|---|---|
| PROVISO_EXCEPTION_FAMILY | 6,089 |
| NEGATION_EXCEPTION_FAMILY | 1,490 |

100% 분류 완료.

#### [10단계] REFERENCE

| family_name | 건수 |
|---|---|
| ARTICLE_REFERENCE_FAMILY | 59,600 |
| EXTERNAL_LAW_REFERENCE_FAMILY | 16,704 |

100% 분류 완료.

#### ACTION_SCOPE_RELATION

594건 생성 (ACTION→SCOPE 385 + OBLIGATION→SCOPE 209).

---

## 최종 상태

### Constraint Node (284,579건)

| node_type | 건수 | 비율 |
|---|---|---|
| REFERENCE | 76,304 | 26.8% |
| OBLIGATION | 50,777 | 17.8% |
| ACTOR | 43,432 | 15.3% |
| CONDITION | 22,641 | 8.0% |
| DEFINITION | 21,253 | 7.5% |
| ACTION | 18,482 | 6.5% |
| DELEGATION | 13,506 | 4.7% |
| EVIDENCE | 9,160 | 3.2% |
| UNKNOWN | 9,009 | 3.2% |
| EXCEPTION | 7,579 | 2.7% |
| DEADLINE | 5,699 | 2.0% |
| FREQUENCY | 2,571 | 0.9% |
| SCOPE | 2,310 | 0.8% |
| TARGET | 1,856 | 0.7% |

### Constraint Edge (54,122건)

| relation_type | 건수 |
|---|---|
| ACTION_TRIGGER_RELATION | 15,883 |
| ACTOR_ACTION_RELATION | 12,604 |
| ACTION_REFERENCE_RELATION | 10,638 |
| ACTION_CONDITION_RELATION | 7,134 |
| ACTION_EVIDENCE_RELATION | 3,043 |
| ACTION_EXCEPTION_RELATION | 2,118 |
| ACTION_TARGET_RELATION | 1,023 |
| ACTION_SCOPE_RELATION | 594 |
| ACTION_DEADLINE_RELATION | 591 |
| ACTION_FREQUENCY_RELATION | 494 |

10/10종 전체 생성 완료.

---

## Validation

| 검증 항목 | 결과 |
|---|---|
| raw_token 누락 | 0건 ✅ |
| semantic expansion | 미발생 ✅ |
| 의미 확정 | 미발생 ✅ |
| cross-part edge | 0건 ✅ |
| Rule 생성 | 없음 ✅ |
| Candidate→Truth 승격 | 없음 ✅ |

---

## 잔여 UNRESOLVED 항목

| 항목 | 건수 | 비고 |
|---|---|---|
| UNKNOWN node_type | 9,009 | AUTHORITY_TOKEN 7,486 + PROHIBITION_TOKEN 1,523 (check constraint에 해당 타입 없음) |
| UNRESOLVED_CONDITION | 18,616 | 일반 "~경우" 조건문 — 패턴 미매칭 |
| UNRESOLVED_DEADLINE | 4,429 | 기한 표현이지만 세부 유형 미매칭 |
| UNRESOLVED_SCOPE | 1,856 | 대상 표현이지만 Scope 유형 미매칭 |
| UNRESOLVED_FREQUENCY | 1,487 | 주기 표현이지만 세부 유형 미매칭 |
| family_name UNKNOWN (기타) | 약 70,700 | ACTOR, DELEGATION, OBLIGATION 등 (family_name이 없는 노드) |

---

## DB 테이블

이번 작업에서 변경된 테이블:

| 테이블 | 변경 내용 |
|---|---|
| constraint_node (284,579) | node_type 복원 213,519건 + family_name 분류 98,900건 |
| constraint_edge (54,122) | Edge 신규 37,148건 (Phase 2: 36,554 + Scope: 594) |

신규 테이블 생성 없음. 기존 테이블만 갱신.

---

## 폐기 사항

없음.

---

## 다음 단계 후보

1. **Penalty Candidate & Obligation-Penalty Mapping Engine** — 벌칙/과태료 조문 식별 및 의무-처벌 연결
2. **AUTHORITY/PROHIBITION check constraint 확장** — UNKNOWN 9,009건 해소
3. **UNRESOLVED family_name 보강** — token_family_registry 확장으로 UNRESOLVED 감소
4. **Numeric Constraint Extraction** — 수치/기한/금액 구조화
5. **Rule Candidate IR 생성** — Constraint Graph 기반 (별도 프롬프트 필요)
