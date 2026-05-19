# Runtime Lifecycle

```
CANDIDATE
  │
  ├── [HUMAN] approve → APPROVED
  ├── [HUMAN] reject → REJECTED
  └── [HUMAN] waive → WAIVED

APPROVED
  └── [SYSTEM] activate → ACTIVATED (snapshot 저장)

ACTIVATED
  └── [SYSTEM] schedule → SCHEDULED

SCHEDULED
  ├── [SYSTEM] due_date 도래 → PENDING
  └── [SYSTEM] due_date 초과 → OVERDUE

PENDING
  ├── [HUMAN] start → IN_PROGRESS
  └── [SYSTEM] due_date 초과 → OVERDUE

IN_PROGRESS
  └── [HUMAN] complete → COMPLETED

OVERDUE
  ├── [HUMAN] start → IN_PROGRESS
  └── [HUMAN] complete → COMPLETED

COMPLETED
  ├── [SYSTEM] archive → ARCHIVED
  └── [SYSTEM] next_cycle → SCHEDULED (periodic)
```

## State Transitions (23개)

| From | To | Trigger | 설명 |
|---|---|---|---|
| CANDIDATE | APPROVED | HUMAN | 사람 승인 |
| CANDIDATE | REJECTED | HUMAN | 거절 |
| CANDIDATE | WAIVED | HUMAN | 면제 |
| APPROVED | ACTIVATED | SYSTEM | 활성화 |
| ACTIVATED | SCHEDULED | SYSTEM | 스케줄 생성 |
| SCHEDULED | PENDING | SYSTEM | 대기 |
| SCHEDULED | OVERDUE | SYSTEM | 기한초과 |
| PENDING | IN_PROGRESS | HUMAN | 실행 |
| PENDING | OVERDUE | SYSTEM | 기한초과 |
| IN_PROGRESS | COMPLETED | HUMAN | 완료 |
| OVERDUE | IN_PROGRESS | HUMAN | 지연실행 |
| OVERDUE | COMPLETED | HUMAN | 지연완료 |
| COMPLETED | ARCHIVED | SYSTEM | 보관 |
| COMPLETED | SCHEDULED | SYSTEM | 다음주기 |
