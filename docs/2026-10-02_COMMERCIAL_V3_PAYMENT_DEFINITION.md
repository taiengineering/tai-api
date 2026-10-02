# Commercial V3 Payment Architecture & Operations Definition

```
Document:       Commercial V3 Payment Architecture & Operations Definition
Status:         CANONICAL
Version:        1.0
Date:           2026-10-02
Scope:          TAI Safe Commercial V3
Source of Truth: Current main source + Production schema + Closed WO evidence
Real PG Verification:       NOT EXECUTED
Production Mock Chain:      VERIFIED
Launch State:               CONDITIONAL READY
```

---

## Section 1 — Executive Summary

TAI Safe Commercial V3는 **MANAGER / FIELD / CUSTOM** 세 가지 상품 유형(product_tier)으로 구성된다.

계약 권한은 `plan_code`가 아니라 **Commercial Version(CV)의 `product_tier`** 가 결정한다.  
V3 결제에서 `plan_code = NULL`이 정상 상태다.

결제 기간에 따라 두 가지 결제 방식으로 분기된다:

- **payment_months = 1** → INICIS 정기결제(Billing) → 카드 전용 자동 갱신 (RS1)
- **payment_months = 3/6/9/12** → INICIS 단건결제(INIStdPay) → 카드 / 계좌이체(DirectBank) / 가상계좌(VBank)

결제가 성공하면 아래 흐름으로 연결된다:

```
Frozen Quote
    ↓
Payment (PAID/SUCCESS)
    ↓
on_payment_success_sync()
    ↓
apply_saas_v2_initial_payment_runtime()
    ↓
apply_saas_v2_contract_atomic (Supabase RPC)
    ↓
Contract  →  Commercial Version  →  Site Scopes
    ↓
Entitlement (product_tier 기반)
    ↓
Runtime Gate (GET /me/commercial/runtime-gate)
```

모든 결제 정보는 Frozen Quote Snapshot이 권위이며, frontend에서 가격을 재계산하지 않는다.

---

## Section 2 — Commercial V3 Product Model

### 상품 유형 (product_tier)

| product_tier | 공식 표시명 | 설명 |
|---|---|---|
| `MANAGER` | TAI Safe 관리자형 | 안전관리 기본 기능 |
| `FIELD` | TAI Safe 현장참여형 | 관리자형 + 현장 참여 기능 |
| `CUSTOM` | TAI Safe 커스터마이징 | 별도 협의 entitlement |

### Legacy vs V3 권한 모델

| 구분 | Legacy | Commercial V3 |
|---|---|---|
| 권한 기준 | `contracts.plan_code` | `saas_contract_commercial_versions.product_tier` |
| 정상 상태 | `plan_code = 'INDUSTRY_PRO'` 등 | `plan_code = NULL` |
| Gate | `/payments/tier-gate` | `/me/commercial/runtime-gate` (generation=COMMERCIAL_V3) |

V3에서 `plan_code = NULL`은 오류가 아니라 **정상 설계**다.  
Legacy `plan_code` authority를 V3 경로에 사용하거나, V3 결과를 legacy `plan_code`로 역산하지 않는다.

### product_type (결제 상품 분류)

V3 신규 구매 시 `payments.product_type = "SAAS"` (bare string).  
Legacy SAAS 결제는 `"SAAS_INDUSTRY"`, `"SAAS_CONSTRUCTION"`, `"SAAS_FACILITY"`, `"SAAS_BUILDING"` 등 sector suffix 형태를 사용했다.  
`_is_commercial_v3_saas_payment()` predicate은 `product_type == "SAAS"` + Frozen Quote V2 스키마를 조합해 V3 경로를 판별한다.

---

## Section 3 — Pricing Authority

### 권위 (Source of Truth)

```
Pricing Authority = Commercial V3 Pricing Engine
                  ↓
             Frozen Quote Snapshot
                  ↓
              payments.total_amount
```

**금지:**
- Frontend 가격 재계산
- legacy `plan_code` price lookup
- `price_master` 현재 플랜 조회
- tier sort_order authority 사용

### Quote 저장 구조

```
quotes
└─ items (JSONB array, len=1)
   └─ items[0]
      ├─ quote_schema_version = "SAAS_QUOTE_V2"
      ├─ product_tier         = "MANAGER" | "FIELD" | "CUSTOM"
      ├─ worker_capacity      = int
      ├─ payment_months       = int
      ├─ pricing_input        = {sites: [...], ...}
      ├─ pricing_snapshot     = {sites, worker, vat_amount, total_amount, ...}
      ├─ policy_version       = "TAI_SAFE_PRICING_POLICY_V3_2026_09_28"
      └─ display_name         = str
```

`quotes` 테이블에 별도 `payment_months` 컬럼이 없는 것이 정상 설계다.  
결제 기간은 `items[0].payment_months`에 저장된다.

### Quote 발행 API

```
POST /me/quotes/v2/issue
Body: {
  product_tier: "MANAGER" | "FIELD" | "CUSTOM"
  worker_capacity: int  (MANAGER는 0 고정)
  payment_months: 1 | 3 | 6 | 9 | 12
  sites: [{ entity_id, sector, criteria_value }]
  contact_name: str
}
```

`criteria_value` 기준:
- `INDUSTRY` sector → DB의 `factories.employee_count`
- `BUILDING` sector → DB의 `factories.building_area`
- `CONSTRUCTION` sector → DB의 `construction_sites.contract_amount × 1억`

---

## Section 4 — Payment Period Policy

| payment_months | 방식 | PG | 결제 수단 |
|---|---|---|---|
| 1 | Recurring (정기) | INICIS Billing (INI Lite Pay) | CARD only |
| 3 | Single (단건) | INIStdPay | Card / DirectBank / VBank |
| 6 | Single (단건) | INIStdPay | Card / DirectBank / VBank |
| 9 | Single (단건) | INIStdPay | Card / DirectBank / VBank |
| 12 | Single (단건) | INIStdPay | Card / DirectBank / VBank |

