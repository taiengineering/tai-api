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

## 2-B. Production 실측 결과 (2026-09-29 GPT READ-ONLY 독립검증)

**Project**: taieng (Production Supabase)
**Production write**: 0

| 항목 | 실측 값 | 의미 |
|------|---------|------|
| `saas_contract_commercial_versions` 테이블 | **NOT APPLIED** | V2 Commercial DDL 미적용 |
| `saas_contract_site_scopes` 테이블 | **NOT APPLIED** | V2 Site Scope DDL 미적용 |
| quotes `service_type=SAAS` 총 수 | 5 | 현존 견적 (V2 미사용) |
| quotes `SAAS_QUOTE_V2` schema | **0** | V2 Pricing 저장 견적 없음 |
| quotes `SAAS_PRICING_V2` snapshot | **0** | V2 pricing_snapshot 없음 |
| payments `product_type='SAAS'` | **0** | V2 SAAS Payment 없음 |
| contracts `service_type='SAAS'` | 8 | 전부 Legacy 계약 |
| ACTIVE SAAS contracts | 5 | 전부 Legacy plan_code 계약 |

**price_master Production 실측 (VERIFIED):**

| service_type | sector | tier_code | criteria_min | criteria_max | amount |
|---|---|---|---|---|---|
| SAAS | INDUSTRY | INDUSTRY_STARTER | 0 | 49 | 149,000 |
| SAAS | INDUSTRY | INDUSTRY_BUSINESS | 50 | 299 | 299,000 |
| SAAS | INDUSTRY | INDUSTRY_PRO | 300 | 499 | 499,000 |
| SAAS | INDUSTRY | INDUSTRY_CUSTOM | 500 | NULL | 0 |
| DIAGNOSIS | INDUSTRY | (tier) | 0 | 49 | 149,000 |
| DIAGNOSIS | INDUSTRY | (tier) | 50 | 299 | 299,000 |
| DIAGNOSIS | INDUSTRY | (tier) | 300 | NULL | 499,000 |

**V3 충돌 VERIFIED:**
- `SAAS INDUSTRY INDUSTRY_PRO.criteria_max = 499` → V3: 300+ (상한 없음) → CONFLICT
- `SAAS INDUSTRY INDUSTRY_CUSTOM, amount=0` → V3: 500+ = INDUSTRY_PRO 499,000 → CONFLICT

**DIAGNOSIS INDUSTRY의 Production은 300+ 무한으로 이미 설정되어 있음** (V3 MANAGER와 동일 구조).

**구조적 결론:**

> V2 Pricing Backend는 코드·검증은 완성됐으나 Production에 V2 commercial runtime artifact가 없다. 기존 SaaS 계약은 전부 Legacy. 이 사실로 인해 V3는 V2/V3 병렬 runtime을 유지할 필요 없이 V2 구현 베이스를 직접 minimal delta 방식으로 진화시킬 수 있다.

---

## 3. 핵심 충돌 발견 — CRITICAL FINDINGS

### 3-A. SAAS INDUSTRY price_master 구조 — V3 CONFLICT (VERIFIED)

`tests/test_pricing_resolver_saas_boundary.py` lines 11–14 (Repository fixture):

```python
_SAAS_INDUSTRY = [
    {"tier_code": "INDUSTRY_STARTER",  "criteria_min": 0,   "criteria_max": 49,  "amount": 149000},
    {"tier_code": "INDUSTRY_BUSINESS", "criteria_min": 50,  "criteria_max": 299, "amount": 299000},
    {"tier_code": "INDUSTRY_PRO",      "criteria_min": 300, "criteria_max": 499, "amount": 499000},
    {"tier_code": "INDUSTRY_CUSTOM",   "criteria_min": 500, "criteria_max": None,"amount": 0     },
]
```

**증거 상태**: Repository fixture와 Production 일치 **VERIFIED** (Section 2-B 실측).

**V3 충돌 2건 (VERIFIED):**

1. `INDUSTRY_PRO.criteria_max = 499` → V3: `300+ → INDUSTRY_PRO`이므로 criteria_max = NULL이어야 함
2. `INDUSTRY_CUSTOM: 500+, amount=0` → V3: 500인 이상이라도 INDUSTRY_PRO = 499,000원

현재 MANAGER INDUSTRY 500인 이상 Preview → INDUSTRY_CUSTOM → `amount=0` → `COMPLIANCE_BASE_QUOTE_REQUIRED`. Composer 도달 불가.

**수정 방법 TBD**: INDUSTRY_PRO criteria_max → NULL + INDUSTRY_CUSTOM 처리 (deactivate or repurpose). OBJ02/OBJ03 설계 후 별도 DATA WO. Production mutation은 Owner Gate 선행.

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

V3에서 FIELD Base는 249,000 고정이므로 uplift 모델이 교체 대상이다.

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

V3는 할인율을 확정했으므로 Policy 객체에 실제 값 주입이 필요하다.

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

**CRITICAL**: `payment_post_process.py` lines 101–105, 117–120에서 `period_months`가 `contracts.end_date`를 직접 계산한다. V3에서 UNRESOLVED인 `payment_months ↔ contract.end_date` coupling의 실제 코드 위치.

**ADDITIONAL CONTEXT (Section 2-B)**: `saas_contract_commercial_versions` 테이블이 Production 미적용이므로 `term_months` DB column은 아직 Production에 없다. OBJ05에서 최종 의미 결정 후 최초 DDL에 반영 가능.

