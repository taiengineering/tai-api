---
title: "TAI Safe Pricing V2 BE-OBJ10-B Evidence"
work_order: WO-PRICING-V2-BE-OBJ10-B
objective: "Contract Row Builder — Frozen Quote Snapshot → SaasV2ApplyPlan"
author: Claude Code
date: 2026-09-28
status: PASS
---

# TAI Safe Pricing V2 BE-OBJ10-B Evidence

## 1. EXECUTION ANCHOR

- Base commit: `0f4d20b8` (OBJ10-A HEAD)
- OBJ10-B commit: `b8f49f20`
- OBJ10-B PATCH1 commit: `0689ddc7`
- Branch: `docs/pricing-canonical-20260927`

## 2. EXISTING PAYMENT POST-PROCESS OBSERVED

| 항목 | 값 |
|------|-----|
| 기존 V1 contract 생성 | `_create_contract_from_payment(sb, pay)` |
| 기존 plan_code 로직 | `(pay.get("plan_code") or "INDUSTRY_PRO").upper()` |
| 기존 period_months | `int(pay.get("period_months") or 12)` |
| 기존 자동생성 판정 | `_should_auto_contract(pay)` — SAAS_PRODUCT_TYPES 한정 |
| 기존 계약 활성화 | `_activate_existing_contract` / `_extend_contract_for_renewal` |
| 기존 contract_no | `_gen_contract_no()` — CON-YYYYMMDD-XXXX |
| 기존 end_date | `_contract_end_date(start, period_months)` — relativedelta |

## 3. REUSE DECISION

| 재사용 항목 | 방식 |
|------------|------|
| `_create_contract_from_payment` | `_build_contract_row_from_payment` 위임으로 리팩터 |
| `_gen_contract_no` / `_contract_end_date` | 변경 없음 — V1 경로 그대로 |
| `build_standard_contract_storage_bundle_v2` | V2 adapter에서 호출 |
| `SaasContractStorageBundleV2` | 플랜 조립 결과에 포함 |

## 4. _PLAN_CODE_UNSET SENTINEL

```
_PLAN_CODE_UNSET = object()  # 동일성 비교 전용

plan_code_override is _PLAN_CODE_UNSET
  → True  (기본/V1): pay.plan_code or "INDUSTRY_PRO" 사용
  → False, override=None (V2): plan_code 행에 포함하지 않음
  → False, override=str   : 해당 값 직접 사용
```

V1 행동 변화 = 0 (`_create_contract_from_payment`는 UNSET 기본값으로 위임).

## 5. _build_contract_row_from_payment (EXTRACTED PURE BUILDER)

```
_build_contract_row_from_payment(pay, *, start, contract_no, plan_code_override=_PLAN_CODE_UNSET)
  → dict[str, Any]
```

| 역할 | 내용 |
|------|------|
| 순수성 | DB I/O = 0, supabase = 0 |
| plan_code | _PLAN_CODE_UNSET → V1 경로 / None → 키 미포함 / str → 직접 |
| period_months | pay.get("period_months") or 12 |
| quote_id | 있으면 포함, 없으면 생략 |
| now_iso() | created_at / updated_at / paid_at fallback 내부 호출 |
| 입력 mutate | 없음 |

## 6. _create_contract_from_payment REFACTORED

```python
def _create_contract_from_payment(sb, pay: dict) -> Optional[str]:
    start = business_today()
    row = _build_contract_row_from_payment(pay, start=start, contract_no=_gen_contract_no())
    ct_res = sb.table("contracts").insert(row).execute()
    ...
```

V1 계약 행 내용 = 0 변화 (plan_code, period_months, amounts, quote_id 동일).

## 7. SaasV2ApplyPlan (PURE DATACLASS)

```python
@dataclass
class SaasV2ApplyPlan:
    payment_id: str
    company_id: str
    contract_id: uuid.UUID       # 사전 생성 — atomic INSERT 동기화용
    contract_row: dict           # id 포함, contracts INSERT 직접 사용
    commercial_bundle: SaasContractStorageBundleV2
```

DB write = 0. 원자적 저장은 BE-OBJ10-C 책임.

