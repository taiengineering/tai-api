# TAI Runtime Operational Simulation Dataset
## 2026-05-12 | Session Handoff

---

## Simulation Dataset Summary

| 항목 | 이전 | 이후 | 목표 |
|------|------|------|------|
| facilities | 20 | **50** | 50+ ✅ |
| equipment | 14 | **150** | 150+ ✅ |
| hazards | 12 | **100** | 100+ ✅ |
| events | 5 | **50** | 50+ ✅ |
| obligations | 11 | 11 | — |
| assignments | 11 | **129** | — |
| schedules | 11 | 11 | — |
| work_orders | 11 | **129** | — |
| worker_queue | 11 | **129** | — |
| checklist_items | 802 | 802 | — |
| inspection_bridge | 324 | 324 | — |

## 사업장 업종 분포
| 업종 | 건수 |
|------|------|
| 제조업 | 14 |
| 화학 | 8 |
| 건설 | 8 |
| 물류 | 5 |
| 병원 | 3 |
| 음식점 | 3 |
| 발전/전기 | 3 |
| 위험물저장 | 2 |
| UNKNOWN/NULL | 3 |
| CLOSED | 1 |

## 사업장 상태 분포
| status | 건수 |
|--------|------|
| ACTIVE | 44 |
| UNKNOWN | 2 |
| UNDER_CONSTRUCTION | 2 |
| INACTIVE | 1 |
| CLOSED | 1 |

## 이벤트 유형 분포
- ACCIDENT 7, NEAR_MISS 3, CONSTRUCTION_START 5, CONSTRUCTION_END 1
- EQUIPMENT_ADDED 6, HAZARD_ADDED 5, WORKER_INCREASE 5
- NIGHT_SHIFT_STARTED 4, CONTRACTOR_ADDED 3, CONTRACTOR_REMOVED 1
- INSPECTION_FAILURE 5, SHUTDOWN 2, RESTART 2, FACILITY_CLOSED 1

## 무결성 검증: 10항목 전부 PASS

## DB 스키마 변경
- runtime_facility_profile.status CHECK: +UNDER_CONSTRUCTION, +CLOSED
- runtime_facility_event_log.event_type CHECK: +CONSTRUCTION_END, +WORKER_INCREASE, +NIGHT_SHIFT_STARTED, +FACILITY_CLOSED