### 3-E. Change Order — V3 Semantic Conflicts (3건)

**Conflict 1: policy_version Gate — V2→V3 전환 차단**

`saas_change_order_v2.py` (line 227: `POLICY_VERSION_MISMATCH`):
- `current_policy_version` ≠ `target_policy_version` → `POLICY_VERSION_MISMATCH` 반환
- **결론**: V2→V3 전환 Change Order 경로 허용 여부 확정 필요 (OBJ05 결정)

**Conflict 2: FIELD scale band → SCALE_BAND_INCREASE 오분류 가능성**

`saas_change_order_v2.py` (lines 380–382: `SCALE_BAND_INCREASE`):
- V3에서 FIELD 가격 249,000 고정 → scale band 변화가 가격 변동 아님
- **결론**: FIELD Change Order 분류 기준 패치 필요

**Conflict 3: term_months semantic split — 비교 기준 ambiguity**

`saas_change_order_v2.py` (lines 261–262: `current_term = cv.term_months` / `target_term = target_selection.term_months`):
- OBJ05 이후 V3가 `payment_months`를 사용하면 V2 CV의 `term_months`와 비교 불일치
- **결론**: OBJ05 결정 후 최소 패치 필요

---

## 4. Price Resolver Special Audit

| 질문 | 실측 결과 |
|------|---------|
| **Q1. FIELD도 현재 SAAS Compliance Base resolve를 거치는가?** | YES. `services/saas_pricing_preview_v2.py:90` |
| **Q2. FIELD 정상가격 계산 전에 base_amount가 필수인가?** | YES (현재). V3에서는 불필요 (249,000 고정) |
| **Q3. FIELD에 산업 500+를 넣으면 어떤 tier/status가 되는가?** | INDUSTRY_CUSTOM row → `amount=0` → `COMPLIANCE_BASE_QUOTE_REQUIRED`. Composer 도달 불가. |
| **Q4. MANAGER 산업 500+는 현재 어떤 tier/status가 되는가?** | 동일. V3: 499,000이어야 함. CONFLICT VERIFIED. |
| **Q5. V3 요구 300+=499,000을 위해 DIAGNOSIS range rule 재사용 가능한가?** | DIAGNOSIS Production 구조가 이미 300+ 무한 (Section 2-B). SAAS INDUSTRY rows 수정으로 동일 구조 맞출 수 있음. Resolver 로직 자체는 변경 없음. |
| **Q6. SAAS INDUSTRY rows 수정 방향** | INDUSTRY_PRO criteria_max → NULL, INDUSTRY_CUSTOM 처리 (deactivate/repurpose). 방식 확정은 OBJ02/OBJ03 이후 DATA WO. |
| **Q7. price_master 변경 vs 별도 V3 band table** | SAAS INDUSTRY rows 직접 수정이 가장 단순. Resolver 로직 재사용 가능. |

---

## 5. term_months Semantic Audit — 주요 hit 분류

| PATH | SYMBOL | USED FOR PRICE? | USED FOR DISCOUNT? | USED FOR PAYMENT PERIOD? | USED FOR CONTRACT DATES? | PERSISTED? | V3 CONFLICT | DISPOSITION CANDIDATE |
|------|--------|-----------------|-------------------|--------------------------|--------------------------|-----------:|-------------|----------------------|
| `schemas/saas_pricing_v2.py:46` | `SaasCommercialSelection.term_months` | YES (multiplier) | YES | NO | NO | NO | RENAME | `payment_months` (patch existing) |
| `schemas/saas_pricing_v2.py:175` | `SaasPricingSnapshotV2.term_months` | YES | YES | YES (→ period_months) | NO | YES (JSON) | RENAME | EVOLVE schema field |
| `schemas/saas_pricing_policy_v2.py:66` | `SaasTermDiscountPolicy.term_months` | NO | YES (key) | NO | NO | NO | RENAME | `payment_months` (patch) |
| `schemas/saas_pricing_preview_v2.py:63` | request `term_months` | NO | YES | NO | NO | NO | RENAME | API EVOLVE BOUNDARY |
| `schemas/saas_contract_commercial_v2.py:87` | DB column `term_months` | NO | NO | YES | PARTIAL (3-way) | YES (DB) | OBJ05 DEPENDENT | DDL not yet applied — can finalize for V3 |
| `migrations/…atomic_apply.sql:32` | DDL `term_months` column | NO | NO | YES | YES (3-way guard) | YES (DDL) | OBJ05 DEPENDENT | Not applied — can finalize for V3 |
| `migrations/…renewal_atomic.sql:342` | 3-way `snap == cv == pay.period_months` | NO | NO | YES | YES | YES | OBJ05 DEPENDENT | Not applied — finalize with OBJ05 |
| `services/payment_post_process.py:101,161` | `period_months → end_date` | NO | NO | NO | **YES (직접)** | NO | **UNRESOLVED** | OBJ05 결정 필수 |

---

## 6. FIELD Pricing Audit — Chain별 현황

