---
STATUS: IMPLEMENTATION PLAN
OWNER DECISION: APPROVED
DATE: 2026-09-27
SCOPE: TAI Safe Pricing V2 — Commercial Contract Model 분리 설계
DEPENDENCY: 2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md
IMPLEMENTATION STATUS: NOT STARTED
---

# TAI Safe Pricing V2

## Current State Analysis & Object Implementation Plan

**설계일:** 2026-09-27
**단계:** IMPLEMENTATION PLAN
**기준:** Owner 확정 가격정책 (`2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md`)
**역할:** GPT 설계/검증 → Claude Code 조사/실행 → Owner 승인

---

## 1. 조사 Anchor

조사 시점 Git main:

```text
tai-api
ee1c60b5f42d89d25eab24b7679990bf7160b093

tai-www
7933f13d859900bdffb9f483b3c4ea609c1d90ac

tai-admin
5f2d2cb079e5a9b47ed621a14678ed7bb07f3c52
```

Pricing DB:

```text
Supabase project: taieng
project ref: vwlahtguyggrhvslabax
```

---

## 2. 현재 구조 실측 결과

### 2.1 가격 SSOT

현재 공식 가격 정본:

```text
price_master + price_service_feature
```

Backend:

```text
services/pricing_resolver_svc.py
routers/public_pricing.py
```

공개 API:

```text
GET /public/pricing/saas-plans
GET /public/pricing/diagnosis-reports
GET /public/pricing/all
GET /public/pricing/resolve
```

현재 `price_master`의 SAAS 구조:

#### INDUSTRY

```text
INDUSTRY_STARTER   149,000   0~49명
INDUSTRY_BUSINESS  299,000   50~299명
INDUSTRY_PRO       499,000   300~499명
INDUSTRY_CUSTOM          0   500명+
```

#### BUILDING

```text
BUILDING_BASIC     149,000   5,000㎡ 이하
BUILDING_STANDARD  349,000   5,000㎡ 초과
BUILDING_CUSTOM          0
```

#### CONSTRUCTION

```text
CONSTRUCTION_STANDARD  249,000   50억 미만
CONSTRUCTION_PREMIUM   499,000   50억 이상
CONSTRUCTION_CUSTOM          0
```

기존 가격 자체는 그대로 **Compliance Base Price**로 사용할 수 있다.

---

## 3. 현재 가장 큰 구조적 문제

현재 시스템은 다음 개념을 하나로 취급한다:

```text
규모
↓
price_master tier_code
↓
contract.plan_code
↓
contract_level
↓
기능 Gate
↓
LEG 실행 Gate
↓
추가결제
```

예: `INDUSTRY_STARTER / BUSINESS / PRO`가 단순 가격구간이 아니라 시스템 Tier 역할까지 한다.

**이 구조는 새로운 가격정책과 맞지 않는다.**

---

## 4. 현재 LEG Gate 구조

Backend:

```text
services/tier_payment_gate_svc.py
services/tier_upgrade_svc.py
```

현재 판정:

```text
사업장 규모 조회
↓
price_master resolve
↓
필요 plan 산정
↓
현재 contract.plan_code 확인
↓
sort_order 비교
↓
FIT / UPGRADE_REQUIRED
```

LEG 실행 전 `_assert_saas_tier_fit_http()` 가 실행된다.

현재: **사업장 규모가 플랜을 초과하면 법령의무 추출 실행까지 차단.**

---

## 5. 현재 추가결제 구조

`services/tier_upgrade_svc.py`는 현재 규모 플랜 Upgrade를 전제로 만들어져 있다:

```text
STARTER → BUSINESS
BUSINESS → PRO
```

계산:

```text
target plan amount - current plan amount = upgrade delta
```

결제 완료 후 `contracts.plan_code`, `subscriptions.plan_code` 변경.

`saas_tier_upgrade_transitions`도 `from/target plan_code + delta` 형태.

**새 가격정책에서는 이 개념만으로 부족하다.**

---

## 6. 현재 Frontend 구조

### tai-www

