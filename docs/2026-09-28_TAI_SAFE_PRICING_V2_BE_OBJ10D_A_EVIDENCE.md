---
title: TAI Safe Pricing V2 BE-OBJ10-D-A Evidence
status: PASS
date: 2026-09-28
branch: docs/pricing-canonical-20260927
author: Claude Code (claude-sonnet-4-6)
wo: WO-PRICING-V2-BE-OBJ10D-A-001
---

# TAI Safe Pricing V2 BE-OBJ10-D-A — V2 Prepaid Renewal Adapter + Billing Boundary Freeze

## 1. Objective

V2 Prepaid Renewal Adapter 구현 및 Billing 경계 Freeze.

- Renewal Quote Frozen Snapshot → INICIS Prepaid 결제 준비 (`payment_type="RENEWAL"`)
- 기존 V2 계약(`contract_id` 필수)에 대한 1회 선불 갱신만 처리
- `subscriptions` / `billing_keys` / auto-recurring 경계 Freeze (이 경계 밖)
- `requested_effective_at` = caller 입력 (Owner Gate 결정, `paid_at` 아님)
- DB Mutation = 0 (plan builder 단계)

## 2. Artifacts

| 파일 | 역할 | DB Write |
|------|------|----------|
| `services/saas_renewal_v2_adapter.py` | Renewal prepare + plan builder | prepare: payments 1 / plan: 0 |
| `tests/test_saas_renewal_v2_adapter.py` | R01-R40 | 0 |

## 3. Test Results

| Suite | PASS | FAIL |
|-------|------|------|
| R01-R40 (OBJ10-D-A) | 40 | 0 |
| Prior V2 adapters (OBJ10-A/B/C regression) | 388 | 0 |
| **Total** | **428** | **0** |

Pre-existing fail: `test_run_inicis_prepare_success_minimal` (gopaymethod, pre-OBJ10-C)

## 4. Design Decisions

### 4.1 Billing Boundary Freeze

| 항목 | 판정 | 근거 |
|------|------|------|
| `subscriptions` 생성 | FROZEN_OUT | V1 CardBilling 전용 경계 밖 |
| `billing_keys` 생성 | FROZEN_OUT | V1 CardBilling 전용 경계 밖 |
| auto-recurring 청구 | FROZEN_OUT | Prepaid Renewal ≠ 자동 반복 |
| `run_billing_prepare` 재사용 | FROZEN_OUT | 스키마 mismatch + 경계 외 |
| `run_billing_return` 재사용 | FROZEN_OUT | 스키마 mismatch + 경계 외 |

**`run_billing_prepare` 스키마 diff (code vs production)**:
- code writes: `plan_code, product_type, status, period_months, price, currency, inicis_order_id`
- production `subscriptions` schema: 미검증 (DDL 조사 별도 WO)

### 4.2 `prepare_saas_v2_renewal_payment_from_quote`

10단계 패턴 (saas_payment_v2_adapter.py 대칭):
1. contracts 조회 → 소유권 + ACTIVE 상태
2. CV 조회 (superseded_at IS NULL) → 현재 유효 버전
3. site_scopes 조회
4. Quote 조회 → 소유권/상태/스키마
5. Item typed validation
6. Snapshot typed validation
7. 금액 3중 정합성 (quote ↔ item ↔ snapshot)
8. `_run_inicis_prepare_exact` 호출:
   - `payment_type="RENEWAL"` ← V1 CardBilling 아님
   - `contract_id=contract_id` ← 기존 계약 (새 계약 생성 아님)
   - `plan_code=None` ← V2 sentinel

### 4.3 `SaasV2RenewalApplyPlan`

```python
@dataclass
class SaasV2RenewalApplyPlan:
    payment_id: str
    company_id: str
    contract_id: uuid.UUID          # 기존 계약
    next_version_no: int            # current_cv.version_no + 1
    requested_effective_at: datetime  # Owner Gate 결정
    commercial_bundle: SaasContractStorageBundleV2
```

### 4.4 `build_saas_v2_renewal_apply_plan`

- DB Write = 0 (pure)
- `effective_from = requested_effective_at` (paid_at 아님 — WO 명시 요건)
- `version_no = current_cv.version_no + 1`
- 원자적 갱신 적용은 BE-OBJ10-D-B에서 처리

## 5. Guard Summary

| Guard | Error Code | Test |
|-------|-----------|------|
| Contract not found | `CONTRACT_NOT_FOUND` | R01 |
| Contract not owned | `CONTRACT_NOT_OWNED` | R02 |
| Contract not ACTIVE | `CONTRACT_NOT_ACTIVE` | R03 |
| No current CV | `CURRENT_CV_NOT_FOUND` | R04 |
| Quote not found | `QUOTE_NOT_FOUND` | R05 |
| Quote not owned | `QUOTE_NOT_OWNED` | R06 |
| Quote not ISSUED | `QUOTE_NOT_ISSUED` | R07 |
| Quote not SAAS | `QUOTE_NOT_SAAS` | R08 |
| Wrong schema version | `QUOTE_NOT_V2` | R09 |
| Malformed item | `QUOTE_ITEM_INVALID` | R10 |
| supply_amount mismatch | `QUOTE_PAYMENT_SNAPSHOT_INVALID` | R11-R14 |
| Pay not PAID/SUCCESS | `RENEWAL_PAYMENT_NOT_PAID` | R21 |
| plan_code != None | `RENEWAL_LEGACY_PLAN_CODE_FORBIDDEN` | R22 |
| No paid_at | `RENEWAL_PAID_AT_REQUIRED` | R23 |
| Naive paid_at | `RENEWAL_PAID_AT_INVALID` | R24 |
| No user_id | `RENEWAL_USER_REQUIRED` | R25 |
| product_type != SAAS | `RENEWAL_PAY_NOT_SAAS` | R26 |
| No contract_id | `RENEWAL_CONTRACT_ID_REQUIRED` | R27 |
| payment_type != RENEWAL | `RENEWAL_PAYMENT_TYPE_INVALID` | R28 |
| period_months mismatch | `RENEWAL_PERIOD_TERM_MISMATCH` | R29 |

## 6. Remaining (별도 WO)

- BE-OBJ10-D-B: Renewal 원자적 적용 (CV supersede + 새 CV INSERT + site_scopes INSERT)
- `requested_effective_at` 정책 검증 (미래 시간 제한 등)
- Production `subscriptions` 스키마 조사 + billing boundary migration plan
- Branch 정합화 (main behind 3 commits)
- PR/merge GPT 독립검증
- Production DDL 적용 (Owner Approval)
