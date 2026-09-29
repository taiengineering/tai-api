---
title: TAI Safe Pricing V2 — OBJ00 Current State Evidence Report
status: EVIDENCE_REPORT
goal: G-muju80oq-0a7566
collected_by: Claude Code (COLLECT role)
collected_date: 2026-09-27
review_required: GPT REVIEW REQUIRED
---

# TAI Safe Pricing V2 — OBJ00 현재 상태 증거 보고서

---

## OBJ00-A: Repo Anchors

**OBSERVED:**
- tai-api: `/Users/taiwangsim/tai-api` / branch: `docs/pricing-canonical-20260927` / HEAD: `512431c2`
- tai-admin: `/Users/taiwangsim/Desktop/tai-engineering/tai-admin` / branch: `feat/sem003-diving-family-ui` / HEAD: `6c84dc54` / main HEAD: `5f2d2cb0`
- tai-www: `/Users/taiwangsim/Desktop/tai-www` / branch: `feat/paid-leg-front-parity` / HEAD: `fd5046a0` / main HEAD: `daa80dfa`
- Supabase project: taieng / ref: `vwlahtguyggrhvslabax`

**EVIDENCE:** `git -C /Users/taiwangsim/tai-api rev-parse HEAD` → `512431c2...`

---

## OBJ00-B: Canonical Document Locations

**OBSERVED:**
- `docs/TAI_SAFE_PRICING_CANONICAL.md` — 현행 정본 포인터 (2026-09-27 생성)
- `docs/2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md` — 최종 정본 문서 (2026-09-27 생성)
- `docs/2026-09-27_TAI_SAFE_PRICING_V2_IMPLEMENTATION_PLAN.md` — V2 구현계획서 (2026-09-27 생성)
- `docs/PRICING_FINAL.md` — V4 구 SoT (Historical only, superseded)
- `docs/SAAS_PRICING_FINAL_20260424.md` — V2 구 가격표 (Historical, INDUSTRY_STARTER_V2=79K, CONSTRUCTION_STANDARD_V2=145K)
- `docs/workorder-be02-pricing-cleanup.md` — 법령진단 price_diagnosis_report 중복 정리 WO (완료)

**EVIDENCE:**
- `tai-api/docs/TAI_SAFE_PRICING_CANONICAL.md`
- `tai-api/docs/2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md`

---

## OBJ00-C: DB Schema Inventory

### price_master
**OBSERVED:** columns: `id, service_type, sector, tier_code, criteria_type, criteria_min, criteria_max, amount, vat_included, vat_rate, billing_unit, display_name, sub_label, icon, is_recommended, is_active, sort_order`

**EVIDENCE:** `tai-api/services/pricing_resolver_svc.py` `PRICE_MASTER_FIELDS` (line ~15)

### contracts
**OBSERVED:** columns (relevant): `id, company_id, service_type, sector, plan_code, supply_amount, vat_amount, total_amount, billing_unit, term_months, status, start_date, end_date`

**EVIDENCE:** Supabase DB inspect / `tai-api/routers/contracts.py` line 123-134

### subscriptions
**OBSERVED:** columns (relevant): `id, company_id, user_id, product_type, plan_code, plan_name, amount, supply_amount, vat_amount, status, billing_key_id, inicis_order_id, charge_cycle`

**EVIDENCE:** `tai-api/supabase/migrations/20260423_billing_phase2_schema_adjust.sql` (billing_key_id nullable, inicis_order_id added)

### payments
**OBSERVED:** columns (relevant): `id, company_id, user_id, contract_id, product_type, plan_code, period_months, total_amount, supply_amount, vat_amount, pg_method, payment_method, payment_type, status_code, service_status, paid_at, expired_at`

**EVIDENCE:** `tai-api/docs/sql/20260831_tai_time_kst_cutover_up.sql` line 306 (SELECT 전체 컬럼 목록)

### saas_tier_upgrade_transitions
**OBSERVED:** 0 rows (실제 업그레이드 전환 이력 없음)

**EVIDENCE:** Supabase SQL `SELECT count(*) FROM saas_tier_upgrade_transitions` → 0

**EVIDENCE:** migration file: `tai-api/migrations/2026-09-10_saas_tier_upgrade_transitions.sql` (파일 존재 확인, 내용 읽기 실패 — 0바이트 또는 접근 불가)

### price_service_feature
**OBSERVED:** price_master와 JOIN되어 features 리스트 제공

