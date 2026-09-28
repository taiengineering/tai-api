---
title: TAI Safe Pricing V3 — BE-OBJ01 Backend Impact Inventory
kind: inventory
status: REVIEW_REQUIRED
date: 2026-09-28
branch: docs/pricing-canonical-20260927
policy_head: 6e34a0cc42a76832c6c415e17b55195e66d20a6b
---

# TAI Safe Pricing V3 — BE-OBJ01 Backend Impact Inventory

**WO**: WO-BE-V3-OBJ01-BACKEND-IMPACT-INVENTORY-001
**Date**: 2026-09-28
**Branch**: `docs/pricing-canonical-20260927`
**Policy SSOT**: `docs/2026-09-28_TAI_SAFE_PRICING_V3_POLICY_RECANONICAL.md` (V3-FROZEN)

> **이 문서는 REVIEW_REQUIRED 상태다. GPT 독립검증 전 APPROVED 불가.**

---

## 1. 조사 범위 및 방법

코드 수정 없이 다음 파일을 직접 읽고, grep 결과로 교차검증했다.

**소스 파일 직접 조사:**
- `schemas/saas_pricing_v2.py`
- `schemas/saas_pricing_policy_v2.py`
- `services/saas_pricing_composer_v2.py`
- `schemas/saas_pricing_preview_v2.py`
- `services/saas_pricing_preview_v2.py`
- `services/pricing_resolver_svc.py`
- `services/saas_payment_v2_adapter.py`
- `services/saas_payment_success_v2_adapter.py`
- `schemas/saas_contract_commercial_v2.py`
- `services/saas_renewal_v2_adapter.py` (lines 1~120, 340~420)
- `services/payment_post_process.py` (lines 55~170)
- `services/saas_quote_v2.py` (lines 1~80)
- `migrations/2026-09-28_saas_contract_commercial_v2_atomic_apply.sql` (grep)
- `migrations/2026-09-28_saas_contract_commercial_v2_renewal_atomic_apply.sql` (grep)
- `tests/test_pricing_resolver_saas_boundary.py` (price_master 구조 확인용)

**전수 grep:**
- `term_months` — 전체 `.py` + `.sql` (runtime hit 목록 수집)
- `field_uplift` + `100000` — pricing-relevant hit 분리
- `period_months` — 전체
- `VALID_TERM_MONTHS`, `pricing_snapshot`, `SaasPricingSnapshotV2`, `SaasCommercialSelection`
- `INDUSTRY_PRO`, `INDUSTRY_CUSTOM`, `INDUSTRY_STARTER`, `INDUSTRY_BUSINESS`
- `price_master INSERT` — seed 없음 확인

**테스트 실행**: NOT RUN (Investigation 단계)

---

## 2. V3 정책 변경 요약 (조사 기준)

| 축 | V2 현재 | V3 확정 |
|----|---------|---------|
| FIELD 가격 모델 | `base_amount + field_uplift_amount(100,000)` | 249,000원 고정 (섹터·규모 무관) |
| MANAGER INDUSTRY 상한 | 300~499 → INDUSTRY_PRO, 500+ → INDUSTRY_CUSTOM(0) | 300+ → INDUSTRY_PRO(499,000), 상한 없음 |
| 할인 키 이름 | `term_months` (결제·계약 혼용) | `payment_months` (할인 기준만) |
| 할인율 | 전부 None (UNRESOLVED) | 1=0% / 3=5% / 6=10% / 9=15% / 12=20% |
| payment_months ↔ end_date | 암묵 연결 (pay.period_months → contract.end_date) | UNRESOLVED (OBJ05 결정) |

---

## 3. 핵심 충돌 발견 — CRITICAL FINDINGS

### 3-A. SAAS INDUSTRY price_master 구조 — V3 CONFLICT

`tests/test_pricing_resolver_saas_boundary.py` lines 11–14 (price_master 구조 반영):

