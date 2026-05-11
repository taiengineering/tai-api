# Rule Candidate IR Builder — 핸드오프 문서

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 "Constraint Integration & Rule Candidate IR Builder" 19단계 전체 실행 완료.
Family Candidate + Numeric Constraint를 조합하여 34,456건 Rule Candidate IR 생성.

---

## 핵심 원칙 (준수 확인)

- ✅ Rule 확정 없음
- ✅ 의무/법 적용 확정 없음
- ✅ Candidate→Truth 승격 없음
- ✅ Semantic Expansion 미발생
- ✅ 단위 환산 미발생
- ✅ UNKNOWN 유지 (프롬프트 14단계)
- ✅ 모든 Slot/Relation CANDIDATE 상태

---

## DB 직접 검증 결과

### 참조 무결성

| 검증 | 결과 |
|---|---|
| slot → rule_candidate orphan | 0건 ✅ |
| relation → rule_candidate orphan | 0건 ✅ |
| numeric_graph_relation → constraint_node broken ref | 0건 ✅ |
| numeric_constraint span 정확성 (\uc6d0\ubb38 \ub300\uc870) | 10/10건 100% 일치 ✅ |

---

## 실행 스크립트

| 파일 | 용도 |
|---|---|
| `scripts/run_rule_candidate.py` | Rule Candidate IR 생성 (19단계) |

```bash
cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
railway run python3 scripts/run_rule_candidate.py
```

---

## 생성 테이블

| 테이블 | 건수 | 역할 |
|---|---|---|
| rule_candidate | 34,456 | part단위 Rule 후보 구조 |
| rule_candidate_slot | 146,595 | Slot (ACTION/SCOPE/NUMERIC/등 14종) |
| rule_candidate_relation | 59,116 | Slot 간 연결 후보 |

---

## 실행 결과

### Rule Candidate 총괄

- Rule Candidate: 34,456건
- with Numeric: 3,492건
- Slot: 146,595건 (avg 4/RC, max 181)
- Relation: 59,116건 (avg 2/RC, max 10)

### Slot 분포

| slot_type | CANDIDATE | UNRESOLVED | 합계 |
|---|---|---|---|
| OBLIGATION | 36,004 | 14,773 | 50,777 |
| ACTOR | 0 | 20,419 | 20,419 |
| ACTION | 18,482 | 0 | 18,482 |
| REFERENCE | 0 | 17,444 | 17,444 |
| CONDITION | 18 | 8,325 | 8,343 |
| UNKNOWN | 0 | 7,177 | 7,177 |
| NUMERIC | 3,681 | 549 | 4,230 |
| DELEGATION | 0 | 4,013 | 4,013 |
| DEFINITION | 2,000 | 1,693 | 3,693 |
| EVIDENCE | 0 | 3,617 | 3,617 |
| DEADLINE | 912 | 2,502 | 3,414 |
| EXCEPTION | 0 | 2,295 | 2,295 |
| FREQUENCY | 747 | 415 | 1,162 |
| SCOPE | 0 | 868 | 868 |
| TARGET | 0 | 661 | 661 |

주: ACTOR/REFERENCE/EVIDENCE/EXCEPTION/SCOPE/TARGET 등이 전건 UNRESOLVED인 이유는
기존 family_candidate.status가 UNRESOLVED였기 때문 (token_family_registry에 해당 family 없음).
node_type은 정확히 분류됨.

### Relation 분포

| relation_type | 건수 |
|---|---|
| ACTION_TRIGGER_RELATION | 15,883 |
| ACTOR_ACTION_RELATION | 12,604 |
| ACTION_REFERENCE_RELATION | 10,638 |
| ACTION_CONDITION_RELATION | 7,134 |
| ACTION_NUMERIC_DEADLINE_RELATION | 3,559 |
| ACTION_EVIDENCE_RELATION | 3,043 |
| ACTION_EXCEPTION_RELATION | 2,118 |
| ACTION_TARGET_RELATION | 1,023 |
| NUMERIC_SCOPE_RELATION | 641 |
| ACTION_NUMERIC_FREQUENCY_RELATION | 604 |
| ACTION_SCOPE_RELATION | 594 |
| ACTION_DEADLINE_RELATION | 591 |
| ACTION_FREQUENCY_RELATION | 494 |
| NUMERIC_TRIGGER_RELATION | 190 |

### 샘플 검증

원문: "사업주는 ... 30일 이내에 작업환경측정을 하고, 그 후 반기에 1회 이상 정기적으로 작업환경을 측정해야 한다."

- Slot 11건: ACTOR(사업주), REFERENCE(제186조), SCOPE(작업환경측정), DEADLINE(30일 이내), NUMERIC(30일 이내, 1회 이상), FREQUENCY(정기적으로), OBLIGATION(측정해야 한다), ACTION(측정해야 한다)
- Relation 10건: ACTOR→ACTION, ACTION→FREQUENCY, ACTION→SCOPE, NUMERIC→DEADLINE, NUMERIC→FREQUENCY 등
- 전수 CANDIDATE 상태 — 의미 확정/Rule 추론 없음

---

## Validation

| 검증 항목 | 결과 |
|---|---|
| raw_token 누락 slot | 0건 ✅ |
| Rule inference | 미발생 ✅ |
| semantic expansion | 미발생 ✅ |
| Candidate→Truth 승격 | 없음 ✅ |
| orphan slot/relation | 0건 ✅ |
| broken references | 0건 ✅ |
| UNRESOLVED slot | 84,751건 (UNKNOWN 유지 — 프롬프트 14단계 준수) |

---

## 이번 세션 누적 DB 테이블 총괄

| 테이블 | 건수 | 작업 |
|---|---|---|
| constraint_node | 284,579 | Constraint Graph Enrichment |
| constraint_edge | 54,122 | Constraint Graph Enrichment |
| numeric_constraint | 10,329 | Numeric Constraint Extraction |
| numeric_family_relation | 8,791 | Numeric Constraint Extraction |
| numeric_issue | 0 | Numeric Constraint Extraction |
| numeric_family_candidate | 10,329 | Numeric-Aware Family Builder |
| numeric_graph_relation | 6,934 | Numeric-Aware Family Builder |
| rule_candidate | 34,456 | Rule Candidate IR Builder |
| rule_candidate_slot | 146,595 | Rule Candidate IR Builder |
| rule_candidate_relation | 59,116 | Rule Candidate IR Builder |

---

## 다음 단계 후보

1. **Penalty Candidate & Obligation-Penalty Mapping Engine** — 벌칙/과태료 조문 식별 및 의무-처벌 연결
2. **Facility Applicability Candidate** — 시설 적용 후보 생성
3. **Task/Schedule Candidate** — 작업/일정 후보 생성
4. **Residual Coverage Engine** — 미처리 조문 탐지
5. **UNRESOLVED Slot 보강** — token_family_registry 확장으로 ACTOR/CONDITION 등의 family_name 할당 증가
