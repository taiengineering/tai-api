---
title: TAI Safe Pricing V3 — BE-OBJ02 Delta Design on Existing Backend
kind: design
status: REVIEW_REQUIRED
date: 2026-09-29
branch: docs/pricing-canonical-20260927
policy_head: 6e34a0cc42a76832c6c415e17b55195e66d20a6b
obj01_head: 424714c616c5a18cc1b70a3f61c28c1eecd9e294
---

# TAI Safe Pricing V3 — BE-OBJ02 Delta Design on Existing Backend

**WO**: WO-BE-V3-OBJ02-DELTA-DESIGN-001
**Date**: 2026-09-29
**Branch**: `docs/pricing-canonical-20260927`
**Base**: `424714c616c5a18cc1b70a3f61c28c1eecd9e294` (OBJ01 FROZEN HEAD)
**Mode**: DESIGN ONLY — NO CODE CHANGE / NO PRODUCTION MUTATION

> **이 문서는 REVIEW_REQUIRED 상태다. GPT 독립검증 전 APPROVED 불가.**

---

## 0. 설계 전제

### 0-A. 불변 원칙

V2 Backend가 Implementation Baseline이다. V3는 V2를 재구축하지 않는다.

다음은 변경 금지:

```
Primary 계산 (site × 100%)
Additional 80% 계산
Worker progressive 계산
VAT 계산
Quote amount integrity
Ownership guard
Payment amount 3-way validation
INICIS exact amount path
Atomic orchestration
Replay
Race recovery
ONE PAYMENT = ONE CONTRACT MUTATION PATH
```

### 0-B. Production 실측 (OBJ01 기준)

```
V2 Commercial DDL       = NOT APPLIED
V2 stored quotes        = 0
V2 stored payments      = 0
Legacy SAAS contracts   = 8 total / 5 active
```

이 사실로 인해:
- V2/V3 병렬 runtime 불필요
- Snapshot dual parser 불필요
- Backward-compatible DDL 불필요
- OBJ10-A/B 복제 불필요

### 0-C. File naming 원칙

**`_v2` 파일명 유지.** V3 Policy = 최초 Production runtime. 파일명 복사는 복잡성을 증가시킬 뿐 reuse value가 없다. 내부 version string (SCHEMA_VERSION 등)만 "V3"로 갱신한다.

---

## 1. V3 Delta — 고정 항목

| 축 | V2 현재 코드 | V3 확정 |
|----|------------|---------|
| **FIELD 가격 모델** | `normal = s.base_amount + policy.field_uplift_amount` (line 204) | `normal = policy.field_base_amount` (249,000 고정) |
| **Policy field 이름** | `field_uplift_amount = 100,000` | `field_base_amount = 249,000` (의미 변경: uplift-on-top → fixed-base) |
| **Discount** | `term_discounts` 전부 `None` | `[0, 500, 1000, 1500, 2000]` bps |
| **MANAGER INDUSTRY range** | `300~499=PRO, 500+=CUSTOM(0)` | `300+=PRO(499,000)` — price_master DATA WO |
| **Semantic rename** | `term_months` | `payment_months` (할인·결제 축만) |
| **Policy version** | `TAI_SAFE_PRICING_POLICY_2026_09_27` | `TAI_SAFE_PRICING_POLICY_V3_2026_09_28` |
| **Schema version** | `SAAS_PRICING_V2` | `SAAS_PRICING_V3` |
| **Quote version** | `SAAS_QUOTE_V2` | `SAAS_QUOTE_V3` |
| **Commercial version** | `SAAS_CONTRACT_COMMERCIAL_V2` | `SAAS_CONTRACT_COMMERCIAL_V3` |
| **OBJ05 미결** | `payment_months ↔ contract.end_date` | OBJ05 결정 전 변경 없음 |

---

## 2. FIELD 가격 설계 세부

### 2-A. Resolver 호출 유지 이유

V3에서 FIELD 가격은 249,000 고정이지만 Resolver 호출은 유지한다.

**유지 근거:**
- `base_band_code` = price_master resolver가 산출한 sector/scale band metadata (`INDUSTRY_PRO`, `INDUSTRY_BUSINESS` 등)
- `base_amount` = Snapshot에 resolver 반환값으로 저장 (scale band 당시 값 기록)
- Commercial Fit Gate가 `contracted_base_band_code` vs `required_base_band_code` 비교에 사용
- FIELD 사업장이 어떤 규모 구간에 속하는지 context 유지

**결론**: Resolver → `base_band_code` + `base_amount` → `SaasSitePricingInput`에 그대로 전달 → Composer FIELD 경로는 `s.base_amount` 무시, `policy.field_base_amount` 사용.

### 2-B. FIELD 다중 사업장 정렬

모든 FIELD 사업장의 `normal = 249,000` (고정). 정렬 키:

```
-x[1] (normal_site_amount DESC)  → 모두 249,000 (동점)
→ sector ASC
→ base_band_code ASC
→ entity_type ASC
→ entity_id ASC (결정론적)
```

동점 정렬이므로 secondary key가 Primary 사업장을 결정한다. 결정론적이고 올바르다. **Composer sort 로직 변경 없음.**

### 2-C. FIELD 가격 체계 (V3 확정)

| 구성 | 계산 |
|------|------|
| Primary 사업장 | `249,000 × 100%` = 249,000원 |
| Additional 사업장 | `249,000 × 80%` = 199,200원 |
| Worker | 기존 progressive 재사용 (변경 없음) |
| Prepaid | `monthly × payment_months` |
| Discount | `payment_months` 키 조회 (V3 rate) |
| VAT | supply × 10% (기존 재사용) |

### 2-D. base_band_code 보존 판정

`SaasSiteScope.base_band_code` = price_master resolver가 산출한 scale/band metadata. FIELD V3에서도 Commercial Fit Gate의 `contracted_base_band_code`로 사용된다.

**보존 이유:**
- **FIELD price authority**: 아님 (가격은 `policy.field_base_amount`)
- **FIELD commercial scope 의미**: UNRESOLVED — Pricing V3는 FIELD 가격을 scale-independent로 확정했으나, commercial scope 관점에서 scale band가 계약 용량 기준인지는 OBJ07에서 결정
- **Scale/band metadata**: YES — 계약 시점 규모 구간 기록. Commercial Fit Gate의 scope 비교 기반.

**판정: 삭제하지 않는다.** `SaasSitePricingInput.base_band_code` 유지. Preview Service에서 resolver tier_code → `base_band_code` 전달 경로 유지.
법령엔진이 `base_band_code`를 법적 compliance 등급으로 소비한다는 증거는 이번 조사에서 확보되지 않음. 단정 금지.