```python
_SAAS_INDUSTRY = [
    {"tier_code": "INDUSTRY_STARTER",  "criteria_min": 0,   "criteria_max": 49,  "amount": 149000},
    {"tier_code": "INDUSTRY_BUSINESS", "criteria_min": 50,  "criteria_max": 299, "amount": 299000},
    {"tier_code": "INDUSTRY_PRO",      "criteria_min": 300, "criteria_max": 499, "amount": 499000},
    {"tier_code": "INDUSTRY_CUSTOM",   "criteria_min": 500, "criteria_max": None,"amount": 0     },
]
```

**V3 충돌 2건:**

1. `INDUSTRY_PRO.criteria_max = 499` → V3: `300+ → INDUSTRY_PRO`이므로 criteria_max = NULL이어야 함
2. `INDUSTRY_CUSTOM: 500+, amount=0` → V3: CUSTOM은 규모 Band 아님. 500인 이상이라도 MANAGER INDUSTRY_PRO = 499,000원

현재 MANAGER INDUSTRY 500인 이상 Preview → INDUSTRY_CUSTOM row → `amount=0` → Composer에서 `base_amount=0` → validation 실패 또는 가격 오류.

### 3-B. FIELD 가격 계산 — V3 CONFLICT (Major)

`services/saas_pricing_composer_v2.py` line 204:

```python
if selection.product_tier == "MANAGER":
    normal = s.base_amount        # MANAGER: Compliance Base 그대로
else:                             # FIELD: base_amount + field_uplift_amount
    normal = s.base_amount + policy.field_uplift_amount
```

`schemas/saas_pricing_policy_v2.py` line 219 (canonical factory):
```python
field_uplift_amount=100000,
```

**현재 FIELD 가격 (site에 따라 다름):**
| 사업장 유형 | base_amount | current normal | V3 정책 |
|-------------|-------------|----------------|---------|
| INDUSTRY ≤49 | 149,000 | 249,000 ✓ | 249,000 |
| INDUSTRY 50~299 | 299,000 | 399,000 ✗ | 249,000 |
| INDUSTRY 300~499 | 499,000 | 599,000 ✗ | 249,000 |
| BUILDING ≤5,000㎡ | 149,000 | 249,000 ✓ (우연 일치) | 249,000 |
| BUILDING >5,000㎡ | 349,000 | 449,000 ✗ | 249,000 |
| CONSTRUCTION <50억 | 249,000 | 349,000 ✗ | 249,000 |
| CONSTRUCTION ≥50억 | 499,000 | 599,000 ✗ | 249,000 |

V3에서 FIELD Base는 249,000 고정이므로 uplift 모델 전체가 교체 대상이다.

또한: Preview 서비스가 FIELD 사업장에도 `resolve_plan("SAAS", sector, criteria_value)`를 호출한다 (`services/saas_pricing_preview_v2.py` line 90). V3에서 FIELD 가격은 Resolver 결과에 의존하지 않는다. 단, `base_band_code` (계약 scope 증거)는 여전히 필요할 수 있으므로 resolver 호출 자체를 제거하는 것과 호출 결과를 가격 계산에서 무시하는 것을 구분해야 한다.

### 3-C. term_discounts — 전부 None (Block Condition)

`schemas/saas_pricing_policy_v2.py` lines 231–235 (canonical factory):
```python
SaasTermDiscountPolicy(term_months=1,  discount_rate_bps=None),
SaasTermDiscountPolicy(term_months=3,  discount_rate_bps=None),
SaasTermDiscountPolicy(term_months=6,  discount_rate_bps=None),
SaasTermDiscountPolicy(term_months=9,  discount_rate_bps=None),
SaasTermDiscountPolicy(term_months=12, discount_rate_bps=None),
```

Composer Step 12: None → `TERM_DISCOUNT_UNRESOLVED` 반환 → Snapshot 생성 불가.

**현재 상태**: 모든 V2 Preview가 `TERM_DISCOUNT_UNRESOLVED`를 반환한다.
V3는 할인율을 확정했으므로 Policy 객체에 실제 값을 넣어야 Quote/Payment까지 진행할 수 있다.

### 3-D. term_months — 결제/계약 의미 혼용 (Semantic Coupling)

`term_months`가 다음 위치에서 동시에 사용된다:

