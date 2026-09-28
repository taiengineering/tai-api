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

**증거 출처**: Repository test fixture VERIFIED (lines 11–14). Production price_master rows = **READ 0회** — production 상태 UNVERIFIED.

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

### 3-E. Change Order — V3 Semantic Conflicts (3건)

Change Order는 기존에 "term_months rename 연쇄" 대상으로만 분류됐으나, 3가지 구체적 의미 충돌이 있다.

**Conflict 1: policy_version Gate — V2→V3 전환 차단**

`saas_change_order_v2.py` (line 227: `POLICY_VERSION_MISMATCH`):
- `current_policy_version` ≠ `target_policy_version` → `POLICY_VERSION_MISMATCH` 반환
- V3 정책 버전 문자열(`V3-FROZEN`)이 V2 policy 버전과 다르면 V2 policy 기반 계약의 V3 upgrade가 이 gate에서 전면 차단됨
- **결론**: V2→V3 전환을 Change Order 경로로 허용할지 여부 확정 필요 (OBJ04/OBJ05 결정)

**Conflict 2: FIELD scale band → SCALE_BAND_INCREASE 오분류 가능성**

`saas_change_order_v2.py` (lines 380–382: `SCALE_BAND_INCREASE`):
- FIELD 사업장 scale 변화 시 `SCALE_BAND_INCREASE` 분류 로직이 호출됨
- V3에서 FIELD 가격은 249,000 고정이므로 scale band 변화가 FIELD 가격 변동을 의미하지 않음
- **결론**: FIELD에 대한 Change Order 분류 기준 패치 필요

**Conflict 3: term_months semantic split — 비교 기준 ambiguity**

`saas_change_order_v2.py` (lines 261–262: `current_term = cv.term_months` / `target_term = target_selection.term_months`):
- `from_term_months / to_term_months` 비교
- OBJ05 이후 V3 Selection이 `payment_months`를 사용하면, V2 CV의 `term_months`와 V3 Selection의 `payment_months`를 직접 비교하는 것은 apples-to-oranges
- **결론**: OBJ05 semantic split 결정 후 Change Order 비교 로직 패치 필요

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

**증거 출처**: Repository test fixture VERIFIED. Production rows = READ 0회, UNVERIFIED.

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
| replay idempotency | `target.effective_from` 기준 → payment_months와 무관 | REUSE-AS-IS |
| race recovery | max 2 atomic RPC — payment_months 변경 영향 없음 | REUSE-AS-IS |
| atomic invariant structure | 구조 자체는 V3와 무관 | REUSE-AS-IS |

결론: **payment_months semantic split 때문에 atomic 구조 자체는 변경 불필요. payload field(`term_months` column) rename or patch가 OBJ05에서 결정된다.**

---

## 10. Reuse Strategy — Classification Matrix

### 10-A. V2 재사용 우선 원칙

TAI Safe Pricing V3는 V2 Backend 재구축 프로젝트가 아니다.

V2에서 이미 구현·검증된 다음 자산은 가능한 한 재사용한다:

- 가격 산술 구조 (Primary 선정, Additional rate, worker 누진, VAT)
- Quote 저장 / 금액 정합성 / 번호 발행
- Payment 3중 금액 검증 / Ownership guard / fail-closed
- Commercial Version 구조 / Site Scope
- Atomic 신규계약 / Atomic Renewal / Replay / Race Recovery
- `ONE PAYMENT = ONE MUTATION PATH` invariant
- Renewal runtime routing

**"V2 외부 behavior, schema compatibility, 기존 stored data, 회귀 결과를 깨지 않는다"** 는 의미에서 V2를 보존한다. 공통화를 위해 pure helper/validator/arithmetic 추출, parser dispatch 추가는 가능하다. 단: V2 regression이 동일하게 PASS해야 한다.

### 10-B. Anti-Duplication Rule

V3 개발에서 다음 금지 원칙을 적용한다:

- 동일 VAT calculator 복제 → 금지
- 동일 worker progressive calculator 복제 → 금지
- 동일 Primary/Additional calculation 복제 → 금지
- 동일 amount integrity validation 복제 → 금지
- 동일 Atomic transaction orchestration 복제 → 금지 우선
- 동일 replay/race recovery 구현 복제 → 금지 우선

필요하면 shared pure core로 추출한다.

### 10-C. Reuse Strategy 분류 기준

| 코드 | 정의 |
|------|------|
| **REUSE-AS-IS** | 현재 구현을 그대로 사용 가능 |
| **REUSE-WITH-POLICY** | 공통 로직은 그대로, V3 policy 값/Strategy만 주입 |
| **REUSE-WITH-PATCH** | 기존 구조를 일반화하거나 작은 분기 추가. V2 regression 필수 |
| **REUSE-WITH-ADAPTER** | 핵심 로직 공유, V2/V3 입력/스냅샷 차이만 얇은 adapter로 변환 |
| **NEW-BOUNDARY** | 의미가 달라 기존 contract를 그대로 쓰면 semantic ambiguity가 생기는 경우만 (예: payment_months API contract). Backend 전체 복제 ≠ NEW-BOUNDARY |
| **UNVERIFIED** | OBJ05 등 선행 의미 결정 필요 |
| **UNRELATED** | V3 SaaS와 무관 |

### 10-D. Classification Matrix

