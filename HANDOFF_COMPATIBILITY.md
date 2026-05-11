# Compatibility Validation Engine — 핸드오프 문서

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 "Rule Candidate Compatibility Validation Engine" 19단계 실행 완료.
59,116건 Relation 호환성 검증 + 757건 Conflict 탐지.

---

## 핵심 원칙 (준수 확인)

- ✅ Rule 확정 없음
- ✅ Conflict 해결 없음 (탐지만)
- ✅ Candidate→Truth 승격 없음
- ✅ Semantic Expansion 미발생
- ✅ UNKNOWN 제거 없음
- ✅ 점수 기반 판정 없음 (PASS/AMBIGUOUS/UNRESOLVED만)

---

## 실행 스크립트

| 파일 | 용도 |
|---|---|
| `scripts/run_compatibility_check.py` | 호환성 검증 + Conflict 탐지 |

```bash
cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
railway run python3 scripts/run_compatibility_check.py
```

---

## 생성 테이블

| 테이블 | 건수 | 역할 |
|---|---|---|
| compatibility_validation | 59,116 | Relation별 호환성 결과 |
| compatibility_issue | 757 | Conflict 탐지 이슈 |

---

## 실행 결과

### Compatibility 결과 총괄

| validation | 건수 | 비율 |
|---|---|---|
| UNRESOLVED | 36,861 | 62.3% |
| PASS | 12,748 | 21.6% |
| AMBIGUOUS | 9,507 | 16.1% |

UNRESOLVED 62.3%는 UNKNOWN family_name 노드에 의한 것으로, token_family_registry 확장 시 감소 가능.

### PASS 주요 조합 (상위 5)

| from_family | to_family | 건수 |
|---|---|---|
| REPORT_FAMILY | MANDATORY_FAMILY | 5,288 |
| INSTALL_FAMILY | MANDATORY_FAMILY | 1,459 |
| INSTALL_FAMILY | MANDATORY_ITEM_FAMILY | 1,253 |
| DEADLINE_THRESHOLD | REPORT_FAMILY | 1,132 |
| INSPECT_FAMILY | MANDATORY_FAMILY | 614 |

### Conflict 탐지

| issue_type | 건수 | 예시 |
|---|---|---|
| ISSUE_EXCEPTION_CONFLICT | 689 | "다만, ~하여야 한다" (단서+의무 공존) |
| ISSUE_FREQUENCY_CONFLICT | 68 | "매년 1회이상" (ANNUAL+UNRESOLVED_FREQUENCY) |
| DEADLINE_CONFLICT | 0 | 탐지됨 없음 |

---

## DB 직접 검증

| 검증 | 결과 |
|---|---|
| 건수 일치 | ✅ 59,116 + 757 |
| PASS 조합 registry 대조 | ✅ 전건 registry 내 |
| FREQUENCY_CONFLICT 원문 확인 | ✅ "매년 1회이상" 등 다중 주기 정당 탐지 |
| EXCEPTION_CONFLICT 원문 확인 | ✅ "다만, ~하여야 한다" 단서+의무 정당 탐지 |
| Conflict 해결 시도 | ✅ 없음 (탐지만) |

---

## 누적 DB 테이블 총괄 (이번 세션)

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

---

## 다음 단계 후보

1. **Penalty Candidate & Obligation-Penalty Mapping Engine** — 벌칙/과태료 조문 식별 및 의무-처벌 연결
2. **Facility Applicability Candidate** — 시설 적용 후보 생성
3. **Task/Schedule Candidate** — 작업/일정 후보 생성
4. **Residual Coverage Engine** — 미처리 조문 탐지
5. **UNRESOLVED 감소** — token_family_registry 확장으로 PASS비율 증가 가능