| 파일 | 위치 | 현재 의미 |
|------|------|----------|
| `schemas/saas_pricing_v2.py:46` | `SaasCommercialSelection.term_months` | 결제월수 선택 |
| `schemas/saas_pricing_v2.py:175` | `SaasPricingSnapshotV2.term_months` | 스냅샷 고정 결제월수 |
| `schemas/saas_pricing_policy_v2.py:66` | `SaasTermDiscountPolicy.term_months` | 할인율 조회 키 |
| `services/saas_pricing_composer_v2.py:253` | `raw_prepaid = monthly × term_months` | 선불 금액 계산 |
| `services/saas_payment_v2_adapter.py:160` | `period_months=snap.term_months` | payments 행 저장 |
| `services/saas_payment_success_v2_adapter.py:284` | `pay.period_months == snap.term_months` | 정합성 검증 |
| `schemas/saas_contract_commercial_v2.py:87` | `term_months` DB 컬럼 | 계약 commercial version 저장 |
| `migrations/…atomic_apply.sql:499` | `(cv->>'term_months')::integer` | SQL 3-way 검증 |
| `migrations/…renewal_atomic_apply.sql:342` | `3-way: snap == cv == pay.period_months` | Renewal SQL 검증 |
| `services/payment_post_process.py:101,161` | `end_date = start + period_months` | **contract.end_date 계산** |
| `services/payment_post_process.py:117` | `_extend_contract_for_renewal: +period_months` | **Renewal end_date 연장** |
| `services/saas_change_order_v2.py:261,262` | `from_term_months / to_term_months` | Change Order 비교 |
| `services/saas_contract_storage_mapper_v2.py:73,114` | `term_months=selection.term_months` | Commercial Version 조립 |

**CRITICAL**: `payment_post_process.py` lines 101–105, 117–120에서 `period_months`가 `contracts.end_date`를 직접 계산한다. 이것이 V3에서 UNRESOLVED인 `payment_months ↔ contract.end_date` coupling의 실제 코드 위치다.

---

## 4. Price Resolver Special Audit

| 질문 | 실측 결과 |
|------|---------|
| **Q1. FIELD도 현재 SAAS Compliance Base resolve를 거치는가?** | YES. `services/saas_pricing_preview_v2.py:90`: `_call_resolver(supabase, site.sector, site.criteria_value)` — MANAGER/FIELD 모두 동일 경로 |
| **Q2. FIELD 정상가격 계산 전에 base_amount가 필수인가?** | YES (현재). Composer line 204: `normal = s.base_amount + policy.field_uplift_amount`. V3에서는 불필요 (249,000 고정) |
| **Q3. FIELD에 산업 500+를 넣으면 어떤 tier/status가 되는가?** | INDUSTRY_CUSTOM row → `amount=0` → Preview Step 207 `has_quote_required=True` → `COMPLIANCE_BASE_QUOTE_REQUIRED` 반환. Composer 도달 불가. |
| **Q4. MANAGER 산업 500+는 현재 어떤 tier/status가 되는가?** | 동일: INDUSTRY_CUSTOM(amount=0) → `COMPLIANCE_BASE_QUOTE_REQUIRED`. V3: 499,000이어야 함 |
| **Q5. V3 요구 300+=499,000을 위해 DIAGNOSIS range rule 재사용 가능한가?** | price_master에 DIAGNOSIS INDUSTRY rows 존재 여부 미확인(read-only). Resolver 로직 자체는 재사용 가능(서비스 코드 변경 없음). price_master DATA에서 SAAS INDUSTRY rows 수정이 필요한 경우 DDL이 아닌 데이터 변경 WO 필요. |
| **Q6. DIAGNOSIS row를 SAAS 계약가격 SSOT로 사용하는 것과 range rule만 재사용하는 것의 구분** | 현재 SAAS용 price_master rows(`service_type=SAAS`)가 별도 존재. range rule 재사용 = SAAS rows의 criteria_max 수정. DIAGNOSIS rows 직접 사용 = 별도 service_type 조회 경로 추가 → 설계 변경 대상. 이번 단계에서 방식 확정 금지. |
| **Q7. price_master 변경 vs 별도 V3 resolver vs policy-local band table** | 대안 3가지. 이번 단계에서 선택 금지. OBJ02/OBJ03 이후 OBJ04에서 결정. |