| Object | Existing Asset Value | V3 Delta | Reuse Strategy | OBJ05 Dep | Evidence |
|--------|---------------------|----------|----------------|-----------|----------|
| **Pricing Schema** (`saas_pricing_v2.py`) | frozen snapshot structure; `term_months` in Selection + Snapshot | payment_months semantic; V3 snapshot contract | REUSE-WITH-POLICY + NEW-BOUNDARY (V3 snapshot only) | YES | lines 46,175 |
| **Pricing Policy** (`saas_pricing_policy_v2.py`) | policy types, validator, canonical factory | FIELD fixed_base=249,000; discounts 0/500/1000/1500/2000 bps; MANAGER range 300+ | REUSE-WITH-POLICY | NO | lines 219,231-235 |
| **Pricing Composer** (`saas_pricing_composer_v2.py`) | site ordering, Primary/Additional calc, worker progressive, VAT, snapshot construction | FIELD: `normal = 249,000` (not base+uplift) | REUSE-WITH-POLICY / REUSE-WITH-PATCH | NO | line 204 |
| **Preview Request Schema** (`saas_pricing_preview_v2.py`) | `term_months` API input field | V3 needs `payment_months` | NEW-BOUNDARY (API contract) | YES | line 63 |
| **Preview Service** (`saas_pricing_preview_v2.py`) | site parsing, resolver call, composer orchestration, error mapping | FIELD resolver path (가격 불필요, context TBD) | REUSE-WITH-PATCH (FIELD 분기 최소화) | NO | line 90 |
| **Price Resolver** (`pricing_resolver_svc.py`) | `resolve_plan` logic, band lookup | FIELD 가격 의존 제거 TBD; context 용도는 별도 판단 | REUSE-AS-IS | NO | lines 47-85 |
| **price_master DATA** (Production DB — 코드 artifact 아님) | Repo fixture VERIFIED; Production READ 0회 | INDUSTRY_PRO criteria_max + INDUSTRY_CUSTOM 처리 | UNVERIFIED (production state) | NO | test lines 11-14 |
| **Quote Request Schema** (`saas_quote_v2.py`) | `term_months` field | V3 needs `payment_months` | NEW-BOUNDARY (API contract) | YES | line 76 |
| **Quote Snapshot Item Schema** | V2 snapshot items with `term_months` | V3 snapshot items with `payment_months` | NEW-BOUNDARY (semantic contract) | YES | — |
| **Quote Service** (`saas_quote_v2.py`) | ownership, server recalculation, freeze, persistence, numbering | V3 request/snapshot parsing | REUSE-WITH-ADAPTER | YES | line 74 |
| **Payment Adapter OBJ10-A** (`saas_payment_v2_adapter.py`) | quote ownership, ISSUED status, SAAS validation, amount 3-way, INICIS prepare | V3 snapshot parsing | REUSE-WITH-ADAPTER (V2 parser + V3 parser → Shared Core) | PARTIAL | line 160 |
| **Payment Success Adapter OBJ10-B** (`saas_payment_success_v2_adapter.py`) | paid status, ownership, amount integrity, period consistency, apply plan, fail-closed | V3 snapshot parsing; payment_months semantic | REUSE-WITH-ADAPTER + OBJ05 sub-boundary | YES | lines 284,307 |
| **Commercial Version Schema** (`saas_contract_commercial_v2.py`) | product_tier, worker_capacity, pricing_policy_version, snapshot, effective_from, term_months | term_months field meaning | REUSE-WITH-PATCH + OBJ05 | YES | line 87 |
| **Contract Builder** (`payment_post_process.py`) | end_date calculation, renewal extend | payment_months ↔ end_date coupling | REUSE-WITH-PATCH + OBJ05 (core blocker) | YES (core) | lines 101,161 |
| **Site Scope** (`saas_contract_commercial_v2.py`) | entity_type, entity_id, sector structure | FIELD base_band_code meaning TBD | REUSE-AS-IS; FIELD base_band_code UNVERIFIED | PARTIAL | line 61 |
| **Contract Storage Mapper** (`saas_contract_storage_mapper_v2.py`) | CV assembly from selection + snapshot | term_months field name | REUSE-WITH-PATCH | YES | lines 73,114 |
| **Change Order** (`saas_change_order_v2.py`) | site diff, worker diff, product tier diff, change line gen, status framework | 3 semantic conflicts (Sec 3-E) | REUSE-WITH-PATCH | YES (Conflict 3) | lines 227,380-382,261,262 |
| **Atomic New Contract SQL OBJ10-C** | ONE PAYMENT = ONE MUTATION invariant, all guards | term_months/payment_months payload field | REUSE-AS-IS / REUSE-WITH-PATCH + OBJ05 | YES | migration lines 32,57-58,499 |
| **Renewal Adapter OBJ10-D-A** (`saas_renewal_v2_adapter.py`) | renewal quote validation, replay, race recovery | payment_months mapping | REUSE-WITH-ADAPTER + OBJ05 | YES | line 358 |
| **Renewal Temporal Logic D-B1** | `end_date → effective_from` conversion | payment_months ↔ contract.end_date | REUSE-WITH-PATCH + OBJ05 | YES (core) | (별도 파일) |
| **Atomic Renewal SQL D-B2** | 3-way invariant structure | 3-way field naming after OBJ05 | REUSE-AS-IS / REUSE-WITH-PATCH + OBJ05 | YES | migration line 342 |
| **Runtime Wiring D-B3** (`saas_renewal_runtime_v2.py`) | V2/Legacy routing, ONE MUTATION invariant | first_apply boundary (OBJ05) | REUSE-AS-IS; first_apply OBJ05 verification | YES (boundary) | source read |
| **Legacy V1 Quote** (`member_quote_svc.py`, `admin_quote_svc.py`) | V1 contract path | — | UNRELATED | NO | — |
| **Frontend-facing API** (`routers/public_pricing_v2.py`) | V2 preview/quote routing | payment_months API contract | NEW-BOUNDARY + REUSE-WITH-PATCH (shared core) | YES | — |
| **Tests** (pricing, preview, quote, payment, commercial, renewal) | V2 regression evidence | V3 policy/boundary | REUSE-AS-IS (V2 regression 유지) + V3 tests 신규 추가 | PARTIAL | test files |

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
  FIELD:   normal = base_amount + field_uplift_amount  ← V3 REUSE-WITH-PATCH
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
  end_date = start + period_months  ← OBJ05 UNRESOLVED coupling
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

