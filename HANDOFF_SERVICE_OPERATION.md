# Runtime Service Operation 핸드오프

## 2026-05-20

## 구축 결과

### Bridge Sync
| Source | Bridge | 건수 |
|---|---|---|
| work_schedules | runtime_task + schedule + instance | 59 |
| inspection_set_items | evidence requirement | 59 |
| 합계 | runtime pipeline | 259 (200 compiler + 59 bridge) |

### E2E 검증
- CASE1 건설: 224 applicability → 100 tasks → 100 instances ✅
- CASE2 사출: 113 applicability → 100 tasks → 100 instances ✅

### Production Blockers
| P0 | 상세 |
|---|---|
| 담당자 미지정 | runtime_task.assignee_id = 0건 |
| 인력데이터 없음 | safety_personnel = 0건 |
| 반복주기 미설정 | work_schedules.repeat_type = 0건 |

### 운영 가능 비율
- 구조 완성: **90%+**
- 데이터 완성: **40%** (스키마만 있는 테이블 다수)
- 운영 가능: **담당자 지정 + 증빗 업로드 연결 시 운영 가능**

## 문서
- `docs/platform-core/runtime-service-operation.md`