---

## 5. term_months Semantic Audit — 주요 hit 분류

| PATH | SYMBOL | USED FOR PRICE? | USED FOR DISCOUNT? | USED FOR PAYMENT PERIOD? | USED FOR CONTRACT DATES? | PERSISTED? | V3 CONFLICT | DISPOSITION CANDIDATE |
|------|--------|-----------------|-------------------|--------------------------|--------------------------|-----------:|-------------|----------------------|
| `schemas/saas_pricing_v2.py:46` | `SaasCommercialSelection.term_months` | YES (multiplier) | YES | NO | NO | NO | RENAME | `payment_months` successor |
| `schemas/saas_pricing_v2.py:175` | `SaasPricingSnapshotV2.term_months` | YES | YES | YES (→ period_months) | NO | YES (JSON) | RENAME | new schema version |
| `schemas/saas_pricing_policy_v2.py:66` | `SaasTermDiscountPolicy.term_months` | NO | YES (key) | NO | NO | NO | RENAME | `payment_months` |
| `schemas/saas_pricing_preview_v2.py:63` | request `term_months` | NO | YES | NO | NO | NO | RENAME | API 필드명 변경 |
| `schemas/saas_contract_commercial_v2.py:87` | DB column `term_months` | NO | NO | YES | PARTIAL (3-way) | YES (DB) | UNVERIFIED | OBJ05 결정 |
| `migrations/…atomic_apply.sql:32` | DDL `term_months` column | NO | NO | YES | YES (3-way guard) | YES (DDL) | UNVERIFIED | OBJ05 결정 (new migration) |
| `migrations/…renewal_atomic.sql:342` | 3-way `snap == cv == pay.period_months` | NO | NO | YES | YES | YES | UNVERIFIED | OBJ05 결정 |
| `services/payment_post_process.py:101,161` | `period_months → end_date` | NO | NO | NO | **YES (직접)** | NO | **UNRESOLVED** | OBJ05 결정 필수 |

---

## 6. FIELD Pricing Audit — Chain별 현황

| 단계 | 현재 요구 값 | V3 필요 여부 | 비고 |
|------|------------|-------------|------|
| Request | `sector + criteria_value` (site 입력) | 필요 (scope 증거) | 가격 계산 외 목적으로 유지 |
| Preview Resolver 호출 | `resolve_plan("SAAS", sector, value)` | 불필요 (가격), 필요 (base_band_code 확보 여부 TBD) | FIELD는 base_amount 불필요 |
| Preview → Composer input | `base_amount` 필수 (`SaasSitePricingInput`) | **불필요** (V3: 249,000 고정) | `SaasSitePricingInput` 인터페이스 변경 필요 |
| Composer FIELD | `normal = base_amount + field_uplift_amount` | 교체 필요: `normal = FIELD_BASE_AMOUNT` | |
| Snapshot `base_amount` | 저장됨 (`SaasSiteScope.base_amount`) | V3에서 의미 변화 (사업장 Compliance Base → no longer price SSOT) | scope 증거 보존 필요 여부 TBD |
| Quote | `term_months` + 금액 freeze | 동일 구조 유지 가능 (명칭 rename) | |
| Payment Prepare | `period_months = snap.term_months` | 동일 값 (결제월수) 전달 | OBJ05 결정 전 변경 없음 |
| Contract Commercial Version | `term_months` 저장 | OBJ05 결정 후 | rename 또는 new column |
| Renewal | `period_months = snap.term_months` | OBJ05 결정 후 | |

---

## 7. MANAGER Range Audit

| 범위 | V2 현재 | V3 요구 | 충돌 |
|------|---------|---------|------|
| ≤49 | INDUSTRY_STARTER (149,000) | ≤49 = 149,000 ✓ | 없음 |
| 50~299 | INDUSTRY_BUSINESS (299,000) | 50~299 = 299,000 ✓ | 없음 |
| 300~499 | INDUSTRY_PRO (499,000) | 300+ = 499,000 — but criteria_max=499 ✗ | CONFLICT |
| 500+ | INDUSTRY_CUSTOM (0) | 300+ = 499,000 (PRO) ✗ | CONFLICT |