## 12. V3 구현 방향

### A. V3에서 실제로 새로운 것 (변경 최소화 원칙)

V3의 신규 의미는 다음이 전부다:

1. **FIELD pricing policy**: fixed 249,000 (base+uplift 모델 제거)
2. **payment discount policy**: 0 / 5 / 10 / 15 / 20%
3. **MANAGER INDUSTRY range**: 300+ (criteria_max 제거)
4. **payment_months semantic name**: term_months coupling 해체
5. **payment_months와 contract period 의미 분리**: OBJ05 결정 대기
6. **V3 API / Snapshot boundary**: payment_months 필드가 필요한 API/Snapshot만

나머지는 기존 자산 재사용 우선이다.

### B. Pricing Policy — REUSE-WITH-POLICY

V2 policy 전체를 복제하지 않는다. 변경된 값만:

- `field_uplift_amount` → `field_base_amount = 249,000`
- `term_discounts` all None → `[0, 500, 1000, 1500, 2000]` bps
- `MANAGER INDUSTRY INDUSTRY_PRO.criteria_max` → NULL
- `PRICING_POLICY_VERSION` 새 버전 문자열

Shared Policy Types (`SaasTermDiscountPolicy` 등)는 그대로 재사용.

### C. Pricing Composer + Preview — REUSE-WITH-POLICY/PATCH

재사용 대상:
- site canonical ordering, Primary 선정
- Additional rate 적용, worker progressive fee
- raw payment, discount, VAT
- snapshot construction pattern

V3 패치 범위:
- FIELD: `normal = policy.field_base_amount` (not `base_amount + uplift`)
- FIELD resolver 경로: 가격 의존 제거 (context 호출 여부 TBD)

복제 금지: Composer 전체 + Preview 전체를 V3용으로 copy하지 않는다.

### D. Snapshot / API Boundary — NEW-BOUNDARY

Snapshot과 Preview/Quote API는 `payment_months` 의미를 담는 새 contract이 필요하다. 이 경우만 NEW-BOUNDARY를 적용한다.

- `SaasPricingSnapshotV3` — payment_months 명시, `schema_version: SAAS_PRICING_V3`
- V2 `SAAS_PRICING_V2` 스냅샷은 read-only 보존

단: Snapshot boundary가 새로 생긴다고 해서 Pricing/Quote/Payment 전체를 복제하지 않는다. 공통 계산결과를 담는 새 boundary일 뿐이다.

### E. Quote / Payment / Renewal — REUSE-WITH-ADAPTER

재사용 대상 (공통화):
- Quote: ownership, recalculation, freeze, persistence, numbering
- Payment: 3-way integrity, INICIS prepare, paid status, fail-closed
- Renewal: replay, race recovery, atomic apply, ONE MUTATION invariant

V3 adapter 범위:
- V3 snapshot 파싱 (thin parser dispatch)
- payment_months semantic mapping

구조 목표:
```
V2 Snapshot Parser ─┐
                   ├→ Shared Core
V3 Snapshot Parser ─┘
```

V2 Adapter 전체 copy 금지. V2 regression PASS 유지 필수.

### F. OBJ05 Dependent Objects — UNVERIFIED sub-boundary

다음은 OBJ05 `payment_months ↔ contract.end_date ↔ renewal boundary` 결정 전에 구체 구현 방식 확정 금지:

- Commercial Version Schema `term_months` field
- Contract Builder `end_date = start + period_months`
- Atomic OBJ10-C payload field
- Renewal Adapter D-A mapping
- Temporal Logic D-B1
- Atomic Renewal D-B2 3-way guard
- Runtime Wiring D-B3 first_apply boundary
- Payment Success OBJ10-B period mapping

### G. Test Strategy

