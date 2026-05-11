# Executable Draft Builder — 핸드오프 문서

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 "Constraint Stabilization & Executable Draft Builder" 20단계 전체 실행 완료.
Compatibility PASS 기반 10,725건 Executable Draft IR 생성.

---

## 핵심 원칙 (준수 확인)

- ✅ PASS 기반만 사용
- ✅ Rule 확정 없음
- ✅ Candidate→Truth 승격 없음
- ✅ Semantic Expansion 미발생
- ✅ UNKNOWN 제거 없음
- ✅ Field Binding은 후보 할당만 (DB 확정 아님)
- ✅ Condition Graph는 법적 Rule 아닔

---

## 실행 스크립트

```bash
cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
railway run python3 scripts/run_executable_draft.py
```

---

## 생성 테이블

| 테이블 | 건수 | 역할 |
|---|---|---|
| executable_draft | 10,725 | PASS 기반 실행 가능 Draft |
| draft_slot | 50,133 | if/then Section별 Slot |
| draft_condition_graph | 10,725 | if[] → then[] 조건 그래프 |
| draft_issue | 0 | 이슈 |

---

## 실행 결과

### Section 분포

| section | 건수 |
|---|---|
| THEN_ACTION | 25,237 |
| IF_ACTOR | 7,513 |
| REFERENCE | 6,196 |
| IF_NUMERIC | 2,589 |
| IF_CONDITION | 2,525 |
| THEN_EVIDENCE | 2,284 |
| THEN_DEADLINE | 2,022 |
| IF_SCOPE | 728 |
| EXCEPTION | 535 |
| THEN_FREQUENCY | 504 |

### Binding Field 분포

| binding_field | 건수 |
|---|---|
| distance_value | 415 |
| equipment_type | 260 |
| facility_type | 220 |
| employee_count | 164 |
| voltage_level | 142 |
| concentration_level | 110 |
| process_type | 33 |
| storage_capacity | 23 |
| power_capacity | 15 |
| area_size | 12 |
| monetary_value | 6 |

### Condition Graph 샘플

| if_families | then_families | 원문 |
|---|---|---|
| [DEADLINE_THRESHOLD, IF_ON_ACCIDENT] | [MANDATORY, RECORD] | "사유가 발생한 날부터 30일 이내에 ... 작성해야 한다" |
| [DISTANCE_THRESHOLD, IF_AFTER_INSTALL, VOLTAGE_THRESHOLD] | [MANDATORY, MANDATORY_ITEM] | "표피전류 가열장치를 시설하는 경우에는 ... 시설하여야 한다" |
| [DEADLINE_THRESHOLD, IF_ON_CHANGE] | [MANDATORY, REPORT] | "변경신고를 하려는 자는 ... 60일 이내에 ... 변경신고서" |

---

## DB 직접 검증

| 검증 | 결과 |
|---|---|
| 건수 일치 | ✅ |
| Binding field 11종 | ✅ |
| Condition Graph 원문 대조 | ✅ if/then이 원문 조건-행위와 정확 대응 |
| Orphan slot/graph/draft | ✅ 전부 0건 |
| Rule inference | ✅ 미발생 |

---

## 누적 DB 테이블 총괄 (이번 세션 전체)

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
| compatibility_validation | 59,116 | Compatibility Validation |
| compatibility_issue | 757 | Compatibility Validation |
| executable_draft | 10,725 | Executable Draft Builder |
| draft_slot | 50,133 | Executable Draft Builder |
| draft_condition_graph | 10,725 | Executable Draft Builder |
| draft_issue | 0 | Executable Draft Builder |

이번 세션 테이블 16개, 총 레코드 약 848K건.

---

## 다음 단계 후보

1. **Penalty Candidate & Obligation-Penalty Mapping Engine** — 벌칙/과태료 조문 식별 및 의무-처벌 연결
2. **Facility Applicability Candidate** — 시설 적용 후보 생성
3. **Task/Schedule Candidate** — 작업/일정 후보 생성
4. **Residual Coverage Engine** — 미처리 조문 탐지
5. **Human Review Queue** — AMBIGUOUS/Conflict 항목 검토 대기열