price_master에서 SAAS INDUSTRY rows:
- `INDUSTRY_PRO.criteria_max`: 499 → NULL로 변경 필요
- `INDUSTRY_CUSTOM` (500+, amount=0) row: V3에서 MANAGER 500+ = INDUSTRY_PRO. CUSTOM row 처리 방식 TBD (data UPDATE or deactivate)

이 변경은 DDL이 아닌 **price_master 데이터 변경**이다. Production mutation — 별도 WO 필요.

---

## 8. Snapshot / Backward Compatibility

**기존 V2 Frozen Snapshot 보존 원칙**: 이미 존재하는 V2 상태의 quotes/contracts의 `pricing_snapshot`은 V3 정책 때문에 재해석하거나 변조하면 안 된다.

| 질문 | 판정 |
|------|------|
| V3 snapshot을 V2 schema에 넣으면 semantic ambiguity가 생기는가? | YES. V3에서 `term_months`는 `payment_months`를 의미하며 `contract_term`과 분리됨. V2 schema의 `term_months` column은 이 분리를 표현할 수 없음. |
| 기존 V2 snapshot read compatibility 유지하면서 V3 schema successor가 필요한가? | YES. V3 Snapshot은 `schema_version: SAAS_PRICING_V3`로 별도 발행 권장. V2 `SAAS_PRICING_V2` 스냅샷은 read-only 보존. |
| snapshot parser / quote parser / payment parser | 현재 `SaasPricingSnapshotV2.model_validate()` 사용. V3는 V3 schema validator 필요. |
| renewal replay path | `snap.term_months`을 `effective_from` 계산에 사용. OBJ05에서 의미 분리 후 replay path 재검토 필요. |

---

## 9. Payment / Renewal Atomicity Guard

V2 invariant: `ONE PAYMENT = EXACTLY ONE CONTRACT MUTATION PATH` — 이 invariant는 V3에서도 반드시 유지된다.

| 영역 | V3 impact | 판정 |
|------|-----------|------|
| new contract atomic (OBJ10-C SQL) | `term_months` column. OBJ05가 rename or new column 결정 → migration 필요 | UNVERIFIED |
| renewal atomic (OBJ10-D-B2 SQL) | 3-way `snap.term_months == cv.term_months == pay.period_months`. V3 semantic split 후 이 3-way가 의미적으로 여전히 correct한지 검증 필요 | UNVERIFIED |
| replay idempotency | `target.effective_from` 기준 → payment_months와 무관 | PRESERVE |
| race recovery | max 2 atomic RPC — payment_months 변경 영향 없음 | PRESERVE |
| atomic invariant structure | 구조 자체는 V3와 무관 | PRESERVE |

결론: **payment_months semantic split 때문에 atomic 구조 자체는 변경 불필요. payload field(`term_months` column) rename or successor가 OBJ05에서 결정된다.**

---

## 10. Classification Matrix