| 단계 | 현재 요구 값 | V3 필요 여부 | 비고 |
|------|------------|-------------|------|
| Request | `sector + criteria_value` (site 입력) | 필요 (scope 증거) | 가격 계산 외 목적으로 유지 |
| Preview Resolver 호출 | `resolve_plan("SAAS", sector, value)` | 불필요 (가격), 필요 (base_band_code 확보 여부 TBD) | FIELD는 base_amount 불필요 |
| Preview → Composer input | `base_amount` 필수 (`SaasSitePricingInput`) | **불필요** (V3: 249,000 고정) | `SaasSitePricingInput` 인터페이스 변경 필요 |
| Composer FIELD | `normal = base_amount + field_uplift_amount` | 교체 필요: `normal = FIELD_BASE_AMOUNT` | |
| Snapshot `base_amount` | 저장됨 (`SaasSiteScope.base_amount`) | V3에서 의미 변화 | scope 증거 보존 필요 여부 TBD |
| Quote | `term_months` + 금액 freeze | 동일 구조 유지, field name patch | |
| Payment Prepare | `period_months = snap.term_months` | 동일 값 (결제월수) 전달 | OBJ05 결정 전 변경 없음 |
| Contract Commercial Version | `term_months` 저장 | OBJ05 결정 후. **DDL 미적용으로 V3 기준으로 최초 적용 가능** | |
| Renewal | `period_months = snap.term_months` | OBJ05 결정 후 | |

---

## 7. MANAGER Range Audit

| 범위 | V2 현재 | V3 요구 | 충돌 |
|------|---------|---------|------|
| ≤49 | INDUSTRY_STARTER (149,000) | ≤49 = 149,000 ✓ | 없음 |
| 50~299 | INDUSTRY_BUSINESS (299,000) | 50~299 = 299,000 ✓ | 없음 |
| 300~499 | INDUSTRY_PRO (499,000) | 300+ = 499,000 — criteria_max=499 ✗ | CONFLICT VERIFIED |
| 500+ | INDUSTRY_CUSTOM (0) | 300+ = 499,000 (PRO) ✗ | CONFLICT VERIFIED |

Production 실측 (Section 2-B)으로 Repository fixture와 Production이 동일함이 확인됨.

수정 내용: `INDUSTRY_PRO criteria_max → NULL`, `INDUSTRY_CUSTOM 처리`. 방법 TBD — OBJ03 후 별도 DATA WO.

---

## 8. Snapshot / Backward Compatibility

**Production 실측 반영 (Section 2-B)**: `SAAS_PRICING_V2` 저장 snapshot = 0. Backward-compatible snapshot parser 병렬 구현 불필요.

**권장 방향**: 현재 Pricing Snapshot Schema를 V3 semantics로 evolve한다.

| 질문 | 판정 |
|------|------|
| Production에 V2 snapshot이 있어 read 호환성이 필요한가? | **NO** — SAAS_PRICING_V2 persisted = 0. Stored V2 compatibility 때문에 parser duplication 불필요. |
| V3 snapshot에 V2 `term_months`를 그대로 쓸 수 있는가? | NO. V3에서 `payment_months` 의미 분리 필요. |
| 권장 방향 | 기존 snapshot schema를 `payment_months`로 evolve. `schema_version: SAAS_PRICING_V3`. Production V2 snapshot = 0이므로 clean migration 가능. |
| renewal replay path | `snap.term_months`을 `effective_from` 계산에 사용. OBJ05 결정 후 최소 패치. |

---

## 9. Payment / Renewal Atomicity Guard

V2 invariant: `ONE PAYMENT = EXACTLY ONE CONTRACT MUTATION PATH` — V3에서도 반드시 유지.

| 영역 | Production 상태 | V3 impact | 판정 |
|------|----------------|-----------|------|
| new contract atomic (OBJ10-C SQL) | **NOT APPLIED** | `term_months` column. OBJ05 결정으로 V3 기준 최초 적용 가능 | OBJ05 DEPENDENT |
| renewal atomic (OBJ10-D-B2 SQL) | **NOT APPLIED** | 3-way guard. OBJ05 결정으로 V3 기준 최초 적용 가능 | OBJ05 DEPENDENT |
| replay idempotency | (code only) | `target.effective_from` 기준 — payment_months와 무관 | REUSE-AS-IS |
| race recovery | (code only) | max 2 atomic RPC — payment_months 변경 영향 없음 | REUSE-AS-IS |
| atomic invariant structure | (code only) | 구조 자체는 V3와 무관 | REUSE-AS-IS |

**결론**: V2 Atomic DDL이 Production 미적용이므로, OBJ05에서 `payment_months` 의미를 확정한 뒤 V3 기준으로 최초 Production DDL 적용이 가능하다. Backward-compatible migration 부담이 없다.

---

## 10. Implementation Strategy — Classification Matrix

### 10-A. Architectural Principle

**V2 Backend는 Implementation Baseline이다.** TAI Safe Pricing V3는 V2 재구축이 아니라 V2의 검증된 구조 위에서 정책/의미 delta만 최소 패치하는 프로젝트다.

**보존 대상은 파일버전이 아니라 invariant다:**

```
Pricing arithmetic (Primary, Additional, Worker, VAT)
Frozen Quote SSOT
Payment 3중 금액 검증
Ownership / Status guard / fail-closed
Atomic contract application
Atomic renewal
Replay / Race recovery
ONE PAYMENT = ONE CONTRACT MUTATION PATH
Legacy SaaS runtime isolation
```

**Production 실측으로 확정된 사실:**

- V2 Commercial DDL (saas_contract_commercial_versions, site_scopes) = **NOT APPLIED**
- V2 stored quotes/snapshots/payments = **0**
- 기존 SaaS contracts = 8건, **전부 Legacy plan_code 계약**

이 사실이 의미하는 것:

