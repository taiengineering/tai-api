# Runtime Worker Engine

## 정의

Runtime Worker는 실행 시점이 도래한 runtime_schedule을 runtime_instance로 materialize하는 계층이다.

## 구조

```
runtime_task (정적 운영 정의)
  │
  ▼
runtime_schedule (next_due_date)
  │
  ▼  [Worker: due_date 도래 확인]
runtime_instance (실제 실행 건)
  │
  ├─ runtime_execution_snapshot (실행 순간 context 고정)
  ├─ runtime_instance_evidence (증빙 수집)
  └─ runtime_audit_trail (상태 변화 기록)
```

## Instance 상태

| State | Trigger | 다음 |
|---|---|---|
| scheduled | Worker 생성 | → pending |
| pending | due_date 도래 | → in_progress / overdue |
| in_progress | 사람 시작 | → completed |
| completed | 증빙 완료 | → (next cycle) |
| overdue | due_date 초과 | → in_progress / escalation |
| cancelled | 취소 | 종료 |

## Worker 동작 규칙

1. `runtime_schedule.next_due_date <= now()` 확인
2. `runtime_instance` 생성 (state=scheduled)
3. `runtime_execution_snapshot` 저장 (context 고정)
4. `runtime_instance_evidence` 생성 (required 상태)
5. `runtime_audit_trail` 기록
6. `runtime.instance_created` 이벤트 emit

## 금지

- ❌ Worker는 판단하지 않는다 (deterministic executor)
- ❌ Notification 직접 dispatch 금지 (EventEnvelope → Notification Engine)
- ❌ 사람 승인 우회 금지
