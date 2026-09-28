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

## PATCH2 Root Cause (GPT B3 PATCH1 재검증 → 발견)

### Root Cause 4: `/inicis/noti` partial projection — `payment_type` 누락

`/inicis/noti` (서버 백업 noti 경로) SELECT에 `payment_type`이 빠져 있어 `payment.get("payment_type") == None`.
`_is_v2_renewal = False`가 되어 V2 Renewal에서도 `contracts.update(is_active=True)`가 실행될 수 있었다.

수정:
1. `routers/payment.py`: `/inicis/noti` SELECT에 `payment_type` 추가.
2. `services/payment_svc.py`: defense-in-depth — `product_type=SAAS` + `payment_type` key absent → skip direct write (partial caller 방어).

---

## PATCH1 Root Causes (GPT B3 독립검증 → 발견)

### Root Cause 1: RENEWAL routing이 contract_id 존재 여부 하위에 중첩

기존 구조에서 `contract_id=NULL`인 malformed RENEWAL이 `_should_auto_contract` / `_create_contract_from_payment` 경로로 새어나갈 수 있었다.

```
BEFORE: if existing_contract_id: → if RENEWAL: → route
AFTER:  if RENEWAL: → route (top-level, before contract_id check)
```

### Root Cause 2: `process_card_success`에 B2 Atomic 외부 contract write

`on_payment_success_sync` 호출 이후 `contracts.update(is_active=True)` 가 무조건 실행되어
V2 Renewal의 경우 B2 Atomic RPC 외부 mutation이 발생했다.

수정: V2 Renewal(`payment_type=RENEWAL AND product_type=SAAS`)이면 해당 write skip.

### Root Cause 3: `_parse_dt_aware` naive datetime silently 보정

naive `target.effective_from`을 UTC로 묵시 변환하여 잘못된 경계로 replay 진행될 수 있었다.

수정: naive → `V2_RUNTIME_TARGET_VERSION_INVALID` fail closed.

---

## 1. 변경 파일

| 파일 | 변경 유형 | 내용 |
|------|----------|------|
| `services/saas_renewal_runtime_v2.py` | 신규 생성 + PATCH1 | V2 Renewal Runtime 분기 로직; naive dt fail-closed |
| `services/payment_post_process.py` | 수정 | RENEWAL top-level routing (contract_id 외부로 이동) |
| `services/payment_svc.py` | 수정 | V2 Renewal: direct contract write skip; SAAS+payment_type absent 방어 |
| `routers/payment.py` | 수정 | `/inicis/noti` SELECT에 `payment_type` 추가 |
| `tests/test_saas_renewal_runtime_v2.py` | 신규 생성 + PATCH1 + PATCH2 | R01-R58 unit tests |

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
- INVALID route: 계약 mutation 없음, 알림 없음 (R42/R48 PASS)
- V2 오류 → legacy fallback 없음 (R45 PASS)
- Replay 경계: `target.effective_from` (NOT `contract.end_date`) (R28 PASS)
- V2 Renewal + contract_id=NULL → runtime으로 전달 → CONTRACT_NOT_FOUND (R46 PASS)
- RENEWAL + contract_id=NULL → `_create_contract_from_payment` call = 0 (R49 PASS)
- V2 Renewal card success → `contracts.update(is_active)` = 0 (R50 PASS)
- naive `target.effective_from` → `V2_RUNTIME_TARGET_VERSION_INVALID` (R53 PASS)

## 4. 라우팅 분기표

| `product_type` | `payment_type` | `contract_id` | 경로 |
|----------------|---------------|--------------|------|
| `SAAS` | `RENEWAL` | any | V2 → `apply_saas_v2_renewal_runtime` |
| `SAAS_CONSTRUCTION` / `SAAS_INDUSTRY` / `SAAS_FACILITY` / `SAAS_BUILDING` | `RENEWAL` | not NULL | LEGACY → `_extend_contract_for_renewal` |
| `SAAS_*` (legacy) | `RENEWAL` | NULL | fail closed: log error, return |
| 그 외 | `RENEWAL` | any | INVALID → fail closed |
| any | `!=RENEWAL` | any | NON-RENEWAL (기존 activate/auto-create 경로) |

## 5. Circular Import 방지