## 8. build_saas_v2_payment_success_apply_plan STEPS (PATCH1 포함)

```
Step 1:  pay.status_code ∈ {PAID,SUCCESS}              → V2_PAYMENT_NOT_PAID
Step 2:  pay.plan_code is None                          → V2_LEGACY_PLAN_CODE_FORBIDDEN
Step 3:  pay.paid_at 존재                               → V2_PAID_AT_REQUIRED
Step 4:  pay.paid_at ISO timezone-aware 파싱            → V2_PAID_AT_INVALID
Step 5:  pay.user_id 존재                               → V2_USER_REQUIRED
Step 6:  pay.user_id UUID 검증                          → V2_USER_INVALID
Step 7:  pay.product_type == "SAAS"                     → PAY_NOT_SAAS_V2
Step 8:  pay.company_id 존재 + quote.company_id 일치    → PAY_NO_COMPANY_ID / PAY_QUOTE_COMPANY_MISMATCH
Step 9:  quote.source == "member_auto"                  → V2_QUOTE_SOURCE_INVALID
Step 10: quote.service_type == "SAAS"                   → V2_QUOTE_SERVICE_INVALID
Step 11: quote.status_code == "ISSUED"                  → QUOTE_NOT_ISSUED
Step 12: pay.quote_id 존재 + quote.id 일치              → PAY_NO_QUOTE_ID / PAY_QUOTE_ID_MISMATCH
Step 13: len(items) == 1 + quote_schema_version         → QUOTE_ITEM_COUNT_INVALID / QUOTE_NOT_V2
Step 14: SaasQuoteSnapshotItemV2.model_validate(item)   → QUOTE_ITEM_INVALID
Step 15: SaasPricingSnapshotV2.model_validate(snapshot) → QUOTE_SNAPSHOT_INVALID
Step 16: 금액 3중 정합성 (pay ↔ item ↔ snapshot)       → AMOUNT_SNAPSHOT_MISMATCH
Step 17: pay.period_months == snapshot.term_months      → PAY_PERIOD_TERM_MISMATCH
Step 18: contract_row 조립 (plan_code_override=None)
Step 19: Commercial Bundle 조립 (effective_from=paid_at_dt, created_by=user_uuid)
```

## 8a. PATCH1 — Payment Success Boundary

| Guard | Error Code |
|-------|-----------|
| status_code ∉ {PAID,SUCCESS} | V2_PAYMENT_NOT_PAID |
| plan_code is not None | V2_LEGACY_PLAN_CODE_FORBIDDEN |
| paid_at 없음 | V2_PAID_AT_REQUIRED |
| paid_at 파싱 실패 또는 naive | V2_PAID_AT_INVALID |
| user_id 없음 | V2_USER_REQUIRED |
| user_id 유효 UUID 아님 | V2_USER_INVALID |
| source != "member_auto" | V2_QUOTE_SOURCE_INVALID |
| service_type != "SAAS" | V2_QUOTE_SERVICE_INVALID |

## 8b. PATCH1 — paid_at → effective_from

```
기존 (WRONG):
  effective_from = datetime.combine(start, datetime.min.time())

수정 후 (CORRECT):
  paid_at_dt = _parse_paid_at(pay["paid_at"])   # timezone-aware 필수
  effective_from = paid_at_dt                    # 결제 성공 시각
```

Contract start_date 로직 = 변화 없음.

## 8c. PATCH1 — user_id → created_by

```
user_uuid = uuid.UUID(pay["user_id"])
build_standard_contract_storage_bundle_v2(..., created_by=user_uuid)
→ commercial_bundle.commercial_version.created_by == user_uuid
```

## 9. FROZEN SNAPSHOT → SaasPricingCalculationResult

```
_frozen_snapshot_to_calc_result(snap):
  status="READY"
  policy_version=snap.policy_version
  site_breakdown=None   (복원 불가 — bundle 조립에 불필요)
  worker_breakdown=snap.worker
  monthly_supply_amount=snap.monthly_supply_amount
  term_months=snap.term_months
  snapshot=snap         (SSOT)
  block_reason=None
```

Repricing = 0. add_vat = 0. price_master = 0.

## 10. AMOUNT AUTHORITY