---

## 3. TABLE A — File Delta Matrix

### `schemas/saas_pricing_v2.py`

| 항목 | 현재 값 | V3 변경 | 이유 |
|------|---------|---------|------|
| `SCHEMA_VERSION` | `"SAAS_PRICING_V2"` | `"SAAS_PRICING_V3"` | V3 최초 production 식별 |
| `VALID_TERM_MONTHS` | `frozenset({1,3,6,9,12})` | `VALID_PAYMENT_MONTHS` (rename) | semantic rename |
| `SaasCommercialSelection.term_months` | `StrictInt` | `payment_months: StrictInt` | rename |
| `SaasCommercialSelection._term_months_allowed` | validator name | `_payment_months_allowed` (rename) | follow field |
| `SaasPricingSnapshotV2.term_months` | `StrictInt` | `payment_months: StrictInt` | rename |
| `SaasPricingSnapshotV2._term_months_allowed` | validator name | `_payment_months_allowed` (rename) | follow field |
| `SaasPricingSnapshotV2._schema_version_canonical` | checks `"SAAS_PRICING_V2"` | checks `"SAAS_PRICING_V3"` | version bump |
| `SaasSiteScope` | unchanged | KEEP AS-IS | base_amount = resolver 당시 scale/band 반환 금액 기록. 법적 compliance evidence로 단정 금지 |
| `SaasWorkerBracketLine`, `SaasWorkerPricingSnapshot` | unchanged | KEEP AS-IS | |

**파일명**: KEEP `schemas/saas_pricing_v2.py`
**실행 시점**: Semantic-Integration (OBJ05 이후 coordinated patch). **OBJ03에서 term_months rename 금지.**

---

### `schemas/saas_pricing_policy_v2.py`

| 항목 | 현재 값 | V3 변경 | 이유 |
|------|---------|---------|------|
| `PRICING_POLICY_VERSION` | `"TAI_SAFE_PRICING_POLICY_2026_09_27"` | `"TAI_SAFE_PRICING_POLICY_V3_2026_09_28"` | V3 정책 |
| `_POLICY_EFFECTIVE_FROM` | `date(2026, 9, 27)` | `date(2026, 9, 28)` | V3 확정일 |
| `VALID_TERM_MONTHS_POLICY` | `frozenset({1,3,6,9,12})` | `VALID_PAYMENT_MONTHS_POLICY` (rename) | semantic rename |
| `SaasTermDiscountPolicy.term_months` | `StrictInt` | `payment_months: StrictInt` | rename |
| `SaasTermDiscountPolicy._term_months_allowed` | validator | rename + update reference | follow field |
| `SaasPricingPolicyV2.field_uplift_amount` | `StrictInt` | `field_base_amount: StrictInt` | 의미 변경: uplift → fixed base |
| `SaasPricingPolicyV2._field_uplift_non_negative` | `>= 0` check | `_field_base_amount_positive` (`> 0` check) | 249,000은 반드시 양수 |
| `get_canonical_pricing_policy_v2` → `field_uplift_amount=100000` | value | `field_base_amount=249000` | V3 확정 |
| `get_canonical_pricing_policy_v2` → `term_discounts` | all `None` | `[0, 500, 1000, 1500, 2000]` bps | V3 확정 |
| `primary_site_rate_bps=10000` | KEEP | KEEP AS-IS | |
| `additional_site_rate_bps=8000` | KEEP | KEEP AS-IS | |
| `worker_brackets` | KEEP | KEEP AS-IS | |
| `vat_rate_bps=1000` | KEEP | KEEP AS-IS | |
| `_validate_term_discounts` canonical check | 1,3,6,9,12 | KEEP AS-IS (값은 같음) | |

**파일명**: KEEP `schemas/saas_pricing_policy_v2.py`
**핵심 원칙**: MANAGER INDUSTRY 300+ 처리는 이 Policy 객체가 아닌 `price_master` DATA 변경이다.

---

### `services/saas_pricing_composer_v2.py`

| 항목 | 현재 코드 | V3 변경 | 이유 |
|------|----------|---------|------|
| `SaasPricingCalculationResult.term_months` | field | `payment_months` (rename) | semantic |
| Step 4 MANAGER path | `normal = s.base_amount` | KEEP AS-IS | MANAGER 로직 불변 |
| Step 4 FIELD path (line 204) | `normal = s.base_amount + policy.field_uplift_amount` | `normal = policy.field_base_amount` | V3 FIELD 고정 249,000 |
| Step 10 (line 253) | `monthly × selection.term_months` | `monthly × selection.payment_months` | rename |
| Step 11 discount lookup (line 258) | `td.term_months == selection.term_months` | `td.payment_months == selection.payment_months` | rename |
| Steps 12–15 snapshot construction | `term_months=selection.term_months` (×여러 곳) | `payment_months=selection.payment_months` | rename |
| Primary/Additional/Worker/VAT arithmetic | KEEP AS-IS | KEEP AS-IS | invariant |
| Canonical sort (`site_normals`) | KEEP AS-IS | KEEP AS-IS | FIELD 동점 정렬도 결정론적으로 올바름 |
| `SaasSitePricingInput.base_amount > 0` | KEEP AS-IS | KEEP AS-IS | MANAGER 필수; FIELD는 resolver 유효값 전달 |

**파일명**: KEEP `services/saas_pricing_composer_v2.py`
**OBJ03 범위**: FIELD formula 수정만. `term_months→payment_months` rename은 Semantic-Integration에서.
**OBJ05 dep**: NO (payment_months = 할인·계산 축만)

---

### `schemas/saas_pricing_preview_v2.py`

| 항목 | 현재 | V3 변경 |
|------|------|---------|
| `SaasPricingPreviewRequestV2.term_months` | `StrictInt` | `payment_months: StrictInt` |
| `SaasPricingPreviewResponseV2.term_months` | `int` | `payment_months: int` |
| 나머지 필드 | KEEP | KEEP AS-IS |

**파일명**: KEEP `schemas/saas_pricing_preview_v2.py`
**API surface**: `payment_months` rename. Production V2 API stored = 0이므로 clean.

---

### `services/saas_pricing_preview_v2.py`