**EVIDENCE:** `tai-api/services/pricing_resolver_svc.py` `load_prices()` 함수

### price_saas_plan (레거시)
**OBSERVED:** 여전히 3개 라우터에서 직접 읽기: `payment_activation_api.py`, `price_setting.py`, `pricing_validation_api.py`

`pricing_validation_api.py` 주석(line 4): "Single Pricing Source: price_master (price_saas_plan / price_diagnosis_report = price_master 위 호환 뷰)"

`public_pricing.py` v3.0.0(2026-06-05) 주석: "price_saas_plan/price_diagnosis_report 직접 참조 제거"

**EVIDENCE:** `grep "price_saas_plan" routers/ -r` → 5개 파일 히트

### product_pricing (레거시)
**OBSERVED:** `product_pricing.py` 라우터가 `product_pricing` 테이블에 CRUD. `pricing_validation_api.py` 2026-07-23 교차검증 제거, "테이블 격리 준비" 상태

**EVIDENCE:** `tai-api/routers/product_pricing.py` line 45, 56

---

## OBJ00-D: price_master Snapshot (SAAS, 2026-09-27)

**OBSERVED:** SAAS service_type 10 rows

| tier_code | sector | criteria_type | criteria_min | criteria_max | amount | sort_order |
|---|---|---|---|---|---|---|
| BUILDING_BASIC | FACILITY | FLOOR_AREA | 0 | 5000 | 149000 | 1.0 |
| BUILDING_STANDARD | FACILITY | FLOOR_AREA | 5001 | 999999 | 349000 | 2.0 |
| BUILDING_CUSTOM | FACILITY | null | null | null | 0 | 3.0 |
| INDUSTRY_STARTER | INDUSTRIAL | WORKER_COUNT | 0 | 49 | 149000 | 1.0 |
| INDUSTRY_BUSINESS | INDUSTRIAL | WORKER_COUNT | 50 | 299 | 299000 | 2.0 |
| INDUSTRY_PRO | INDUSTRIAL | WORKER_COUNT | 300 | 499 | 499000 | 3.0 |
| INDUSTRY_CUSTOM | INDUSTRIAL | null | null | null | 0 | 4.0 |
| CONSTRUCTION_STANDARD | CONSTRUCTION | CONTRACT_AMOUNT | 0 | 5000000000 | 249000 | 1.0 |
| CONSTRUCTION_PREMIUM | CONSTRUCTION | CONTRACT_AMOUNT | 5000000000 | 9999999999999 | 499000 | 2.0 |
| CONSTRUCTION_CUSTOM | CONSTRUCTION | null | null | null | 0 | 3.0 |

**EVIDENCE:** Supabase SQL `SELECT tier_code, sector, criteria_type, criteria_min, criteria_max, amount, sort_order FROM price_master WHERE service_type='SAAS' ORDER BY sector, sort_order`

---

## OBJ00-E: Contract Inventory (2026-09-27)

**OBSERVED:** 총 7개 SAAS contracts

| plan_code | status | amount | count |
|---|---|---|---|
| BUILDING_BASIC_V3 | ACTIVE | 149000 | 2 |
| BUILDING_STANDARD_V3 | ACTIVE | 349000 | 1 |
| CONSTRUCTION_PREMIUM_V2 | ACTIVE | 499000 | 1 |
| CONSTRUCTION_STANDARD_V2 | ACTIVE | 249000 | 1 |
| INDUSTRY_BUSINESS_V2 | ACTIVE | 299000 | 1 |
| INDUSTRY_PRO | ACTIVE | 499000 | 1 |

plan_code suffix 패턴: `_V2`, `_V3` 혼재. `INDUSTRY_PRO`는 suffix 없음.

**EVIDENCE:** Supabase SQL `SELECT plan_code, status, total_amount FROM contracts WHERE service_type='SAAS' AND status='ACTIVE'`

---

## OBJ00-F: Subscription Inventory (2026-09-27)

**OBSERVED:** 총 41 subscriptions (전체 PENDING)

plan_code 세대별 현황:

| plan_code | amount | count |
|---|---|---|
| IND_STARTER | 79000 | 1 |
| BUILDING_BASIC | 131818 | 1 |
| BUILDING_BASIC_V3 | 149000 | 9 |
| BUILDING_STANDARD | 249000 | 1 |
| BUILDING_STANDARD_V3 | 349000 | 2 |
| CONSTRUCTION_PREMIUM_V2 | 499000 | 1 |
| CONSTRUCTION_STANDARD_V2 | 249000 | 1 |
| INDUSTRY_BUSINESS_V2 | 299000 | 2 |
| INDUSTRY_PRO | 499000 | 1 |
| INDUSTRY_STARTER_V3 | 149000 | 9 |
| (기타 세대) | 다수 | 나머지 |

