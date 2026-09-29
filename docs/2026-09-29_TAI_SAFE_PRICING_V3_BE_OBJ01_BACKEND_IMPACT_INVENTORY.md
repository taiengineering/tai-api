---
title: "TAI Safe Pricing V3 — BE-OBJ01 Backend Impact Inventory"
status: FINAL
object: BE-V3-OBJ01
version: "1.0-CLOSED"
date: "2026-09-29"
---

# TAI Safe Pricing V3 — BE-OBJ01 Backend Impact Inventory

STATUS: FINAL / CLOSED / PASS
OBJECT: BE-V3-OBJ01 Backend Impact Inventory
ANCHOR: 67b97fa7b632a4bbffa80356061ce894c5c6e7e7
GPT FACTUAL VERIFY: PASS
GPT SEMANTIC VERIFY: PASS

---

## 1. 목적

Pricing V3 정책(FROZEN `6e34a0cc`) 및 SEMANTIC-INTEGRATION CLOSED(`67b97fa7`) 이후 Backend 전체 Commercial Chain을 전수조사하여 Object별 PRESERVE / REOPEN / SUCCESSOR 판정을 확정한다.

코드 변경 없이 조사 결과만 기록한다.

---

## 2. V3 확정 사실 (재논의 불가)

| 항목 | 확정값 |
|------|--------|
| FIELD facility base | 249,000원/시설/월 (고정, sector/scale 무관) |
| MANAGER base | sector/scale → price_master → compliance base |
| Additional facility | 80% (additional_site_rate_bps=8000) |
| Worker brackets | 1-20:3,000 / 21-50:2,500 / 51-100:2,000 / 101-300:1,500 / 301+:1,200 |
| payment_months discounts | 1=0% / 3=5% / 6=10% / 9=15% / 12=20% |
| payment_months | 결제로 선결제한 서비스 기간; contractual commitment 아님 |
| service interval | [start_date 00:00 KST, end_date 00:00 KST) |
| D-01 | paid_at >= end_boundary → RENEWAL_CONTRACT_EXPIRED |
| Pending renewal limit | 1건 (RENEWAL_ALREADY_SCHEDULED) |
| Snapshot SSOT | Frozen Quote Snapshot (server reprice 금지) |

---

## 3. PRESERVE Objects (15)

### 3.1 Pricing Policy — PRESERVE

`schemas/saas_pricing_policy_v2.py`

- `field_base_amount = 249,000` (L219)
- `additional_site_rate_bps = 8,000` (L221)
- Worker brackets: 1-20/21-50/51-100/101-300/301+ (L223-227)
- payment_months bps: 0/500/1,000/1,500/2,000 (L231-235)
- `policy_version = "TAI_SAFE_PRICING_POLICY_V3_2026_09_28"`
- 100,000 uplift: ABSENT (코드 없음)

### 3.2 Pricing Composer — PRESERVE

`services/saas_pricing_composer_v2.py`

- FIELD path: `product_tier == "FIELD"` → `normal = policy.field_base_amount` (249,000 flat; resolver amount DISCARDED)
- MANAGER path: `product_tier == "MANAGER"` → `normal = s.base_amount` (resolver compliance base)
- Worker: 계약 전체 1회 계산 (시설별 반복 없음)
- Additional: 금액 내림차순 정렬 후 비Primary 시설에 8,000bps 적용
- Discount: integer floor (`raw_prepaid * bps // 10000`)

### 3.3 Base Resolver — PRESERVE

`services/pricing_resolver_svc.py`

- `resolve_plan(sector, criteria_value)` → `price_master` row → `tier_code` + `amount`
- FIELD: resolver 호출하되 반환 amount는 Composer에서 무시 (249,000 사용); `base_band_code`(=`tier_code`)만 사용
- MANAGER: resolver amount = compliance base (직접 사용)
- V3 canonical chain에서 직접 price_master 접근 없음 (모두 resolver 경유)

### 3.4 Preview — PRESERVE

`services/saas_pricing_preview_v2.py`

- 입력: `product_tier`, `worker_capacity`, `payment_months`, `sites[]`
- 출력: `status`, `product_tier`, `pricing_mode`, `payment_months`, `resolved_sites[]`, `calculation`, `block_reason`
- 클라이언트 주입 차단: `extra="forbid"`, `pricing_mode`/`policy_version`/`amount` 서버 파생 전용

### 3.5 Quote — PRESERVE

`services/saas_quote_v2.py`

- 발행 시 서버 reprice: Step 2 `preview_saas_price_v2()` 호출 (클라이언트 snapshot 불신뢰)
- Frozen 보존 필드: `pricing_input` dict + `pricing_snapshot` dict + 전 금액/수량 필드
- `pricing_input` 보존: `product_tier`, `worker_capacity`, `payment_months`, 사업장 목록 (증거 dict)
- 3-way cross-validation: tier/mode/payment_months/사업장 교차 검증