1. V2/V3 병렬 runtime 유지 불필요
2. Stored V2 snapshot parser 병렬 구현 불필요
3. OBJ10-A/B V3 전용 복제 불필요
4. Commercial DDL = OBJ05 결정 후 V3 기준 최초 적용 가능

**Legacy 계약은 별도 route로 보존한다.** Legacy contracts는 V3 pricing과 무관하게 기존 경로를 유지한다.

### 10-B. Anti-Duplication Rule

- 동일 VAT calculator 복제 → 금지
- 동일 Primary/Additional calculation 복제 → 금지
- 동일 worker progressive calculator 복제 → 금지
- 동일 amount integrity validation 복제 → 금지
- 동일 Atomic transaction orchestration 복제 → 금지
- 동일 replay/race recovery 복제 → 금지

필요하면 shared pure helper로 추출한다.

### 10-C. Implementation Strategy 분류 기준

| 코드 | 정의 |
|------|------|
| **PATCH EXISTING** | 현재 V2 코드를 V3 policy/semantic으로 최소 수정. V2 codebase 직접 사용. |
| **REUSE-AS-IS** | 현재 구현 그대로 사용. 변경 없음. |
| **EVOLVE BOUNDARY** | API/Snapshot 같은 의미 경계에서 field 이름/version만 evolve. Backend core 복제 아님. |
| **OBJ05 DEPENDENT** | `payment_months ↔ contract.end_date ↔ renewal boundary` 결정 후 최소 패치. |
| **LEGACY PRESERVE** | Legacy contract runtime. 변경 금지. |
| **UNRELATED** | V3 SaaS와 무관. |

### 10-D. Classification Matrix

| Object | Production State | V3 Delta | Strategy | OBJ05 Dep | Evidence |
|--------|-----------------|----------|----------|-----------|----------|
| **Pricing Schema** (`saas_pricing_v2.py`) | Code only; 0 stored | `payment_months` rename; V3 schema_version | EVOLVE BOUNDARY | YES | lines 46,175 |
| **Pricing Policy** (`saas_pricing_policy_v2.py`) | Code only | field_base=249,000; discounts 0/500/1000/1500/2000; policy_version | PATCH EXISTING | NO | lines 219,231-235 |
| **Pricing Composer** (`saas_pricing_composer_v2.py`) | Code only | FIELD: `normal = 249,000` (not base+uplift) | PATCH EXISTING | NO | line 204 |
| **Preview Request Schema** (`saas_pricing_preview_v2.py`) | Code only | `payment_months` field | EVOLVE BOUNDARY | YES | line 63 |
| **Preview Service** (`saas_pricing_preview_v2.py`) | Code only | FIELD resolver path (가격 불필요) | PATCH EXISTING | NO | line 90 |
| **Price Resolver** (`pricing_resolver_svc.py`) | Code only | FIELD 가격 의존 제거 TBD; resolver logic sound | REUSE-AS-IS | NO | lines 47-85 |
| **price_master DATA** (Production DB) | **CONFLICT VERIFIED** | INDUSTRY_PRO criteria_max + INDUSTRY_CUSTOM | DATA WO (OBJ03 후) | NO | Section 2-B |
| **Quote Request Schema** (`saas_quote_v2.py`) | Code only; 0 stored | `payment_months` field | EVOLVE BOUNDARY | YES | line 76 |
| **Quote Snapshot Item Schema** | Code only; 0 stored | V3 schema_version; `payment_months` | EVOLVE BOUNDARY | YES | — |
| **Quote Service** (`saas_quote_v2.py`) | Code only; 0 stored | V3 request/snapshot 처리 | PATCH EXISTING | YES | line 74 |
| **Payment Adapter OBJ10-A** (`saas_payment_v2_adapter.py`) | Code only; 0 paid | V3 snapshot 처리 | PATCH EXISTING | PARTIAL | line 160 |
| **Payment Success Adapter OBJ10-B** (`saas_payment_success_v2_adapter.py`) | Code only; 0 paid | V3 snapshot 처리; payment_months semantic | PATCH EXISTING + OBJ05 | YES | lines 284,307 |
| **Commercial Version Schema** (`saas_contract_commercial_v2.py`) | **NOT APPLIED** | `term_months` field meaning | PATCH EXISTING + OBJ05 | YES | line 87 |
| **Contract Builder** (`payment_post_process.py`) | Code only | `payment_months ↔ end_date` coupling | OBJ05 DEPENDENT | YES (core) | lines 101,161 |
| **Site Scope** (`saas_contract_commercial_v2.py`) | **NOT APPLIED** | FIELD base_band_code V3 용도 TBD | REUSE-AS-IS (NOT YET APPLIED) | PARTIAL | line 61 |
| **Contract Storage Mapper** (`saas_contract_storage_mapper_v2.py`) | Code only | `term_months` → `payment_months` | PATCH EXISTING | YES | lines 73,114 |
| **Change Order** (`saas_change_order_v2.py`) | Code only | 3 semantic conflicts (Sec 3-E) | PATCH EXISTING | YES (C3) | lines 227,380-382,261,262 |
| **Atomic New Contract SQL OBJ10-C** | **NOT APPLIED** | `term_months` payload. OBJ05 후 V3 기준 최초 DDL 가능 | OBJ05 DEPENDENT | YES | migration lines 32,57-58,499 |
| **Renewal Adapter OBJ10-D-A** (`saas_renewal_v2_adapter.py`) | Code only | payment_months mapping | PATCH EXISTING + OBJ05 | YES | line 358 |
| **Renewal Temporal Logic D-B1** | Code only | payment_months ↔ contract.end_date | OBJ05 DEPENDENT | YES (core) | (별도 파일) |
| **Atomic Renewal SQL D-B2** | **NOT APPLIED** | 3-way guard. OBJ05 후 V3 기준 최초 DDL 가능 | OBJ05 DEPENDENT | YES | migration line 342 |
| **Runtime Wiring D-B3** (`saas_renewal_runtime_v2.py`) | Code only | first_apply boundary (OBJ05) | REUSE-AS-IS; OBJ05 verify | YES (boundary) | source read |
| **Legacy SaaS runtime** (V1 plan_code path) | **8 total / 5 active, all Legacy plan_code** | — | LEGACY PRESERVE | NO | Section 2-B |
| **Legacy V1 Quote** (`member_quote_svc.py`, `admin_quote_svc.py`) | Active | — | UNRELATED | NO | — |
| **Frontend-facing API** (`routers/public_pricing_v2.py`) | Code only | `payment_months` boundary | EVOLVE BOUNDARY (얇은 route) | YES | — |
| **Tests** | Code only | V3 policy값 기준 갱신 | PATCH EXISTING + invariant REUSE-AS-IS | PARTIAL | test files |