V2 regression tests를 버리지 않는다:
- V2 regression = 유지 (REUSE-AS-IS)
- Shared Core tests = 공통화된 로직 검증
- V3 policy/boundary tests = 추가

기존 V2 test를 V3용으로 전환해서 V2 회귀증거를 잃는 방식 금지.

### H. 최소 작업 Object 순서 (REUSE-FIRST)

기존 방향(Policy Successor → Composer Successor → Preview Successor → Payment Successor)처럼 Backend를 수평복제하는 흐름 금지.

```
OBJ02   — V3 Policy Delta + Shared Core Reuse Design
          기존 Pricing Core에서 무엇을 공통화할지 최소 설계.
          V3 policy values only (field_base=249000, discounts, MANAGER range).

OBJ03   — Pricing Core Minimal Implementation
          REUSE-WITH-POLICY/PATCH 기준.
          기존 arithmetic/snapshot 패턴 재사용.

OBJ-PM-READ — Production price_master READ-ONLY Verify
          실제 rows 읽기 (UNVERIFIED 해소).
          충돌 확인 시에만 별도 Data Mutation WO 발행.

OBJ04   — V3 Boundary Integration
          payment_months API / V3 snapshot boundary.
          Preview/Quote는 shared core 재사용 + FIELD 분기 PATCH.

OBJ05   — Temporal Semantics Decision
          payment_months ↔ service period ↔ contract.end_date ↔ renewal boundary 확정.
          Change Order 3-E Conflicts 해소.

OBJ06   — Payment / Contract Minimal Integration
          기존 payment/atomic core 재사용.
          V3 parser/adapter + payload PATCH만.

OBJ07   — Change Order / Renewal Minimal Integration
          기존 Change Order/Atomic Renewal/Runtime 최대 재사용.
          OBJ05 boundary PATCH만.

REFREEZE — V2 regression 100% + V3 tests + 통합 E2E.
```

### I. 성공 기준 (Objective Metric)

V3 성공 기준은 "신규 V3 파일 수 최대화"가 아니다:

- V2 regression 100% 유지
- V3 정책 충족
- duplicated business logic 최소
- shared core 최대
- semantic boundary(Snapshot/API)만 version 분리
- Atomic invariant 유지
- maintenance surface 최소화

---

## 13. 조사 결과 요약

