---
title: "TAI Safe Pricing V2 BE-OBJ10-A Evidence"
work_order: WO-PRICING-V2-BE-OBJ10-A
objective: "Quote V2 → Existing INICIS Payment Adapter"
author: Claude Code
date: 2026-09-28
status: PASS
---

# TAI Safe Pricing V2 BE-OBJ10-A Evidence

## 1. EXECUTION ANCHOR

- Base commit: `de4a9a22`
- OBJ10-A commit: `129df126`
- Branch: `docs/pricing-canonical-20260927`

## 2. EXISTING PAYMENT PIPELINE OBSERVED

| 항목 | 값 |
|------|-----|
| 기존 단건결제 | `run_inicis_prepare(body: PrepareBody)` |
| 기존 DB INSERT | `supabase.table("payments").insert(row)` |
| 기존 SAAS 상품 타입 | `SAAS_CONSTRUCTION, SAAS_INDUSTRY, SAAS_FACILITY, SAAS_BUILDING` |
| 기존 금액 계산 | `add_vat(body.amount)` → supply + vat = total |
| 기존 서명 파라미터 | `order_id, timestamp, signature, verification, mKey` |
| 기존 POST-PROCESS | `on_payment_success_sync` (card/vbank success에서 호출) |
| 기존 Billing | `run_billing_prepare / run_billing_charge` |
| 기존 PrepareBody | `amount, product_type, user_id, goodname, ...` |

## 3. REUSE DECISION

| 재사용 항목 | 방식 |
|------------|------|
| `services/payment_svc.py` | 공통 core 추출 후 V1 위임 |
| `services/member_quote_svc.get_member_quote` | Adapter에서 직접 호출 |
| `services/payment_helpers.py` | 변경 없음. 기존 상수/유틸 활용 |
| `schemas/saas_pricing_v2.SaasPricingSnapshotV2` | Adapter에서 재검증 |
| `schemas/saas_quote_v2.SaasQuoteSnapshotItemV2` | Adapter에서 재검증 |

## 4. EXISTING RUN_INICIS_PREPARE REFACTOR

`run_inicis_prepare` → `_run_inicis_prepare_exact` 위임 구조:

```
run_inicis_prepare(body)
  body.product_type in SAAS_PRODUCT_TYPES → period_months 검증
  add_vat(body.amount) → supply / vat / total 계산
  _run_inicis_prepare_exact(supabase, sign_key, *, supply, vat, total, ...)
```

V1 행동 변화 = 0 (동일 amount 전달, 동일 row 구조, 동일 서명 파라미터).

## 5. EXACT AMOUNT PREPARE CORE

`_run_inicis_prepare_exact(supabase, sign_key, *, supply_amount, vat_amount, total_amount, ...)`:

| 역할 | 내용 |
|------|------|
| 금액 검증 | supply_amount >= 0, vat_amount >= 0, total_amount > 0, supply+vat == total |
| INICIS 서명 | order_id, timestamp, m_key, signature, verification |
| DB INSERT | payments 1건 |
| 금액 계산 | 없음 (입력값 그대로 사용) |

## 6. V2 QUOTE ADAPTER

`services/saas_payment_v2_adapter.py::prepare_saas_v2_payment_from_quote`:

```
Step 1: get_member_quote(supabase, quote_id)
Step 2: company_id 소유권 검증
Step 3: status_code == ISSUED
Step 4: service_type == SAAS
Step 5: len(items) == 1
Step 6: quote_schema_version == SAAS_QUOTE_V2
Step 7: SaasQuoteSnapshotItemV2.model_validate(item)
Step 8: SaasPricingSnapshotV2.model_validate(item.pricing_snapshot)
Step 9: quote/item/snapshot 금액 3중 정합성
Step 10: _run_inicis_prepare_exact(...)
```

## 7. QUOTE OWNERSHIP

```
quote.company_id == auth company_id (인증 컨텍스트)
```

클라이언트 company_id 입력 = 0.

## 8. V2 SNAPSHOT AUTHORITY

| Payment 필드 | 출처 |
|-------------|------|
| supply_amount | snapshot.prepaid_supply_amount |
| vat_amount | snapshot.vat_amount |
| total_amount | snapshot.total_amount |
| period_months | snapshot.term_months |
| goodname | item.display_name |

클라이언트 amount = 0. VAT 재계산 = 0.

## 9. AMOUNT CROSS VALIDATION

```
quote.supply_amount == item.supply_amount == snapshot.prepaid_supply_amount
quote.vat_amount    == item.vat_amount    == snapshot.vat_amount
quote.total_amount  == item.total_amount  == snapshot.total_amount
```

불일치: `QUOTE_PAYMENT_SNAPSHOT_INVALID` / payments INSERT = 0.

## 10. PRODUCT_TYPE / PLAN_CODE BOUNDARY

| 항목 | 값 |
|------|-----|
| internal product_type | `SAAS` |
| Public PrepareBody 허용 추가 | NOT_FOUND |
| SAAS_PRODUCT_TYPES 수정 | NOT_FOUND |
| plan_code | `None` |

`product_type=SAAS`는 V2 payment를 V1 `SAAS_INDUSTRY/BUILDING/CONSTRUCTION` 구조와 구분하기 위한 내부 식별자.