- `IND_STARTER` (79000) — V1 구 코드
- `BUILDING_BASIC` (131818) — 공급가 역산 방식의 구 금액
- `BUILDING_STANDARD` (249000) — V3 이전 금액
- 최신 세대: `BUILDING_BASIC_V3`, `BUILDING_STANDARD_V3`, `INDUSTRY_STARTER_V3` 등 (_V3 suffix)

**EVIDENCE:** Supabase SQL `SELECT plan_code, amount, count(*) FROM subscriptions GROUP BY plan_code, amount ORDER BY count DESC`

---

## OBJ00-G: saas_tier_upgrade_transitions

**OBSERVED:** 0 rows

**EVIDENCE:** Supabase SQL `SELECT count(*) FROM saas_tier_upgrade_transitions` → `{"count": 0}`

---

## OBJ00-H: Backend Producer 파일 목록

**OBSERVED:** pricing 관련 서비스·라우터 파일 목록 (tai-api main branch)

| 파일 | 역할 |
|---|---|
| `services/pricing_resolver_svc.py` | price_master 조회 + 플랜 매칭 (SSOT 소비) |
| `services/tier_payment_gate_svc.py` | LEG 진입 전 SaaS tier 게이트 |
| `services/tier_upgrade_svc.py` | 플랜 업그레이드 트랜지션 |
| `services/member_quote_svc.py` | 견적 계산 + snapshot |
| `routers/public_pricing.py` | 공개 pricing API (v3.0.0) |
| `routers/payment_plan_resolver.py` | 계약별 금액 조회 |
| `routers/payment.py` | 결제 처리 + plan_code 전달 |
| `routers/payment_billing.py` | 빌링(구독 결제) |
| `routers/contracts.py` | 계약 CRUD |
| `routers/price_master_admin.py` | price_master CRUD API |
| `routers/payment_activation_api.py` | price_saas_plan 직접 읽기 (레거시) |
| `routers/price_setting.py` | price_saas_plan CRUD (레거시) |
| `routers/product_pricing.py` | product_pricing 테이블 CRUD (레거시) |
| `routers/pricing_validation_api.py` | price_master 무결성 검증 |

**EVIDENCE:** `find tai-api/ -name "*.py" | xargs grep -l "price_master\|plan_code\|tier_code"` 결과

---

## OBJ00-I: 핵심 Backend 파일 상세

### pricing_resolver_svc.py
**OBSERVED:**
```python
PRICE_MASTER_FIELDS = "id, service_type, sector, tier_code, criteria_type, criteria_min, criteria_max, amount, vat_included, vat_rate, billing_unit, display_name, sub_label, icon, is_recommended, is_active, sort_order"

def load_prices(supabase, service_type, sector=None) -> list:
    # price_master + price_service_feature JOIN, features 리스트 포함 반환

def resolve_plan(supabase, service_type, sector, value=None) -> dict:
    # WORKER_COUNT/FLOOR_AREA: criteria_min <= value <= criteria_max (inclusive)
    # CONTRACT_AMOUNT: criteria_min <= value < criteria_max (exclusive upper)
    # 반환: {"status": "success", "data": row, "matched_by": "criteria"|"default"}
```
**EVIDENCE:** `tai-api/services/pricing_resolver_svc.py`

### public_pricing.py
**OBSERVED:**
- Router prefix: `"/public/pricing"` (코드 기준)
- 파일 상단 주석에 `prefix="/n"` 기재 — GPT REVIEW REQUIRED
- 테스트 파일은 `/n/saas-plans` 경로 참조
- 5분 in-memory 캐시
- Endpoints: `/saas-plans`, `/diagnosis-reports`, `/all`, `/resolve`, `/saas`(legacy), `/diagnosis`(legacy), `/cache`(DELETE)

**EVIDENCE:** `tai-api/routers/public_pricing.py` line 2, router prefix 선언부 / 테스트 파일 grep 결과