| 항목 | 현재 | V3 변경 |
|------|------|---------|
| Step 3 CUSTOM: `term_months=request.term_months` | rename | `payment_months=request.payment_months` |
| Step 4 Selection: `term_months=request.term_months` | rename | `payment_months=request.payment_months` |
| `request.term_months` refs (lines 150–175) | rename | `request.payment_months` |
| Step 6 FIELD resolver call | KEEP AS-IS | Resolver 호출 유지 (Section 2-A) |
| Step 6 FIELD `amount_int > 0` check | KEEP AS-IS | After price_master fix, INDUSTRY amount 0 없음 |
| Step 6 MANAGER resolver call | KEEP AS-IS | 불변 |
| Response `term_months=request.term_months` | rename | `payment_months=request.payment_months` |

**파일명**: KEEP `services/saas_pricing_preview_v2.py`
**FIELD 설계 결정**: Resolver 호출 유지. Composer FIELD 경로가 `policy.field_base_amount` 사용으로 가격을 고정시킴. Preview Service는 별도 처리 불필요.

---

### `services/pricing_resolver_svc.py`

**변경 없음.** KEEP AS-IS.

`INDUSTRY_PRO criteria_max → NULL` (price_master DATA WO 후): resolver의 `hi_ok = True` (cmax=None) 경로가 300+ 자연 처리. Resolver logic 변경 0.

---

### `schemas/saas_quote_v2.py`

| 항목 | 현재 | V3 변경 |
|------|------|---------|
| `SAAS_QUOTE_SCHEMA_VERSION` | `"SAAS_QUOTE_V2"` | `"SAAS_QUOTE_V3"` |
| `SaasQuoteSnapshotItemV2.term_months` | `int` | `payment_months: int` |
| `SaasQuoteIssueRequestV2` | inherits `SaasPricingPreviewRequestV2` | 상속으로 자동 반영 (explicit 필드 없음) |

**파일명**: KEEP `schemas/saas_quote_v2.py`

---

### `services/saas_quote_v2.py`

| 항목 | 현재 코드 | V3 변경 |
|------|----------|---------|
| `_validate_snapshot_against_request` (line 74–76) | `snap.term_months != request.term_months` | `snap.payment_months != request.payment_months` |
| `_build_pricing_input` (line 107) | `"term_months": request.term_months` | `"payment_months": request.payment_months` |
| `_build_quote_item` (line 139) | `quantity=snap.term_months` | `quantity=snap.payment_months` |
| `_build_quote_item` (line 152) | `term_months=snap.term_months` | `payment_months=snap.payment_months` |
| Ownership, server re-price, snapshot freeze, amount storage, numbering, issue flow | KEEP AS-IS | 불변 |

**파일명**: KEEP `services/saas_quote_v2.py`

---

### `services/saas_payment_v2_adapter.py`

| 항목 | 현재 코드 | V3 변경 |
|------|----------|---------|
| Line 160: `period_months=snap.term_months` | rename | `period_months=snap.payment_months` |
| Schema version check (line 107) | `SAAS_QUOTE_SCHEMA_VERSION` 상수 사용 | 자동 갱신 (상수 변경으로) |
| Ownership, ISSUED, SAAS, 3-way amount, INICIS prepare | KEEP AS-IS | 불변 |

**파일명**: KEEP `services/saas_payment_v2_adapter.py`
**OBJ05 dep**: PARTIAL — `period_months`는 Payment에 저장. `contract.end_date` 연산은 `payment_post_process.py`에서 OBJ05 결정 후.

---

### `services/saas_payment_success_v2_adapter.py`

| 항목 | 현재 코드 | V3 변경 |
|------|----------|---------|
| Step 17 (line 284): `pay_period != snap.term_months` | rename | `pay_period != snap.payment_months` |
| Step 19 (line 307): `term_months=snap.term_months` | rename | `payment_months=snap.payment_months` |
| `_frozen_snapshot_to_calc_result` (line 120): `term_months=snap.term_months` | rename | `payment_months=snap.payment_months` |
| 3-way amount integrity (Steps 16) | KEEP AS-IS | 불변 |
| All ownership/status guards (Steps 1–15) | KEEP AS-IS | 불변 |

**파일명**: KEEP `services/saas_payment_success_v2_adapter.py`

**OBJ05 경계 명시:**

```
이 파일에서 결정되는 것 (OBJ05 이전 확정 가능):
  pay.period_months == snap.payment_months  (결제월수 정합성 — PASS/FAIL 판정)

이 파일에서 결정되지 않는 것 (OBJ05 DEFER):
  payment_months → contract.end_date 계산
  (payment_post_process.py lines 101-105, 117-120에서 처리)
```

---

### `schemas/saas_contract_commercial_v2.py`

| 항목 | 현재 | V3 변경 |
|------|------|---------|
| `COMMERCIAL_STORAGE_SCHEMA_VERSION` | `"SAAS_CONTRACT_COMMERCIAL_V2"` | `"SAAS_CONTRACT_COMMERCIAL_V3"` |
| `SaasContractCommercialVersionV2.term_months` | `StrictInt` | `payment_months: StrictInt` (Python schema) |
| `VALID_TERM_MONTHS` import | rename to `VALID_PAYMENT_MONTHS` | follow pricing_v2.py rename |
| DB column 최종 이름 | `term_months` (DDL not applied) | **OBJ05 DEPENDENT** — DDL 미적용이므로 V3 기준 최초 작성 가능 |

**파일명**: KEEP `schemas/saas_contract_commercial_v2.py`
**DDL**: Production 미적용. OBJ05 `payment_months` semantics 확정 후 V3 기준 최초 DDL 작성.

---

### `services/saas_contract_storage_mapper_v2.py`

| 항목 | 현재 | V3 변경 |
|------|------|---------|
| `selection.term_months` (line 73) | rename | `selection.payment_months` |
| `selection.term_months` (line 114) | rename | `selection.payment_months` |
| Mapping structure 전체 | KEEP AS-IS | 불변 |

**파일명**: KEEP `services/saas_contract_storage_mapper_v2.py`

---

### `services/saas_change_order_v2.py`

**Conflict 1 — policy_version gate (line 227)**

Production V2 Commercial = 0. 기존 V2 CV가 없으므로 V2→V3 전환 문제 없음. V3 Change Orders는 V3 policy_version으로 발행 → V3 policy_version으로 검증 → PASS. **코드 변경 불필요.**

**Conflict 2 — FIELD scale band (lines 380–382)**

현재: scale band 변경 → SCALE_BAND_INCREASE/DECREASE (가격 변화로 분류).
V3: FIELD 가격 = 249,000 고정 → scale band 변경은 **가격 변화가 아님**.

**확정된 사실 (Pricing V3 근거):**

