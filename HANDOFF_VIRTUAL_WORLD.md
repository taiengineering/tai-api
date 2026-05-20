# Virtual Runtime World 핸드오프

## 2026-05-20

## 구축 결과

### 데이터 규모
| 항목 | 건수 |
|---|---|
| Virtual Company | 1 |
| Virtual Factories | 10 |
| Virtual Personnel | 15 (12정상/2대기/1만료) |
| Virtual Tasks | 80 (10공장 × 8task) |
| Virtual Schedules | 80 |
| Virtual Instances | 80 |
| Virtual Evidence | 80 |
| Virtual Audit | 80 |
| Registry | 26 |

### 상태 분포
| Instance | Evidence | Personnel |
|---|---|---|
| completed 10 | validated 10 | VERIFIED 12 |
| in_progress 10 | uploaded 10 | PENDING 2 |
| pending 10 | missing 60 | EXPIRED 1 |
| scheduled 20 | | |
| overdue 20 | | |
| cancelled 10 | | |

### 운영 메트릭
| 메트릭 | 값 |
|---|---|
| Assignment Coverage | 0% |
| Qualification Compliance | 80% |
| Overdue Ratio | 25% |
| Evidence Completion | 12.5% |
| Runtime Completion | 12.5% |
| Unresolved Ratio | 37.5% |
