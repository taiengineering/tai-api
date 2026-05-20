# Runtime Input Compatibility Audit 핸드오프

## 2026-05-20

## 핵심 발견

기존 Safe 입력 구조가 Runtime과 **80% 이상 호환**.
신규 대형 개발이 필요한 것이 아니라, 비어 있는 스키마에 데이터를 채우고 연결하면 됨.

## 이미 충분한 영역

| 영역 | 근거 |
|---|---|
| CONDITION | factories 15+ 필드, 332건 |
| THRESHOLD | equipment_assets capacity, 1,285건 |
| SCHEDULE | work_schedules + inspection_sets, 383건 |
| HOW | inspection_set_items 5,184건 |
| 서식 | document_forms 260건 |

## 핵심 Gap (구조는 있으나 데이터 없음)

| Gap | 스키마 필드 | 해결 |
|---|---|---|
| safety_personnel | 38필드 | 데이터 투입 |
| safety_agencies | 22필드 | 데이터 투입 |
| education_history | 스키마 완비 | 데이터 투입 |

## 중복 구현 위험

- work_schedules vs runtime_schedule (스케줄 이중)
- inspection_sets.cycle vs runtime_schedule.recurrence (주기 이중)
- obligation_assignment vs assignment_requirement (배정 vs 요구조건)

## P0 작업

1. safety_personnel 데이터 투입
2. work_schedules → runtime_schedule 단방향 동기화
3. safety_personnel.qualification → fix_qualification_master 연결