```
FIELD scale-band 변화
→ price_delta = 0  (FIELD 가격 = 249,000 고정, scale-independent — CONFIRMED)
→ SCALE_BAND_INCREASE/DECREASE를 가격 변화 이벤트로 발행하면 안 됨
```

**미결 — commercial classification (OBJ07 결정 필요):**

`price_delta = 0`은 확정이다. 그러나 FIELD scale band 변화가 **commercial scope 이벤트**로 기록되어야 하는지는 별개의 질문이다.

- `FIELD_SCOPE_BAND_CHANGE`는 현재 `schemas/saas_change_order_v2.py` ChangeType에 존재하지 않는다.
- 존재하지 않는 enum 추가는 schema/persistence/test 영향을 포함한 별도 설계가 필요하다.
- OBJ07 Commercial Fit 설계 결정 이후에만 올바른 이벤트 분류를 확정할 수 있다.

**판정:**

`price_delta = 0` guard 코드는 OBJ07에서 commercial scope 결정 후 함께 실행. 이번 OBJ02에서는 새 enum 확정 금지. 가격 delta와 commercial 이벤트 분류를 혼합 결정하지 않는다.

**Conflict 3 — term comparison (lines 261–262)**

`current_term = cv.term_months` / `target_term = target_selection.term_months`

**OBJ05 DEFER.** `payment_months` rename + `contract.end_date` coupling 결정 후 최소 패치.

**파일명**: KEEP `services/saas_change_order_v2.py`

---

### `services/saas_renewal_v2_adapter.py` (D-A)

| 항목 | 현재 | V3 변경 |
|------|------|---------|
| Line 358: `period_months=snap.term_months` | rename | `period_months=snap.payment_months` |
| Lines 620, 622, 625: `pay.period_months != snap.term_months` | rename | `snap.payment_months` |
| Line 638: `term_months=snap.term_months` | rename | `payment_months=snap.payment_months` |
| 나머지 구조 | KEEP AS-IS | |

**파일명**: KEEP `services/saas_renewal_v2_adapter.py`

---

### `schemas/saas_commercial_fit_v2.py`

실제 소스 확인:
- `CommercialFitReasonCode`: `SITE_OUT_OF_SCOPE`, `SCALE_BAND_EXCEEDED`, `WORKER_CAPACITY_EXCEEDED`
- `SiteFitStatus`: `FIT`, `SITE_OUT_OF_SCOPE`, `SCALE_BAND_EXCEEDED`
- `CommercialFitStatus`: `FIT`, `CHANGE_REQUIRED`, `CUSTOM_REVIEW_REQUIRED`

| 항목 | 현재 | V3 변경 |
|------|------|---------|
| `CommercialFitReasonCode` enum | 3개 값 | KEEP AS-IS — 새 enum 추가 금지 (OBJ07 결정) |
| `SaasActualCommercialSiteV2.required_base_band_code` | scale band input | KEEP AS-IS |
| `SaasComplianceBandCatalogEntryV2` | band sort_order catalog | KEEP AS-IS |
| `SaasCommercialFitResultV2` | result struct | KEEP AS-IS |

**파일명**: KEEP `schemas/saas_commercial_fit_v2.py`
**Strategy**: REUSE-AS-IS (schema 변경 없음)

---

### `services/saas_commercial_fit_gate_v2.py`

실제 소스 확인:
- Step 7 (line 204–229): 각 actual site의 `required_sort > contracted_sort` → `SCALE_BAND_EXCEEDED`
- Step 8 (line 231–233): `actual_worker_count > cv.worker_capacity` → `WORKER_CAPACITY_EXCEEDED`
- Step 3 (line 85–98): `product_tier == "CUSTOM"` → `CUSTOM_REVIEW_REQUIRED`

**설계 경계:**

이 게이트는 **계약 범위(scope) 게이트**이며 **가격 게이트가 아니다.** `SCALE_BAND_EXCEEDED`는 "현재 계약 band보다 큰 규모의 사업장이 실제 운영 중"임을 의미하며, 가격 상승과 별개로 commercial scope 계약 한도를 초과했음을 의미할 수 있다.

**확정된 사실:**
- Pricing V3: FIELD 가격 = 249,000 고정 (scale-independent)

**미결 질문 (OBJ07 결정 필요):**
- FIELD 계약에서 scale band 증가는 commercial scope를 초과하는가?
  - YES → `SCALE_BAND_EXCEEDED` + `CHANGE_REQUIRED` 유지 (가격 변화 없이 계약 재협의 필요)
  - NO → `SCALE_BAND_EXCEEDED` 불발생, `FIT` 처리
  - METADATA_ONLY → `SCALE_BAND_EXCEEDED` 미발생, 별도 이벤트 or 기록 전용

Pricing V3 "FIELD 가격이 scale-independent"라는 사실만으로 Commercial scope 의미를 단정할 수 없다. 이 두 도메인은 분리된다.

**판정: REUSE-AS-IS FOR NOW.** V3 FIELD guard 코드 추가는 OBJ07에서 Commercial Fit 설계 결정 후 실행.

**파일명**: KEEP `services/saas_commercial_fit_gate_v2.py`
**Strategy**: REUSE-AS-IS FOR NOW — FIELD SCALE SEMANTICS DEFER to OBJ07

---

### `tests/test_saas_commercial_fit_gate_v2.py`

| 항목 | 변경 |
|------|------|
| MANAGER band increase 기존 테스트 | KEEP (SCALE_BAND_EXCEEDED 동작 확인) |
| FIELD band increase | BASELINE CAPTURE — 현재 동작(`SCALE_BAND_EXCEEDED`) 기록. V3 FIELD scope semantics = OBJ07 결정 후 기대값 수정 여부 확정 |
| FIELD site out of scope | BASELINE CAPTURE — `SITE_OUT_OF_SCOPE` 현재 동작 기록 |
| FIELD worker capacity exceeded | BASELINE CAPTURE — `WORKER_CAPACITY_EXCEEDED` 현재 동작 기록 |

**파일명**: KEEP `tests/test_saas_commercial_fit_gate_v2.py`
**Strategy**: BASELINE CAPTURE (FIELD scope guard 추가 = OBJ07 결정 후)

---

### Temporal / Atomic (D-B1, OBJ10-C, D-B2, D-B3)

