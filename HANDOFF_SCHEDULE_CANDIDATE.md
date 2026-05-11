# Schedule Candidate Builder — 핸드오프 문서

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 "Schedule Candidate & Operational Timeline Builder" 20단계 전체 실행 완료.
572건 Task에서 1,159건 Schedule Candidate 생성.

---

## 핵심 원칙

- ✅ 날짜 계산 없음
- ✅ Calendar/cron/RRULE 생성 없음
- ✅ due date 확정 없음
- ✅ Candidate→Truth 승격 없음

---

## 실행

```bash
railway run python3 scripts/run_schedule_candidate.py
```

---

## 테이블

| 테이블 | 건수 |
|---|---|
| schedule_candidate | 1,159 |
| schedule_candidate_issue | 0 |

---

## 결과

### schedule_type

| type | 건수 |
|---|---|
| UNRESOLVED_WINDOW_CANDIDATE | 447 |
| NUMERIC_DEADLINE_WINDOW_CANDIDATE | 434 |
| UNRESOLVED_TIMELINE_CANDIDATE | 70 |
| NUMERIC_FREQUENCY_TIMELINE_CANDIDATE | 70 |
| IMMEDIATE_WINDOW_CANDIDATE | 56 |
| YEARLY_TIMELINE_CANDIDATE | 41 |
| PERIODIC_TIMELINE_CANDIDATE | 41 |

### status

| status | 건수 |
|---|---|
| POSSIBLE_CANDIDATE | 530 |
| UNRESOLVED | 517 |
| CANDIDATE | 112 |

### DB 검증

| 검증 | 결과 |
|---|---|
| orphan | ✅ 0건 |
| 건수 | ✅ 1,159 |

---

## 이번 세션 누적 (10개 프롬프트)

| # | 프롬프트 | 결과 |
|---|---|---|
| 1 | Constraint Graph | 284,579 Node / 54,122 Edge |
| 2 | Subtype | 14종 node, 100% 분류 |
| 3 | Numeric Constraint | 10,329 |
| 4 | Numeric Family | 10,329 / 6,934 |
| 5 | Rule Candidate IR | 34,456 RC / 146K Slot |
| 6 | Compatibility | PASS 12,748 / 757 Issue |
| 7 | Executable Draft | 10,725 / 50K Slot |
| 8 | Facility Applicability | 25,920 / MATCH 3,045 |
| 9 | Task Candidate | 3,388 / 15,456 Rel |
| 10 | Schedule Candidate | 1,159 / 572 Task |

테이블 24개, 총 ~982K 레코드.