---

## 11. Dependency Graph (실제 코드 기준)

```
Public Preview Request (term_months)
  ↓
Preview Service
  ↓ resolve_plan("SAAS", sector, value) ← MANAGER/FIELD 공통 (V3 FIELD는 분기 필요)
Price Resolver → price_master (CONFLICT VERIFIED)
  ↓
  base_band_code + base_amount → SaasSitePricingInput
  ↓
Pricing Composer
  MANAGER: normal = base_amount
  FIELD:   normal = base_amount + field_uplift_amount  ← PATCH EXISTING
  term_months → raw_prepaid = monthly × term_months
  term_months → discount lookup → READY/TERM_DISCOUNT_UNRESOLVED
  ↓
SaasPricingSnapshotV2 (term_months frozen)  ← EVOLVE BOUNDARY (0 stored)
  ↓
Quote Service (Preview 재실행 → snapshot freeze)  ← PATCH EXISTING
  ↓
Payment Adapter OBJ10-A  ← PATCH EXISTING
  ↓
Payment Success Adapter OBJ10-B  ← PATCH EXISTING + OBJ05
  ↓
Contract Builder  ← OBJ05 DEPENDENT
  ↓
Atomic Contract Apply OBJ10-C  ← NOT APPLIED; OBJ05 후 V3 기준 DDL
  ↓
[Contract Active]

Renewal path:
  Renewal Adapter D-A  ← PATCH EXISTING + OBJ05
  Temporal Logic D-B1  ← OBJ05 DEPENDENT
  Atomic Renewal D-B2  ← NOT APPLIED; OBJ05 후 V3 기준 DDL
  Runtime Branch D-B3  ← REUSE-AS-IS; OBJ05 boundary verify
```

---

## 12. V3 구현 방향

### A. V3에서 실제로 새로운 것

1. **FIELD pricing**: fixed 249,000 (base+uplift 제거)
2. **Payment discount**: 0 / 5 / 10 / 15 / 20%
3. **MANAGER INDUSTRY range**: 300+ (no max)
4. **`payment_months` semantic**: `term_months` coupling 해체
5. **`payment_months` ↔ contract period 분리**: OBJ05 결정
6. **API/Snapshot boundary**: `payment_months` field evolve (0 stored이므로 clean)

나머지는 기존 검증된 구현 재사용이다.

### B. Pricing Policy + Composer (PATCH EXISTING)

V2 Policy 구조 재사용. 변경 값만:
- `field_uplift_amount` → `field_base_amount = 249,000`
- `term_discounts` all None → `[0, 500, 1000, 1500, 2000]` bps
- `PRICING_POLICY_VERSION` 새 버전 문자열

Composer FIELD 분기: `normal = policy.field_base_amount`. 나머지 산술(Primary/Additional/Worker/VAT) 재사용.

**Pricing Policy ≠ price_master.** `INDUSTRY_PRO criteria_max`, `INDUSTRY_CUSTOM` 처리는 Policy 코드가 아니라 price_master DATA 변경이다.

### C. Snapshot Evolve (Production V2 stored = 0)

V2 snapshot stored = 0이므로 backward-compatible parser 병렬 구현 불필요.

기존 schema를 V3 semantics로 직접 evolve:
- `term_months` → `payment_months`
- `schema_version: SAAS_PRICING_V3`

V2/V3 dual parser = 불필요. 구체 field 변경은 OBJ04.

### D. Payment (PATCH EXISTING)

Production V2 payment = 0. OBJ10-A/B 별도 V3 복제 불필요.

기존 OBJ10-A/B 검증된 구현(ownership, 3-way integrity, INICIS, fail-closed)을 기반으로 V3 snapshot/payment_months 처리 최소 패치.

### E. Commercial DDL (OBJ05 후 최초 적용)

`saas_contract_commercial_versions`, `saas_contract_site_scopes` = Production 미적용.

OBJ05에서 `payment_months` 의미 확정 후 V3 기준으로 최초 Production DDL 적용 가능. Backward-compatible migration 부담 없음. 단: DDL은 별도 Owner Gate 후 실행.