| 파일 | V3 영향 | 판정 |
|------|---------|------|
| `payment_post_process.py` lines 101-105, 117-120 | `payment_months → contract.end_date` coupling | **OBJ05 DEPENDENT** |
| `saas_renewal_runtime_v2.py` | first_apply boundary = `contract.end_date` | REUSE-AS-IS; OBJ05 boundary verify |
| `migrations/…atomic_apply.sql` | `term_months` column, VALID constraint, 3-way guard | **OBJ05 DEPENDENT** — DDL not applied, write V3-fresh |
| `migrations/…renewal_atomic.sql` | 3-way `snap == cv == pay.period_months` | **OBJ05 DEPENDENT** — DDL not applied |

---

## 4. TABLE B — KEEP / PATCH / EVOLVE / DEFER Matrix

| Object | Strategy | Exact Symbol(s) Changed | Files | OBJ05 Dep |
|--------|----------|------------------------|-------|-----------|
| **Pricing Policy** | PATCH | `field_uplift_amount→field_base_amount`; `term_discounts`; `policy_version`; `term_months→payment_months` | `saas_pricing_policy_v2.py` | NO |
| **Pricing Core Schema** | PATCH | `SCHEMA_VERSION`; `SaasCommercialSelection.term_months→payment_months`; `SaasPricingSnapshotV2.term_months→payment_months` | `saas_pricing_v2.py` | NO |
| **Pricing Composer** | PATCH | FIELD formula (line 204); `selection.term_months→payment_months` (×8) | `saas_pricing_composer_v2.py` | NO |
| **Price Resolver** | REUSE-AS-IS | 변경 없음 | `pricing_resolver_svc.py` | NO |
| **Preview Request Schema** | EVOLVE | `term_months→payment_months` in Request + Response | `saas_pricing_preview_v2.py` | NO |
| **Preview Service** | PATCH | `request.term_months→payment_months` refs; FIELD path KEEP | `saas_pricing_preview_v2.py` | NO |
| **Quote Schema** | EVOLVE | `SAAS_QUOTE_V2→V3`; `SaasQuoteSnapshotItemV2.term_months→payment_months` | `saas_quote_v2.py` | NO |
| **Quote Service** | PATCH | `snap/request.term_months→payment_months` (×4) | `saas_quote_v2.py` (services) | NO |
| **OBJ10-A Payment Adapter** | PATCH | `snap.term_months→payment_months` (line 160) | `saas_payment_v2_adapter.py` | PARTIAL |
| **OBJ10-B Payment Success Adapter** | PATCH | `snap.term_months→payment_months` (×3); guards KEEP | `saas_payment_success_v2_adapter.py` | YES (end_date) |
| **Commercial Schema** | PATCH + OBJ05 | `COMMERCIAL_V2→V3`; Python `term_months→payment_months`; DB column OBJ05 | `saas_contract_commercial_v2.py` | YES |
| **Contract Builder** | OBJ05 DEPENDENT | `payment_months→end_date` coupling | `payment_post_process.py:101,161` | YES (core) |
| **Site Scope** | REUSE-AS-IS | 변경 없음 (DDL not applied, V3 first DDL) | `saas_contract_commercial_v2.py` | PARTIAL |
| **Storage Mapper** | PATCH | `selection.term_months→payment_months` (×2) | `saas_contract_storage_mapper_v2.py` | YES |
| **Commercial Fit Gate Schema** | REUSE-AS-IS | 변경 없음 (새 enum 추가 = OBJ07) | `saas_commercial_fit_v2.py` | NO |
| **Commercial Fit Gate Service** | REUSE-AS-IS FOR NOW | FIELD scale semantics = UNRESOLVED. OBJ07 결정 후 PATCH 여부 확정 | `saas_commercial_fit_gate_v2.py` | NO |
| **Commercial Fit Gate Tests** | BASELINE CAPTURE | 현재 동작 기록. FIELD scope V3 guard = OBJ07 결정 후 추가 | `test_saas_commercial_fit_gate_v2.py` | NO |
| **Change Order** | PATCH | Conflict 2: FIELD price_delta=0 CONFIRMED / commercial classification = UNRESOLVED / FIELD guard = NOT YET DECIDED; `term_months→payment_months` = semantic patch; Conflict 1 = no change; Conflict 3 = OBJ05 | `saas_change_order_v2.py` | YES (C3) |
| **Atomic New Contract OBJ10-C** | OBJ05 DEPENDENT | DDL not applied; V3 기준 최초 작성 | `migrations/…atomic_apply.sql` | YES |
| **Renewal Adapter D-A** | PATCH + OBJ05 | `snap.term_months→payment_months` (×4) | `saas_renewal_v2_adapter.py` | YES |
| **Temporal Logic D-B1** | OBJ05 DEPENDENT | `payment_months↔contract.end_date` | `payment_post_process.py` | YES (core) |
| **Atomic Renewal D-B2** | OBJ05 DEPENDENT | DDL not applied; V3 기준 최초 작성 | `migrations/…renewal_atomic.sql` | YES |
| **Runtime Wiring D-B3** | REUSE-AS-IS | first_apply boundary OBJ05 verify | `saas_renewal_runtime_v2.py` | YES (boundary) |
| **Legacy SaaS runtime** | LEGACY PRESERVE | 변경 금지 | V1 경로 파일들 | NO |
| **Tests** | PATCH + invariant REUSE | SUPERSEDED policy값 갱신; V3 cases 추가 | test files | PARTIAL |
| **Frontend API** | EVOLVE | `payment_months` boundary (얇은 route) | `routers/public_pricing_v2.py` | NO |
| **price_master** | DATA WO | `INDUSTRY_PRO.criteria_max→NULL`, `INDUSTRY_CUSTOM` 처리 | Production DB (Owner Gate 후) | NO |

---

## 5. TABLE C — FIELD 데이터 의존성

| 축 | V3 입력 | V3 미사용 (가격 목적) | 보존 이유 |
|----|---------|-------------------|---------|
| **PRICE 계산** | `payment_months`, `worker_capacity`, site count(len) | `sector`, `criteria_value`, `base_amount` | price = 249,000 고정 |
| **FACILITY CONTEXT** | `entity_id`, `entity_type`, `sector`, `criteria_value` | — | scope 식별, Commercial Fit Gate 입력 |
| **SCALE/BAND METADATA** | `base_band_code` (resolver tier_code) | FIELD price authority 아님 | Commercial Fit Gate `contracted_base_band_code` 사용 |
| **SNAPSHOT EVIDENCE** | `base_amount` (resolver 반환값) | FIELD price 계산 미사용 | scale band 당시 resolver 값 기록 |
| **FIELD 가격 산출** | `policy.field_base_amount = 249,000` | `s.base_amount` (Composer에서 무시) | Policy 객체가 가격 권위값 |

