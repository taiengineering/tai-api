# Runtime Execution Architecture 핸드오프

## 2026-05-19

## 구축 결과

| 항목 | 건수 |
|---|---|
| Runtime Task (CASE1 건설) | 100 |
| Runtime Task (CASE2 사출) | 100 |
| Runtime Schedule | 200 |
| Runtime Event Log | 200 |
| State Transition Rules | 23 (14 execution + 9 review) |

## Lifecycle States: 11개

candidate → approved → activated → scheduled → pending → in_progress → completed → archived
scheduled/pending → overdue → completed
candidate → rejected/waived

## 3계층 Boundary

1. Structural Runtime (Compiler) — 법령→Metadata
2. Operational Runtime (Orchestrator) — 승인→실행→완료
3. Runtime Projection (Cockpit) — 조회전용

## 문서

- `docs/platform-core/runtime-execution-architecture.md`
- `docs/platform-core/runtime-lifecycle.md`
- `docs/platform-core/runtime-projection-boundary.md`
- `docs/platform-core/deterministic-runtime-compiler.md`
