# Runtime Audit Architecture

## 모든 Runtime 상태 변화 기록

## runtime_audit_trail 필드

| 필드 | 설명 |
|---|---|
| entity_type | instance / task / schedule / evidence / escalation / replay |
| entity_id | 대상 UUID |
| action | CREATED / STATE_CHANGE / ASSIGNED / EVIDENCE_UPLOAD / COMPLETED / OVERDUE / ESCALATED / REPLAYED |
| from_state | 이전 상태 |
| to_state | 이후 상태 |
| actor_type | HUMAN / SYSTEM / WORKER / REPLAY |
| idempotency_key | 중복 방지 키 |

## Audit 대상

- State transition (scheduled → pending → completed)
- Assignment (담당자 지정)
- Evidence upload (증빙 업로드)
- Completion (완료)
- Overdue (기한초과)
- Escalation (에스컬레이션)
- Replay (복구)