**base_band_code 보존 판정: 삭제하지 않는다.** `SaasSiteScope.base_band_code`는 V3 FIELD에서도 Commercial Fit Gate의 scale/band metadata로 사용된다. FIELD price authority로는 사용되지 않는다. FIELD commercial scope에서 band가 계약 용량 기준 역할을 하는지는 UNRESOLVED — OBJ07에서 결정.

---

## 6. TABLE D — price_master 변경 대안

### 현재 Production (`SAAS INDUSTRY`)

| tier_code | criteria_min | criteria_max | amount |
|-----------|-------------|-------------|--------|
| INDUSTRY_STARTER | 0 | 49 | 149,000 |
| INDUSTRY_BUSINESS | 50 | 299 | 299,000 |
| INDUSTRY_PRO | 300 | **499** | 499,000 |
| INDUSTRY_CUSTOM | 500 | NULL | **0** |

### V3 목표

```
300+ → INDUSTRY_PRO (499,000), 상한 없음
```

### 대안 A (권장) — INDUSTRY_PRO criteria_max → NULL + INDUSTRY_CUSTOM deactivate

```sql
UPDATE price_master
SET criteria_max = NULL
WHERE service_type = 'SAAS' AND sector = 'INDUSTRY' AND tier_code = 'INDUSTRY_PRO';

UPDATE price_master
SET is_active = FALSE
WHERE service_type = 'SAAS' AND sector = 'INDUSTRY' AND tier_code = 'INDUSTRY_CUSTOM';
```

**효과**:

| tier_code | criteria_max | is_active | 결과 |
|-----------|-------------|-----------|------|
| INDUSTRY_STARTER | 49 | TRUE | 0~49 |
| INDUSTRY_BUSINESS | 299 | TRUE | 50~299 |
| INDUSTRY_PRO | **NULL** | TRUE | **300+** |
| INDUSTRY_CUSTOM | NULL | **FALSE** | 조회 안 됨 |

**평가**:
- resolver 변경 0 (`cmax=None → hi_ok=True` 이미 구현)
- 중복 range 없음
- fallback ambiguity 없음
- `INDUSTRY_CUSTOM`의 `amount=0` 제거 → `COMPLIANCE_BASE_QUOTE_REQUIRED` 발생 없음
- `CUSTOM` product_tier (상품 선택)와 `INDUSTRY_CUSTOM` tier_code (규모 구간) 혼동 제거
- 유지보수 최소

### 대안 B — INDUSTRY_PRO criteria_max → NULL + INDUSTRY_CUSTOM amount 수정

```sql
UPDATE price_master
SET criteria_max = NULL
WHERE service_type = 'SAAS' AND sector = 'INDUSTRY' AND tier_code = 'INDUSTRY_PRO';

-- INDUSTRY_CUSTOM 행 유지, amount 수정 (대신 range 중복 발생)
```

**문제점**: `INDUSTRY_PRO criteria_max=NULL` 이후 `INDUSTRY_CUSTOM criteria_min=500`이 overlap. Resolver가 300~499 → PRO, 500+ → CUSTOM으로 나뉠 수 있음 (resolver 로직에 따라). 중복 range 위험.

**판정: 대안 A 권장.** INDUSTRY_CUSTOM deactivate가 명확하고 안전하다.

**실행 시점**: OBJ03 이후 Owner Gate 승인 후 별도 DATA WO 실행. 이번 OBJ02에서는 SQL 작성 금지.

---

## 7. TABLE E — 테스트 영향

### A. INVARIANT — 그대로 유지

| 대상 | 유지 이유 |
|------|---------|
| Primary/Additional site 계산 | arithmetic 불변 |
| Worker progressive 계산 | bracket 로직 불변 |
| VAT 계산 | vat_rate_bps=1000 불변 |
| Amount integrity 3-way | pay/item/snapshot 금액 검증 |
| Ownership guard | quote 소유권 |
| Atomic orchestration | ONE PAYMENT = ONE CONTRACT MUTATION |
| Replay / Race recovery | `target.effective_from` 경계 |
| INICIS exact amount path | 결제 금액 SSOT |

### B. SUPERSEDED POLICY — V3 기준으로 값 수정

| 현재 테스트 | V2 기준 | V3 수정 방향 |
|------------|---------|------------|
| FIELD uplift 테스트 | `normal = base_amount + 100,000` | `normal = 249,000` 고정으로 갱신 |
| INDUSTRY 500+ CUSTOM `amount=0` | `COMPLIANCE_BASE_QUOTE_REQUIRED` | price_master fix 후 INDUSTRY_PRO 499,000 |
| `discount_rate_bps=None` 테스트 | `TERM_DISCOUNT_UNRESOLVED` | V3 실제 rate 0/500/1000/1500/2000 bps |
| `term_months` field 이름 테스트 | `selection.term_months` | `selection.payment_months` |
| Policy version 문자열 | `TAI_SAFE_PRICING_POLICY_2026_09_27` | `TAI_SAFE_PRICING_POLICY_V3_2026_09_28` |

### C. 신규 V3 케이스 (OBJ03 이후 추가)

| 케이스 | 검증 목표 |
|--------|---------|
| FIELD 1 사업장 | `final_site_amount = 249,000` |
| FIELD 2 사업장 | Primary 249,000 / Additional 199,200 |
| FIELD 3 사업장 | Primary 249,000 / Additional × 2 (199,200 each) |
| FIELD worker 20/21/50/51/100/101/300/301명 | progressive 정확성 |
| MANAGER INDUSTRY 299/300/499/500명 | 300+ = PRO, 500 = PRO (NOT CUSTOM) |
| payment_months 1/3/6/9/12 할인 | 0/5/10/15/20% 정확성 |
| MANAGER mixed-sector facilities | 가장 높은 정상가격 facility가 Primary |
| FIELD mixed-sector facilities | 모두 249,000 normal → deterministic Primary + Additional 80% |
| VAT 계산 (supply × 10%) | FIELD/MANAGER 동일 |
| CUSTOM route | `CUSTOM_REQUIRED` 변화 없음 |
| **Commercial Fit — MANAGER band increase** | `SCALE_BAND_EXCEEDED` 유지 |
| **Commercial Fit — FIELD band increase** | BASELINE CAPTURE — 현재 동작(`SCALE_BAND_EXCEEDED`) 기록. V3 FIELD scope 기대값 = OBJ07 결정 |
| **Commercial Fit — FIELD site out of scope** | BASELINE CAPTURE — `SITE_OUT_OF_SCOPE` 현재 동작 기록 |
| **Commercial Fit — FIELD worker exceeded** | BASELINE CAPTURE — `WORKER_CAPACITY_EXCEEDED` 현재 동작 기록 |