- **payment_months = 1** = 자동 갱신, RS1 Scheduler가 매월 재청구
- **payment_months = 3/6/9/12** = 선결제 기간형, 기간 종료 후 수동 갱신

Renewal(수동 갱신)은 항상 `3/6/9/12` 중 하나다 (`create_renewal_quote` 내 `_ALLOWED_RENEWAL_MONTHS` 제약).

---

## Section 5 — New Purchase Flow

```
┌─────────────────────────────────────────────────────────────┐
│  POST /me/quotes/v2/issue                                   │
│  → Frozen Quote (items[0] snapshot)                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  POST /me/quotes/v2/{quote_id}/payment/prepare              │
│  → payments row (status=PENDING, product_type=SAAS)         │
└──────────────────────────┬──────────────────────────────────┘
                           │
           ┌───────────────┴────────────────┐
           │ payment_months=1               │ payment_months=3/6/9/12
           ▼                               ▼
   INICIS INI Lite Pay              INIStdPay popup
   (Billing Key 발급)               gopaymethod=""
           │                               │
           │                    ┌──────────┼──────────┐
           │                    ▼          ▼          ▼
           │                  Card    DirectBank    VBank
           │                    │          │          │
           │                    └────┬─────┘    PENDING
           │                         │           입금 대기
           │                    process_         process_
           │                    card_success()   vbank_deposit()
           │                         │          (웹훅 수신 후)
           └─────────────────────────┘
                           │
                    status=SUCCESS
                    pg_method 기록
                           │
                           ▼
           POST /payments/inicis/return (callback)
           → on_payment_success_sync(payment_id)
                           │
                           ▼
           services/payment_post_process.py
           ├─ WP-A: _bootstrap_buyer_company_admin()
           ├─ UPGRADE path: apply_saas_tier_upgrade()
           ├─ RENEWAL path: apply_saas_v2_renewal_runtime()
           └─ SAAS initial path:
              apply_saas_v2_initial_payment_runtime()
                           │
                           ▼
           services/saas_initial_payment_runtime_v2.py
           ├─ plan_code=None guard
           ├─ payment_type=RENEWAL/UPGRADE guard
           ├─ Frozen Quote 로드 (quote_id 필수)
           └─ apply_saas_v2_contract_plan_atomic()
                           │
                           ▼
           apply_saas_v2_contract_atomic (Supabase RPC)
           ← service_role credential 필수
                           │
                ┌──────────┼──────────┐
                ▼          ▼          ▼
           contracts  commercial_  site_scopes
                       versions
```

**핵심 불변식:**
- `product_type = "SAAS"` + `plan_code = NULL` + Frozen Quote → V3 경로
- Frozen Quote repricing 금지
- V3 initial runtime: `_create_contract_from_payment()` 호출 금지 (V1 경로)
- Atomic RPC 최대 2회 (race recovery 1회 허용)

---

## Section 6 — Single Payment (INIStdPay)

### payment_months = 3/6/9/12

**Frontend 결제 폼:**
```javascript
gopaymethod = ""   // INIStdPay popup이 결제수단 선택 담당
```

별도 frontend CARD/VBANK selector는 canonical이 아니다.  
결제수단 선택은 INIStdPay popup의 책임이다.

### Card / DirectBank 흐름

```
INIStdPay
    ↓
POST /payments/inicis/return
    ↓
process_card_success(payment, auth_result, pg_method)
    → status_code = "SUCCESS"
    → pg_method = "Card" | "DirectBank"
    ↓
on_payment_success_sync()
```

### VBank 흐름

```
INIStdPay
    ↓
POST /payments/inicis/return
    ↓
process_vbank_issued(payment, auth_result)
    → status_code = "PENDING"
    → pg_method = "VBANK"
    (입금 대기)
    ↓
POST /payments/inicis/vbank/notify  (INICIS → server webhook)
    ↓
process_vbank_deposit(order_id, result_code, depositor, data)
    → status_code = "SUCCESS"
    ↓
on_payment_success_sync()
```

VBank는 입금 확인 전까지 contract가 생성되지 않는다.

---

## Section 7 — Recurring Billing / RS1

### payment_months = 1 구매 흐름

```
POST /me/quotes/v2/issue (payment_months=1)
    ↓
POST /me/quotes/v2/{quote_id}/payment/prepare
    ↓
INICIS INI Lite Pay (Billing Key 발급 페이지)
    ↓
POST /payments/inicis/billing/return (callback)
    ↓
_wire_subscription_activated()
    → subscriptions row 생성 (ACTIVE)
    → billing_keys row 생성 (ACTIVE)
    → next_billing_at = contract.end_date - 1일 (KST midnight)
```

### RS1 Scheduler (자동 갱신)

```
cron_job_master:
  job_code: SAAS_RECURRING_BILLING
  endpoint_url: direct://saas_recurring_billing
  cron_expression: 0 * * * *  (매시 정각)
  is_active: true
  notify_on_fail: true

cron_schedule_config:
  is_enabled: true
  last_status: SUCCESS  (2026-10-02T23:00:02 KST 기준)
```

### RS1 실행 흐름 (services/saas_recurring_billing_scheduler.py)

