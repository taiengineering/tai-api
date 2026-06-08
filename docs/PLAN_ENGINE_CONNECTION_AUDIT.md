# TAI API 전체 엔진 연결 검증 계획

> 배경: 법령엔진에서 "엔진은 완성되었으나 소비자 경로가 연결 안 됨" 발견 (PR #105).
> 같은 패턴이 다른 엔진/파이프라인에도 있을 수 있음.

## 검증 대상 (12개)

| # | 엔진 | 상태 |
|---|------|------|
| 1 | Legal (법령) | ✅ 수정됨 (PR #105) |
| 2 | Check (점검) | ⏳ evidence.chain 미연결 알려짐 |
| 3 | Contract (계약) | ⏳ |
| 4 | Document (문서) | ⏳ |
| 5 | Schedule (일정) | ⏳ |
| 6 | Notification (알림) | ⏳ |
| 7 | Equipment (설비) | ⏳ |
| 8 | Runtime Activation | ⏳ |
| 9 | Runtime Evaluator | ⏳ |
| 10 | SaaS Setup | ⏳ |
| 11 | Compiler Core | ⏳ |
| 12 | Residual Intelligence | ⏳ |

## 실행 순서 (3일)

- Day 1 AM: 전체 엔진 목록 + 연결 상태 (기획서 vs 실제 코드)
- Day 1 PM: DB 데이터 실측 + ENV 전수 조사
- Day 2 AM: E2E 시나리오 테스트 (7개 소비자 + 5개 엔진간)
- Day 2 PM: Check 엔진 파이프라인 추적
- Day 3: 감사 보고서 F-005~F-020 잔여 항목

## 검증 패턴 (각 엔진마다)

1. 기획서 확인 → 기획된 데이터 소스/API 기록
2. 실제 코드 추적 → router → service → DB 테이블
3. 기획 vs 실제 비교
4. 판정: CONNECTED / DISCONNECTED / DEAD / PARTIAL

## 산출물

- ENGINE_CONNECTION_AUDIT.md
- E2E_TEST_RESULTS.md
- REMAINING_ISSUES.md