### tier_payment_gate_svc.py
**OBSERVED:**
- `resolve_saas_tier_gate_context()`: factory 또는 site 로드 → 유일한 ACTIVE SAAS contract 로드 → `_match_current_plan` → `resolve_plan` → sort_order 비교 → FIT(>=) or UPGRADE_REQUIRED(<)
- `_match_current_plan`: `contract.plan_code` vs `price_master.tier_code` 정확한 UPPER 매칭
- `_normalize_tier` (payment_plan_resolver.py): `_V\d+` suffix 제거하여 price_master lookup

**EVIDENCE:** `tai-api/services/tier_payment_gate_svc.py`, `tai-api/routers/payment_plan_resolver.py`

### tier_upgrade_svc.py
**OBSERVED:**
- `prepare_saas_tier_upgrade()`: delta = target_supply - current_supply → `saas_tier_upgrade_transitions` INSERT (status=PREPARED)
- `apply_saas_tier_upgrade()`: `contracts.plan_code` + `subscriptions.plan_code` 동시 UPDATE

**EVIDENCE:** `tai-api/services/tier_upgrade_svc.py`

### payment_plan_resolver.py
**OBSERVED:**
```python
def _normalize_tier(plan_code: str) -> str:
    code = re.sub(r"_V\d+$", "", code)  # INDUSTRY_STARTER_V2 → INDUSTRY_STARTER
    return code

# GET /plan-amount: normalized tier_code로 price_master 조회
# CUSTOM or amount<=0 → resolvable=false
```
**EVIDENCE:** `tai-api/routers/payment_plan_resolver.py`

### member_quote_svc.py
**OBSERVED:**
- `calc_quote(supabase, service_type, sector, tier_code, term_months)`: price_master 조회, VAT 서버 계산
- `_snapshot_item()`: 견적 생성 시점 가격 불변 스냅샷
- `create_auto_quote()`: 서버 재계산, 클라이언트 금액 신뢰 안 함

**EVIDENCE:** `tai-api/services/member_quote_svc.py`

---

## OBJ00-J: LEG Gate Paths

**OBSERVED:**
`_assert_saas_tier_fit_http(supabase, current, *, factory_id=None, site_id=None)` 호출 경로:

| Route | Method | Line | Arg |
|---|---|---|---|
| `/diagnose/industrial-leg` | POST | ~144 | factory_id |
| `/diagnose/construction-leg` | POST | ~178 | site_id |
| `/diagnose/building-leg` | POST | ~207 | factory_id |

결과: FIT → 200 통과 / UPGRADE_REQUIRED → HTTP 402 `SAAS_TIER_UPGRADE_REQUIRED` / PRICING_NOT_FOUND → 503 / 기타 TierGateError → 409

**EVIDENCE:** `tai-api/routers/legal_engine.py` `_assert_saas_tier_fit_http` 함수 및 3개 route 호출부

---

## OBJ00-K: Quote Consumer

**OBSERVED:**
- `routers/member_quotes.py`: `tier_code` 수신 → `member_quote_svc.calc_quote()` 호출
- `routers/admin_quotes.py`: plan_code 참조

**EVIDENCE:**
```
# member_quotes.py
tier_code: str  (line 29)
get_supabase(), body.service_type, body.sector, body.tier_code, body.term_months  (line 64)
```

---

## OBJ00-L: Payment / Billing Consumer

**OBSERVED:**

### payment.py
- `payment.get("plan_code")` → `_fire_automation("payment.failed", {..., "plan_code": ...})` (lines 152, 183)
- `process_card_success(..., plan_code=payment.get("plan_code"), ...)` (line 168)
- `_sector_from_plan_code(plan_code)`: plan_code 앞 단어 → sector 파생 (BUILDING/INDUSTRY/CONSTRUCTION)

**EVIDENCE:** `tai-api/routers/payment.py` lines 152, 168, 183 / `tai-api/services/payment_svc.py` lines 46-57

### payment_billing.py
- `_charge_subscription_once(supabase, subscription, ...)`: subscription에서 `plan_code`, `amount`, `supply_amount`, `vat_amount` 직접 읽어 payments 테이블 INSERT
- 구독 상태: PENDING→ACTIVE→CANCELLED/PAUSED/FAILED

**EVIDENCE:** `tai-api/routers/payment_billing.py` lines 301-339

---

## OBJ00-M: tai-www Pricing UI Inventory

**OBSERVED:**