```
cron trigger (매시)
    ↓
due subscriptions 조회
(next_billing_at <= now AND status=ACTIVE AND product_type=SAAS)
    ↓
build_v3_recurring_charge_context()
├─ subscription fresh read
├─ billing_key fresh read
└─ V3 linkage: cycle-1 success payment 확인
    ↓
_charge_subscription_once()
    ↓
INICIS Billing API (INIAPI)
    ↓
payment row 생성 (cycle=1: 기존 PENDING row 재사용/payment_type=CARD; cycle≥2: 신규 row/payment_type=RENEWAL, pg_method=CardBilling)
    ↓
on_payment_success_sync()
    ↓
payment_type=RENEWAL 경로 (cycle≥2) / CARD 경로 (cycle=1, SAAS initial 분기):
    classify_renewal_runtime_route() → "V2"
    apply_saas_v2_renewal_runtime()
    apply_saas_v2_renewal_atomic (RPC)
    → new CV (version_no + 1)
    → old CV.superseded_at 설정
    → contract.end_date 연장
    → subscription.next_billing_at 재정렬
```

### RS1 실패 처리

| 실패 유형 | 기록 |
|---|---|
| charge 실패 | `payments.status_code = "FAILED"` |
| post_process 실패 | `status = partial`, `reason_code = POST_PROCESS_FAILED` |
| 배치 전체 실패 | `cron_job_log.status ≠ SUCCESS` |
| 예외 발생 | `log.error() / log.exception()`, Railway 앱 로그 |
| batch failures > 0 | `SaasRecurringBillingError` → cron_job_log status=FAILED |

**현재 운영 제약:** `notify_on_fail=true` DB flag 존재, 실제 Slack/webhook proactive alert 구현 없음.  
→ 후속 WO: WO-COMM-V3-OBSERVABILITY-001

---

## Section 8 — Contract Architecture

### V3 계약 정보 분리 구조

```
contracts                           (계약 shell / lifecycle)
    id, contract_no, company_id
    status_code, is_active
    service_type = "SAAS"
    start_date, end_date
    contract_amount, vat_amount, total_amount
    quote_id
    plan_code  ← V3에서 NULL. pricing/entitlement authority로 사용 금지.

saas_contract_commercial_versions   (Commercial authority)
    id, contract_id
    version_no          ← 1부터 시작, renewal마다 +1
    product_tier        ← V3 entitlement/authority 기준
    payment_months
    worker_capacity
    pricing_mode, pricing_result_status, pricing_policy_version
    pricing_snapshot    (견적 스냅샷 JSONB)
    effective_from
    superseded_at       ← 현재 활성 버전 = NULL
    renewal_payment_id  ← 갱신 결제 ID (initial=NULL)
    commercial_schema_version = "SAAS_CONTRACT_COMMERCIAL_V2"

saas_contract_site_scopes           (적용 사업장 범위)
    id, commercial_version_id       ← contract_id가 아님
    entity_type = "factory" | "site"
    entity_id
    sector = "INDUSTRY" | "BUILDING" | "CONSTRUCTION"
    base_band_code
```

**중요:**  
`saas_contract_site_scopes`는 `commercial_version_id`로 조인한다. `contract_id`로 직접 조인하지 않는다.

---

## Section 9 — Commercial Version (CV)

### 불변식

| 이벤트 | 결과 |
|---|---|
| 초기 구매 | version_no=1, superseded_at=NULL, renewal_payment_id=NULL |
| Renewal | version_no + 1, 구 버전 superseded_at 설정, 신 버전 renewal_payment_id 설정 |
| 해지 후 | contract ACTIVE 유지, CV 변경 없음, 다음 RS1 미발생 |

### 현재 활성 CV 조건

```
contract_id = {current_contract_id}
AND superseded_at IS NULL
AND effective_from <= now()
```

Ambiguous (2건 이상) = `CURRENT_CV_AMBIGUOUS` 오류.

---

## Section 10 — Site Scope

각 Commercial Version에 적용 범위를 고정한다.

```
saas_contract_site_scopes
├─ commercial_version_id  (CV와 1:N)
├─ entity_type:  "factory" | "site"
├─ entity_id:    UUID (factories.id / construction_sites.id)
├─ sector:       "INDUSTRY" | "BUILDING" | "CONSTRUCTION"
└─ base_band_code: e.g., "INDUSTRY_STARTER"
```

Quote Snapshot의 `sites[i].entity_id`와 Site Scope의 `entity_id`는 동일 공장/건설현장을 가리킨다.  
Renewal 시 새 CV에 동일 Site Scope가 복사된다.

---

## Section 11 — Buyer Activation (WP-A)

`payment_post_process._bootstrap_buyer_company_admin()` — 결제 성공 직후 실행.

### Case 분류

| Case | 조건 | 동작 |
|---|---|---|
| A | 회사 내 ACTIVE admin 0 + buyer가 이미 admin capability role (010/011 등) | role 유지 + ACTIVE |
| B | 회사 내 ACTIVE admin 0 + buyer가 non-capability role | role_code=002 설정 + ACTIVE |
| C (Legacy) | 회사 내 ACTIVE admin ≥ 1 | NOOP |
| **C (V3)** | 회사 내 ACTIVE admin ≥ 1 + V3 결제 | buyer를 ACTIVE로 강제 설정 (role 유지) |

**V3 Case C:**
- 기존 admin 존재 → buyer role overwrite 금지
- status_code = ACTIVE, is_active = true 설정
- buyer가 이미 ACTIVE → no churn

**idempotent:** 재실행 시 이미 정상이면 변경 없음.

### V3 결제 predicate

`_is_commercial_v3_saas_payment()` 조건:
1. `pay.product_type == "SAAS"`
2. `pay.company_id` 존재
3. `pay.quote_id` 존재
4. quote: `company_id` 일치, `source="member_auto"`, `service_type="SAAS"`, `items` len=1, `items[0].quote_schema_version == "SAAS_QUOTE_V2"`

---

## Section 12 — Runtime Gate

### Endpoint

```
GET /me/commercial/runtime-gate?factory_id={uuid}
GET /me/commercial/runtime-gate?site_id={uuid}
```