```
RUNTIME term_months HITS  = 48개 (runtime 파일 기준, V1/Admin 제외)
FIELD PRICING CONFLICTS   = 5개 (INDUSTRY 50-299, 300-499, BUILDING 5000+, CONSTRUCTION 49억, 50억+)
INDUSTRY_PRO RANGE        = 300~499 (V3 요구: 300+ 상한 없음)
INDUSTRY_CUSTOM 500+      = amount=0 (V3 요구: 500+ → INDUSTRY_PRO = 499,000)
term_discount_rate_bps    = 전부 None (V3 요구: 0/500/1000/1500/2000 bps)
CHANGE ORDER SEMANTIC CONFLICTS = 3건 (line 227, lines 380-382, lines 261-262)

PRICE RESOLVER
  FIELD current resolution  = resolve_plan("SAAS", sector, value) (MANAGER와 동일)
  MANAGER 500+ resolution   = INDUSTRY_CUSTOM → amount=0 → COMPLIANCE_BASE_QUOTE_REQUIRED
  V3 conflict               = FIELD 가격 계산 불필요 / MANAGER 500+ → INDUSTRY_PRO 필요
  price_master 증거: Repository test fixture VERIFIED / Production rows READ 0회 = UNVERIFIED

─────────────────────────────────────────────────
Reuse Strategy 분류 요약
─────────────────────────────────────────────────

REUSE-AS-IS         = 3  (Price Resolver, Site Scope entity structure, Runtime D-B3 routing
                          — Atomic/Replay/Race structure도 REUSE-AS-IS 해당)
REUSE-WITH-POLICY   = 2  (Pricing Policy, Pricing Composer primary)
REUSE-WITH-PATCH    = 6  (Preview Service, Storage Mapper, Change Order,
                          Commercial Version, Contract Builder, D-B1 — 대부분 OBJ05 dep)
REUSE-WITH-ADAPTER  = 4  (Quote Service, OBJ10-A, OBJ10-B, Renewal D-A)
NEW-BOUNDARY        = 4  (Preview Request API, Quote Request API,
                          Quote Snapshot V3, Frontend API)
UNVERIFIED          = 2+ (price_master production, OBJ05 dependent sub-boundaries)
UNRELATED           = 2  (Legacy V1, Admin Quote)

OBJ05 DEPENDENT OBJECTS = 12
  (Commercial Schema, Contract Builder, Storage Mapper, Change Order C3,
   OBJ10-C payload, D-A, D-B1, D-B2, D-B3 first_apply,
   Snapshot boundary, OBJ10-B period mapping, Frontend API)

─────────────────────────────────────────────────

DUPLICATION POLICY
  동일 business logic V2/V3 복제 = 금지 우선
  Shared Core 추출 = 우선

V2 REGRESSION POLICY
  V2 regression tests 유지 필수
  V3 tests = 신규 추가

─────────────────────────────────────────────────

PROPOSED MINIMAL OBJECT ORDER
  OBJ02   Policy Delta + Shared Core Design
  OBJ03   Pricing Core REUSE-WITH-POLICY/PATCH
  OBJ-PM-READ  price_master READ-ONLY Verify
  OBJ04   V3 Boundary Integration
  OBJ05   Temporal Semantics Decision
  OBJ06   Payment / Contract Minimal Integration
  OBJ07   Change Order / Renewal Minimal Integration
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
  BE-V3-OBJ02 — V3 Policy Delta + Shared Core Reuse Design
  (REUSE-WITH-POLICY: field_base_amount + confirmed discounts + shared core design)
```

---

## Appendix A — term_months Runtime Hit Manifest (48건)

V1/Admin 경로 제외. V3 SaaS 런타임 기준. ✓ = 해당 용도로 사용됨.

**해석 원칙**: 해당 coupling이 존재함 → shared core / adapter / patch / boundary 중 최소 변경 방식으로 해결. 각 hit가 자동으로 "새 V3 파일 필요"를 의미하지 않는다.

### A-1. Schemas