| Object | V3 Conflict | Classification | Evidence | Reason |
|--------|-------------|----------------|----------|--------|
| **Pricing Schema** (`saas_pricing_v2.py`) | `term_months` = payment_months만, but 이름 혼용 | REOPEN | lines 46,175 | semantic rename 필요 |
| **Pricing Policy** (`saas_pricing_policy_v2.py`) | `field_uplift_amount=100000` (uplift model); `term_discounts` all None | **SUCCESSOR REQUIRED** | lines 204, 219, 231-235 | FIELD 가격 모델 근본 변경; V2 canonical factory 보존 + V3 factory 신규 |
| **Pricing Composer** (`saas_pricing_composer_v2.py`) | FIELD: `normal = base_amount + uplift` | REOPEN | line 204 | FIELD 계산식 교체 |
| **Preview Request Schema** (`saas_pricing_preview_v2.py`) | `term_months` 필드명 | REOPEN | line 63 | API 필드명 rename |
| **Preview Service** (`saas_pricing_preview_v2.py`) | FIELD도 SAAS resolver 경유 | REOPEN | line 90 | FIELD resolver 경로 재설계 |
| **Price Resolver** (`pricing_resolver_svc.py`) | resolve_plan 로직 자체는 sound | PRESERVE | lines 47-85 | 로직 변경 없음 |
| **price_master DATA** (DB rows) | INDUSTRY_PRO criteria_max=499; INDUSTRY_CUSTOM amount=0 | REOPEN (data) | test lines 13-14 | price_master UPDATE WO 필요 |
| **Quote Issue Request Schema** (`saas_quote_v2.py`) | `term_months` 필드명 | REOPEN | line 76 | rename |
| **Quote Snapshot Item Schema** | `term_months` in frozen item | REOPEN | — | new schema version |
| **Quote Service** (`saas_quote_v2.py`) | calls preview → snapshot; Preview fix 후 동작 가능 | REOPEN (indirect) | line 74 | Preview 의존 |
| **Payment Adapter OBJ10-A** (`saas_payment_v2_adapter.py`) | `period_months=snap.term_months` — 결제월수 전달 구조 sound | PRESERVE | line 160 | 로직 유효 |
| **Payment Success Adapter OBJ10-B** (`saas_payment_success_v2_adapter.py`) | `pay.period_months == snap.term_months` 정합성 검증 sound | PRESERVE | line 284 | 로직 유효 |
| **Commercial Version Schema** (`saas_contract_commercial_v2.py`) | `term_months` column — OBJ05 결정 후 rename/new column | UNVERIFIED | line 87 | OBJ05 선행 필요 |
| **Contract Builder** (`payment_post_process.py`) | `end_date = start + period_months` — payment_months↔end_date 직접 coupling | UNVERIFIED | lines 101,161 | OBJ05 결정 필수 |
| **Site Scope Persistence** | `base_band_code` FIELD에도 저장 — scope 증거 역할 유지 | PRESERVE | `saas_contract_commercial_v2.py:61` | FIELD scope 식별에 필요 |
| **Contract Storage Mapper** (`saas_contract_storage_mapper_v2.py`) | `term_months=selection.term_months` | REOPEN | lines 73,114 | rename 연쇄 |
| **Change Order** (`saas_change_order_v2.py`) | `from_term_months / to_term_months` | REOPEN | lines 261-262 | rename 연쇄 |
| **Atomic New Contract SQL OBJ10-C** | `term_months` DDL column + check constraint | UNVERIFIED | migration lines 32,57-58 | OBJ05 → new migration 필요 |
| **Renewal Adapter OBJ10-D-A** (`saas_renewal_v2_adapter.py`) | `period_months=snap.term_months` for renewal prepare | UNVERIFIED | line 358 | OBJ05 결정 후 |
| **Renewal Temporal Logic D-B1** | `contract_end_date_to_effective_at_v2` — end_date ↔ payment_months | UNVERIFIED | (별도 파일) | OBJ05 결정 후 |
| **Atomic Renewal SQL D-B2** | 3-way: `snap.term_months == cv.term_months == pay.period_months` | UNVERIFIED | migration line 342 | OBJ05 결정 후 |
| **Runtime Wiring D-B3** (`saas_renewal_runtime_v2.py`) | V2/Legacy 분기만. 가격 로직 없음 | PRESERVE | source read | 분기 로직 sound |
| **Legacy V1 Quote** (`member_quote_svc.py`, `admin_quote_svc.py`) | V1 contract type, 별도 경로 | UNRELATED | — | V3 SaaS와 무관 |
| **Frontend-facing API** (`routers/public_pricing_v2.py`) | Preview 결과 반환 | REOPEN (indirect) | — | Preview fix 후 update |
| **Tests (pricing, preview, quote, payment, commercial, renewal)** | 전부 uplift model / None discount / 300-499 range 기반 | REOPEN | test files | 핵심 fix 후 전면 갱신 |

---

## 11. Dependency Graph (실제 코드 기준)