### F. OBJ05 필수 결정 항목

- `payment_months`가 `contract.end_date` 계산에 직접 쓰이는가, 분리되는가
- `term_months` DB column 최종 이름 (rename or new semantic)
- Renewal `effective_from` 경계 (`contract.end_date` 사용 유지 여부)
- Change Order Conflict 3 해소 (term/payment 비교 기준)

### G. Test Policy

보존해야 하는 것은 **invariant regression**이다:
- Primary/Additional/Worker/VAT 정확성
- Amount integrity validation
- Atomicity / Replay / Race recovery
- Ownership / Security / Fail-closed

변경이 허용되는 것:
- FIELD uplift behavior 테스트 → V3 fixed 기준으로 갱신
- 500+ CUSTOM behavior → V3 PRO 기준으로 갱신
- discount=None behavior → V3 actual rates 기준으로 갱신

V2 정책값을 계속 PASS시킬 필요 없음 — 이것들은 V3에서 명시적으로 SUPERSEDED됨.

### H. 최소 작업 순서 (OBJ-PM-READ 완료)

Production read가 이미 완료됐으므로 OBJ-PM-READ 제거.

```
OBJ02
— V3 Delta Design on Existing Backend
  정확히 결정: 어떤 class/field를 최소 변경, 어떤 helper 공유

OBJ03
— Pricing Core Minimal Patch
  FIELD fixed 249,000 / discounts / MANAGER range 통합
  기존 arithmetic 재사용

OBJ-PM-DATA  (Owner Gate 선행)
— Production price_master DATA WO
  INDUSTRY_PRO criteria_max → NULL
  INDUSTRY_CUSTOM 처리
  (방법 OBJ03 후 최종 결정)

OBJ04
— API / Snapshot / Quote Integration
  EVOLVE BOUNDARY (payment_months)
  기존 Quote/Preview core PATCH EXISTING

OBJ05
— Temporal Semantics Decision
  payment_months ↔ contract.end_date ↔ renewal boundary
  Change Order 3-E Conflicts 해소

OBJ06
— Payment / Commercial / Atomic Integration
  OBJ10-A/B PATCH EXISTING
  Commercial DDL V3 기준 최초 작성

OBJ07
— Change Order / Renewal Integration
  D-A/B1/B2/B3 PATCH EXISTING (OBJ05 기반)

REFREEZE
— invariant regression + V3 E2E
```

---

## 13. 조사 결과 요약

```
RUNTIME term_months HITS  = 48개 (runtime 파일 기준, V1/Admin 제외)
FIELD PRICING CONFLICTS   = 5개 (INDUSTRY 50-299, 300-499, BUILDING 5000+, CONSTRUCTION 49억, 50억+)
INDUSTRY_PRO RANGE        = 300~499 (V3 요구: 300+) — CONFLICT VERIFIED (Section 2-B)
INDUSTRY_CUSTOM 500+      = amount=0 — CONFLICT VERIFIED (Section 2-B)
term_discount_rate_bps    = 전부 None (V3 요구: 0/500/1000/1500/2000 bps)
CHANGE ORDER SEMANTIC CONFLICTS = 3건 (line 227, lines 380-382, lines 261-262)

PROD V2 COMMERCIAL TABLES = NOT APPLIED
PROD V2 QUOTES            = 0
PROD V2 PAYMENTS          = 0
PROD LEGACY SAAS CONTRACTS = 8 (전부 Legacy plan_code)
PROD ACTIVE SAAS          = 5

─────────────────────────────────────────────────
V2 Backend Role
─────────────────────────────────────────────────

IMPLEMENTATION BASELINE
= 재구현 금지. 검증된 구조/invariant 직접 재사용.

V3 Strategy
= MINIMAL DELTA UPGRADE

Legacy runtime
= PRESERVE (8 Legacy contracts)

─────────────────────────────────────────────────
Implementation Strategy 분류
─────────────────────────────────────────────────

PATCH EXISTING   = 11 (Policy, Composer, Preview Service, Quote Service,
                        OBJ10-A, OBJ10-B, Storage Mapper, Change Order,
                        Renewal D-A, Tests, Frontend API)
REUSE-AS-IS      = 3  (Price Resolver, Site Scope structure, D-B3 routing)
EVOLVE BOUNDARY  = 5  (Pricing Schema, Preview Request, Quote Request,
                       Quote Snapshot, Frontend API boundary)
OBJ05 DEPENDENCY = CROSS-CUTTING
                   PRIMARY STRATEGY = OBJ05 DEPENDENT:
                     Contract Builder / OBJ10-C / D-B1 / D-B2
                   D-B3 = REUSE-AS-IS; first_apply boundary OBJ05 verify 필요
                   ADDITIONAL OBJ05 DEP (mixed-strategy):
                     Pricing Schema / Preview Request / Quote Request /
                     Quote Snapshot / Quote Service / OBJ10-A partial /
                     OBJ10-B / Commercial Schema / Site Scope partial /
                     Storage Mapper / Change Order C3 / Renewal D-A
                   → Matrix OBJ05 Dep column이 SSOT. 단일 count 없음.
DATA WO          = 1  (price_master Production)
LEGACY PRESERVE  = 1  (Legacy SaaS runtime — 8 total / 5 active)
UNRELATED        = 2  (Legacy V1 Quote, Admin)

─────────────────────────────────────────────────

V2/V3 병렬 runtime    = 불필요 (Production V2 stored = 0)
Snapshot dual parser  = 불필요
OBJ10-A/B 복제        = 불필요
Backward-compatible DDL = 불필요 (DDL not yet applied)

DUPLICATION POLICY    = 동일 business logic 복제 금지
INVARIANT REGRESSION  = 유지 필수 (policy values 변경은 V3 기준)

─────────────────────────────────────────────────

PROPOSED MINIMAL OBJECT ORDER
  OBJ02   V3 Delta Design
  OBJ03   Pricing Core Minimal Patch
  OBJ-PM-DATA  price_master DATA WO (Owner Gate)
  OBJ04   API / Snapshot / Quote
  OBJ05   Temporal Semantics
  OBJ06   Payment / Commercial / Atomic
  OBJ07   Change Order / Renewal
  REFREEZE

production DDL     = 0 (Investigation)
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
  BE-V3-OBJ02 — V3 Delta Design on Existing Backend
  (V2 Implementation Baseline 기준 최소 delta 설계)
```