현재 SaaS 가격페이지는 규모별 플랜 자체를 상품 Tier처럼 보여준다:

```text
STARTER / BUSINESS / PRO / CUSTOM
```

주요 consumer:

```text
src/lib/render/buyerGuide.js
src/lib/render/pricingCards.js
src/pages/service/saas.astro
src/modules/pricing.js
src/modules/payment.js
```

현재 UI의 "관리자/작업자 등록 무제한" 문구는 새 정책과 더 이상 맞지 않는다.

### tai-admin

현재 인증 후 저장되는 값:

```text
contract_plan_code
contract_sector
contract_level
contract_addons
```

plan code를 숫자 `contract_level`로 변환하며, 소비처가 이미 여러 곳이다:

```text
useAuth.ts / menu-tadmin.js / plan-gate.js / help/useHelp.ts
dashboard / FixcChat / TBM
useTierPaymentGate.ts / tierPaymentGateContract.ts
TierPaymentGateAlert.vue / tierPaymentLaunch.ts
```

주요 소비 페이지: `diagnosis-step1`, `construction-extraction`

---

## 7. 견적/결제 영향 범위

현재 견적은 `service_type / sector / tier_code / term_months`를 기준으로 `price_master` 가격을 Snapshot한다.

결제 월요금 Resolver: `contract.plan_code → price_master.tier_code → amount` (1:1 관계).

새 가격: `Base + Tier + Sites + Worker Capacity + Term` 합성가격 → **기존 `plan_code → amount` 모델을 그대로 사용할 수 없다.**

---

## 8. Target Architecture 핵심

다음을 만들지 않는다:

```text
INDUSTRY_BUSINESS_FIELD_100_SITE3    ← 조합 폭발
BUILDING_STANDARD_MANAGER_SITE2      ← 거부
```

**가격을 독립 Object로 분리한다.**

---

## 9. Target Commercial Objects

### OBJECT A — Product Tier

```text
MANAGER  = 관리자 중심 운영
FIELD    = 관리자 + 현장 작업자 참여
CUSTOM   = 별도 협의
```

Product Tier는 기능/운영방식이다. 규모가격이 아니다.

---

### OBJECT B — Compliance Base Band

현재 `price_master` 구조를 그대로 활용한다.

```text
INDUSTRY_STARTER / BUSINESS / PRO
BUILDING_BASIC / STANDARD
CONSTRUCTION_STANDARD / PREMIUM
```

정확한 의미: **해당 사업장의 법적 관리범위에 따른 Base Price Band**

---

### OBJECT C — Site Scope

계약에 포함된 실제 관리사업장. 각 Site 최소 구성:

```text
entity_type / entity_id / sector / base_price_code
base_amount / is_primary / discount_rate / final_site_base
```

원칙:

```text
가장 높은 정상가격 Site 1개 = 100%
추가 Site = 각 정상가격 × 80%
```

가입 순서에 따라 가격이 달라지면 안 된다.

---

### OBJECT D — Worker Capacity

FIELD에서만 존재. `contracted_worker_capacity` (실제 사람 이름과 라이선스 미귀속).

계약 Capacity 안에서 사용자 교체 가능.

누적구간 방식:

```text
1~20       3,000원/인/월
21~50      2,500원/인/월
51~100     2,000원/인/월
101~300    1,500원/인/월
301+       1,200원/인/월
```

---

### OBJECT E — Contract Term

```text
1 / 3 / 6 / 9 / 12 months
```

TAI는 선불. 정확한 할인율은 미확정 → 현재 구현에서 임의 생성 금지.

---

### OBJECT F — Price Snapshot

계약이 만들어진 순간 가격 계산결과를 Freeze한다:

```json
{
  "policy_version": "...",
  "product_tier": "FIELD",
  "sites": [],
  "worker_capacity": 100,
  "worker_amount": 235000,
  "term_months": 12,
  "discount_rate": null,
  "monthly_supply": 0,
  "term_supply": 0,
  "vat_amount": 0,
  "total_amount": 0
}
```

계약 이후 `price_master`가 바뀌어도 기존 계약 금액을 소급 재계산하지 않는다.