### 3.6 PDF — PRESERVE

`services/member_quote_pdf_svc.py`

- MONTHLY 기간 표시: `item.get("quantity")` (legacy + V3 공통 호환; Semantic-Integration CLOSED)
- live price_master 재조회: ABSENT (Frozen Quote item만 읽음)

### 3.7 Payment Prepare — PRESERVE

`services/saas_payment_v2_adapter.py`

- Amount source: Frozen quote snapshot
- 3-way 금액 검증: quote/item/snapshot
- `period_months = snap.payment_months` (L160)
- `plan_code = None` sentinel 강제

### 3.8 Payment Success — PRESERVE

`services/saas_payment_success_v2_adapter.py`

- 3-way guard: `pay.period_months != snap.payment_months` → `PAY_PERIOD_TERM_MISMATCH` (L283-288)
- `CV.effective_from = paid_at_dt` (L315)
- `plan_code = None` 강제 (`V2_LEGACY_PLAN_CODE_FORBIDDEN` guard)
- `end_date = start + relativedelta(months=period_months)`

### 3.9 Commercial Version — PRESERVE

`schemas/saas_contract_commercial_v2.py`

- `pricing_snapshot`: immutable Pydantic field; `model_validator`가 `payment_months`/tier/mode/policy_version 교차검증
- live price_master 재조회 경로: ABSENT (storage mapper는 snapshot에서만 파생)

### 3.10 Atomic New Contract SQL — PRESERVE

`migrations/2026-09-28_saas_contract_commercial_v2_atomic_apply.sql`

- 컬럼: `payment_months` (NOT NULL INTEGER), `CHECK IN (1,3,6,9,12)` — `term_months` 아님
- Idempotency: `payment.contract_id` 확인 + scope tuple 비교 → `ALREADY_APPLIED`
- Partial state detection: 3 경로

### 3.11 Renewal Plan — PRESERVE

`services/saas_renewal_v2_adapter.py`

- 3-way guard: `pay.period_months != snap.payment_months` → `RENEWAL_PERIOD_TERM_MISMATCH` (L620-625)
- Reprice: ABSENT (`_frozen_snapshot_to_calc_result` — Snapshot SSOT)
- `requested_effective_at`: caller 제공 (paid_at 아님; 모듈 docstring L25)

### 3.12 Renewal Runtime — PRESERVE

`services/saas_renewal_runtime_v2.py`

- D-01 guard: `paid_at_dt >= contract_end_boundary` → `V2_RUNTIME_CONTRACT_EXPIRED` (L341-348)
- Replay invariant: `target_cv.effective_from` anchor (contract.end_date 사용 안 함)

### 3.13 Atomic Renewal SQL — PRESERVE

`migrations/2026-09-28_saas_contract_commercial_v2_renewal_atomic_apply.sql`

- `payment_months` 3-way: `v_snap_payment_months` / `v_pay_period_months` / `CV.payment_months` 3중 검증
- D-01 SQL guard: `v_pay_paid_at >= v_boundary` → `V2_RENEWAL_CONTRACT_EXPIRED`
- `new_end_date = old_end_date + payment_months` (KST midnight boundary)
- Replay anchor: `target_cv.effective_from`

#### Renewal Invariants (두 개 분리)

```text
Future pending renewal max 1건
= saas_renewal_v2_adapter.py
  find_future_commercial_versions_v2()
  → RENEWAL_ALREADY_SCHEDULED (Python adapter-level)

One payment = one renewal CV
= SQL UNIQUE INDEX uix_saas_ccv_renewal_payment_id
  (WHERE renewal_payment_id IS NOT NULL)
  동일 payment_id가 둘 이상의 renewal CV에 사용되는 것 차단
```

이 두 invariant는 서로 다른 보장이다.

### 3.14 Entitlement Domain Logic — PRESERVE

`services/saas_entitlement_gate_v2.py`

- `plan_code`, `contract_level`, `sort_order` 의존: 모두 명시적 금지 (module docstring L10)
- MANAGER → `COMPLIANCE_CORE`
- FIELD → `COMPLIANCE_CORE`, `FIELD_TBM`, `FIELD_RA`, `FIELD_INSPECTION`, `FIELD_SIGN`, `FIELD_HAZARD_REPORT`

### 3.15 Schema Version — PRESERVE

```text
SAAS_PRICING_V2              = schemas/saas_pricing_v2.py
SAAS_QUOTE_V2                = schemas/saas_quote_v2.py
SAAS_CONTRACT_COMMERCIAL_V2  = schemas/saas_contract_commercial_v2.py
```