---

## Appendix A — term_months Runtime Hit Manifest (48건)

V1/Admin 경로 제외. V3 SaaS 런타임 기준. ✓ = 해당 용도로 사용됨.

**해석 원칙**: 각 hit는 해당 coupling이 존재함을 나타낸다. "새 V3 파일 필요"로 자동 연결하지 않는다. Production V2 stored = 0이므로 backward-compat 이중 구현 없이 최소 patch/evolve로 해결한다.

### A-1. Schemas

| 파일 | 라인 | 심볼 / 용도 | PRICE | DISCOUNT | PAYMENT | CONTRACT DATE | RENEWAL | PERSISTED | V3 STRATEGY | Object |
|------|------|-----------|:-----:|:--------:|:-------:|:-------------:|:-------:|:---------:|:-----------:|--------|
| `schemas/saas_pricing_v2.py` | 46 | `SaasCommercialSelection.term_months` — user selection | ✓ | ✓ | — | — | — | — | EVOLVE | Pricing Schema |
| `schemas/saas_pricing_v2.py` | 55,57,59 | validator (`VALID_TERM_MONTHS`) | — | — | — | — | — | — | EVOLVE | Pricing Schema |
| `schemas/saas_pricing_v2.py` | 175 | `SaasPricingSnapshotV2.term_months` — frozen in snapshot | ✓ | ✓ | ✓ | — | — | ✓(JSON, 0 stored) | EVOLVE | Pricing Schema |
| `schemas/saas_pricing_v2.py` | 185,187,189 | validator | — | — | — | — | — | — | EVOLVE | Pricing Schema |
| `schemas/saas_pricing_policy_v2.py` | 66 | `SaasTermDiscountPolicy.term_months` — discount key | — | ✓ | — | — | — | — | PATCH | Pricing Policy |
| `schemas/saas_pricing_policy_v2.py` | 69,71,73 | validator | — | — | — | — | — | — | PATCH | Pricing Policy |
| `schemas/saas_pricing_policy_v2.py` | 201 | input validation loop | — | ✓ | — | — | — | — | PATCH | Pricing Policy |
| `schemas/saas_pricing_policy_v2.py` | 231-235 | canonical factory (all `None`) | — | ✓ | — | — | — | — | PATCH values | Pricing Policy |
| `schemas/saas_pricing_preview_v2.py` | 63 | request `term_months` — API input | — | ✓ | — | — | — | — | EVOLVE | Preview Schema |
| `schemas/saas_pricing_preview_v2.py` | 93 | response `term_months` | — | ✓ | — | — | — | — | EVOLVE | Preview Schema |
| `schemas/saas_quote_v2.py` | 76 | Quote request `term_months` | — | ✓ | — | — | — | — | EVOLVE | Quote Schema |
| `schemas/saas_contract_commercial_v2.py` | 87 | DB column `term_months` | — | — | ✓ | ✓ | — | ✓(DB, NOT APPLIED) | OBJ05 | Commercial Schema |
| `schemas/saas_contract_commercial_v2.py` | 121,123,125 | validator | — | — | ✓ | — | — | — | OBJ05 | Commercial Schema |
| `schemas/saas_contract_commercial_v2.py` | 194,196 | cross-validation with snapshot | — | — | ✓ | — | — | — | OBJ05 | Commercial Schema |
| `schemas/saas_change_order_v2.py` | 100,101 | `from/to_term_months` Optional | — | — | ✓ | — | — | — | PATCH | Change Order Schema |
| `schemas/saas_change_order_v2.py` | 145,146 | `current/target_term_months` | — | — | ✓ | — | — | — | PATCH | Change Order Schema |

### A-2. Services