### 파일 구조
| 파일 | 역할 |
|---|---|
| `src/lib/modules/pricing.js` | SAAS/DIAG 데이터 상수 + API fallback |
| `src/lib/api.js` | API endpoint 매핑 |
| `src/lib/render/pricingCards.js` | 카드 렌더러 |
| `src/pages/pricing.astro` | 메인 요금제 페이지 |
| `src/pages/service/saas.astro` | SaaS 소개 페이지 |
| `src/pages/free-diagnosis.astro` | 무료진단 (하드코딩 가격 포함) |

### API 호출 (src/lib/api.js)
```javascript
all:              direct('/public/pricing/all'),
saasPlans:        direct('/public/pricing/saas-plans'),
diagnosisReports: direct('/public/pricing/diagnosis-reports'),
resolve:          direct('/public/pricing/resolve' + qs(params)),
```

### 하드코딩 SAAS 가격 (src/lib/modules/pricing.js)
| plan_code | price | sector |
|---|---|---|
| BUILDING_BASIC_V3 | 149000 | FACILITY |
| BUILDING_STANDARD_V3 | 349000 | FACILITY |
| BUILDING_CUSTOM_V3 | 0 | FACILITY |
| INDUSTRY_STARTER_V3 | 149000 | INDUSTRIAL |
| INDUSTRY_BUSINESS_V3 | 299000 | INDUSTRIAL |
| INDUSTRY_PRO_V3 | 499000 | INDUSTRIAL |
| INDUSTRY_CUSTOM_V3 | 0 | INDUSTRIAL |
| CONSTRUCTION_STANDARD_V3 | 249000 | CONSTRUCTION |
| CONSTRUCTION_PREMIUM_V3 | 499000 | CONSTRUCTION |
| CONSTRUCTION_CUSTOM_V3 | 0 | CONSTRUCTION |

### 하드코딩 DIAG 가격 (src/lib/modules/pricing.js)
| plan_code | price |
|---|---|
| BUILDING_BASIC_DIAG_V4 | 149000 |
| BUILDING_STANDARD_DIAG_V4 | 349000 |
| INDUSTRY_STARTER_DIAG_V4 | 149000 |
| INDUSTRY_BUSINESS_DIAG_V4 | 299000 |
| INDUSTRY_PRO_DIAG_V4 | 499000 |
| CONSTRUCTION_STANDARD_DIAG_V4 | 249000 |
| CONSTRUCTION_PREMIUM_DIAG_V4 | 499000 |

API 응답 있을 경우 `normalizeSaasAPI()` / `normalizeDiagAPI()`로 오버라이드. 없을 경우 하드코딩 fallback 사용.

**EVIDENCE:** `tai-www/src/lib/modules/pricing.js` lines 11-62, 84-138

---

## OBJ00-N: tai-www 가격 관련 현재 문구

**OBSERVED:**

### pricing.astro 주요 문구
- "시설 1개 기준 / 월 · VAT 별도 · 관리자/작업자 무제한"
- "월 구독 기준이며, 구독은 언제든지 취소 가능하며 위약금이 없습니다."
- "법령진단은 1회성 단건 결제 서비스"
- "결제일로부터 3개월간 안전관리 설계서 재발행·조회가 가능"
- "SaaS 구독은 결제 후 7일 이내 이용 내역이 없을 경우 전액 환불"

### free-diagnosis.astro 하드코딩 가격 (구 가격)
```javascript
// line 1234-1235 (INDUSTRY fallback)
const feeMap = { BUILDING: paidFee || 99000, INDUSTRY: 79000, CONSTRUCTION: 145000 };
// line 1267-1269 (old tier cards)
{ code:'BASIC', name:'PAID-1', price:79000 }
{ code:'STANDARD', name:'PAID-2', price:149000 }
{ code:'PREMIUM', name:'PAID-3', price:249000 }
```

**EVIDENCE:** `tai-www/src/pages/pricing.astro` lines 296-416 / `tai-www/src/pages/free-diagnosis.astro` lines 1234-1269

---

## OBJ00-O: tai-admin Commercial Context Inventory

**OBSERVED:**

### useAuth.ts (vue3/src/composables/useAuth.ts)
localStorage 키 목록: `contract_plan_code`, `contract_sector`, `contract_level`, `contract_addons`

