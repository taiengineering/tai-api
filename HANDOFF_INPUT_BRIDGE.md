# Runtime Input Bridge 핸드오프

## 2026-05-20

## 핵심

입력을 새로 만드는 것이 아니다.
기존 Safe 입력 → Runtime Execution 브릿지 연결.

## Source of Truth 정의

| 영역 | Source | Runtime | Sync |
|---|---|---|---|
| 스케줄 | work_schedules | runtime_schedule | → 단방향 |
| 점검 | inspection_set_items | runtime_instance_evidence | → 단방향 |
| 서식 | document_forms | evidence_type | → 단방향 |
| 인력 | safety_personnel | assignment_validation | → 단방향 |
| 설비 | equipment_assets | condition | → 단방향 |
| 현장 | factories | condition | → 단방향 |

## Bridge 매핑 요약

### Schedule: work_schedules → runtime_schedule
- repeat_type → schedule_type
- repeat_interval → recurrence_rule
- assigned_user_id → inspector_id
- planned_date → next_due_date

### Evidence: inspection_set_items → runtime_instance_evidence
- check_type(BOOLEAN) → evidence_type(점검표)
- is_required → state(missing)
- item_name → description

### Document: document_forms → evidence requirement
- category(일상/정기/작업시) → schedule_type(periodic/event_based)
- obligation(법정필수/의무) → requirement level

### Personnel: safety_personnel → assignment validation
- qualification_type → requirement.qualification_name
- qualification_verified → validation source
- entity_type → individual/organization

## 문서
- `docs/platform-core/runtime-input-bridge.md`

## P0 작업
1. work_schedules → runtime_schedule sync 서비스 구현
2. inspection_set_items → evidence type 매핑 구현
3. safety_personnel 데이터 투입