| 파일 | 라인 | 심볼 / 용도 | PRICE | DISCOUNT | PAYMENT | CONTRACT DATE | RENEWAL | PERSISTED | V3 STRATEGY | Object |
|------|------|-----------|:-----:|:--------:|:-------:|:-------------:|:-------:|:---------:|:-----------:|--------|
| `services/saas_pricing_composer_v2.py` | 107 | `result.term_months` pass-through | ✓ | ✓ | — | — | — | — | PATCH | Pricing Composer |
| `services/saas_pricing_composer_v2.py` | 178 | `SaasPricingCalculationResult(term_months=...)` | ✓ | ✓ | — | — | — | — | PATCH | Pricing Composer |
| `services/saas_pricing_composer_v2.py` | 253 | `raw_prepaid = monthly × term_months` | ✓ | — | ✓ | — | — | — | PATCH | Pricing Composer |
| `services/saas_pricing_composer_v2.py` | 258,262 | discount lookup by `term_months` | — | ✓ | — | — | — | — | PATCH | Pricing Composer |
| `services/saas_pricing_composer_v2.py` | 276,312,328 | snapshot construction | ✓ | ✓ | ✓ | — | — | ✓(snap, 0 stored) | PATCH | Pricing Composer |
| `services/saas_pricing_preview_v2.py` | 49 | error message reference | — | — | — | — | — | — | PATCH | Preview Service |
| `services/saas_pricing_preview_v2.py` | 150,161,173,227,249 | `SaasCommercialSelection(term_months=request.term_months)` | ✓ | ✓ | — | — | — | — | PATCH | Preview Service |
| `services/saas_quote_v2.py` | 74,77 | snapshot vs request validation | — | ✓ | — | — | — | — | PATCH | Quote Service |
| `services/saas_quote_v2.py` | 106 | `"term_months": request.term_months` (quote item) | — | ✓ | ✓ | — | — | ✓(0 stored) | PATCH | Quote Service |
| `services/saas_quote_v2.py` | 139 | `quantity=snap.term_months` | ✓ | — | ✓ | — | — | — | PATCH | Quote Service |
| `services/saas_quote_v2.py` | 152 | `term_months=snap.term_months` | ✓ | ✓ | ✓ | — | — | ✓ | PATCH | Quote Service |
| `services/saas_payment_v2_adapter.py` | 160 | `period_months=snap.term_months` → payments | — | — | ✓ | — | — | ✓(0 paid) | PATCH | OBJ10-A |
| `services/saas_payment_success_v2_adapter.py` | 62 | error code docstring | — | — | — | — | — | — | PATCH | OBJ10-B |
| `services/saas_payment_success_v2_adapter.py` | 120 | `SaasCommercialSelection(term_months=snap.term_months)` | ✓ | ✓ | — | — | — | — | PATCH | OBJ10-B |
| `services/saas_payment_success_v2_adapter.py` | 282,284,287 | `pay.period_months == snap.term_months` 정합성 | — | — | ✓ | — | — | — | PATCH | OBJ10-B |
| `services/saas_payment_success_v2_adapter.py` | 307 | `term_months=snap.term_months` → SaasCommercialSelection | ✓ | ✓ | ✓ | — | — | — | PATCH+OBJ05 | OBJ10-B |
| `services/saas_renewal_v2_adapter.py` | 99 | error code docstring | — | — | — | — | — | — | PATCH | D-A |
| `services/saas_renewal_v2_adapter.py` | 358 | `period_months=snap.term_months` renewal prepare | — | — | ✓ | — | ✓ | ✓(0 paid) | PATCH+OBJ05 | D-A |
| `services/saas_renewal_v2_adapter.py` | 620,622,625 | `pay.period_months != snap.term_months` 검증 | — | — | ✓ | — | ✓ | — | PATCH+OBJ05 | D-A |
| `services/saas_renewal_v2_adapter.py` | 638 | `term_months=snap.term_months` → renewal bundle | ✓ | ✓ | ✓ | — | ✓ | ✓ | PATCH+OBJ05 | D-A |
| `services/saas_change_order_v2.py` | 93,94 | `current_term_months = cv.term_months` | — | — | ✓ | — | — | — | PATCH | Change Order Svc |
| `services/saas_change_order_v2.py` | 207,210,211 | selection vs snapshot validation | — | ✓ | ✓ | — | — | — | PATCH | Change Order Svc |
| `services/saas_change_order_v2.py` | 261,262 | `current_term / target_term` comparison | — | ✓ | ✓ | — | — | — | PATCH+OBJ05 | Change Order Svc |
| `services/saas_change_order_v2.py` | 268,269,445,446,471,472,504,505 | `from/to_term_months` population | — | ✓ | ✓ | — | — | ✓(CO) | PATCH | Change Order Svc |
| `services/saas_contract_storage_mapper_v2.py` | 73,114 | `term_months=selection.term_months` → CV | — | — | ✓ | ✓ | — | ✓(0 stored) | PATCH | Storage Mapper |

### A-3. Migrations (Atomic Guard — NOT APPLIED)

| 파일 | 라인 | 심볼 / 용도 | PAYMENT | CONTRACT DATE | RENEWAL | PERSISTED | V3 STRATEGY | Object |
|------|------|-----------|:-------:|:-------------:|:-------:|:---------:|:-----------:|--------|
| `migrations/…atomic_apply.sql` | 32 | DDL `term_months integer` column | — | ✓ | — | ✓(NOT APPLIED) | OBJ05 DEPENDENT | OBJ10-C SQL |
| `migrations/…atomic_apply.sql` | 57-58 | `VALID_TERM_MONTHS` check constraint | ✓ | — | — | ✓(NOT APPLIED) | OBJ05 DEPENDENT | OBJ10-C SQL |
| `migrations/…atomic_apply.sql` | 499 | `(cv->>'term_months')::integer` 3-way | ✓ | ✓ | — | ✓(NOT APPLIED) | OBJ05 DEPENDENT | OBJ10-C SQL |
| `migrations/…renewal_atomic.sql` | 342 | 3-way: `snap == cv == pay.period_months` | ✓ | ✓ | ✓ | ✓(NOT APPLIED) | OBJ05 DEPENDENT | D-B2 SQL |