`saas_renewal_v2_adapter.py`가 `payment_post_process.py`에서 `PAID_STATUS_CODES`를 모듈 레벨에서 import한다.
`saas_renewal_runtime_v2.py`의 `saas_renewal_v2_adapter` / `saas_renewal_atomic_apply_v2` / `member_quote_svc` import는
모두 함수 body 내부 lazy import로 처리한다 (`_build_and_apply`).

## 6. Idempotency (Replay) 설계

```
apply_saas_v2_renewal_runtime(sb, pay):
  1. lookup target CV by renewal_payment_id
  2-a. found → _run_replay: effective_from = target.effective_from (tz-aware required)
  2-b. not found → _run_first_apply: effective_from = contract_end_date_to_effective_at_v2(contract.end_date)
       on exception → re-lookup → found → _run_replay (race recovery)
                                → not found → re-raise
  max atomic RPC calls = 2 (1 normal + 1 race recovery)
```

**이중 연장 방지**: replay 경로에서 `target.effective_from`을 사용하므로
`contract.end_date`가 이미 연장된 상태여도 동일한 경계로 재진입, 멱등성 보장.

## 7. Test Results (PATCH1 최종)

### R01-R53 (unit, no DB)

| 범위 | PASS | FAIL |
|------|------|------|
| R01-R07 `classify_renewal_runtime_route` | 7 | 0 |
| R08-R12 `_validate_v2_payment_guards` | 5 | 0 |
| R13-R21 first apply contract validation | 9 | 0 |
| R22-R27 first apply build/apply path | 6 | 0 |
| R28-R35 replay path | 8 | 0 |
| R36-R39 race recovery + invariants | 4 | 0 |
| R40-R45 PPP routing wiring | 6 | 0 |
| R46-R49 RENEWAL cannot create new contract | 4 | 0 |
| R50-R52 card success atomic boundary | 3 | 0 |
| R53 naive effective_from rejected | 1 | 0 |
| R54-R57 noti partial projection boundary | 4 | 0 |
| R58 noti SELECT static assertion | 1 | 0 |
| **합계** | **58** | **0** |

### B2 Regression

| 테스트 | PASS | FAIL |
|--------|------|------|
| A01-A42 (unit) | 42 | 0 |
| I01-I36 (PostgreSQL) | 36 | 0 |

### Full Regression

| 항목 | 수량 |
|------|------|
| PASS | 7087 |
| FAIL (pre-existing) | 95 |
| SKIP | 18 |
| **B3 신규 실패** | **0** |

pre-existing 95건: `test_wo010_*`, `test_wp04d_*`, `test_sm_core22_*`, `test_wp1_corr2_*` 등 — B3와 무관 (LEG_INPUT_FIELDS 카운트, 인프라 환경 의존 등).

### Production Mutation

| 항목 | 수량 |
|------|------|
| Production DDL | 0 |
| Production DB mutation | 0 |
| Runtime wiring changes | `payment_post_process.py` + `payment_svc.py` only |

## 8. payment_post_process.py 변경 요약 (PATCH1)

기존: RENEWAL 분기가 `existing_contract_id` 블록 하위에 중첩.

```python
existing_contract_id = pay.get("contract_id")
if existing_contract_id:
    if payment_type == "RENEWAL":  # ← contract_id NULL이면 이 블록 진입 불가
        ...
```

PATCH1 이후: RENEWAL이 top-level로 이동, contract_id 여부와 독립.

```python
if payment_type == "RENEWAL":      # ← contract_id=NULL이어도 진입
    route = classify_renewal_runtime_route(pay)
    if route == "V2":
        result = apply_saas_v2_renewal_runtime(sb, pay)  # 내부에서 CONTRACT_NOT_FOUND
        send_payment_notification(...)
        return
    if route == "LEGACY":
        legacy_contract_id = pay.get("contract_id")
        if not legacy_contract_id:
            logger.error(...)
            return
        _extend_contract_for_renewal(...)
        send_payment_notification(...)
        return
    logger.error(...)  # INVALID
    return
# 여기부터 NON-RENEWAL: activate / auto-create 경로
```

## 9. payment_svc.py 변경 요약 (PATCH1)

기존: `if contract_id: contracts.update(is_active=True)` 무조건 실행.

PATCH1 이후: V2 Renewal이면 skip.

```python
_is_v2_renewal = (
    (payment.get("payment_type") or "").upper() == "RENEWAL"
    and payment.get("product_type") == "SAAS"
)
if contract_id and not _is_v2_renewal:
    supabase.table("contracts").update({"is_active": True, ...})...
```