| Payment 필드 | 출처 |
|-------------|------|
| contract_amount | pay.supply_amount (== snapshot.prepaid_supply_amount, Step 8 검증) |
| vat_amount | pay.vat_amount (== snapshot.vat_amount, Step 8 검증) |
| total_amount | pay.total_amount (== snapshot.total_amount, Step 8 검증) |
| end_date | start + relativedelta(months=snapshot.term_months) |

클라이언트 amount = 0. VAT 재계산 = 0.

## 11. V2 plan_code BOUNDARY

| 항목 | 값 |
|------|-----|
| V2 contract_row.plan_code | 미포함 (key absent) |
| plan_code_override | None (sentinel 구분) |
| SAAS_PRODUCT_TYPES 수정 | NOT_FOUND |
| _should_auto_contract V2 진입 | NOT_FOUND (product_type="SAAS" 비포함) |

## 12. PERIOD / TERM CONSISTENCY GUARD

```
pay.period_months == snapshot.term_months
불일치: PAY_PERIOD_TERM_MISMATCH
```

V2 prepare 단계에서 period_months=snap.term_months 설정됨.
추가 검증으로 drift 방지.

## 13. CONTRACT_ID PRE-GENERATION

```
contract_id = uuid.uuid4()
contract_row["id"] = str(contract_id)
commercial_bundle.commercial_version.contract_id = contract_id
```

atomic INSERT 시 contracts + commercial_versions 동일 UUID 참조 가능.

## 14. V1 BEHAVIOR PRESERVATION

```
_create_contract_from_payment(sb, pay):
  plan_code = (pay.plan_code or "INDUSTRY_PRO").upper() ← UNSET 기본값
  period_months = int(pay.period_months or 12)
  amounts = pay.supply/vat/total
  quote_id passthrough
  V1 행동 변화 = 0
```

B11-B15 (5개 회귀 테스트) PASS.

## 15. COMMERCIAL BUNDLE BOUNDARY

```
saas_contract_commercial_versions INSERT = 0
saas_contract_site_scopes INSERT          = 0
```

DDL 미적용 (BE-OBJ04 제안만). 원자적 저장은 BE-OBJ10-C 책임.

## 16. CONTRACT DB BOUNDARY

```
contracts INSERT   = 0  (플랜 조립만)
contracts UPDATE   = 0
payments UPDATE    = 0  (contract_id 연결 = BE-OBJ10-C 책임)
```

## 17. SUBSCRIPTION / BILLING BOUNDARY

```
subscriptions read/write = 0
billing_keys             = 0
```

BE-OBJ10-D 책임.

## 18. CHANGE ORDER / RENEWAL BOUNDARY

BE-OBJ10-C / BE-OBJ10-D 책임.

## 19. TEST RESULT

```
OBJ10-B 전체 (B01-B95): 95 PASS / 0 FAIL
```

포함 내용:
- B01-B10: `_build_contract_row_from_payment` 단위 (sentinel / plan_code / amounts / dates)
- B11-B15: `_create_contract_from_payment` V1 회귀
- B16-B25: `build_saas_v2_payment_success_apply_plan` quote/item/snapshot 검증 오류
- B26-B30: 금액 3중 정합성 (pay ↔ item ↔ snapshot)
- B31-B34: period_months / term_months 정합성
- B35-B50: contract_row 필드 계약
- B51-B60: SaasV2ApplyPlan 필드 계약
- B61-B70: commercial_bundle 필드 계약
- B71-B82: source guards (repricing 0 / DB write 0 / router 0)
- B83-B86: PATCH1-A payment status (PAID/SUCCESS only)
- B87-B88: PATCH1-B quote source (member_auto) / service (SAAS)
- B89: PATCH1-C legacy plan_code prohibition
- B90-B92: PATCH1-D paid_at required + parse + effective_from exact
- B93-B95: PATCH1-E user_id required + UUID + created_by exact

## 20. PRICING REGRESSION

```
Pricing V2 회귀: 627 PASS / 0 FAIL
  (test_saas_pricing_composer_v2 + test_saas_pricing_preview_v2 +
   test_saas_pricing_policy_v2 + test_saas_contract_commercial_v2 +
   test_saas_pricing_v2_contract + test_saas_quote_v2 +
   test_member_quotes + test_admin_quotes + test_member_quote_pdf)
```