V3 정책은 `pricing_snapshot.policy_version` 문자열로 분리됨. 스키마 version bump 불필요.

---

## 4. REOPEN Objects (3)

### 4.1 Change Order — REOPEN

`services/saas_change_order_v2.py` / `schemas/saas_change_order_v2.py`

#### V3 충돌 근거

현재 코드: site 비교 루프 (L354-402)에서 product_tier와 무관하게 `cur_sort vs tgt_sort` 비교 후 `SCALE_BAND_INCREASE` / `SCALE_BAND_DECREASE` 생성.

V3 FIELD에서 scale-only band 변화 발생 시:
- `expansion_types.add("SCALE_BAND_INCREASE")` → expansion 존재 판정
- 그러나 FIELD facility price = 249,000 고정 → `target_monthly == current_monthly`
- → `delta = 0` → `INVALID_CHANGE_DELTA` 경로 가능

V3:
```text
FIELD facility price = 249,000 (sector/scale 무관)
FIELD scale band ≠ commercial price axis
```

#### 후속 WO 요구사항

- FIELD-tier-aware site comparison semantics
- FIELD에서 scale band 변화는 Commercial Change trigger 아님
- MANAGER는 현행 scale-band semantics 유지

---

### 4.2 Commercial Fit Gate — REOPEN

`services/saas_commercial_fit_gate_v2.py`

#### V3 충돌 근거

현재 코드: CUSTOM 조기분기(L86) 외 MANAGER/FIELD 동일 `sort_order` 비교 경로.

`L222-227`: `contracted_sort_order < required_sort_order` → `SCALE_BAND_EXCEEDED` → `CHANGE_REQUIRED`

V3:
```text
MANAGER: scale band = compliance pricing axis → sort_order 비교 유효
FIELD:   facility base = 249,000 fixed
         scale band 변화 ≠ 가격 변화
         SCALE_BAND_EXCEEDED → CHANGE_REQUIRED 는 V3 FIELD semantics와 불일치
```

#### 후속 WO 요구사항

- product-tier-aware fit semantics
- FIELD: site scope + FIELD-관련 commercial axis 중심 재정의
- MANAGER/FIELD worker-capacity 책임 경계도 후속 REOPEN에서 명시적 검토
- 임의 결정 금지 (구현 WO에서 GPT 설계 후 진행)

---

### 4.3 Current LEG Gate Wiring — REOPEN (PRE-OPEN BLOCKER)

`routers/legal_engine.py`

#### Blocker 근거

```text
routers/legal_engine.py L21:
  from services.tier_payment_gate_svc import evaluate_saas_tier_gate

LEG endpoints:
  POST /legal-engine/diagnose/industrial-leg   L144
  POST /legal-engine/diagnose/construction-leg L178
  POST /legal-engine/diagnose/building-leg     L207

  모두: _assert_saas_tier_fit_http()
       → evaluate_saas_tier_gate()
       → tier_payment_gate_svc._match_current_plan(contract.plan_code)
```

V3 계약: `plan_code = NULL` (canonical)

```text
_match_current_plan(NULL):
  wanted = (None or "").strip().upper() = ""
  → UNKNOWN_CURRENT_PLAN 발생
```

#### 구조적 충돌 흐름

```text
V3 계약 생성 (plan_code = NULL)
        ↓
현재 SaaS LEG endpoint 호출
        ↓
_assert_saas_tier_fit_http()
        ↓
evaluate_saas_tier_gate()
        ↓
_match_current_plan(NULL)
        ↓
UNKNOWN_CURRENT_PLAN
        ↓
LEG 실행 전 차단
```

#### 후속 WO 요구사항

- Commercial Fit Gate REOPEN 및 Entitlement Runtime 확정 이후에만 LEG wiring 교체
- V1 gate를 먼저 임의 제거하지 않음
- Commercial Fit + Entitlement semantic/runtime contract 확정 → 공식 LEG endpoint wiring 변경

---

## 5. SUCCESSOR_REQUIRED Objects (1)

### 5.1 Entitlement Runtime Wiring — SUCCESSOR_REQUIRED

`saas_entitlement_gate_v2.py` domain logic은 PRESERVE (3.14).

Runtime integration:
```text
router wiring = 0
runtime consumer = 0
```

이는 regression 부족이 아니라 integration 자체가 없는 상태.

"wiring 확인 필요"가 아니라 후속 WO에서 wiring을 새로 구현해야 함.

---

## 6. Legacy Assets

### 6.1 Legacy Tier Gate Service — LEGACY ASSET

`services/tier_payment_gate_svc.py`

- `plan_code` + `price_master.sort_order` 기반 V1 gate
- V3 canonical chain에서 직접 import 없음
- **현재 `routers/legal_engine.py`가 사용 중** (LEG endpoint wiring — REOPEN 4.3 참조)
- `routers/payment.py` → `/tier-gate`, `/tier-upgrade` endpoints도 사용 중
- 삭제 금지 (LEG Gate Wiring REOPEN 완료 전까지)

