# Human Review Finalization & Compliance Package — 최종 핸드오프

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 11개 전체 실행 완료.
30개 시설에 대한 Compliance Candidate Package 생성.

---

## 핵심: 최종 결정은 사람이 한다.

---

## 실행

```bash
railway run python3 scripts/run_compliance_package.py
```

---

## 테이블

| 테이블 | 건수 |
|---|---|
| compliance_package | 30 |
| compliance_review_queue | 1,737 |
| compliance_audit_log | 20 |

---

## 결과

### Package Status

| status | 건수 |
|---|---|
| CANDIDATE | 28 |
| NEEDS_HUMAN_REVIEW | 1 |
| UNRESOLVED | 1 |

### Review Queue

| issue_type | 건수 |
|---|---|
| AMBIGUOUS_APPLICABILITY | 1,103 |
| UNRESOLVED_SCHEDULE | 517 |
| ISSUE_EXCEPTION_CONFLICT | 89 |
| ISSUE_FREQUENCY_CONFLICT | 28 |

### Audit Log (20단계 전체 파이프라인)

| Step | 단계 | 테이블 | 건수 |
|---|---|---|---|
| 1 | Evidence Token | evidence_token | 237,892 |
| 2 | Canonicalization | evidence_normalized | 283,175 |
| 3 | Family Grouping | family_candidate | 284,579 |
| 4 | Constraint Graph | constraint_node | 284,579 |
| 5 | Constraint Edge | constraint_edge | 54,122 |
| 6 | Numeric Constraint | numeric_constraint | 10,329 |
| 7 | Numeric Family | numeric_family_candidate | 10,329 |
| 8 | Rule Candidate IR | rule_candidate | 34,456 |
| 9 | Rule Candidate Slot | rule_candidate_slot | 146,595 |
| 10 | Rule Candidate Relation | rule_candidate_relation | 59,116 |
| 11 | Compatibility Validation | compatibility_validation | 59,116 |
| 12 | Compatibility Issue | compatibility_issue | 757 |
| 13 | Executable Draft | executable_draft | 10,725 |
| 14 | Draft Slot | draft_slot | 50,133 |
| 15 | Draft Condition Graph | draft_condition_graph | 10,725 |
| 16 | Facility Applicability | facility_applicability | 25,920 |
| 17 | Facility App Detail | facility_applicability_detail | 36,390 |
| 18 | Task Candidate | task_candidate | 3,388 |
| 19 | Task Candidate Relation | task_candidate_relation | 15,456 |
| 20 | Schedule Candidate | schedule_candidate | 1,159 |

---

## 전체 세션 총괄

| # | 프롬프트 | 결과 | DB검증 |
|---|---|---|---|
| 1 | Constraint Graph Enrichment | 284,579 Node / 54,122 Edge | ✅ |
| 2 | Constraint Subtype | 14종 node, SCOPE/EVIDENCE/EXCEPTION/REFERENCE 100% | ✅ |
| 3 | Numeric Constraint | 10,329 / span 100% | ✅ |
| 4 | Numeric Family | 10,329 / 6,934 Rel | ✅ |
| 5 | Rule Candidate IR | 34,456 RC / 146K Slot / 59K Rel | ✅ |
| 6 | Compatibility Validation | PASS 12,748 / 757 Issue | ✅ |
| 7 | Executable Draft | 10,725 / 50K Slot / 10K Graph | ✅ |
| 8 | Facility Applicability | 25,920 / MATCH 3,045 | ✅ |
| 9 | Task Candidate | 3,388 / 15,456 Rel | ✅ |
| 10 | Schedule Candidate | 1,159 / 572 Task | ✅ |
| 11 | Compliance Package | 30 Package / 1,737 Review / 20 Audit | ✅ |

**테이블 27개, 총 822,016 레코드.**
**전체 orphan 0건, broken ref 0건.**

---

## 준수 사항 총괄

- ✅ Rule 확정 없음 (11개 프롬프트 전체)
- ✅ 의무/위반/과태료 확정 없음
- ✅ Candidate→Truth 승격 없음
- ✅ Semantic Expansion 미발생
- ✅ 단위 환산 없음
- ✅ Calendar/cron/날짜 생성 없음
- ✅ UNKNOWN 유지
- ✅ Conflict 탐지만 (해결 없음)
- ✅ Human Review 우회 없음
- ✅ source_span 전 파이프라인 보존
- ✅ Confidence Score 없음

---

## 다음 단계

1. **Human Review** — 1,737건 Review Queue 검토
2. **Penalty Candidate Engine** — 벌칙/과태료 조문 식별
3. **Residual Coverage** — 미처리 조문 탐지
4. **UNRESOLVED 보강** — token_family_registry 확장
5. **API 연동** — Compliance Package → 프론트엔드 노출