```
Public Preview Request (term_months)
  ↓
Preview Service
  ↓ resolve_plan("SAAS", sector, value) ← MANAGER/FIELD 공통 (V3 FIELD는 분기 필요)
Price Resolver → price_master
  ↓
  base_band_code + base_amount → SaasSitePricingInput
  ↓
Pricing Composer
  MANAGER: normal = base_amount
  FIELD:   normal = base_amount + field_uplift_amount  ← V3 REOPEN
  term_months → raw_prepaid = monthly × term_months
  term_months → discount lookup → READY/TERM_DISCOUNT_UNRESOLVED
  ↓
SaasPricingSnapshotV2 (term_months frozen)
  ↓
Quote Service (Preview 재실행 → snapshot freeze)
  ↓ snap.term_months
Quote Frozen Item
  ↓
Payment Adapter OBJ10-A
  period_months = snap.term_months → payments row
  ↓
Payment Success Adapter OBJ10-B
  pay.period_months == snap.term_months (검증)
  ↓
Contract Builder (payment_post_process)
  end_date = start + period_months  ← UNRESOLVED coupling
  ↓
Atomic Contract Apply OBJ10-C (SQL)
  term_months column + 3-way check
  ↓
[Contract Active]

Renewal path:
Quote → Payment
  period_months = snap.term_months
  ↓
Renewal Adapter D-A
  ↓
Temporal Logic D-B1 (end_date → effective_from)
  ↓
Atomic Renewal D-B2 (3-way: snap == cv == pay.period_months)
  ↓
Runtime Branch D-B3 → apply_saas_v2_renewal_runtime
```

---

## 12. Required Decision Output

### A. V3 Pricing Core — REOPEN 필수

1. **Pricing Policy** (SUCCESSOR REQUIRED)
   - `field_uplift_amount` 제거 → `field_base_amount=249000` 추가
   - `term_discounts` 전부 `None` → 실제 값 (0/500/1000/1500/2000 bps) 채움
   - `PRICING_POLICY_VERSION` 새 버전 문자열

2. **Pricing Composer** (REOPEN)
   - FIELD 계산: `normal = policy.field_base_amount` (not `base_amount + uplift`)

3. **price_master DATA** (별도 Data WO)
   - `SAAS INDUSTRY INDUSTRY_PRO.criteria_max = 499 → NULL`
   - `SAAS INDUSTRY INDUSTRY_CUSTOM` row 처리 (deactivate or amount update)

### B. Quote까지 영향받는 것

- Preview Request Schema (`term_months` rename)
- Preview Service (FIELD resolver path 재설계)
- Quote Service (Preview 의존)
- Quote Snapshot Item Schema (new schema version)
- Quote → `saas_contract_storage_mapper_v2.py` (term_months 연쇄)

### C. Payment까지 영향받는 것

- Payment Adapter OBJ10-A (`period_months=snap.term_months`): 로직은 PRESERVE, 필드명 rename 연쇄에 따라 영향
- Payment Success Adapter OBJ10-B: 동일 (PRESERVE logic, rename 연쇄)

### D. Contract Persistence까지 영향받는 것

- `payment_post_process.py` `end_date = start + period_months` — OBJ05 결정 후
- `saas_contract_commercial_v2.py` `term_months` column — OBJ05 후 new migration
- Atomic SQL OBJ10-C — OBJ05 후

### E. Renewal까지 영향받는 것

- OBJ10-D-A, D-B1, D-B2 전체 — OBJ05 결정 후
- D-B3 Runtime Wiring — PRESERVE (영향 없음)

### F. 기존 Frozen Object 중 실제 보존 가능한 것

| Object | 판정 | 이유 |
|--------|------|------|
| `pricing_resolver_svc.py` (로직) | PRESERVE | resolve_plan 로직 sound; price_master data만 변경 |
| `saas_payment_v2_adapter.py` (OBJ10-A) | PRESERVE | period_months = payment_months 전달 구조 correct |
| `saas_payment_success_v2_adapter.py` (OBJ10-B) | PRESERVE | 금액 3중 정합성 + period_months 검증 구조 sound |
| `saas_contract_commercial_v2.py` site_scopes | PRESERVE | base_band_code scope 보존 구조 sound |
| `saas_renewal_runtime_v2.py` (D-B3) | PRESERVE | V2/Legacy 분기 로직 sound |
| Atomic replay/race recovery 구조 | PRESERVE | effective_from 기준 — payment_months와 무관 |