---

## 10. 최종 가격 공식

월 기준:

```text
SITE_NORMAL = Compliance Base + Tier Uplift

Tier Uplift:
  MANAGER = 0
  FIELD   = +100,000
  CUSTOM  = quote

다사업장:
  PRIMARY SITE     = SITE_NORMAL × 100%
  ADDITIONAL SITE  = SITE_NORMAL × 80%

FIELD:
  WORKER FEE = progressive(worker_capacity)

MONTHLY SUPPLY = Σ SITE CHARGE + WORKER CAPACITY CHARGE

PREPAID SUPPLY = MONTHLY SUPPLY × TERM × TERM POLICY

FINAL PAYMENT = VAT + PREPAID SUPPLY
```

---

## 11. Gate 분리 (매우 중요)

현재 하나인 Tier Gate를 두 Object로 분리한다.

### Gate A — Commercial Fit

```text
실제 사업장 규모 vs 계약한 Compliance Base Band
→ PRICE_SCOPE_CHANGE_REQUIRED
```

가격/계약 Gate다.

### Gate B — Entitlement

```text
MANAGER 가능:
  법령의무 추출 / 점검업무 생성 / 관리자 점검 / 문서 / 일정 / 증빙

FIELD 전용:
  작업자 TBM 참여 / 위험성평가 참여 / 점검 수행 / 서명 / 위험제보
```

**규모가격과 기능권한을 다시 섞으면 안 된다.**

---

## 12. Backend Object Plan

### PRC-BE-OBJ01 — Commercial Domain Contract V2

목적: `Scale Band != Product Tier`를 Domain Contract로 확정.

정의:

```text
product_tier / base_band / sites / worker_capacity
term / pricing_policy_version / price_snapshot
```

Exit:
- 가격개념 명명 확정
- JSON/API contract 확정
- Legacy plan mapping 정의
- DB write 없음

---

### PRC-BE-OBJ02 — Pricing Policy Model

`price_master`는 Compliance Base SSOT로 유지.

새 정책 레이어에 필요한 것:

```text
FIELD uplift = 100,000
additional site rate = 0.8
worker brackets
term discount policy
policy version
```

권장 구조: `saas_pricing_policy` + `saas_worker_price_bracket`

`price_master`를 MANAGER/FIELD 조합표로 폭발시키지 않는다.

Exit: 정책 데이터모델 / versioning / effective_from / audit 가능 / rollback 가능

---

### PRC-BE-OBJ03 — Pricing Composer

신규 순수 Domain Service. `calculate_saas_price()` 단일 진입점.

Input: `product_tier / sites[] / worker_capacity / term_months`

Output: `base breakdown / tier uplift / site discounts / worker bracket breakdown / monthly supply / prepaid supply / VAT / total / policy version`

모든 가격 계산은 이 한 경로를 사용한다. Frontend / Payment / Quote / Contract 자체 계산 금지.

Exit: 경계값 테스트 (0/1/20/21, 50/51, 100/101, 300/301/305) + 다사업장 순서불변성 PASS

---

### PRC-BE-OBJ04 — Contract Commercial Snapshot V2

현재 `contracts.plan_code` 하나만으로는 새 계약을 표현할 수 없다.

Contract에 핵심 Query용 값 정규화:

```text
product_tier / worker_capacity / pricing_policy_version / term_months
```

사업장 Scope는 별도 relation으로 보존:

```text
saas_contract_sites
```

전체 계약 당시 가격은 immutable snapshot으로 보존.

`max_user_count`를 Worker Capacity 의미로 재사용하지 않는다.  
이유: 관리자 User ≠ 유료 Worker Capacity

Exit: Contract V2 schema / Site binding / immutable pricing snapshot / legacy columns compatibility 정의

---

### PRC-BE-OBJ05 — Gate Split

현재 `tier_payment_gate_svc.py`를 의미적으로 분리:

```text
commercial_fit_svc   → 사업장 규모 / Site / Worker Capacity 범위 검사
entitlement_svc      → MANAGER / FIELD / CUSTOM capability
```

