# Numeric-Aware Family Builder — 핸드오프 문서

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 "Numeric-Aware Family Builder" 17단계 전체 실행 완료.
숫자 조건(10,329건)을 Family Candidate로 매핑하고, Action/Scope/Trigger와의 연결 후보 6,934건 생성.

---

## 핵심 원칙 (준수 확인)

- ✅ Numeric Constraint 수정 없음 (1단계)
- ✅ 법적 의미 확정 없음 (50명이상→선임의무 등 금지)
- ✅ Rule 생성 없음
- ✅ Semantic Expansion 미발생
- ✅ 단위 환산 미발생
- ✅ 모든 출력 CANDIDATE 상태
- ✅ "즉시"/"지체 없이" 등 숫자 없는 표현 제외

---

## 실행 스크립트

| 파일 | 용도 |
|---|---|
| `scripts/run_numeric_family.py` | 테이블 생성 + 17단계 전체 실행 |

```bash
cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
railway run python3 scripts/run_numeric_family.py
```

---

## 생성 테이블

| 테이블 | 건수 | 역할 |
|---|---|---|
| numeric_family_candidate | 10,329 | 숫자 조건 → Family 후보 |
| numeric_graph_relation | 6,934 | Action/Scope/Trigger 연결 후보 |

---

## 실행 결과

### Family Candidate status

| status | 건수 |
|---|---|
| CANDIDATE | 8,779 |
| UNRESOLVED | 1,538 |
| CONTEXT_RESTRICTED_CANDIDATE | 12 |

### Family Candidate 분포 (분류된 것)

| family_name | 건수 |
|---|---|
| DEADLINE_THRESHOLD_FAMILY | 5,056 |
| FREQUENCY_THRESHOLD_FAMILY | 891 |
| EMPLOYEE_THRESHOLD_FAMILY | 783 |
| DISTANCE_THRESHOLD_FAMILY | 691 |
| MONETARY_THRESHOLD_FAMILY | 563 |
| CONCENTRATION_THRESHOLD_FAMILY | 302 |
| VOLTAGE_THRESHOLD_FAMILY | 277 |
| CAPACITY_THRESHOLD_FAMILY | 181 |
| POWER_THRESHOLD_FAMILY | 26 |
| AREA_THRESHOLD_FAMILY | 21 |
| UNKNOWN_THRESHOLD_FAMILY (UNRESOLVED) | 1,538 |

### Graph Relation

| relation_type | 건수 | 설명 |
|---|---|---|
| ACTION_NUMERIC_DEADLINE_RELATION | 3,559 | DEADLINE + ACTION/OBLIGATION |
| NUMERIC_SCOPE_RELATION | 2,339 | 숫자조건 → Scope Family |
| ACTION_NUMERIC_FREQUENCY_RELATION | 604 | FREQUENCY + ACTION/OBLIGATION |
| NUMERIC_TRIGGER_RELATION | 432 | PERIODIC operator → PERIODIC_TRIGGER |

### Subject 기반 제한 (CONTEXT_RESTRICTED_CANDIDATE)

| subject | family | 건수 |
|---|---|---|
| 상시근로자/근로자 | EMPLOYEE_THRESHOLD_FAMILY | 10 |
| 전압 | VOLTAGE_THRESHOLD_FAMILY | 2 |

---

## Validation

| 검증 항목 | 결과 |
|---|---|
| source_span 누락 | 0건 ✅ |
| raw_text 누락 | 0건 ✅ |
| semantic expansion | 미발생 ✅ |
| Rule 생성 | 없음 ✅ |
| 단위 환산 | 미발생 ✅ |

---

## 누적 DB 테이블 (이번 세션 생성)

| 테이블 | 건수 | 생성 시점 |
|---|---|---|
| constraint_node | 284,579 | Constraint Graph Enrichment |
| constraint_edge | 54,122 | Constraint Graph Enrichment |
| numeric_constraint | 10,329 | Numeric Constraint Extraction |
| numeric_family_relation | 8,791 | Numeric Constraint Extraction |
| numeric_issue | 0 | Numeric Constraint Extraction |
| numeric_family_candidate | 10,329 | Numeric-Aware Family Builder |
| numeric_graph_relation | 6,934 | Numeric-Aware Family Builder |

---

## 다음 단계 후보

1. **Penalty Candidate & Obligation-Penalty Mapping Engine** — 벌칙/과태료 조문 식별 및 의무-처벌 연결
2. **Rule Candidate IR 생성** — Constraint Graph + Numeric Family 기반
3. **Facility Applicability Candidate** — 시설 적용 후보 생성
4. **Task/Schedule Candidate** — 작업/일정 후보 생성
5. **Residual Coverage Engine** — 미처리 조문 탐지