```typescript
// PLAN_MAP (lines 46-60) — plan_code → level + sector 매핑 (하드코딩)
const PLAN_MAP: Record<string, { level: number, sector: string }> = {
  FREE:                  { level: 0, sector: 'FREE' },
  BUILDING_BASIC:        { level: 1, sector: 'FACILITY' },
  BUILDING_STANDARD:     { level: 2, sector: 'FACILITY' },
  BUILDING_CUSTOM:       { level: 3, sector: 'FACILITY' },
  INDUSTRY_STARTER:      { level: 1, sector: 'INDUSTRIAL' },
  INDUSTRY_BUSINESS:     { level: 2, sector: 'INDUSTRIAL' },
  INDUSTRY_PRO:          { level: 3, sector: 'INDUSTRIAL' },
  INDUSTRY_CUSTOM:       { level: 4, sector: 'INDUSTRIAL' },
  CONSTRUCTION_STANDARD: { level: 1, sector: 'CONSTRUCTION' },
  CONSTRUCTION_PREMIUM:  { level: 2, sector: 'CONSTRUCTION' },
  CONSTRUCTION_CUSTOM:   { level: 3, sector: 'CONSTRUCTION' },
}
```

로그인 시 `contract.plan_code`를 `PLAN_MAP[planCode.toUpperCase()]`으로 조회하여 sector/level 결정.
미상 plan_code → `{ level: 0, sector: '' }` (실패-오픈, nav 전체 노출)

**EVIDENCE:** `tai-admin/vue3/src/composables/useAuth.ts` lines 18, 46-60, 127-133

### diagnosis-purchaseFormat.ts (vue3/src/utils/)
```typescript
export const SECTOR_PRICES: Record<string, SectorPriceTable> = {
  BUILDING:         { s2: 29000,  s3: 59000 },
  MANUFACTURING:    { s2: 49000,  s3: 99000 },
  CONSTRUCTION:     { s2: 79000,  s3: 149000 },
  SPECIAL_FACILITY: { s2: 49000,  s3: 99000 },
}
```
이 파일은 구 diagnosis 2단계/3단계 가격 테이블 (현행 price_master 기준 아님).

**EVIDENCE:** `tai-admin/vue3/src/utils/diagnosis-purchaseFormat.ts` lines 11-14

---

## OBJ00-P: tai-admin Tier Gate Inventory

**OBSERVED:**

### tierPaymentGateContract.ts
**경로:** `vue3/src/composables/tierPaymentGateContract.ts`

핵심 기능:
- `buildTierGateEndpoint(target)`: `GET /payments/tier-gate?factory_id=...` 또는 `?site_id=...`
- `prepareTierUpgrade()`: `POST /payments/tier-upgrade/prepare`
- `parseTierGateResult()`: status=`FIT`|`UPGRADE_REQUIRED` 파싱
- 금액·플랜코드·업그레이드 로직 없음 — 서버 응답 보존·표시만

**EVIDENCE:** `tai-admin/vue3/src/composables/tierPaymentGateContract.ts` (467 lines)

### useTierPaymentGate.ts
**경로:** `vue3/src/composables/useTierPaymentGate.ts`

`createTierPaymentGateController`를 Vue reactive state로 래핑.
export: `loadTierGate(target)`, `prepareTierUpgrade(target, buyer, returnUrl?)`

**EVIDENCE:** `tai-admin/vue3/src/composables/useTierPaymentGate.ts`

### TierPaymentGateAlert.vue
**경로:** `vue3/src/components/TierPaymentGateAlert.vue`

```
서버 GET /payments/tier-gate 결과만 보여 준다. 호출·라우팅·단위환산 없음.
```
FIT → "현재 결제 등급: {planDisplayLabel}" / UPGRADE_REQUIRED → "현재 등급 + 필요 등급" 표시

**EVIDENCE:** `tai-admin/vue3/src/components/TierPaymentGateAlert.vue` lines 3, 56-75

### tierPaymentLaunch.ts
**경로:** `vue3/src/composables/tierPaymentLaunch.ts`

주석 line 2: "provider script / amount / plan 을 프론트에서 다루지 않는다. field 는 token 하나."

**EVIDENCE:** `tai-admin/vue3/src/composables/tierPaymentLaunch.ts` line 2

### 소비 위치
| 파일 | 역할 |
|---|---|
| `vue3/src/pages/construction-extraction/useConstructionExtraction.ts` | LEG 진입 전 site_id 기준 gate 체크 |
| `vue3/src/pages/diagnosis-step1/useDiagnosisStep1List.ts` | LEG 진입 전 factory_id 기준 gate 체크 |

**EVIDENCE:** `grep useTierPaymentGate vue3/src/ -r` 결과

---

## OBJ00-Q: 하드코딩 값 레지스터

**OBSERVED:**

