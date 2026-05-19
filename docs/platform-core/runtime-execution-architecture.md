# Runtime Execution Architecture

## 2026-05-19

## 개요

TAI Runtime Execution은 법령 Compiler 결과를 실제 운영 lifecycle로 전환하는 시스템이다.

```
runtime_candidate
  ↓ (사람 승인)
approved
  ↓ (시스템 활성화)
activated
  ↓ (스케줄 생성)
scheduled
  ↓ (실행 대기)
pending
  ↓
in_progress → completed → [archived | scheduled(next)]
  ↓
overdue → escalated
```

---

## Runtime Lifecycle States

| State | 설명 | Transition |
|---|---|---|
| candidate | 엔진이 생성한 후보 | → approved / rejected / waived |
| approved | 사람이 승인 | → activated |
| activated | 시스템 활성화 (snapshot 저장) | → scheduled |
| scheduled | 스케줄 생성 완료 | → pending / overdue |
| pending | 실행 대기 | → in_progress / overdue |
| in_progress | 실행 중 | → completed |
| completed | 완료 | → archived / scheduled(next) |
| overdue | 기한 초과 | → in_progress / completed |
| waived | 면제 | 종료 |
| rejected | 거절 | 종료 |
| archived | 보관 | 종료 |

---

## Runtime Schedule Types

| Type | 설명 | 예시 |
|---|---|---|
| periodic | 주기 반복 | 매년, 매월, 분기 |
| one_time | 1회성 | 설치 후, 변경 시 |
| deadline | 기한부 | 14일 이내, 30일 이내 |

---

## Runtime Execution Boundary

### Structural Runtime (법령 내부)
- WHO, WHEN, HOW, CONDITION, SCHEDULE, THRESHOLD
- 법령 구조에서 deterministic 추출
- Compiler가 책임

### Operational Runtime (운영 실행)
- approval, assignment, evidence, overdue, notification, completion
- 사람 + 시스템이 책임
- Orchestrator가 책임

### Runtime Projection (시각화)
- cockpit, dashboard, analytics
- 조회만 가능. 상태 변경 불가.
- Projection Layer가 책임

---

## 금지 규칙

- ❌ 계층 간 Ownership 침범 금지
- ❌ Projection이 Runtime 상태 변경 금지
- ❌ Task 자동 승인 금지
- ❌ 사람 승인 우회 금지