factory_id와 site_id 중 하나만 전달해야 한다.

### 판정 흐름

```
Auth → company_id
    ↓
current contract (ACTIVE SAAS)
    ↓
current commercial version (superseded_at IS NULL)
    ↓
product_tier → entitlement 확인
    ↓
site scope 확인 (factory_id / site_id가 CV에 연결된 scope인지)
    ↓
Response
```

### Response 형태

**generation = COMMERCIAL_V3 (V3 계약 존재)**
```json
{
  "generation": "COMMERCIAL_V3",
  "can_execute": true | false,
  "status": "ALLOWED" | "DENIED" | ...,
  "reason_code": null | "...",
  "product_tier": "MANAGER" | "FIELD" | "CUSTOM",
  "commercial_version_no": 1,
  "target": { "entity_type": "factory", "entity_id": "..." }
}
```

**generation = NOT_COMMERCIAL_V3 (V3 계약 없음)**
```json
{
  "generation": "NOT_COMMERCIAL_V3"
}
```
→ SAFE Frontend가 `/payments/tier-gate` (legacy) 로 fallback.

**V3에서 legacy `plan_code` gate를 사용하지 않는다.**

---

## Section 13 — Entitlement

`services/saas_entitlement_gate_v2.py` 기준.

### Tier별 Entitlement Set

```
MANAGER_ENTITLEMENTS = (
    "COMPLIANCE_CORE",
)

FIELD_ENTITLEMENTS = (
    "COMPLIANCE_CORE",
    "FIELD_TBM",
    "FIELD_RA",
    "FIELD_INSPECTION",
    "FIELD_SIGN",
    "FIELD_HAZARD_REPORT",
)

CUSTOM: custom_entitlements (별도 협의)
  - custom_entitlements = None → status = "CUSTOM_CONTEXT_REQUIRED"
```

FIELD는 MANAGER의 모든 entitlement를 포함한다.  
CUSTOM은 custom_entitlements 설정 전까지 CUSTOM_CONTEXT_REQUIRED로 판정된다.

---

## Section 14 — Renewal (수동 갱신)

### 대상

payment_months = 3/6/9/12 계약의 기간 만료 전 수동 갱신.  
RS1(payment_months=1) 계약은 수동 갱신 불가 (`create_renewal_quote` 에서 CV.payment_months=1 차단).

### 흐름

```
Admin My Contract
    ↓
POST /me/quotes/v2/renewal/issue
Body: { payment_months: 3 | 6 | 9 | 12 }
    ↓
Frozen Renewal Quote
    ↓
POST /me/quotes/v2/{quote_id}/renewal/payment/prepare
    ↓
INIStdPay (Card / DirectBank / VBank)
    ↓
POST /payments/inicis/renewal/return (callback)
    ↓
on_payment_success_sync()
    payment_type = "RENEWAL"
    ↓
classify_renewal_runtime_route() → "V2" (product_type=SAAS)
    ↓
apply_saas_v2_renewal_runtime()
    ↓
apply_saas_v2_renewal_atomic (RPC)
    → new CV (version_no + 1, renewal_payment_id = payment_id)
    → old CV.superseded_at 설정
    → contract.end_date 연장
```

### Server-Derived Fields (Client Input = 0)

Renewal Quote 발행 시 client가 보내는 것:
- `payment_months` (필수)

Server가 파생하는 것:
- company_id (auth token)
- contract_id (current active contract)
- payment_id (V3 latest eligible payment)
- current_version (current CV)
- product_tier (현재 CV에서 복사)
- site_scopes (현재 CV에서 복사)
- pricing (Pricing Engine 재계산)
- amount (Frozen Quote에 저장)

---

## Section 15 — Renewal Payment Methods

Renewal도 Card / DirectBank / VBank 모두 지원한다.

| 결제 수단 | payment_type | pg_method | status 흐름 |
|---|---|---|---|
| Card | RENEWAL | Card | PENDING → SUCCESS |
| DirectBank | RENEWAL | DirectBank | PENDING → SUCCESS |
| VBank | RENEWAL | VBANK | PENDING(입금 대기) → SUCCESS |

`payment_type = "RENEWAL"`은 고정.  
실제 결제 수단 구분은 `pg_method`로 한다.

---

## Section 16 — Subscription Control

### API (origin/main 기준)

```
GET  /me/commercial/subscription
  → RS1 구독 상태 + next_billing_at 조회
  → DB write = 0

POST /me/commercial/subscription/cancel
  → RS1 구독 해지
```

### Authority 체인 (서버 파생, client input = 0)

```
auth_token → company_id
    ↓
current active contract (contract_id)
    ↓
payments.contract_id + product_type=SAAS + status=PAID/SUCCESS + charge_cycle=1
    ↓
subscription_id
    ↓
subscriptions.company_id 검증
```

Client는 subscription_id, company_id, billing_key_id를 직접 보내지 않는다.

---

## Section 17 — Cancellation Semantics

### 해지 효과

```
subscriptions.status = "CANCELLED"
subscriptions.next_billing_at = NULL
subscriptions.ended_at = now()
billing_keys.status = "REVOKED"
```

### 해지 비효과 (변경 없음)

```
contract.status_code = ACTIVE  (변경 없음)
contract.end_date               (변경 없음)
refund                         = 없음
INICIS BillKey 원격 폐기         = 없음 (DB only)
```

**해지의 의미:**  
현재 서비스 즉시 종료가 아니라 **다음 자동 청구 중단**이다.  
계약 만료일까지 서비스 이용이 가능하다.

---

## Section 18 — Payment Status / Type Definitions

> **원칙:** `payment_type`은 결제의 비즈니스 목적/처리 경로를 나타낸다.  
> `pg_method`는 실제 PG 수단을 나타낸다.  
> 두 값은 독립적이며 혼동하지 않는다.

