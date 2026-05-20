# Runtime Human Governance Simulation

## 개념

Runtime는 완전 자동 운영 시스템이 아니다.
사람의 운영 결정이 들어와야 안정화되는 **Human Governance 기반 운영 시스템**이다.

---

## 시뮬레이션 결과

### Before vs After

| 메트릭 | Before | After | 변화 |
|---|---|---|---|
| Assignment Coverage | 0% | **80%** | +80%p |
| Overdue | 20 (25%) | **12 (15%)** | -40% |
| Completed | 10 (12.5%) | **18 (22.5%)** | +80% |
| Evidence Validated | 10 | **17** | +70% |
| Evidence Missing | 60 | **47** | -22% |
| Evidence Rejected | 0 | **3** | (자격불일치 발견) |
| Escalations | 0 | **22** | (문제 가시화) |
| Risk Score | 53.25 | **27.35** | **-48.6%** |

### Assignment Injection 분포

| 유형 | 비율 | 건수 |
|---|---|---|
| 정상 배정 | 40% | 32 |
| 자격 불일치 | 20% | 16 |
| 과부하 | 10% | 8 |
| 기관 위탁 | 10% | 8 |
| 미지정 | 20% | 16 |

### Escalation 분포

| Level | 건수 | 조건 |
|---|---|---|
| CRITICAL | 3 | overdue + 미지정 |
| HIGH | 3 | overdue + 자격불일치 |
| MEDIUM | 6 | 과부하 배정 |
| LOW | 10 | evidence missing |

---

## TAI Runtime 역할

### 시스템이 하는 것
- 법령 요구조건 추출 (Compiler)
- 운영 일정 생성 (Scheduler)
- 기한 초과 감지 (Worker)
- 문제 가시화 (Cockpit)
- 위험 수치화 (Risk Score)

### 사람이 하는 것
- 담당자 지정
- 자격 검증/갱신
- 기관 선택
- 증빗 제출
- 완료 판정
- 선임 승인

### 금지
- 자동 담당자 지정
- 자동 법적 충족 확정
- 자동 운영 결정
