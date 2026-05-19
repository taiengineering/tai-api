# Runtime Projection Boundary

## 3계층 분리

### Layer 1: Structural Runtime (Compiler)
**소유:** Legal Runtime Compiler
**책임:** 법령 → Runtime Metadata 변환
**데이터:** rule_candidate, task_candidate, schedule_candidate, runtime_metadata_resolution
**특성:** Deterministic. LLM 금지. Candidate 상태.

### Layer 2: Operational Runtime (Orchestrator)
**소유:** Runtime Execution Orchestrator
**책임:** approval → activation → schedule → execution → evidence → completion
**데이터:** runtime_task, runtime_schedule, runtime_event_log, evidence
**특성:** 사람+시스템. 상태전이 규칙 준수.

### Layer 3: Runtime Projection (Cockpit)
**소유:** Projection Layer
**책임:** 조회 + 시각화
**View:**
- candidate_queue: 승인 대기 후보
- approval_queue: 승인 대기
- activated_runtime: 활성 운영
- overdue_runtime: 기한 초과
- evidence_missing: 증빙 미제출
- completion_status: 완료 현황
- runtime_history: 이력

**특성:** 읽기 전용. 상태 변경 금지.

---

## Ownership 규칙

- Compiler는 Metadata만 생성. Runtime 상태 변경 금지.
- Orchestrator만 Runtime 상태 변경 가능.
- Projection은 조회만. 쓰기 금지.
- 사람 승인 없이 candidate → activated 전환 금지.
