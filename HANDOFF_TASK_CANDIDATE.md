# Compliance Task Candidate Generator — 핸드오프 문서

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 "Compliance Task Candidate Generator" 21단계 전체 실행 완료.
Applicability MATCH/POSSIBLE 기반 3,388건 Task Candidate 생성.

---

## 핵심 원칙 (준수 확인)

- ✅ 의무 확정 없음
- ✅ 스케줄/Calendar 생성 없음
- ✅ Priority 추론 없음
- ✅ Candidate→Truth 승격 없음
- ✅ Applicability 기반만 사용

---

## 실행 스크립트

```bash
cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
railway run python3 scripts/run_task_candidate.py
```

---

## 생성 테이블

| 테이블 | 건수 | 역할 |
|---|---|---|
| task_candidate | 3,388 | 시설별 Task 후보 |
| task_candidate_relation | 15,456 | Scope/Numeric/Frequency 등 연결 |
| task_candidate_issue | 0 | 이슈 |

---

## 실행 결과

### Task Type

| task_type | 건수 |
|---|---|
| REPORT_TASK_CANDIDATE | 988 |
| INSTALL_TASK_CANDIDATE | 769 |
| APPOINTMENT_TASK_CANDIDATE | 764 |
| NOTIFY_TASK_CANDIDATE | 200 |
| MANAGE_TASK_CANDIDATE | 198 |
| INSPECTION_TASK_CANDIDATE | 144 |
| VERIFY_TASK_CANDIDATE | 130 |
| DESIGNATE_TASK_CANDIDATE | 84 |
| MEASURE_TASK_CANDIDATE | 42 |
| EXECUTE_TASK_CANDIDATE | 28 |
| TRAINING_TASK_CANDIDATE | 14 |
| PRESERVE_TASK_CANDIDATE | 14 |
| RECORD_TASK_CANDIDATE | 13 |

### Status

| status | 건수 | 설명 |
|---|---|---|
| POSSIBLE_OPERATION_TASK | 2,201 | POSSIBLE_CANDIDATE 기반 |
| CANDIDATE | 1,187 | MATCH_CANDIDATE 기반 |

### Relation

| relation_type | 건수 |
|---|---|
| ACTOR | 4,292 |
| SCOPE | 4,193 |
| REFERENCE | 3,056 |
| NUMERIC | 2,092 |
| EVIDENCE | 881 |
| DEADLINE | 503 |
| EXCEPTION | 287 |
| FREQUENCY | 152 |

### 샘플 검증

인천공장 INSPECTION_TASK_CANDIDATE:
- Source: INSPECT_FAMILY + MANDATORY_FAMILY
- SCOPE: 작업환경측정, 소방대상물
- FREQUENCY: 매년, 정기적으로
- EVIDENCE: 별표 29, 별지 제6호서식
- 의무 확정/스케줄 생성 없음 ✅

---

## DB 검증

| 검증 | 결과 |
|---|---|
| 건수 일치 | ✅ 3,388 + 15,456 + 0 |
| Orphan (applicability 미참조) | ✅ 0건 |
| 샘플 원문 대조 | ✅ 정확 |

---

## 이번 세션 누적 총괄

| # | 프롬프트 | 핵심 결과 |
|---|---|---|
| 1 | Constraint Graph | 284,579 Node / 54,122 Edge |
| 2 | Subtype | 14종 node, SCOPE/EVIDENCE/EXCEPTION/REFERENCE 100% |
| 3 | Numeric Constraint | 10,329건 / span 100% |
| 4 | Numeric Family | 10,329 Family / 6,934 Relation |
| 5 | Rule Candidate IR | 34,456 RC / 146,595 Slot / 59,116 Rel |
| 6 | Compatibility | PASS 12,748 / Conflict 757 |
| 7 | Executable Draft | 10,725 Draft / 50,133 Slot / 10,725 Graph |
| 8 | Facility Applicability | 25,920 평가 / MATCH 3,045 |
| 9 | Task Candidate | 3,388 Task / 15,456 Relation |

테이블 22개, 총 레코드 약 980K건.

---

## 다음 단계 후보

1. **Penalty Candidate & Obligation-Penalty Mapping Engine**
2. **Residual Coverage Engine** — 미처리 조문 탐지
3. **Human Review Queue** — AMBIGUOUS/Conflict/NEEDS_HUMAN_REVIEW 항목
4. **Task → Schedule Draft** — Human 검토 후 스케줄 생성