---

## 8. CUSTOM 경로 설계

CUSTOM:
- `standard_preview = 0`
- `standard_automatic_quote = 0`

현재 `CUSTOM_REQUIRED` 분기 구조를 V3에서 재사용한다. 변경 없음. `SaasCommercialSelection(product_tier="CUSTOM")` validation, Composer Step 1 shortcut, Preview Service Step 3 shortcut 모두 유지.

---

## 9. VAT 설계

현재 Composer Step 13:
```python
vat_amount = prepaid_supply_amount * policy.vat_rate_bps // 10000
total_amount = prepaid_supply_amount + vat_amount
```

```
RAW_SUPPLY
→ discount (payment_months 기준)
→ prepaid_supply_amount
→ VAT = prepaid × 10%
→ total = prepaid + VAT
```

V3 canonical 순서와 동일. **REUSE-AS-IS.** `vat_rate_bps=1000` 변경 없음. round/truncation(integer floor) 변경 없음.

---

## 10. Versioning 설계

| Version String | V2 현재 | V3 판정 | Production stored V2 = 0인 이유 |
|----------------|---------|---------|--------------------------------|
| `SCHEMA_VERSION` | `"SAAS_PRICING_V2"` | `"SAAS_PRICING_V3"` | V3가 최초 production runtime |
| `SAAS_QUOTE_SCHEMA_VERSION` | `"SAAS_QUOTE_V2"` | `"SAAS_QUOTE_V3"` | stored quotes = 0 |
| `COMMERCIAL_STORAGE_SCHEMA_VERSION` | `"SAAS_CONTRACT_COMMERCIAL_V2"` | `"SAAS_CONTRACT_COMMERCIAL_V3"` | DDL not applied |
| `PRICING_POLICY_VERSION` | `"TAI_SAFE_PRICING_POLICY_2026_09_27"` | `"TAI_SAFE_PRICING_POLICY_V3_2026_09_28"` | V3 정책 확정 |

**V2 runtime compatibility를 위한 dual parser 근거 없음.** Version string 변경 = clean cut.

---

## 10-B. payment_months Rename — Atomic Execution 원칙

`term_months → payment_months` rename은 부분 실행 금지.

**이유:** 현재 48개 runtime hit에서 Preview / Quote / Payment / Commercial / Change Order / Renewal 전체가 `selection.term_months` / `snap.term_months` / `request.term_months`를 직접 참조한다. Pricing Schema만 먼저 rename하면 다음 Object가 완료될 때까지 repository가 불일치 상태가 된다.

**실행 조건:** OBJ05에서 `payment_months ↔ contract.end_date ↔ renewal boundary` 의미가 확정된 후, consumer chain 전체를 하나의 coordinated semantic patch에서 동시에 rename.

**최소 대상 (한 번에 정합화):**

```
schemas/saas_pricing_v2.py
schemas/saas_pricing_policy_v2.py
services/saas_pricing_composer_v2.py
schemas/saas_pricing_preview_v2.py
services/saas_pricing_preview_v2.py
schemas/saas_quote_v2.py
services/saas_quote_v2.py
services/saas_payment_v2_adapter.py
services/saas_payment_success_v2_adapter.py
schemas/saas_contract_commercial_v2.py
services/saas_contract_storage_mapper_v2.py
services/saas_change_order_v2.py
services/saas_renewal_v2_adapter.py
Atomic SQL relevant fields
Tests
```

`contract.end_date` / DB column / renewal boundary는 OBJ05 의미 결정 종속.

---

## 10-C. Discount Semantic Rename

`payment_months != contract term`으로 정책을 분리한 이상, "term discount"라는 이름을 남기면 다음 개발자가 다시 `term = 계약기간`으로 해석할 위험이 있다. Production V2 persisted = 0이므로 clean rename 시점이다.

**권장 V3 이름 (coordinated semantic patch에서 함께 실행):**

| 현재 | V3 |
|------|-----|
| `SaasTermDiscountPolicy` | `SaasPaymentDiscountPolicy` |
| `term_discounts` | `payment_discounts` |
| `term_discount_rate_bps` | `payment_discount_rate_bps` |
| `TERM_DISCOUNT_UNRESOLVED` | `PAYMENT_DISCOUNT_UNRESOLVED` |
| `VALID_TERM_MONTHS_POLICY` | `VALID_PAYMENT_MONTHS_POLICY` |

**실행 시점:** OBJ05 이후 coordinated semantic patch. payment_months rename과 동시 실행.

---

## 10-D. Version Bump Timing

다음 version string bump는 consumer chain이 정합화되는 coordinated boundary patch에서 실행. OBJ03 pricing formula patch에서 선제 bump 금지.

| Version String | 적용 시점 |
|----------------|---------|
| `SAAS_PRICING_V3` | coordinated semantic patch (OBJ04/Semantic-Integration) |
| `SAAS_QUOTE_V3` | 동시 |
| `SAAS_CONTRACT_COMMERCIAL_V3` | 동시 |
| `TAI_SAFE_PRICING_POLICY_V3_2026_09_28` | OBJ03 (policy object 단독 변경으로 안전) |

**이유:** 중간 상태에서 V3 schema version + V2 field consumer 혼합 금지.

---

## 11. 필수 결론

### 1. 신규 Backend core 파일 수

**= 0**

V3는 V2 구현 위에 policy/semantic delta만 적용한다. 신규 `_v3` 파일 생성 없음.

### 2. PATCH EXISTING 파일

```
schemas/saas_pricing_policy_v2.py           (OBJ03)
services/saas_pricing_composer_v2.py        (OBJ03)
services/saas_change_order_v2.py            (OBJ07)
services/saas_pricing_preview_v2.py         (Semantic-Integration)
services/saas_quote_v2.py                   (Semantic-Integration)
services/saas_payment_v2_adapter.py         (Semantic-Integration)
services/saas_payment_success_v2_adapter.py (Semantic-Integration)
services/saas_contract_storage_mapper_v2.py (Semantic-Integration)
services/saas_renewal_v2_adapter.py         (Semantic-Integration)
tests/* (SUPERSEDED values / V3 cases)

= 9 services + tests
```

**REUSE-AS-IS FOR NOW (OBJ07 결정 대기):**