## 21. PAYMENT REGRESSION

```
test_saas_payment_v2_adapter.py:          43 PASS
test_saas_payment_success_v2_adapter.py:  95 PASS  (PATCH1 후)
test_payment_svc.py:                       1 PASS / 1 FAIL (PRE-EXISTING)
test_payment.py:                           2 PASS
test_payment_helpers.py:                   4 PASS
test_payment_proof_type.py:               17 PASS
test_payment_current.py:                  11 PASS
test_payment_my_projection.py:             9 PASS
test_payment_my_tax_status.py:            11 PASS
test_payment_company_admin_bootstrap.py:  11 PASS

Payment 소계: 204 PASS / 1 PRE-EXISTING FAIL
```

PRE-EXISTING: `test_payment_svc.py::test_run_inicis_prepare_success_minimal::gopaymethod == "Card"`
→ 기존 코드 `""` 반환. 이번 작업과 무관.

## 22. SOURCE GUARDS

| 항목 | 결과 |
|------|------|
| `add_vat(` in Adapter | NOT_FOUND |
| `split_supply_vat(` in Adapter | NOT_FOUND |
| `* 0.1` in Adapter | NOT_FOUND |
| `price_master` in Adapter | NOT_FOUND |
| `pricing_resolver` in Adapter | NOT_FOUND |
| `"contracts"` write in Adapter | NOT_FOUND |
| `"saas_contract_commercial_versions"` in Adapter | NOT_FOUND |
| `"subscriptions"` in Adapter | NOT_FOUND |
| `routers` import in Adapter | NOT_FOUND |
| `get_supabase` in Adapter | NOT_FOUND |

## 23. PRODUCTION MUTATION

```
Production contracts INSERT = 0
Production contracts UPDATE = 0
Production payments UPDATE  = 0
Production DELETE           = 0
DDL                         = 0
```

FakeSupabase / dataclass 전용 검증.

## 24. FILES CHANGED

Modified (initial commit `b8f49f20`):
- `services/payment_post_process.py`
  - `_PLAN_CODE_UNSET = object()` sentinel 추가
  - `_build_contract_row_from_payment(pay, *, start, contract_no, plan_code_override)` 추출
  - `_create_contract_from_payment` 위임 구조로 변경 (V1 행동 변화 = 0)

Created (initial commit `b8f49f20`):
- `services/saas_payment_success_v2_adapter.py`
- `tests/test_saas_payment_success_v2_adapter.py`

Modified (PATCH1 commit `0689ddc7`):
- `services/saas_payment_success_v2_adapter.py`
  - 5개 Payment Success 경계 가드 추가 (Steps 1-6, 9-10)
  - `_parse_paid_at()` helper 추가
  - `effective_from = paid_at_dt` (결제 성공 시각 사용)
  - `created_by = user_uuid` mapper에 전달
- `tests/test_saas_payment_success_v2_adapter.py`
  - fixture `_valid_pay()` 보강 (status_code, user_id, plan_code)
  - fixture `_valid_quote()` 보강 (source, service_type)
  - B83-B95 (13개 신규 테스트) 추가

Created:
- `docs/2026-09-28_TAI_SAFE_PRICING_V2_BE_OBJ10B_EVIDENCE.md`

## 25. NOT_FOUND

- Contracts INSERT in V2 Adapter: NOT_FOUND
- Commercial Versions INSERT: NOT_FOUND
- Server Repricing in Adapter: NOT_FOUND
- Public endpoint 노출: NOT_FOUND
- SAAS_PRODUCT_TYPES 수정: NOT_FOUND
- Subscription / Billing write: NOT_FOUND

## 26. UNVERIFIED

- Production INICIS API 실 호출 (Fake Supabase 전용 검증)
- saas_contract_commercial_versions DDL 적용 후 실 INSERT (BE-OBJ10-C 책임)
- Atomic write (contracts + commercial_versions + payments.contract_id) (BE-OBJ10-C 책임)

## 27. GPT REVIEW REQUIRED
