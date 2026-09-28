---
title: TAI Safe Pricing V2 — BE-OBJ10-D-B3 Evidence
kind: evidence
status: CANDIDATE
date: 2026-09-28
branch: docs/pricing-canonical-20260927
---

# TAI Safe Pricing V2 — BE-OBJ10-D-B3 Evidence

**OBJ**: Renewal Runtime Branch Wiring (V1/V2 분기)
**Base**: `d6985e1040012949141d92979c2816a2aacf7c39` (B2 FROZEN HEAD)
**Date**: 2026-09-28
**Branch**: `docs/pricing-canonical-20260927`

---

## 1. 변경 파일

| 파일 | 변경 유형 | 내용 |
|------|----------|------|
| `services/saas_renewal_runtime_v2.py` | 신규 생성 | V2 Renewal Runtime 분기 로직 |
| `services/payment_post_process.py` | 수정 | RENEWAL 경로 V1/V2 라우팅 추가 |
| `tests/test_saas_renewal_runtime_v2.py` | 신규 생성 | R01-R45 unit tests |

## 2. FREEZE 자산 변경 없음

| 파일 | 상태 |
|------|------|
| `migrations/2026-09-28_saas_contract_commercial_v2_renewal_atomic_apply.sql` | UNCHANGED |
| `services/saas_renewal_atomic_apply_v2.py` | UNCHANGED |
| `tests/test_saas_renewal_atomic_apply_v2.py` | UNCHANGED |
| `tests/test_saas_renewal_atomic_apply_v2_postgres.py` | UNCHANGED |

## 3. 핵심 Invariant

- `ONE RENEWAL PAYMENT = EXACTLY ONE CONTRACT MUTATION PATH`
- V2 경로 내부: `_extend_contract_for_renewal` call count = 0 (R38 PASS)
- LEGACY 경로 내부: `apply_saas_v2_renewal_runtime` call count = 0 (R39 PASS)
- INVALID route: 계약 mutation 없음, 알림 없음 (R42 PASS)
- V2 오류 → legacy fallback 없음 (R45 PASS)
- Replay 경계: `target.effective_from` (NOT `contract.end_date`) (R28 PASS)

## 4. 라우팅 분기표

| `product_type` | `payment_type` | 경로 |
|----------------|---------------|------|
| `SAAS` | `RENEWAL` | V2 → `apply_saas_v2_renewal_runtime` |
| `SAAS_CONSTRUCTION` / `SAAS_INDUSTRY` / `SAAS_FACILITY` / `SAAS_BUILDING` | `RENEWAL` | LEGACY → `_extend_contract_for_renewal` |
| 그 외 | `RENEWAL` | INVALID → fail closed (return, no mutation) |
| any | `!=RENEWAL` | NOT_RENEWAL (기존 경로 그대로) |

## 5. Circular Import 방지

`saas_renewal_v2_adapter.py`가 `payment_post_process.py`에서 `PAID_STATUS_CODES`를 모듈 레벨에서 import한다.
`saas_renewal_runtime_v2.py`의 `saas_renewal_v2_adapter` / `saas_renewal_atomic_apply_v2` / `member_quote_svc` import는
모두 함수 body 내부 lazy import로 처리한다 (`_build_and_apply`).

## 6. Idempotency (Replay) 설계

```
apply_saas_v2_renewal_runtime(sb, pay):
  1. lookup target CV by renewal_payment_id
  2-a. found → _run_replay: effective_from = target.effective_from
  2-b. not found → _run_first_apply: effective_from = contract_end_date_to_effective_at_v2(contract.end_date)
       on exception → re-lookup → found → _run_replay (race recovery)
                                → not found → re-raise
  max atomic RPC calls = 2 (1 normal + 1 race recovery)
```

**이중 연장 방지**: replay 경로에서 `target.effective_from`을 사용하므로
`contract.end_date`가 이미 연장된 상태여도 동일한 경계로 재진입, 멱등성 보장.

## 7. Test Results

### R01-R45 (unit, no DB)

| 범위 | PASS | FAIL |
|------|------|------|
| R01-R07 `classify_renewal_runtime_route` | 7 | 0 |
| R08-R12 `_validate_v2_payment_guards` | 5 | 0 |
| R13-R21 first apply contract validation | 9 | 0 |
| R22-R27 first apply build/apply path | 6 | 0 |
| R28-R35 replay path | 8 | 0 |
| R36-R39 race recovery + invariants | 4 | 0 |
| R40-R45 PPP routing wiring | 6 | 0 |
| **합계** | **45** | **0** |

### B2 Regression (A01-A42)

42 PASS / 0 FAIL (FREEZE 유지 확인)

### Production Mutation

| 항목 | 수량 |
|------|------|
| Production DDL | 0 |
| Production DB mutation | 0 |
| Runtime wiring changes | `payment_post_process.py` routing block only |

## 8. payment_post_process.py 변경 요약

기존:
```python
if (pay.get("payment_type") or "").upper() == "RENEWAL":
    _extend_contract_for_renewal(sb, pay, existing_contract_id)
```

변경 후:
```python
if (pay.get("payment_type") or "").upper() == "RENEWAL":
    from services.saas_renewal_runtime_v2 import (
        classify_renewal_runtime_route,
        apply_saas_v2_renewal_runtime,
    )
    route = classify_renewal_runtime_route(pay)
    if route == "V2":
        result = apply_saas_v2_renewal_runtime(sb, pay)
        ...
    elif route == "LEGACY":
        _extend_contract_for_renewal(sb, pay, existing_contract_id)
        ...
    else:
        logger.error("[RENEWAL_RUNTIME_ROUTE_INVALID] ...")
        return  # no mutation, no notification
```