## 11. V1 BEHAVIOR PRESERVATION

```
run_inicis_prepare(body) 기존 동작:
  add_vat(body.amount) 유지
  supply = body.amount 유지
  quote_id / contract_id / plan_code / period_months / proof_type passthrough 유지
  gopaymethod = "" 유지 (PRE-EXISTING)
```

`test_payment_svc.py::test_run_inicis_prepare_success_minimal` gopaymethod 실패
= PRE-EXISTING (de4a9a22 이전부터 동일 실패, git stash로 확인).

## 12. RUNTIME WIRING

```
grep "prepare_saas_v2_payment_from_quote" routers/ services/ (adapter 제외)
= 0 match
```

Runtime endpoint = 0. Runtime consumer = 0.

## 13. CONTRACT BOUNDARY

```
contracts INSERT   = 0
contracts UPDATE   = 0
Commercial V2 접근 = 0
```

BE-OBJ10-B 책임.

## 14. SUBSCRIPTION BOUNDARY

```
subscriptions read/write = 0
billing_keys = 0
```

BE-OBJ10-D 책임.

## 15. CHANGE ORDER DEFERRED

BE-OBJ10-C에서 다룸.

## 16. RENEWAL DEFERRED

BE-OBJ10-D에서 다룸.

## 17. TEST RESULT

```
OBJ10-A 신규 (A01-A43): 43 PASS / 0 FAIL
```

포함 내용:
- A01-A10: V1 run_inicis_prepare regression (supply/vat/total/fields 유지)
- A11-A14: _run_inicis_prepare_exact 직접 테스트 (금액 검증, add_vat 호출 없음)
- A15-A19: Quote 조회/소유권/상태/서비스타입
- A20-A24: V2 Quote schema version / item 검증
- A25-A28: 금액 3중 정합성
- A29-A38: 정상 V2 준비 필드 계약
- A39-A43: Source guard (VAT 공식 0, pricing engine 0, contracts 0, runtime consumer 0)

## 18. PRICING REGRESSION

```
Pricing V2 회귀 (8 파일): 508 PASS / 0 FAIL
OBJ09 포함 전체 Pricing: 605 PASS / 0 FAIL
```

## 19. QUOTE REGRESSION

```
test_member_quotes.py + test_admin_quotes.py + test_member_quote_pdf.py:
206 PASS / 0 FAIL
```

## 20. PAYMENT REGRESSION

```
test_payment_svc.py:                    1 PASS / 1 FAIL (PRE-EXISTING)
test_payment.py:                        2 PASS
test_payment_helpers.py:                4 PASS
test_payment_proof_type.py:            17 PASS
test_payment_current.py:               11 PASS
test_payment_my_projection.py:          9 PASS
test_payment_my_tax_status.py:         11 PASS
test_payment_company_admin_bootstrap.py: 11 PASS

Payment 소계: 66 PASS / 1 PRE-EXISTING FAIL
```

PRE-EXISTING 실패: `test_run_inicis_prepare_success_minimal::gopaymethod == "Card"`
→ 기존 코드가 `""` 반환. 이번 작업과 무관. git stash 검증으로 확인.

## 21. SOURCE GUARDS

| 항목 | 결과 |
|------|------|
| `add_vat(` in Adapter | NOT_FOUND |
| `split_supply_vat(` in Adapter | NOT_FOUND |
| `* 0.1` in Adapter | NOT_FOUND |
| pricing_resolver in Adapter | NOT_FOUND |
| pricing_composer in Adapter | NOT_FOUND |
| `price_master` in Adapter | NOT_FOUND |
| `"contracts"` write in Adapter | NOT_FOUND |
| `"subscriptions"` write in Adapter | NOT_FOUND |
| routers에서 adapter import | NOT_FOUND |
| Public PrepareBody에 SAAS 추가 | NOT_FOUND |

## 22. PRODUCTION MUTATION

```
Production payments INSERT = 0
Production UPDATE          = 0
Production DELETE          = 0
DDL                        = 0
```

FakeSupabase / MagicMock 전용 검증.

## 23. FILES CHANGED

Created:
- `services/saas_payment_v2_adapter.py`
- `tests/test_saas_payment_v2_adapter.py`
- `docs/2026-09-28_TAI_SAFE_PRICING_V2_BE_OBJ10A_EVIDENCE.md`

Modified:
- `services/payment_svc.py` (공통 INICIS prepare core `_run_inicis_prepare_exact` 추출, `run_inicis_prepare` 위임 구조로 변경)

## 24. NOT_FOUND

- Public endpoint `POST /payments/saas-v2/prepare`: NOT_FOUND (Runtime 0)
- SAAS_PRODUCT_TYPES에 "SAAS" 추가: NOT_FOUND
- Commercial V2 테이블 접근: NOT_FOUND
- Contract INSERT: NOT_FOUND
- Server Repricing in Adapter: NOT_FOUND

## 25. UNVERIFIED

- Production INICIS API 실 호출 (Fake Supabase 전용 검증)
- BE-OBJ10-B DDL 적용 후 Commercial V2 연결 (10-B 책임)

## 26. GPT REVIEW REQUIRED