### payment_type (결제 분류)

| payment_type | 의미 | 사용 경로 | 소스 |
|---|---|---|---|
| `CARD` | 단건 카드/VBank 결제 준비 + RS1 cycle=1 | 신규 구매 prepare, RS1 cycle=1 (기존 PENDING row 재사용) | `payment_svc._prepare_payment()` / `payment_billing._charge_subscription_once()` cycle=1 |
| `RENEWAL` | 자동 갱신(RS1) cycle≥2 + 수동 갱신 단건결제 | RS1 cycle≥2 V3 SAAS: `payment_row["payment_type"] = "RENEWAL"` (line 508); 수동 갱신 prepare | `payment_billing._charge_subscription_once()` line 508 / `member_quotes.renewal_payment_prepare()` |
| `UPGRADE` | Tier 업그레이드 | upgrade prepare 경로 | `payment.upgrade_prepare()` |
| `VBANK` | 가상계좌 구매 분류 | VBank prepare 경로 일부 | `payment_svc._prepare_payment()` |
| `BILLING` | **EXISTS / NON-CANONICAL (V3)** — 레거시 writer에서 기록. V3 RS1에서는 사용하지 않음. | 레거시 billing path (`payment_billing.py` line ~861 구 writer) | 레거시. V3 SAAS cycle≥2 canonical = `RENEWAL` |

**RS1 payment_type 상세 (Commercial V3 SAAS):**

| RS1 charge cycle | payment_type | pg_method | 근거 |
|---|---|---|---|
| cycle = 1 | `CARD` | `CardBilling` | 기존 PENDING row 재사용; `payment_type` 불변 (prepare에서 CARD 고정) |
| cycle ≥ 2 | `RENEWAL` | `CardBilling` | 새 payment row 생성: default `CARD` (line 450) → V3 SAAS override `RENEWAL` (line 508) |

소스: `routers/payment_billing.py`
- line 450: `"payment_type": "CARD"` (신규 row 기본값)
- line 451: `"pg_method": "CardBilling"`
- line 508: `payment_row["payment_type"] = "RENEWAL"` (product_type=="SAAS" and is_recurring 조건)

### pg_method (결제 수단)

| pg_method | 설명 |
|---|---|
| `Card` | 카드 (INIStdPay 또는 수동) |
| `DirectBank` | 계좌이체 |
| `VBANK` | 가상계좌 |
| `CardBilling` | INICIS 정기결제 (RS1, cycle=1 및 cycle≥2 모두 동일) |

### status_code (결제 상태)

| status_code | 의미 | Writer |
|---|---|---|
| `PENDING` | 결제 대기 (VBank 입금 전, 결제 준비 직후) | `_prepare_payment()` |
| `SUCCESS` | 결제 성공 — Card / DirectBank / VBank 입금 / RS1 Billing 성공 모두 기록 | `process_card_success()`, `process_vbank_deposit()`, `_charge_subscription_once()` (RS1 canonical) |
| `PAID` | **ACCEPTED SUCCESS STATUS / LEGACY-COMPATIBLE** — `PAID_STATUS_CODES`에 포함되어 post-process reader가 인정. 현재 Commercial V3 RS1 canonical writer 값은 `SUCCESS`. | 레거시 writer 또는 mock 환경 |
| `FAILED` | 결제 실패 | `_apply_failure_to_subscription()` |

`PAID_STATUS_CODES = frozenset({"PAID", "SUCCESS"})` — post-process reader(on_payment_success_sync)는 두 값 모두 성공으로 처리.  
단, 이것이 모든 writer가 `PAID`를 기록한다는 의미가 아니다. **Commercial V3 현재 RS1 canonical writer는 `SUCCESS`를 사용한다** (`_charge_subscription_once()` → `status_code="SUCCESS"`).

---

## Section 19 — Atomic RPC

### 역할

```
apply_saas_v2_contract_atomic   — 신규 계약 + CV + SiteScope 원자적 영구화
apply_saas_v2_renewal_atomic    — Renewal CV 원자적 영구화 (old CV supersede)
```

### 필수 조건

- **service_role credential** 필수 (RLS 우회)
- DB 내 RPC 함수로 정의 (Production DDL 적용 완료)
- Python INSERT/UPDATE 직접 호출 금지 (원자성 보장 불가)

### Production 상태 (2026-10-02 기준)

```
apply_saas_v2_contract_atomic  : EXISTS ✓
apply_saas_v2_renewal_atomic   : EXISTS ✓
Production DB: vwlahtguyggrhvslabax (Supabase)
```

---

## Section 20 — Supabase Client

### 현재 main source (db/supabase_client.py)

```python
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_KEY")
    or os.environ.get("SUPABASE_KEY")
)
```

**`SUPABASE_SERVICE_ROLE_KEY`는 현재 main source canonical env 이름이 아니다.**  
(`routers/auth.py`는 `SUPABASE_SERVICE_ROLE_KEY`도 읽지만, `db/supabase_client.py`는 다르다.)

### Production (Railway)

```
SUPABASE_SERVICE_KEY = service_role JWT  ← BOUND ✓
```

이 값이 존재하므로 `db/supabase_client.py`가 service_role key를 사용한다. Atomic RPC 정상 동작.

### 로컬 개발 환경 주의사항

로컬 `.env`에 `SUPABASE_SERVICE_KEY` 미설정 시 `SUPABASE_KEY` (anon key) fallback.  
anon key로는 `apply_saas_v2_contract_atomic` 등 RPC 실행 시 `permission denied` 발생.  
**운영 아키텍처가 아니므로 문서화하지 않는다.** 로컬 개발 시 `SUPABASE_SERVICE_KEY`를 설정할 것.

---

## Section 21 — Observability

### 현재 관측 가능한 데이터

