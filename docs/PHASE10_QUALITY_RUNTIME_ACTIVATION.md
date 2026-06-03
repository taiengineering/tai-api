# Phase 10 — Quality Store Backfill Smoke Test

> **범위 정정 (2026-06-03):** 원래 이름 “Quality Runtime Activation”은 잘못된 명칭입니다. 실제로 수행한 것은 다음입니다.

## Phase 10에서 실제 검증된 것

- ✅ obligation_quality 테이블에 1000건 적재 가능 (먱등 upsert)
- ✅ 3상태 분류 구조 작동
- ✅ 멱등 적재 가능
- ✅ `fully_classified: true`

## Phase 10에서 실제 성공하지 않은 것

- ❌ LEG 결과 → Check 통과 → READY 만들기 (구조 검증 안 함)
- ❌ 정제 결과가 실제 운영 가능한 의무를 만들었는지

**예시:** 1000건 전부 TRACE_REQUIRED가 나온 이유 = 증거 연결이 다 비어 있어서. 이것은 Phase 10의 구조 문제가 아니라 **실제 운영 데이터의 현재 상태**를 정직하게 반영한 것.

## 지년 다음 두 단계 (정확한 출체)

```text
Phase 10A — LEG → Check Output Verification
           (45cminc/leg repo, PR을 별도 생성)

Phase 10B — Check → Quality Verification
           (taiengineering/tai-api, PR을 별도 생성)
```

두 단계를 통과한 후에만 Schedule Gate 활성화를 논의할 수 있습니다.

## Coverage 데이터 (현재 상태)

실제 타당한 실제이지만:

| 것 | 값 |
|------|-----|
| obligation_quality_rows | 1000 |
| READY | 0 |
| TRACE_REQUIRED | 1000 |
| CORRECTION_REQUIRED | 0 |
| admin_obligation_queue_total | 0 |
| fully_classified | true |

다음 근본 과제 = Phase 10A 통과(LEG→Check 연결) + Phase 10B 통과(Check→Quality 연결) 이후 READY 발생.