### G. BE-V3-OBJ02 이후 최소 작업 Object 순서

```
OBJ02  — Pricing Policy V3 Successor
         field_base_amount=249000 / discount rates 확정 / new policy_version

OBJ03  — Pricing Composer REOPEN
         FIELD: normal = policy.field_base_amount
         (price_master resolve 의존 제거 or FIELD base 고정 분기)

OBJ-PM — price_master Data WO (별도)
         INDUSTRY_PRO criteria_max → NULL
         INDUSTRY_CUSTOM row 처리

OBJ04  — Preview + Snapshot REOPEN
         FIELD resolver 경로 재설계
         Schema version: SAAS_PRICING_V3 (SAAS_PRICING_V2 보존)
         term_months → payment_months rename

OBJ05  — Payment / Contract Temporal Semantic Split
         payment_months vs contract.end_date 관계 확정
         _build_contract_row_from_payment end_date 계산 방식
         saas_contract_commercial_v2 schema (new migration if rename needed)
         Atomic SQL 3-way guard 재검토

OBJ06  — Renewal Re-Freeze (D-A, D-B1, D-B2 재검토, OBJ05 이후)

REFREEZE — 전체 회귀 + GPT 독립검증 + Backend FROZEN
```

---

## 13. 조사 결과 요약

```
RUNTIME term_months HITS  = 48개 (runtime 파일 기준)
FIELD PRICING CONFLICTS   = 5개 (INDUSTRY 50-299, 300-499, BUILDING 5000+, CONSTRUCTION 49억, 50억+)
INDUSTRY_PRO RANGE        = 300~499 (V3 요구: 300+ 상한 없음)
INDUSTRY_CUSTOM 500+      = amount=0 (V3 요구: 500+ → INDUSTRY_PRO = 499,000)
term_discount_rate_bps    = 전부 None (V3 요구: 0/500/1000/1500/2000 bps)

PRICE RESOLVER
  FIELD current resolution  = resolve_plan("SAAS", sector, value) (MANAGER와 동일)
  MANAGER 500+ resolution   = INDUSTRY_CUSTOM → amount=0 → COMPLIANCE_BASE_QUOTE_REQUIRED
  V3 conflict               = FIELD 가격 계산 불필요 / MANAGER 500+ → INDUSTRY_PRO 필요

SUCCESSOR REQUIRED  = 1  (Pricing Policy)
REOPEN              = 11 (Schema×4, Composer, Preview Request, Preview Service,
                          Quote, Storage Mapper, Change Order, Tests)
PRESERVE            = 7  (Resolver Logic, OBJ10-A, OBJ10-B, Site Scope, D-B3, Replay, Atomicity)
UNVERIFIED          = 7  (Commercial Version Schema, Contract Builder, OBJ10-C SQL,
                          D-A, D-B1, D-B2, price_master data WO 이후)
UNRELATED           = 2  (Legacy V1 Quote, Admin Quote)

PROPOSED OBJECT ORDER
  OBJ02 Policy Successor
  OBJ03 Composer REOPEN
  OBJ-PM price_master Data
  OBJ04 Preview + Snapshot
  OBJ05 Temporal Semantic Split
  OBJ06 Renewal Re-Freeze
  REFREEZE

production reads   = 0 (Investigation)
production DDL     = 0
production mutation = 0
deploy             = 0
PR                 = 0
merge              = 0
```

---

## 14. Gate 상태

```
BE-V3-OBJ01 = COMPLETE (REVIEW_REQUIRED)
→ GPT 독립검증 대기

다음 Gate (OBJ01 GPT PASS 후):
  BE-V3-OBJ02 — Pricing Policy V3 Successor
  (SUCCESSOR REQUIRED: field_base_amount + confirmed discounts)
```