LEG는 Product Tier 때문에 차단하지 않는다.  
두 Tier 모두 Compliance Engine을 사용한다.  
FIELD 전용 Endpoint만 FIELD entitlement를 검사한다.

Exit: Scale sort_order를 기능 Gate로 사용 않음 / MANAGER도 LEG 정상실행 / FIELD participant API는 MANAGER에서 차단 / regression PASS

---

### PRC-BE-OBJ06 — Prepaid Change Order

현재 `tier_upgrade_svc.py`의 `plan A → plan B` 차액결제를 일반화:

```text
MANAGER → FIELD
Worker Capacity 증가
Site 추가
Compliance Base Band 증가
CUSTOM 전환 요청
```

공통 개념: `CURRENT SNAPSHOT → REQUESTED SNAPSHOT → DELTA → PREPAID PAYMENT → APPLY`

계약기간 중 감소: 즉시 환불 자동처리 X, 다음 Renewal 반영.  
세부 prorata 정책은 별도 Owner 결정 전까지 정책 인터페이스만 만든다.

Exit: idempotent / server authoritative / client amount 신뢰 0 / payment 성공+contract apply 원자성 검증

---

### PRC-BE-OBJ07 — Pricing / Quote API V2

Frontend는 계산하지 않는다.

예상 API:

```text
POST /public/pricing/saas/preview
POST /me/quotes/saas/preview
POST /me/quotes/saas
```

Input: `tier / sector+site facts / site list / worker capacity / term`

Output: `breakdown / monthly equivalent / prepaid amount / VAT / total / custom_required`

기존 `GET /public/pricing/saas-plans`, `GET /public/pricing/resolve`는 Diagnosis + Legacy 소비자가 있으므로 즉시 제거하지 않는다.

---

### PRC-BE-OBJ08 — Quote / Billing Consumer Migration

현재 `plan_code → 단일 amount` 전제를 가진 모든 소비자를 Commercial Snapshot 방식으로 전환:

```text
member quote / payment_plan_resolver / billing / renewal / upgrade / subscription
```

`GET /payments/plan-amount`의 1:1 가격 해석은 V2에서 더 이상 정본이 될 수 없다.

Exit: 가격 계산 복제 0

---

### PRC-BE-OBJ09 — Legacy Contract Migration

현재 실측:

```text
contracts total      7
active contracts     5
subscriptions        41
tier upgrade ledger  0
```

이전 세대 plan code 혼재 (`INDUSTRY_STARTER / STARTER_V2 / INDUSTRY_PRO / CONSTRUCTION_STANDARD / STANDARD`).

일괄 UPDATE 금지. 분류 후 Owner Approval로 실제 전환:

```text
MIGRATE / KEEP_LEGACY / TEST_INVALID / MANUAL_REVIEW
```

`saas_tier_upgrade_transitions = 0` → 진행 중인 Tier Upgrade 전환 건 없음 (지금이 구조 전환 적기).

---

### PRC-BE-OBJ10 — Backend E2E / Release Gate

필수 Matrix:

```text
3 sectors × MANAGER/FIELD × scale boundaries × 1/2/3 sites × worker boundaries × term
```

경계값: `49/50 / 299/300 / 5000/5000.1㎡ / 50억-1/50억 / 20/21 / 50/51 / 100/101 / 300/301/305 workers`

Diagnosis 가격은 regression-only. 변경 금지.

---

## 13. Frontend Object Plan

Frontend는 두 Repo로 분리:

```text
tai-www   = 구매 / 가격 / 견적
tai-admin = SaaS 이용 / 계약 / 권한
```

---

## 14. tai-www Frontend

### PRC-FE-WWW-OBJ01 — 2 Tier Pricing Page

현재 `STARTER / BUSINESS / PRO` 카드 → 제거.

공개 선택:

```text
TAI Safe Manager      149,000원부터
TAI Safe Field        249,000원부터
Custom / Enterprise   별도 견적
```

"관리자/작업자 등록 무제한" 문구 제거.

---