| 파일 | 라인 | 심볼 / 용도 | PRICE | DISCOUNT | PAYMENT | CONTRACT DATE | RENEWAL | PERSISTED | V3 CONFLICT | Object |
|------|------|-----------|:-----:|:--------:|:-------:|:-------------:|:-------:|:---------:|:-----------:|--------|
| `schemas/saas_pricing_v2.py` | 46 | `SaasCommercialSelection.term_months` — user selection | ✓ | ✓ | — | — | — | — | RENAME | Pricing Schema |
| `schemas/saas_pricing_v2.py` | 55,57,59 | validator (`VALID_TERM_MONTHS`) | — | — | — | — | — | — | RENAME | Pricing Schema |
| `schemas/saas_pricing_v2.py` | 175 | `SaasPricingSnapshotV2.term_months` — frozen in snapshot | ✓ | ✓ | ✓ | — | — | ✓(JSON) | NEW-BOUNDARY | Pricing Schema |
| `schemas/saas_pricing_v2.py` | 185,187,189 | validator | — | — | — | — | — | — | NEW-BOUNDARY | Pricing Schema |
| `schemas/saas_pricing_policy_v2.py` | 66 | `SaasTermDiscountPolicy.term_months` — discount key | — | ✓ | — | — | — | — | RENAME | Pricing Policy |
| `schemas/saas_pricing_policy_v2.py` | 69,71,73 | validator | — | — | — | — | — | — | RENAME | Pricing Policy |
| `schemas/saas_pricing_policy_v2.py` | 201 | input validation loop | — | ✓ | — | — | — | — | RENAME | Pricing Policy |
| `schemas/saas_pricing_policy_v2.py` | 231-235 | canonical factory (all `None`) | — | ✓ | — | — | — | — | REPLACE values | Pricing Policy |
| `schemas/saas_pricing_preview_v2.py` | 63 | request `term_months` — API input | — | ✓ | — | — | — | — | NEW-BOUNDARY | Preview Schema |
| `schemas/saas_pricing_preview_v2.py` | 93 | response `term_months` | — | ✓ | — | — | — | — | NEW-BOUNDARY | Preview Schema |
| `schemas/saas_quote_v2.py` | 76 | Quote request `term_months` | — | ✓ | — | — | — | — | NEW-BOUNDARY | Quote Schema |
| `schemas/saas_contract_commercial_v2.py` | 87 | DB column `term_months` | — | — | ✓ | ✓ | — | ✓(DB) | UNVERIFIED | Commercial Schema |
| `schemas/saas_contract_commercial_v2.py` | 121,123,125 | validator | — | — | ✓ | — | — | — | UNVERIFIED | Commercial Schema |
| `schemas/saas_contract_commercial_v2.py` | 194,196 | cross-validation with snapshot | — | — | ✓ | — | — | — | UNVERIFIED | Commercial Schema |
| `schemas/saas_change_order_v2.py` | 100,101 | `from/to_term_months` Optional fields | — | — | ✓ | — | — | — | PATCH | Change Order Schema |
| `schemas/saas_change_order_v2.py` | 145,146 | `current/target_term_months` | — | — | ✓ | — | — | — | PATCH | Change Order Schema |

### A-2. Services

