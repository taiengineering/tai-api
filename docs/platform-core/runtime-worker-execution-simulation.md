# Runtime Worker Execution Simulation

## 개념

담당자 배정 이후, 실제 작업 수행/체크/증빗/검토/완료/반려/재작업 흐름 시뮬레이션.

---

## 3단계 누적 변화

| 메트릭 | Phase 0 | Phase 1 | Phase 2 |
|---|---|---|---|
| Completed | 12.5% | 22.5% | **32.5%** |
| Overdue | 25% | 15% | **10%** |
| Evidence Validated | 12.5% | 21.3% | **41.3%** |
| Evidence Missing | 75% | 58.8% | **46.3%** |
| Health Score | ~15 | ~45 | **~55** |

## 핵심 발견

### 가장 심각한 병목
1. **자격 불일치 배정 (16건, 20%)** — 법적 무효 위험
2. **증빗 미제출 (37건, 46%)** — 완료 판정 불가
3. **담당자 미지정 (11건, 14%)** — 실행 주체 없음

### TAI가 해결하는 것
- 기한 관리 누락 → Schedule 자동 + Overdue 감지
- 증빗 누락 → Evidence requirement 자동 생성
- 자격 불일치 → Assignment Requirement 출력 + 경고
- 법적 리스크 → Risk Score + Escalation 가시화

### 사람이 해야 하는 것
- 담당자 지정, 자격 갱신, 증빗 제출, 검토/승인, 재작업

## Rework 성공률: **75%** (3/4)

## 실행 전이 32건 발생
- scheduled→in_progress: 10
- pending→in_progress: 5
- in_progress→completed: 8
- overdue→in_progress: 4
- uploaded→validated: 8
- uploaded→rejected: 5
- rejected→validated: 3
- rejected→rejected: 1