| 데이터 | 위치 | 내용 |
|---|---|---|
| 결제 성공/실패 | `payments.status_code` | PAID/SUCCESS/FAILED |
| 계약 생성 | `contracts`, `saas_contract_commercial_versions` | contract_id, status_code |
| RS1 실행 결과 | `cron_job_log` | status, result_summary, error_message |
| RS1 부분 실패 | `payments.status_code = "FAILED"` | charge 실패 건 |
| post_process 실패 | `cron_job_log.status ≠ SUCCESS` | SaasRecurringBillingError |
| 앱 예외 | Railway application logs | log.error() / log.exception() |

### 주요 correlation key

```
quote_id → payment_id → contract_id → company_id
payment_id → subscription_id (RS1)
inicis_order_id (payments.inicis_order_id)
```

### 관측 가능한 실패 상태

```
POST_PROCESS_FAILED      → status=partial, reason_code=POST_PROCESS_FAILED
payment.status_code=FAILED → RS1 청구 실패
atomic RPC failure        → [INITIAL_V2_RUNTIME] / [V2_INIT] error log
callback failure          → Railway log + HTTP 401/500
```

---

## Section 22 — Known Operational Limitation

현재 상태:
- **DB/log 기반 사후 관측 = 존재**
- **Proactive Alert = 없음**

`cron_job_master.notify_on_fail = true` DB flag는 설정되어 있으나  
실제 Slack/webhook proactive alert 코드 구현은 존재하지 않는다.

운영자가 직접 아래를 확인해야 한다:
- `payments` WHERE `status_code = 'FAILED'` (최근 30일)
- `cron_job_log` WHERE `status != 'SUCCESS'`
- Railway application log의 error/exception 메시지

**후속 작업:** WO-COMM-V3-OBSERVABILITY-001 (Slack/webhook proactive alert 구현)

---

## Section 23 — Legacy Boundary

### 경계 정의

| 구분 | Legacy | Commercial V3 |
|---|---|---|
| 권한 기준 | `contracts.plan_code` | `saas_contract_commercial_versions.product_tier` |
| 게이트 | `POST /payments/tier-gate` | `GET /me/commercial/runtime-gate` |
| 결제 flow | V1 `_create_contract_from_payment()` | V2 Atomic RPC |
| Pricing | legacy plan_code price lookup | Frozen Quote Snapshot |
| `product_type` | `SAAS_INDUSTRY` 등 sector suffix | `SAAS` |

### 금지

- V3 contract에서 legacy `plan_code` authority 사용
- legacy `plan_code`에서 V3 product_tier 자동 변환
- V3 결제 후처리에서 `_create_contract_from_payment()` 호출

### Shared Consumer Dispatch

`on_payment_success_sync()` 내 분기 순서:
1. `payment_type = UPGRADE` → tier upgrade 전용 경로
2. `payment_type = RENEWAL` → renewal runtime (V2 or LEGACY 분류)
3. `product_type = "SAAS"` → V3 initial runtime
4. `contract_id` 존재 → activate existing contract (legacy)
5. `_should_auto_contract()` → V1 contract 생성 (legacy)

---

## Section 24 — Deprecated / Non-Canonical Paths

다음은 코드에 존재하나 V3 canonical이 아니다:

| 경로 / 구조 | 상태 | 이유 |
|---|---|---|
| Frontend 별도 CARD/VBANK selector | NOT V3 CANONICAL | gopaymethod="" (INIStdPay popup 책임) |
| `contracts.plan_code` pricing authority | NOT V3 CANONICAL | product_tier 사용 |
| legacy `SAAS_INDUSTRY` 등 product_type | EXISTS (legacy path) | V3는 bare `"SAAS"` |
| `/payments/tier-gate` (plan_code gate) | EXISTS (legacy fallback) | V3는 /me/commercial/runtime-gate |
| `_create_contract_from_payment()` | EXISTS (V1 path) | V3 initial에서 호출 금지 |
| V1 `_build_contract_row_from_payment()` | EXISTS (legacy) | V3 atomic RPC 사용 |
| Renewal VBANK 전용 별도 엔드포인트 | NOT USED | INIStdPay 단일 처리 |
| `saas_payment_v2_adapter.py` SAAS_PRODUCT_TYPES | legacy 판별 | V3는 별도 predicate 사용 |

---

## Section 25 — Validation History

| WO | 내용 | 상태 |
|---|---|---|
| V3-01 Runtime Wiring | V3 runtime-gate + useCoreExecutionGate | CLOSED |
| V3-02 Pricing Plan Control | Pricing V3 plan 표시 제어 | CLOSED |
| V3-03 Buyer Activation | WP-A V3 Case C | CLOSED |
| V3-04 VBank Wiring | V3 Frozen Quote VBank 연결 | CLOSED |
| V3-05 Display Compatibility | planChip V3 tier guard + formatProductTier | CLOSED |
| V3-06 Quarantine Boundary | generation boundary 검증 | CLOSED |
| V3-07A INICIS Single | Renewal 단건결제 canonical 배선 | CLOSED |
| V3-07B Manual Renewal | V3 수동 갱신 UI + API | CLOSED |
| V3-07C Subscription Control | RS1 구독 조회/해지 API | CLOSED |
| E2E-COMM-01 | Mock Full Chain 13/13 PASS | CLOSED FINAL |

---

## Section 26 — Launch Status

```
WO-COMM-V3-LAUNCH-READINESS-001 = CLOSED — CONDITIONAL READY (2026-10-02)
```

