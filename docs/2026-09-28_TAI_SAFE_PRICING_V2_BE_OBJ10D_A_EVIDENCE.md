---
title: TAI Safe Pricing V2 BE-OBJ10-D-A Evidence
status: PATCH1_PASS
date: 2026-09-28
branch: docs/pricing-canonical-20260927
author: Claude Code (claude-sonnet-4-6)
wo: WO-PRICING-V2-BE-OBJ10D-A-001 + PATCH1
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
| `services/saas_renewal_v2_adapter.py` | Renewal prepare + plan builder (PATCH1 포함) | prepare: payments 1 / plan: 0 |
| `tests/test_saas_renewal_v2_adapter.py` | R01-R53 (PATCH1) | 0 |

## 3. Test Results

### PATCH1 최종 (R01-R53)

| Suite | PASS | FAIL |
|-------|------|------|
| R01-R53 (OBJ10-D-A PATCH1) | 53 | 0 |
| OBJ10-A/B/C 회귀 | 195 | 0 |
| **Total** | **248** | **0** |

Pre-existing fail: `test_run_inicis_prepare_success_minimal` (gopaymethod, keypass.enc 미존재, pre-OBJ10-C)
Pre-existing fail: `test_B7_get_inspection_sets_official_linked` (LEG identity bridge 컬럼 순서, pre-OBJ10-D)
Pre-existing fail: `test_T10_contract_files_still_importable_and_stable` (LEG_INPUT_FIELDS count 216→249, pre-OBJ10-D)

Production DB Mutation = 0 (plan builder) / payments 1 (prepare side)

## 4. Design Decisions

### 4.1 Billing Boundary Freeze

| 항목 | 판정 | 근거 |
|------|------|------|
| `subscriptions` 생성 | FROZEN_OUT | V1 CardBilling 전용 경계 밖 |
| `billing_keys` 생성 | FROZEN_OUT | V1 CardBilling 전용 경계 밖 |
| auto-recurring 청구 | FROZEN_OUT | Prepaid Renewal ≠ 자동 반복 |
| `run_billing_prepare` 재사용 | FROZEN_OUT | 스키마 mismatch + 경계 외 |
| `run_billing_return` 재사용 | FROZEN_OUT | 스키마 mismatch + 경계 외 |

**Production inventory (실측, 2026-09-28)**:
- `subscriptions`: total=41 / ACTIVE=0
- `billing_keys`: total=0 / ACTIVE=0
- `payments` (BILLING type): 0건
- `payments` (RENEWAL type): 2건 (PENDING — D-A 이전 테스트 데이터)

**`run_billing_prepare` 스키마 diff (code vs production)**:
- code writes: `plan_code, product_type, status, period_months, price, currency, inicis_order_id`
- production `subscriptions` schema: 미검증 (DDL 조사 별도 WO)

### 4.2 `prepare_saas_v2_renewal_payment_from_quote` (PATCH1 후)

9단계 패턴 (site_scopes 제거):
1. contracts 조회 → 소유권 + ACTIVE 상태 + **service_type=SAAS** (PATCH A)
2. CV 조회 (superseded_at IS NULL) → 현재 유효 버전
3. Quote 조회 → 소유권/**source=member_auto** (PATCH A)/상태/스키마
4. Item typed validation
5. Snapshot typed validation
6. 금액 3중 정합성 (quote ↔ item ↔ snapshot)
7. `_run_inicis_prepare_exact` 호출:
   - `payment_type="RENEWAL"` ← V1 CardBilling 아님
   - `contract_id=contract_id` ← 기존 계약 (새 계약 생성 아님)
   - `plan_code=None` ← V2 sentinel

### 4.3 `SaasV2RenewalApplyPlan` (PATCH D 후)

```python
@dataclass
class SaasV2RenewalApplyPlan:
    payment_id: str
    company_id: str
    contract_id: uuid.UUID          # 기존 계약
    quote_id: str                   # pay.quote_id (PATCH D)
    current_version_no: int         # current_cv.version_no (PATCH D)
    next_version_no: int            # current_cv.version_no + 1
    requested_effective_at: datetime  # Owner Gate 결정
    commercial_bundle: SaasContractStorageBundleV2
```

### 4.4 `build_saas_v2_renewal_apply_plan` (PATCH B+C 후)

- DB Write = 0 (pure, `site_scopes` 인수 제거)
- `effective_from = requested_effective_at` (paid_at 아님 — WO 명시 요건)
- `version_no = current_cv.version_no + 1`
- 22-step plan with PATCH B+C identity guards
- 원자적 갱신 적용은 BE-OBJ10-D-B에서 처리

## 5. Guard Summary

### 5.1 Prepare side

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
| contract.service_type != SAAS | `CONTRACT_NOT_SAAS` | R41 (PATCH A) |
| quote.source != member_auto | `QUOTE_SOURCE_INVALID` | R42 (PATCH A) |

### 5.2 Plan builder (pure)

| Guard | Error Code | Test |
|-------|-----------|------|
| Pay not PAID/SUCCESS | `RENEWAL_PAYMENT_NOT_PAID` | R21 |
| plan_code != None | `RENEWAL_LEGACY_PLAN_CODE_FORBIDDEN` | R22 |
| No paid_at | `RENEWAL_PAID_AT_REQUIRED` | R23 |
| Naive paid_at | `RENEWAL_PAID_AT_INVALID` | R24 |
| No user_id | `RENEWAL_USER_REQUIRED` | R25 |
| product_type != SAAS | `RENEWAL_PAY_NOT_SAAS` | R26 |
| No contract_id | `RENEWAL_CONTRACT_ID_REQUIRED` | R27 |
| payment_type != RENEWAL | `RENEWAL_PAYMENT_TYPE_INVALID` | R28 |
| period_months mismatch | `RENEWAL_PERIOD_TERM_MISMATCH` | R29 |
| CV schema_version mismatch | `CURRENT_CV_SCHEMA_INVALID` | R43 (PATCH B) |
| CV superseded_at IS NOT NULL | `CURRENT_CV_SUPERSEDED` | R44 (PATCH B) |
| CV version_no < 1 | `CURRENT_CV_VERSION_NO_INVALID` | R45 (PATCH B) |
| pay.contract_id != cv.contract_id | `RENEWAL_CONTRACT_CV_MISMATCH` | R46 (PATCH B) |
| pay.company_id != quote.company_id | `RENEWAL_COMPANY_MISMATCH` | R47 (PATCH B) |
| No pay.quote_id | `RENEWAL_QUOTE_ID_REQUIRED` | R48 (PATCH B) |
| pay.quote_id != quote.id | `RENEWAL_QUOTE_ID_MISMATCH` | R49 (PATCH B) |
| quote.source != member_auto (plan re-check) | `QUOTE_SOURCE_INVALID` | R50 (PATCH B) |
| requested_effective_at naive | `RENEWAL_EFFECTIVE_AT_INVALID` | R51 (PATCH C) |
| requested_effective_at < cv.effective_from | `RENEWAL_EFFECTIVE_BEFORE_CURRENT_VERSION` | R52 (PATCH C) |

## 6. Remaining (별도 WO)

- BE-OBJ10-D-B: Renewal 원자적 적용 (CV supersede + 새 CV INSERT + site_scopes INSERT)
- `requested_effective_at` 정책 검증 (미래 시간 제한 등)
- Production `subscriptions` 스키마 조사 + billing boundary migration plan
- Branch 정합화 (main behind 3 commits)
- PR/merge GPT 독립검증
- Production DDL 적용 (Owner Approval)
