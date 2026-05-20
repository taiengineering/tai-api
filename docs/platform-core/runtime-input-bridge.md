# Runtime Input Bridge

## 원칙

입력을 새로 만드는 것이 아니다.
이미 존재하는 Safe 입력 구조를 Runtime Execution의 Input Source Layer로 연결한다.

---

## 1. Source of Truth 정의

| 영역 | Source of Truth | Runtime Layer | Sync 방향 |
|---|---|---|---|
| **스케줄** | `work_schedules` | `runtime_schedule` | work → runtime (단방향) |
| **점검항목** | `inspection_set_items` | `runtime_instance_evidence` | items → evidence (단방향) |
| **서식** | `document_forms` | `runtime_instance_evidence` | forms → evidence_type (단방향) |
| **인력** | `safety_personnel` | `runtime_assignment_requirement` | personnel → validation (단방향) |
| **설비** | `equipment_assets` | `runtime_task.metadata` | assets → condition (단방향) |
| **현장** | `factories` | `runtime_task.metadata` | factory → condition (단방향) |

**규칙:** Runtime Layer에서 Source of Truth를 수정하지 않는다. 역방향 sync 금지.

---

## 2. Schedule Bridge

```
work_schedules (Source of Truth)
  │  repeat_type → schedule_type
  │  repeat_interval → recurrence_rule.interval
  │  repeat_weekday → recurrence_rule.weekday
  │  assigned_user_id → inspector_id
  │  planned_date → next_due_date
  │  inspection_set_id → task_id (via bridge)
  ▼
runtime_schedule (Execution Layer)
```

### 필드 매핑

| work_schedules | runtime_schedule | 변환 |
|---|---|---|
| repeat_type | schedule_type | daily→periodic, weekly→periodic, monthly→periodic, once→one_time |
| repeat_interval | recurrence_rule.interval | 직접 매핑 |
| repeat_weekday | recurrence_rule.weekday | 직접 매핑 |
| repeat_day | recurrence_rule.day_of_month | 직접 매핑 |
| week_of_month | recurrence_rule.week | 직접 매핑 |
| start_date | next_due_date (초기) | 시작일 = 첫 due date |
| assigned_user_id | inspector_id | 직접 매핑 |
| active_yn | status | true→active, false→inactive |

---

## 3. Evidence Bridge

```
inspection_set_items (Source of Truth)
  │  check_type → evidence_type
  │  is_required → state='missing' (required)
  │  item_name → evidence description
  │  threshold_value → validation criteria
  ▼
runtime_instance_evidence (Execution Layer)
```

### Evidence Type 매핑

| check_type | evidence_type | evidence_format |
|---|---|---|
| BOOLEAN | 점검표 | 체크리스트 |
| NUMERIC (향후) | 측정기록 | 서면/전자 |
| PHOTO (향후) | 사진 | 이미지 |
| DOCUMENT (향후) | 문서 | 서면/전자 |

---

## 4. Document Bridge

```
document_forms (Source of Truth)
  │  category → schedule_type mapping
  │  obligation → requirement level
  │  law_ref → source_trace
  │  submit_to → evidence target
  ▼
runtime_instance_evidence (Execution Layer)
```

### Category → Schedule Type

| document_forms.category | runtime schedule | 의미 |
|---|---|---|
| 일상 (98) | periodic (daily) | 매일 점검/기록 |
| 정기 (72) | periodic (monthly/yearly) | 정기 보고/점검 |
| 작업시 (24) | event_based | 작업 전 허가 |
| 착공전 (23) | one_time | 착공 전 제출 |
| 사고시 (22) | event_based (immediate) | 즉시 보고 |
| 변경시 (15) | event_based | 변경 시 신고 |
| 종료 (4) | deadline | 완료 보고 |
| 감독대응 (2) | conditional | 요청 시 |

---

## 5. Personnel Bridge

```
safety_personnel (Source of Truth)
  │  qualification_type → qualification_name
  │  qualification_grade → qualification_grade
  │  entity_type → subject_type (individual/organization)
  │  verified_status → validation status
  │  current_slots/max_slots → capacity check
  ▼
runtime_assignment_requirement (Constraint Layer)
  │  qualification_name + minimum_count
  ▼
Validation Layer (향후)
  │  personnel.qualification ≥ requirement.qualification?
  ▼
Human Decision
```

### 자격 매핑 경로

```
runtime_assignment_requirement.qualification_name
  = '산업안전기사'
        │
        ▼
fix_qualification_master.name
  WHERE code = 'SAFETY-001' (예시)
        │
        ▼
safety_personnel.qualification_type
  WHERE qualification_type = '산업안전기사'
  AND qualification_verified = true
```

---

## 6. Runtime Activation Input Flow

```
사업장 등록 (factories)
    │
    ▼
법령엔진 실행
    │  → runtime_candidate 생성
    ▼
안전관리자 Cockpit
    │  → candidate 확인 + 승인
    ▼
점검세트 선택 (inspection_sets)
    │  → 324개 세트 중 선택
    ▼
스케줄 설정 (work_schedules)
    │  → repeat_type + interval + weekday
    ▼
담당자 지정 (users)
    │  → assigned_user_id
    │  → qualification check (향후 validation layer)
    ▼
Activation
    │  → runtime_task 생성
    │  → runtime_schedule 생성 (work_schedules에서 sync)
    │  → runtime_instance_evidence 생성 (inspection_set_items에서 sync)
    │  → runtime_execution_snapshot 저장
    ▼
Runtime Execution
```

---

## 7. Runtime Input Source Map

| Runtime Metadata | Source of Truth | 테이블 | 필드 |
|---|---|---|---|
| CONDITION | `factories` | employee_count, sector, construction_amount | 15+ 필드 |
| THRESHOLD | `equipment_assets` | capacity_value, capacity_unit | 1,285건 |
| HOW | `inspection_set_items` | item_name, check_type | 5,184건 |
| SCHEDULE | `work_schedules` | repeat_type, repeat_interval | 59건 |
| EVIDENCE | `document_forms` | category, obligation, law_ref | 260건 |
| ASSIGNMENT | `safety_personnel` + `fix_qualification_master` | qualification_type, grade | 58 + 0건 |

---

## 8. 중복 방지 전략

| 중복 쌍 | Source of Truth | Runtime Layer | 전략 |
|---|---|---|---|
| work_schedules vs runtime_schedule | **work_schedules** | runtime_schedule | 단방향 sync. runtime에서 원본 수정 금지 |
| inspection_sets.cycle vs runtime recurrence | **inspection_sets** | runtime_schedule | cycle 정보를 recurrence_rule로 변환 |
| obligation_assignment vs assignment_requirement | 각각 독립 | 역할 분리 | assignment=실제배정, requirement=요구조건 |

---

## 9. 자동 배정 금지

- ❌ Runtime에서 Source of Truth 수정 금지
- ❌ 역방향 sync 금지
- ❌ Assignment 자동화 금지
- ❌ Activation 사람 승인 우회 금지
