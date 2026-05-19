# Runtime Replay Strategy

## 목적

운영 Runtime 장애 복구.

## 원칙

1. **Idempotent**: 동일 입력 → 동일 결과 (idempotency_key 사용)
2. **Event Sourcing**: runtime_event_log 기반 재구성
3. **Audit Trail**: 모든 replay 작업 기록

## Replay 유형

| 유형 | 설명 |
|---|---|
| Missed Instance Recovery | Worker 장애로 미생성 instance 복구 |
| Event Replay | runtime_event_log 재생 |
| Instance Regeneration | snapshot 기반 instance 재생성 |

## Replay Flow

```
1. missed schedule 탐색 (next_due_date < now AND instance 없음)
2. idempotency_key 검증 (replay_YYYYMMDD_{task_id})
3. runtime_instance 생성
4. runtime_audit_trail 기록 (actor_type=REPLAY)
5. runtime.instance_replayed emit
```

## 금지

- ❌ 미래 스케줄 replay 금지
- ❌ 이미 완료된 instance 재생성 금지
- ❌ Approval 자동 replay 금지