### 6.2 Legacy Tier Upgrade — LEGACY_ONLY

`services/tier_upgrade_svc.py`

- `plan_code` + `sort_order` 기반 V1 tier upgrade
- V3 canonical chain: ABSENT
- `routers/payment.py` `/tier-upgrade` endpoint 전용

---

## 7. Dead / Unused (1)

### 7.1 contract_level — DEAD/UNUSED_CANDIDATE

- non-test Python 파일 hits: 0
- `saas_entitlement_gate_v2.py` module docstring에서 명시적 금지
- 삭제는 이번 WO 금지 (별도 cleanup WO)

---

## 8. plan_code Consumer 분류

```text
A. V3 fail-closed guards — PRESERVE
   services/saas_payment_v2_adapter.py:159     plan_code=None sentinel
   services/saas_payment_success_v2_adapter.py V2_LEGACY_PLAN_CODE_FORBIDDEN guard
   services/saas_renewal_v2_adapter.py         RENEWAL_LEGACY_PLAN_CODE_FORBIDDEN guard
   services/saas_renewal_runtime_v2.py:168,170 plan_code=NULL guard

B. V3 blocker (current LEG wiring) — REOPEN
   routers/legal_engine.py
   → tier_payment_gate_svc → plan_code dependency
   → V3 contract plan_code=NULL → UNKNOWN_CURRENT_PLAN

C. Legacy runtime — LEGACY_ONLY
   routers/payment.py → /tier-gate, /tier-upgrade
   services/tier_payment_gate_svc.py
   services/tier_upgrade_svc.py

D. Display / reporting — LEGACY/SHARED (no action)
   routers/anonymous_diagnosis.py, diagnosis_plan_recommend.py
   services/customer360_svc.py, automation_svc.py 등
```

---

## 9. Final Decision Matrix

| Object | Candidate | Follow-up |
|--------|-----------|-----------|
| Pricing Policy | PRESERVE | — |
| Pricing Composer | PRESERVE | — |
| Base Resolver | PRESERVE | — |
| Preview | PRESERVE | — |
| Quote | PRESERVE | — |
| PDF | PRESERVE | — |
| Payment Prepare | PRESERVE | — |
| Payment Success | PRESERVE | — |
| Commercial Version | PRESERVE | — |
| Atomic New Contract SQL | PRESERVE | — |
| Change Order | REOPEN | FIELD-tier-aware site comparison |
| Renewal Plan | PRESERVE | — |
| Renewal Runtime | PRESERVE | — |
| Atomic Renewal SQL | PRESERVE | — |
| Commercial Fit Gate | REOPEN | FIELD product-tier-aware fit semantics |
| Entitlement Domain Logic | PRESERVE | — |
| Entitlement Runtime Wiring | SUCCESSOR_REQUIRED | runtime integration WO |
| Legacy Tier Gate Service | LEGACY ASSET | LEG wiring REOPEN 완료 전까지 삭제 금지 |
| Current LEG Gate Wiring | REOPEN | Commercial Fit + Entitlement 확정 후 교체 |
| Legacy Tier Upgrade | LEGACY_ONLY | V1 전용 유지 |
| Schema Version | PRESERVE | — |
| contract_level | DEAD/UNUSED_CANDIDATE | cleanup WO |

**집계:**

```text
PRESERVE              = 15
REOPEN                = 3  (Change Order, Commercial Fit Gate, LEG Gate Wiring)
SUCCESSOR_REQUIRED    = 1  (Entitlement Runtime Wiring)
LEGACY ASSET          = 1  (Tier Gate Service)
LEGACY_ONLY           = 1  (Legacy Tier Upgrade)
DEAD/UNUSED_CANDIDATE = 1  (contract_level)
UNRESOLVED            = 0
TOTAL                 = 22
```

---

## 10. Implementation Dependency Order

```text
1. Commercial Fit Gate semantic REOPEN
2. Change Order semantic REOPEN
3. Entitlement Runtime Integration (SUCCESSOR)
4. LEG Gate Wiring replacement
   (Commercial Fit + Entitlement runtime contract 확정 이후)
5. Integrated regression + pre-open gate
```

LEG Gate를 먼저 임의 교체 금지.
Commercial Fit과 Entitlement의 semantic/runtime contract를 먼저 확정한 후 공식 LEG endpoint wiring 변경.

---

## 11. Production / Deployment 금지

```text
Production DDL    = NOT APPLIED
Deploy            = NOT DONE
PR / Merge        = NOT DONE
```

REOPEN Object 구현 WO 완료 및 GPT Independent Verify 이후에만 진행.