| 검증 항목 | 결과 |
|---|---|
| LR01 Deployment | PASS (tai-api 63eb1ec5 / tai-admin 9f8e903e / tai-www 73adaf86) |
| LR02 Environment | PASS (INICIS 단건/Billing env vars 전부 존재) |
| LR03 Callback Wiring | PASS (production domain, source route 확인) |
| LR04 RS1 Scheduler | PASS (is_active=true, is_enabled=true, last_status=SUCCESS) |
| LR05 Web Wiring | PASS (pricing, checkout, my-contract, renewal, runtime-gate 전부 응답) |
| LR06 Observability | PASS WITH CONDITION (사후 관측 경로 존재, proactive alert 없음) |

Launch Blocker: **0**  
남은 조건: 첫 실제 고객 결제 발생 시 운영 관측 절차 실행

---

## Section 27 — Production Mock Verification

```
WO-COMM-V3-FIRST-LIVE-PAYMENT-001 = CLOSED FINAL (2026-10-02)
Production Mock Payment Chain: VERIFIED
Real Card Payment: NOT EXECUTED / UNVERIFIED
```

| 검증 항목 | 결과 |
|---|---|
| Quote issue (MANAGER/3m/INDUSTRY/467,115원) | PASS |
| Payment prepare (product_type=SAAS, plan_code=NULL) | PASS |
| Mock PAID → on_payment_success_sync() | PASS |
| Contract ACTIVE (CON-20261002-8386) | PASS |
| Commercial Version v1 (MANAGER, 3m, superseded_at=NULL) | PASS |
| Site Scope (INDUSTRY, factory, INDUSTRY_STARTER) | PASS |
| Buyer Activation (is_active=True, Case C V3) | PASS |
| Runtime Gate (COMMERCIAL_V3, can_execute=true) | PASS |
| /me/commercial/contract (state=ACTIVE) | PASS |
| Correlation chain | PASS |
| Side effects (subscription=0, billing_key=0) | PASS |
| CODE CHANGE / DDL / REAL PG CALL / REAL MONEY | 0 |

**"LIVE PAYMENT VERIFIED" 또는 "FIRST REAL PAYMENT VERIFIED" 표현 금지.** 실제 INICIS PG를 통과하지 않았다.

---

## Section 28 — Production State

*As of 2026-10-02 (동적 상태 — 이후 변경 가능)*

```
Commercial V3 schema applied:        ✓
  - saas_contract_commercial_versions
  - saas_contract_site_scopes
  - subscriptions (V3 컬럼 포함)

Atomic RPC applied:                  ✓
  - apply_saas_v2_contract_atomic
  - apply_saas_v2_renewal_atomic

RS1 Scheduler:
  is_active:  true
  is_enabled: true
  cron:       0 * * * * (매시 정각)
  last_status: SUCCESS

Production domains:
  API:   https://api.taieng.co.kr
  WWW:   https://taieng.co.kr
  Admin: https://admin.taieng.co.kr

Callback URLs (production):
  INICIS return:  https://api.taieng.co.kr/payments/inicis/return
  Billing return: https://api.taieng.co.kr/payments/inicis/billing/return
  VBank notify:   https://api.taieng.co.kr/payments/inicis/vbank/notify
```

---

## Section 29 — Architecture Diagram

### 신규 구매 흐름

```
                    ┌─────────────────────┐
                    │   Pricing V3 Engine  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Frozen Quote      │
                    │  (items[0] snapshot) │
                    └──────────┬──────────┘
                               │
                ┌──────────────┴──────────────┐
                │ payment_months=1             │ payment_months=3/6/9/12
                ▼                             ▼
       INICIS Billing                      INIStdPay
       (INI Lite Pay)                    gopaymethod=""
       CARD only                    Card / DirectBank / VBank
                │                             │
                │                    ┌────────┼────────┐
                │                    ▼        ▼        ▼
                │                  Card  DirectBank  VBank
                │                    │        │      PENDING
                │                    └────┬───┘      입금 후
                │                         ▼       process_vbank_deposit()
                │                    status=SUCCESS     │
                │                         └────────────┤
                └─────────────────────────────────────►│
                                                       ▼
                                          on_payment_success_sync()
                                                       │
                                          ┌────────────┼────────────┐
                                          ▼            ▼            ▼
                                       UPGRADE      RENEWAL       SAAS
                                       (upgrade)    (renewal)   (initial)
                                          │            │            │
                                          ▼            ▼            ▼
                                      tier_upgrade  renewal_v2  initial_v2
                                       _svc         _runtime    _runtime
                                                       │            │
                                                       └────┬───────┘
                                                            ▼
                                                     Atomic RPC
                                                   (service_role)
                                                        │
                                          ┌─────────────┼─────────────┐
                                          ▼             ▼             ▼
                                       Contract     Commercial    Site Scopes
                                                     Version
                                          │
                                          ▼
                                     Entitlement
                                          │
                                          ▼
                                    Runtime Gate
                                GET /me/commercial/runtime-gate
```

### Renewal 흐름

```
Admin My Contract
        │
        ▼
POST /me/quotes/v2/renewal/issue
  { payment_months: 3|6|9|12 }
        │
        ▼
Frozen Renewal Quote
  (product_tier 현재 CV에서 복사, repricing)
        │
        ▼
POST /me/quotes/v2/{quote_id}/renewal/payment/prepare
        │
        ▼
INIStdPay (Card / DirectBank / VBank)
        │
        ▼
on_payment_success_sync (payment_type=RENEWAL)
        │
        ▼
classify_renewal_runtime_route → "V2"
        │
        ▼
apply_saas_v2_renewal_atomic (RPC)
        │
  ┌─────┴──────┐
  ▼            ▼
old CV      new CV
superseded  version_no+1
_at 설정    renewal_payment_id 설정
            contract.end_date 연장
```

### RS1 흐름