```
services/saas_commercial_fit_gate_v2.py
tests/test_saas_commercial_fit_gate_v2.py

  → FIELD scale band commercial semantics = UNRESOLVED
  → OBJ07에서 "FIELD scale = commercial scope 한도인가?" 결정 후
     PATCH 여부 및 guard 코드 실행
```

**schemas (payment_months rename 포함):**

```
schemas/saas_pricing_v2.py          (Semantic-Integration — NOT OBJ03)
schemas/saas_pricing_preview_v2.py  (Semantic-Integration)
schemas/saas_quote_v2.py            (Semantic-Integration)
schemas/saas_contract_commercial_v2.py (Semantic-Integration + OBJ05)
```

### 3. EVOLVE BOUNDARY 파일

```
schemas/saas_pricing_preview_v2.py  (term_months→payment_months API boundary)
schemas/saas_quote_v2.py             (SAAS_QUOTE_V3 + payment_months)
schemas/saas_contract_commercial_v2.py (COMMERCIAL_V3 + payment_months; DB = OBJ05)
routers/public_pricing_v2.py         (얇은 route, payment_months boundary)

= 4 파일
```

### 4. OBJ05 DEFER 파일

```
payment_post_process.py  (lines 101-105, 117-120)
saas_contract_commercial_v2.py (DB column finalization)
migrations/…atomic_apply.sql (term_months DB column + constraint)
migrations/…renewal_atomic.sql (3-way guard)
saas_change_order_v2.py Conflict 3 (lines 261-262)
saas_renewal_runtime_v2.py (first_apply boundary verify)

= 6 영역
```

### 5. Production DATA mutation 필요 여부

**필요 (price_master):**
- `INDUSTRY_PRO.criteria_max = 499 → NULL`
- `INDUSTRY_CUSTOM.is_active = FALSE`

**시점**: OBJ03 이후 Owner Gate 승인 후 별도 DATA WO 실행. OBJ02에서 SQL 작성 금지.

### 6. OBJ03에서 실제 수정할 최소 파일 목록

**OBJ03 = Pricing Formula/Policy Patch ONLY.** `term_months` rename은 OBJ03에서 제외.

```
schemas/saas_pricing_policy_v2.py
  - field_uplift_amount → field_base_amount (= 249,000)
  - term_discounts all None → [0, 500, 1000, 1500, 2000] bps
  - PRICING_POLICY_VERSION 갱신
  (NOTE: SaasTermDiscountPolicy.term_months rename은 coordinated patch로 이동)

services/saas_pricing_composer_v2.py
  - FIELD formula: normal = policy.field_base_amount
  (NOTE: term_months refs rename은 coordinated patch로 이동)

tests/test_saas_pricing_policy_v2.py
tests/test_saas_pricing_composer_v2.py
  - SUPERSEDED policy values 갱신
  - V3 FIELD / MANAGER / discount cases 추가
```

OBJ03 commit 자체가 기존 consumer와 **일관된 runnable state**를 유지해야 한다.

`schemas/saas_pricing_v2.py`의 `term_months` rename = **OBJ03 범위 아님**.

### 7. 개정된 Object 실행 순서

```
OBJ03
— Pricing Formula/Policy Minimal Patch
  FIELD 249,000 / discounts / policy version
  term_months naming 유지 (rename = later)
  파일: saas_pricing_policy_v2.py / saas_pricing_composer_v2.py / tests

OBJ-PM-DATA  (Owner Gate 선행)
— Production price_master DATA WO
  INDUSTRY_PRO criteria_max → NULL
  INDUSTRY_CUSTOM deactivate

OBJ05
— Temporal Semantic Decision
  payment_months ↔ contract.end_date ↔ renewal boundary
  DB field semantic 확정

Semantic-Integration  (OBJ04 대체)
— Coordinated payment_months rename
  모든 consumer chain 동시 정합
  discount semantic rename (SaasPaymentDiscountPolicy 등)
  version strings 동시 bump (SAAS_PRICING_V3 등)

OBJ06
— Commercial / Atomic Integration
  OBJ10-A/B Semantic-Integration 기반 패치
  Commercial DDL V3 기준 최초 작성 (OBJ05 기반)

OBJ07
— Change Order + Commercial Fit + Renewal Integration
  DESIGN DECISION: "FIELD scale band = commercial scope 계약 한도인가?"

  A. YES — FIELD scale band = 계약 한도
     Commercial Fit: required_sort > contracted_sort → SCALE_BAND_EXCEEDED → CHANGE_REQUIRED 유지
                     FIELD guard 추가하지 않음. 현재 동작 그대로.
     Change Order: price_delta = 0 유지. commercial event/classification 방식은 OBJ07에서 설계.

  B. NO — FIELD scale band ≠ 계약 한도
     Commercial Fit: FIELD scale 증가로 SCALE_BAND_EXCEEDED 발생하지 않도록 Step 7 guard patch.
     Change Order: price_delta = 0. scale event 처리 여부 OBJ07 확정.

  C. METADATA_ONLY — FIELD scale band = scope metadata only
     Commercial Fit: scale 증가만으로 CHANGE_REQUIRED 발생하지 않음.
                     Metadata 기록 방식은 OBJ07에서 별도 결정. 새 enum 사전 확정 금지.

  결정 후 Commercial Fit Gate + Change Order Conflict 2 최소 패치 실행
  D-A/B1/B2/B3 OBJ05 기반 패치

REFREEZE
— full regression / V3 E2E
```

**의존성 원칙:** OBJ05 결정 전 contract semantic rename 금지. 번호보다 dependency가 우선.

---

## 12. Gate 상태

```
BE-V3-OBJ02 = COMPLETE (REVIEW_REQUIRED)
→ GPT 독립검증 대기

다음 Gate (OBJ02 GPT PASS 후):
  BE-V3-OBJ03 — Pricing Core Minimal Patch

  코드 대상:
    schemas/saas_pricing_policy_v2.py
    services/saas_pricing_composer_v2.py
    tests/test_saas_pricing_policy_v2.py
    tests/test_saas_pricing_composer_v2.py

  OBJ03 금지:
    schemas/saas_pricing_v2.py 변경
    term_months / payment_months rename
    SAAS_PRICING_V3 / SAAS_QUOTE_V3 version bump
    Commercial schema 변경
```

---

## 13. 불변 조건

```
schemas 변경:      0 (이번 WO는 설계 문서만)
services 변경:     0
tests 실행:        0
migrations:        0
production reads:  0
production DDL:    0
production mutation: 0
deploy:            0
PR:                0
merge:             0
```