| 파일 | 라인 | 심볼 / 용도 | PRICE | DISCOUNT | PAYMENT | CONTRACT DATE | RENEWAL | PERSISTED | V3 CONFLICT | Object |
|------|------|-----------|:-----:|:--------:|:-------:|:-------------:|:-------:|:---------:|:-----------:|--------|
| `services/saas_pricing_composer_v2.py` | 107 | `result.term_months` pass-through | ✓ | ✓ | — | — | — | — | PATCH | Pricing Composer |
| `services/saas_pricing_composer_v2.py` | 178 | `SaasPricingCalculationResult(term_months=...)` | ✓ | ✓ | — | — | — | — | PATCH | Pricing Composer |
| `services/saas_pricing_composer_v2.py` | 253 | `raw_prepaid = monthly × term_months` | ✓ | — | ✓ | — | — | — | PATCH | Pricing Composer |
| `services/saas_pricing_composer_v2.py` | 258,262 | discount lookup by `term_months` | — | ✓ | — | — | — | — | PATCH | Pricing Composer |
| `services/saas_pricing_composer_v2.py` | 276,312,328 | snapshot construction | ✓ | ✓ | ✓ | — | — | ✓(snap) | PATCH | Pricing Composer |
| `services/saas_pricing_preview_v2.py` | 49 | error message reference | — | — | — | — | — | — | PATCH | Preview Service |
| `services/saas_pricing_preview_v2.py` | 150,161,173,227,249 | `SaasCommercialSelection(term_months=request.term_months)` | ✓ | ✓ | — | — | — | — | PATCH | Preview Service |
| `services/saas_quote_v2.py` | 74,77 | snapshot vs request validation | — | ✓ | — | — | — | — | ADAPTER | Quote Service |
| `services/saas_quote_v2.py` | 106 | `"term_months": request.term_months` (quote item) | — | ✓ | ✓ | — | — | ✓(item) | ADAPTER | Quote Service |
| `services/saas_quote_v2.py` | 139 | `quantity=snap.term_months` | ✓ | — | ✓ | — | — | — | ADAPTER | Quote Service |
| `services/saas_quote_v2.py` | 152 | `term_months=snap.term_months` | ✓ | ✓ | ✓ | — | — | ✓ | ADAPTER | Quote Service |
| `services/saas_payment_v2_adapter.py` | 160 | `period_months=snap.term_months` → payments | — | — | ✓ | — | — | ✓(pay) | ADAPTER | OBJ10-A |
| `services/saas_payment_success_v2_adapter.py` | 62 | error code docstring | — | — | — | — | — | — | ADAPTER | OBJ10-B |
| `services/saas_payment_success_v2_adapter.py` | 120 | `SaasCommercialSelection(term_months=snap.term_months)` | ✓ | ✓ | — | — | — | — | ADAPTER | OBJ10-B |
| `services/saas_payment_success_v2_adapter.py` | 282,284,287 | `pay.period_months == snap.term_months` 정합성 | — | — | ✓ | — | — | — | ADAPTER | OBJ10-B |
| `services/saas_payment_success_v2_adapter.py` | 307 | `term_months=snap.term_months` → SaasCommercialSelection | ✓ | ✓ | ✓ | — | — | — | ADAPTER | OBJ10-B |
| `services/saas_renewal_v2_adapter.py` | 99 | error code docstring | — | — | — | — | — | — | ADAPTER | D-A |
| `services/saas_renewal_v2_adapter.py` | 358 | `period_months=snap.term_months` renewal prepare | — | — | ✓ | — | ✓ | ✓(pay) | ADAPTER | D-A |
| `services/saas_renewal_v2_adapter.py` | 620,622,625 | `pay.period_months != snap.term_months` 검증 | — | — | ✓ | — | ✓ | — | ADAPTER | D-A |
| `services/saas_renewal_v2_adapter.py` | 638 | `term_months=snap.term_months` → renewal bundle | ✓ | ✓ | ✓ | — | ✓ | ✓ | ADAPTER | D-A |
| `services/saas_change_order_v2.py` | 93,94 | `current_term_months = cv.term_months` | — | — | ✓ | — | — | — | PATCH | Change Order Svc |
| `services/saas_change_order_v2.py` | 207,210,211 | selection vs snapshot validation | — | ✓ | ✓ | — | — | — | PATCH | Change Order Svc |
| `services/saas_change_order_v2.py` | 261,262 | `current_term / target_term` comparison | — | ✓ | ✓ | — | — | — | PATCH | Change Order Svc |
| `services/saas_change_order_v2.py` | 268,269,445,446,471,472,504,505 | `from/to_term_months` population | — | ✓ | ✓ | — | — | ✓(CO) | PATCH | Change Order Svc |
| `services/saas_contract_storage_mapper_v2.py` | 73,114 | `term_months=selection.term_months` → CV | — | — | ✓ | ✓ | — | ✓(CV) | PATCH | Storage Mapper |

### A-3. Migrations (Atomic Guard)

| 파일 | 라인 | 심볼 / 용도 | PAYMENT | CONTRACT DATE | RENEWAL | PERSISTED | V3 CONFLICT | Object |
|------|------|-----------|:-------:|:-------------:|:-------:|:---------:|:-----------:|--------|
| `migrations/…atomic_apply.sql` | 32 | DDL `term_months integer` column | — | ✓ | — | ✓(DDL) | UNVERIFIED | OBJ10-C SQL |
| `migrations/…atomic_apply.sql` | 57-58 | `VALID_TERM_MONTHS` check constraint | ✓ | — | — | ✓(DDL) | UNVERIFIED | OBJ10-C SQL |
| `migrations/…atomic_apply.sql` | 499 | `(cv->>'term_months')::integer` 3-way | ✓ | ✓ | — | ✓(SQL) | UNVERIFIED | OBJ10-C SQL |
| `migrations/…renewal_atomic.sql` | 342 | 3-way: `snap == cv == pay.period_months` | ✓ | ✓ | ✓ | ✓(SQL) | UNVERIFIED | D-B2 SQL |
