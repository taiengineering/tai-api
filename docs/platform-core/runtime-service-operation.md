# Runtime Service Operation

## 2026-05-20

## 개요

기존 Safe 운영 구조를 Runtime Execution에 연결하여 실제 서비스 운영 가능 상태를 만든다.

---

## 1. 연결 결과

| Source | Runtime | Sync | 건수 |
|---|---|---|---|
| work_schedules (59) | runtime_task + schedule | → 단방향 | 59 bridge 생성 |
| inspection_set_items (5,184) | evidence requirement | → 단방향 | 연결 완료 |
| document_forms (260) | evidence type | → 단방향 | 매핑 정의 |
| factories (332) | condition | → 단방향 | 이미 연결 |
| equipment_assets (1,285) | threshold | → 단방향 | 이미 연결 |

## 2. Runtime Pipeline 전체 현황

| 계층 | 건수 |
|---|---|
| runtime_task (법령 compiler) | 200 |
| runtime_task (Safe bridge) | 59 |
| runtime_task (전체) | **259** |
| runtime_schedule | **259** |
| runtime_instance | **259** |
| runtime_instance_evidence | **262** |
| runtime_audit_trail | 200 |
| runtime_event_log | 200 |

## 3. E2E 검증

| CASE | Applicability | Tasks | Schedules | Instances | Evidence |
|---|---|---|---|---|---|
| 건설현장 78억 | 224 | 100 | 100 | 100 | 101 |
| 사출공장 250명 | 113 | 100 | 100 | 100 | 102 |

## 4. Production Blockers

| 우선순위 | Blocker | 영향 |
|---|---|---|
| **P0** | safety_personnel **0건** | 담당자 자격 검증 불가 |
| **P0** | runtime_task.assignee_id **0건** | 실행 주체 없음 |
| **P0** | work_schedules.repeat_type **0건** | 반복주기 미설정 |
| **P1** | attachments **0건** | 증빗 업로드 미연결 |
| **P1** | safety_agencies **0건** | 전문기관 위탁 불가 |
| **P2** | education_history **0건** | 교육 이력 추적 불가 |
| **P2** | form_submissions **0건** | 서식 입력 미연결 |

## 5. 최소 운영 가능 상태 (Minimum Operable Runtime)

| 조건 | 현재 | 필요 작업 |
|---|---|---|
| candidate 생성 | ✅ 가능 (259건) | - |
| activation | ✅ 가능 (lifecycle 정의) | - |
| runtime schedule | ✅ 생성됨 (259건) | repeat_type 설정 필요 |
| evidence upload | ⚠️ 구조만 | attachment upload flow 연결 |
| overdue 처리 | ✅ 구조 존재 | Worker cron 필요 |
| cockpit 표시 | ⚠️ 데이터 존재 | projection 쿼리 필요 |
| 담당자 지정 | ❌ 0건 | **핵심 blocker** |

## 6. 운영 흐름

```
factories (332)
  │
  ▼
법령엔진 → runtime_candidate (200)
  │
  ▼
안전관리자 승인 → activation
  │
  ├─ inspection_set 선택 (324세트)
  ├─ work_schedule 설정 (59건 → bridge)
  ├─ 담당자 지정 (❌ 0건)
  └─ evidence requirement (✅ 262건)
  │
  ▼
runtime_task (259) → schedule (259)
  │
  ▼
runtime_instance (259) → evidence (262)
  │
  ▼
execution → completion → audit
```