| 값 | 위치 | 파일 | 비고 |
|---|---|---|---|
| 149000 | `SAAS.BUILDING[0].price` | tai-www/src/lib/modules/pricing.js:13 | BUILDING_BASIC_V3 |
| 349000 | `SAAS.BUILDING[1].price` | tai-www/src/lib/modules/pricing.js:15 | BUILDING_STANDARD_V3 |
| 149000 | `SAAS.INDUSTRY[0].price` | tai-www/src/lib/modules/pricing.js:21 | INDUSTRY_STARTER_V3 |
| 299000 | `SAAS.INDUSTRY[1].price` | tai-www/src/lib/modules/pricing.js:23 | INDUSTRY_BUSINESS_V3 |
| 499000 | `SAAS.INDUSTRY[2].price` | tai-www/src/lib/modules/pricing.js:25 | INDUSTRY_PRO_V3 |
| 249000 | `SAAS.CONSTRUCTION[0].price` | tai-www/src/lib/modules/pricing.js:31 | CONSTRUCTION_STANDARD_V3 |
| 499000 | `SAAS.CONSTRUCTION[1].price` | tai-www/src/lib/modules/pricing.js:33 | CONSTRUCTION_PREMIUM_V3 |
| 79000 | `feeMap.INDUSTRY` | tai-www/src/pages/free-diagnosis.astro:1234 | 구 가격 fallback |
| 99000 | `feeMap.BUILDING` | tai-www/src/pages/free-diagnosis.astro:1234 | 구 가격 fallback |
| 145000 | `feeMap.CONSTRUCTION` | tai-www/src/pages/free-diagnosis.astro:1234 | 구 가격 fallback |
| 79000 | `price:79000` (BASIC tier card) | tai-www/src/pages/free-diagnosis.astro:1267 | 구 BASIC 가격 |
| 149000 | `price:149000` (STANDARD tier card) | tai-www/src/pages/free-diagnosis.astro:1268 | 구 STANDARD 가격 |
| 249000 | `price:249000` (PREMIUM tier card) | tai-www/src/pages/free-diagnosis.astro:1269 | 구 PREMIUM 가격 |
| 29000,59000 | BUILDING s2/s3 | tai-admin/vue3/src/utils/diagnosis-purchaseFormat.ts:11 | 구 진단 가격 |
| 49000,99000 | MANUFACTURING s2/s3 | tai-admin/vue3/src/utils/diagnosis-purchaseFormat.ts:12 | 구 진단 가격 |
| 79000,149000 | CONSTRUCTION s2/s3 | tai-admin/vue3/src/utils/diagnosis-purchaseFormat.ts:13 | 구 진단 가격 |

**EVIDENCE:** grep 결과 및 파일 직접 확인

---

## OBJ00-R: 테스트 파일

**OBSERVED:**
- tai-api 총 테스트 파일: 383개 (`find . -name "test_*.py" -o -name "*_test.py"`)
- `tests/test_pricing_resolver.py` 존재 확인
- `tests/test_tier_payment_gate.py` 존재 확인
- tai-admin: `vue3/src/composables/__tests__/tierPaymentLaunch.test.mjs` 존재
- tai-admin: `vue3/src/pages/construction-extraction/__tests__/constructionExtraction.test.ts` 존재

**EVIDENCE:** `find tai-api/tests -name "*pricing*" -o -name "*tier*"` 결과

---

## OBJ00-S: 마이그레이션 파일

**OBSERVED:**

| 파일 | 내용 |
|---|---|
| `migrations/2026-09-10_saas_tier_upgrade_transitions.sql` | saas_tier_upgrade_transitions 테이블 생성 (내용 읽기 불가 — 파일 크기 0 또는 접근 실패) |
| `supabase/migrations/20260423_billing_phase2_schema_adjust.sql` | subscriptions.billing_key_id NULLABLE, inicis_order_id 컬럼 추가, payments UNIQUE constraint |

**EVIDENCE:** `find . -name "*.sql" -path "*/migrations/*"` 결과

---

## OBJ00-T: 의존 엣지 요약

**OBSERVED:**