```
cron (0 * * * *)
        │
        ▼
due subscriptions 조회
(next_billing_at <= now)
        │
        ▼
build_v3_recurring_charge_context()
  ├─ subscription ACTIVE 확인
  ├─ billing_key ACTIVE 확인
  └─ cycle-1 success payment 확인
        │
        ▼
INICIS Billing API (INIAPI)
        │
  ┌─────┴──────┐
  ▼            ▼
성공            실패
SUCCESS         FAILED
  │            └──→ cron_job_log status ≠ SUCCESS
  ▼
on_payment_success_sync
(cycle≥2: payment_type=RENEWAL → RENEWAL runtime; cycle=1: payment_type=CARD → SAAS initial runtime)
  │
  ▼
new CV + contract.end_date + next_billing_at 재정렬
```

---

## Section 30 — New Developer Rules

Commercial V3 결제 관련 코드를 수정하기 전에 반드시 준수한다.

1. **이 문서를 먼저 읽는다.**  새 세션에서 과거 WO를 전부 다시 추론하지 않는다.

2. **기존 Pipeline을 확인한다.**  `on_payment_success_sync()` → 분기 구조를 이해한 후 수정한다.

3. **기존 component를 재사용한다.**  새 writer, 새 RPC, 새 atomic 함수를 만들기 전에 기존 것으로 커버되는지 먼저 확인한다.

4. **payment_type과 pg_method를 혼동하지 않는다.**  `payment_type`은 결제의 비즈니스 목적/경로(CARD/RENEWAL/UPGRADE/VBANK)이고, `pg_method`는 실제 PG 수단(Card/DirectBank/VBANK/CardBilling)이다.  `BILLING`은 레거시 값으로 V3 RS1 canonical이 아니다(V3 RS1 canonical = `CARD`(cycle=1) / `RENEWAL`(cycle≥2)).

5. **`plan_code`를 V3 authority로 사용하지 않는다.**  V3 권한 기준은 `product_tier`다. `plan_code = NULL`이 정상이다.

6. **Frozen Quote를 repricing하지 않는다.**  Quote Snapshot에 저장된 금액이 권위다. 결제 금액을 별도로 계산하지 않는다.

7. **client에게 contract/payment authority를 넘기지 않는다.**  company_id, contract_id, subscription_id, billing_key_id는 서버가 auth token에서 파생한다.

8. **신규 PG endpoint를 만들기 전 기존 INIStdPay/Billing 자산을 확인한다.**  단건은 INIStdPay, 정기는 INICIS Billing으로 처리하는 것이 canonical이다.

9. **Legacy path를 삭제하지 않는다.**  V3 이전 계약 고객이 legacy path를 통해 서비스 중일 수 있다. `/payments/tier-gate`, `plan_code` 기반 contract 등을 임의로 제거하지 않는다.

10. **수정 후 GPT 독립검증을 받는다.**  Claude Code PASS ≠ Gate CLOSED. 순서: Claude 실행 → Claude 보고 → GPT 독립검증 → GPT Verdict → Next WO.

---

## Supporting Evidence — Source Files

### tai-api (Backend)

```
services/payment_post_process.py
  - on_payment_success_sync()
  - _bootstrap_buyer_company_admin() (WP-A, Case A/B/C)
  - PAID_STATUS_CODES, SAAS_PRODUCT_TYPES
  - _is_commercial_v3_saas_payment()

services/saas_initial_payment_runtime_v2.py
  - apply_saas_v2_initial_payment_runtime()

services/saas_renewal_runtime_v2.py
  - classify_renewal_runtime_route()
  - apply_saas_v2_renewal_runtime()

services/saas_recurring_billing_scheduler.py
  - build_v3_recurring_charge_context()
  - _charge_subscription_once()
  - SaasRecurringBillingError

services/saas_entitlement_gate_v2.py
  - MANAGER_ENTITLEMENTS, FIELD_ENTITLEMENTS
  - evaluate_saas_entitlement_v2()

services/saas_entitlement_runtime_v2.py
  - resolve_saas_entitlement_context_v2()

services/member_commercial_svc.py
  - get_member_commercial_contract()
  - get_member_runtime_gate()

services/member_subscription_svc.py  (origin/main, WO-07C)
  - get_member_subscription()
  - cancel_member_subscription()
  - _resolve_subscription_by_contract()

services/saas_renewal_quote_svc.py
  - create_renewal_quote()

services/payment_svc.py
  - process_card_success()
  - process_vbank_issued()
  - process_vbank_deposit()

services/payment_helpers.py
  - SAAS_PRODUCT_TYPES
  - DEFAULT_RETURN_URL, BILLING_RETURN_URL
  - make_order_id(), split_supply_vat()

routers/member_quotes.py
  - POST /me/quotes/v2/issue
  - POST /me/quotes/v2/{quote_id}/payment/prepare
  - POST /me/quotes/v2/renewal/issue
  - POST /me/quotes/v2/{quote_id}/renewal/payment/prepare

routers/member_commercial.py
  - GET /me/commercial/contract
  - GET /me/commercial/runtime-gate
  - GET /me/commercial/subscription   (WO-07C)
  - POST /me/commercial/subscription/cancel  (WO-07C)

routers/payment.py
  - POST /payments/inicis/return
  - POST /payments/inicis/vbank/notify

routers/payment_billing.py
  - POST /payments/inicis/billing/return
  - POST /payments/subscriptions/{id}/cancel

db/supabase_client.py
  - get_supabase() — SUPABASE_SERVICE_KEY or SUPABASE_KEY
```

### tai-www (Frontend)

```
src/pages/mypage/checkout/index.astro
  - V3 Frozen Quote → INIStdPay / Billing 분기
```

### tai-admin (Frontend)

```
vue3/src/pages/my-contract/index.vue
  - 계약 목록 표시

vue3/src/pages/my-contract/useV3Renewal.ts
  - V3 수동 갱신 흐름

vue3/src/pages/my-contract/useV3Subscription.ts
  - RS1 구독 조회/해지 (WO-07C)
```