### PRC-FE-WWW-OBJ02 — Price Calculator

고객 질문: `업종 / 규모 / 사업장 수 / Tier / Worker Capacity / 기간`

Price Formula를 Frontend에 넣지 않는다. Backend Preview API 호출.

결과: `Compliance Base / Tier / 추가사업장 할인 / 작업자 / 기간 / VAT / 선불 결제액` 설명 가능하게 표시.

---

### PRC-FE-WWW-OBJ03 — Purchase / Quote Handoff

가격계산 결과에 Quote Token / Snapshot ID 부여.

결제로 넘어갈 때 `amount / plan_code / worker count`를 Front가 재조립하지 않는다.  
서버의 Quote Snapshot을 전달한다.

---

### PRC-FE-WWW-OBJ04 — MyPage Quote / Contract

현재 동적 `tier_code` 카탈로그 선택 UI → V2로 변경.

고객에게는:

```text
관리자형/현장참여형 / 사업장 / 인원 / 계약기간
```

구매자 언어 우선 (`INDUSTRY_BUSINESS` → `TAI Safe 관리자형 사업장 2개`).

---

## 15. tai-admin Frontend

### PRC-FE-ADM-OBJ01 — Commercial Context V2

현재 `contract_plan_code / contract_sector / contract_level / contract_addons`에 V2 Context 추가:

```text
contract_product_tier / contract_worker_capacity / contract_site_count
contract_pricing_version / contract_entitlements
```

기존 `contract_level` 즉시 삭제 금지. Legacy consumer 조사 후 단계적 치환.

---

### PRC-FE-ADM-OBJ02 — Entitlement Gate

현재 plan level 기준 Feature Gate → entitlement 기준 전환:

```text
COMPLIANCE_CORE
FIELD_TBM / FIELD_RA_PARTICIPATION / FIELD_INSPECTION
FIELD_SIGN / FIELD_HAZARD_REPORT
```

- Manager: `COMPLIANCE_CORE = true`, `FIELD_* = false`
- Field: `COMPLIANCE_CORE = true`, `FIELD_* = true`

---

### PRC-FE-ADM-OBJ03 — LEG / Commercial Fit UX

현재 `TierPaymentGateAlert` (`현재 플랜 → 상위 플랜` UX) → `계약 범위 변경 필요` UX로 변경:

```text
사업장 규모 변경 / 추가 사업장 필요 / 현장참여형 전환 / 참여인원 증원
```

각각 정확한 이유와 가격 Breakdown을 보여준다.

---

### PRC-FE-ADM-OBJ04 — Contract Expansion UX

SaaS 내부에서:

```text
관리자형 → 현장참여형
작업자 Capacity 추가
사업장 추가
```

가능하게 한다.

Flow:

```text
변경 요청 → 서버 Preview → 변경 후 가격 → 추가 선불금액 → 결제 → Contract Snapshot 갱신
```

---

### PRC-FE-ADM-OBJ05 — Legacy Plan Cleanup

현재 plan code를 기능권한으로 해석하는 코드 제거:

```text
useAuth / menu-tadmin / plan-gate / help / dashboard / Fixc / TBM / tier payment gate / tests
```

단: `contract_level == 0`을 단순 비가입자 여부로 사용하는 로직은 별도 검토 후 보존 가능.  
`contract_level` 사용처를 일괄 삭제하지 않는다.

---

## 16. 구현 순서

**Backend First.**

```text
OBJ00  CURRENT STATE FREEZE
         ↓
BE-01  Domain Contract
         ↓
BE-02  Pricing Policy
         ↓
BE-03  Pricing Composer
         ↓
BE-04  Contract Snapshot
         ↓
BE-05  Gate Split
         ↓
BE-06  Change Order
         ↓
BE-07  API V2
         ↓
BE-08  Quote/Billing Migration
         ↓
BE-09  Legacy Migration
         ↓
FRONTEND
```

Frontend 순서:

```text
WWW-01 Tier Page → WWW-02 Calculator → WWW-03 Purchase → WWW-04 MyPage
ADM-01 Contract Context → ADM-02 Entitlements → ADM-03 Commercial Fit
                       → ADM-04 Expansion Payment → ADM-05 Legacy Cleanup
```

마지막:

```text
BE/FE Integrated E2E → Production Preview → Owner Approval → Cutover
```

---

## 17. 구현 금지사항

초기 구현에서 절대 하면 안 되는 것:

```text
기존 price_master 전체 재설계
Scale Band 삭제
DIAGNOSIS 가격 변경
조합 plan_code 생성
Frontend 가격계산
contract_level 일괄 삭제
Legacy plan code 즉시 삭제
Production contract 일괄 migration
기존 결제코드에 부분 Patch만 덧붙이기
```

---

## 18. Release Strategy

Big Bang 변경 금지.

```text
Phase 1  V2 backend read-only preview
Phase 2  V2 contract schema + compatibility
Phase 3  V2 frontend pricing calculator
Phase 4  V2 purchase / prepaid contract
Phase 5  Admin entitlement migration
Phase 6  Legacy gate retirement
```

Cutover 전에는 V1 데이터 보존. Rollback 가능해야 한다.

---

## 19. 보안 별도 트랙

Supabase Security Advisory 확인 사항:

```text
public.price_master / public.price_service_feature 포함 143 tables RLS disabled
```

이 문제는 Pricing V2 설계와 **별개 Security Object**로 분리한다.

**이번 가격개편 작업 중 일괄 ENABLE RLS 금지.**  
(Policy 없이 RLS 활성화 시 Backend/Frontend access 차단 가능)

별도 조사: `SEC-OBJ-PRICING-RLS-AUDIT`

```text
실제 grants / anon+authenticated access / service role path
public pricing read requirements / admin pricing write requirements
```

---

## 20. Architecture Lock

**현재 (V1):**

```text
Scale = Plan = Price = Feature Level = LEG Gate
```

**목표 (V2):**

```text
Product Tier          → MANAGER / FIELD / CUSTOM
Compliance Base       → Sector + Scale
Site Scope            → Site count + 20% additional-site discount
Worker Capacity       → Progressive prepaid pricing
Contract              → Frozen commercial snapshot
Entitlement           → Product Tier capability
Commercial Fit        → Scale / Site / Capacity compliance
```

```text
ARCHITECTURE_DIRECTION         = COMPOSITION PRICING
PLAN_CODE_COMBINATION_EXPLOSION = REJECTED
PRICE_MASTER                   = KEEP AS COMPLIANCE BASE SSOT
PRODUCT_TIER                   = MANAGER / FIELD / CUSTOM
SCALE_BAND                     = PRICE DIMENSION, NOT FEATURE TIER
WORKER                         = PREPAID CAPACITY
SITE                           = CONTRACT SCOPE
FRONTEND PRICE CALCULATION     = FORBIDDEN
SERVER PRICE COMPOSER          = SINGLE SOURCE
LEG CORE                       = AVAILABLE TO MANAGER AND FIELD
FIELD PARTICIPATION            = ENTITLEMENT-GATED
DIAGNOSIS PRICING              = OUT OF SCOPE / REGRESSION ONLY
```

---

## 21. 첫 구현 Object

Frontend부터 바꾸면 안 된다.

`tai-admin`에서 이미 `STARTER → BUSINESS → PRO` 구조가 LEG 실행 Gate와 실제 추가결제까지 연결돼 있기 때문이다.

**첫 구현 Object: `BE-OBJ01 Commercial Domain Contract V2`**

`Product Tier`와 `Scale Band`를 먼저 분리 → 가격엔진 → 계약 → Gate → 결제 순서로 고정 → Frontend가 안전하게 따라온다.

현재 `saas_tier_upgrade_transitions = 0` (진행 중 업그레이드 없음) → 지금이 구조를 바꾸기에 좋은 시점.

**다음 단계:** `OBJ00 — Pricing V2 Current-State Full Inventory & Freeze` 조사 지시서 작성 → Claude Code 실행 → GPT 독립검증 → BE-OBJ01 구현.