```
price_master (SAAS, DIAGNOSIS)
  ← pricing_resolver_svc.load_prices()   [READ]
  ← pricing_resolver_svc.resolve_plan()  [READ]
      ← tier_payment_gate_svc             [내부 호출]
          ← legal_engine.py _assert_saas_tier_fit_http
              ← /diagnose/industrial-leg
              ← /diagnose/construction-leg
              ← /diagnose/building-leg
      ← member_quote_svc.calc_quote()
          ← routers/member_quotes.py
      ← payment_plan_resolver.py /plan-amount
          (+ _normalize_tier: INDUSTRY_STARTER_V2 → INDUSTRY_STARTER)
  ← public_pricing.py /public/pricing/*   [READ, 5분 캐시]
      ← tai-www src/lib/api.js
          ← src/lib/modules/pricing.js fetchFromAPI()
              ← pricing.astro, pricingCards.js

contracts.plan_code
  ← tier_payment_gate_svc._match_current_plan()  [vs price_master.tier_code UPPER match]
  ← _normalize_tier()                             [_V\d+ 제거]
  ← tier_upgrade_svc.apply_saas_tier_upgrade()   [UPDATE]
  ← payment.py / payment_billing.py              [READ plan_code]
  ← useAuth.ts PLAN_MAP                          [로그인 시 nav gate]
      (매핑: BUILDING_BASIC → {level:1, sector:'FACILITY'}, ...)

subscriptions.plan_code
  ← payment_billing.py _charge_subscription_once [READ]
  ← tier_upgrade_svc.apply_saas_tier_upgrade()   [UPDATE]

price_saas_plan (레거시, 아직 직접 읽기)
  ← payment_activation_api.py   [READ, "Single Pricing Source" 구 주석]
  ← price_setting.py            [CRUD]
  ← pricing_validation_api.py   [READ 무결성 검증]

product_pricing (레거시, 격리 준비)
  ← product_pricing.py          [CRUD, "격리 준비" 상태]
```

**EVIDENCE:** 전 섹션 수집 결과 종합

---

## OBJ00-U: UNVERIFIED / NOT_FOUND 레지스터

**UNVERIFIED:**

1. `public_pricing.py` 실제 마운트 prefix — 코드: `"/public/pricing"`, 상단 주석: `"/n"`, 테스트: `/n/saas-plans`. 세 곳이 불일치. 실제 라이브 라우터 마운트 지점 미확인.
   → GPT REVIEW REQUIRED

2. `migrations/2026-09-10_saas_tier_upgrade_transitions.sql` 파일 내용 — 0바이트로 읽힘. DB에 실제 적용된 schema와 일치 여부 미확인.
   → GPT REVIEW REQUIRED

3. `price_saas_plan` vs `price_master` 실제 데이터 동기 상태 — 두 테이블 내용이 일치하는지 미확인.
   → GPT REVIEW REQUIRED

4. tai-admin `useAuth.ts` PLAN_MAP에 `_V2`, `_V3` suffix 항목 없음 — contracts.plan_code가 `BUILDING_BASIC_V3`일 때 `_normalize`를 거치지 않으면 PLAN_MAP 미매칭 → sector='' (실패-오픈). 실제 로그인 시 nav 동작 미확인.
   → GPT REVIEW REQUIRED

5. tai-admin `diagnosis-purchaseFormat.ts` SECTOR_PRICES (29K/49K/59K/79K/99K/149K) — 이 파일이 현재 prod에서 활성 소비되는지 아니면 dead code인지 미확인.
   → GPT REVIEW REQUIRED

6. `tai-www/src/pages/free-diagnosis.astro` 구 가격 (79000/99000/145000 feeMap) — V2 전환 후 이 fallback이 실제 사용자에게 노출되는 코드 경로인지 미확인.
   → GPT REVIEW REQUIRED

**NOT_FOUND:**

- `TierPaymentGateAlert.vue`의 upgrade 결제 실행 코드 — 컴포넌트는 표시만 함. 실제 결제 실행 경로(tierPaymentLaunch.ts 연결 지점)가 tai-admin 내에서 명시적으로 확인되지 않음.
- tai-www에서 `SAAS_TIER_UPGRADE_REQUIRED` (HTTP 402) 처리 코드 — grep 결과 없음. tai-www는 LEG 결과를 표시하지 않는 것으로 추정.
- `payment_activation_api.py` 현재 활성 사용 endpoint 목록 — 파일 내 주석 "Single Pricing Source: price_saas_plan"이 구 아키텍처 기준인지 확인 필요.

---

## 수집 완료 선언

```
GPT REVIEW REQUIRED
```

섹션 OBJ00-A ~ OBJ00-U 수집 완료. 분석·평가·우선순위 판정은 GPT 독립검증 후 진행.
