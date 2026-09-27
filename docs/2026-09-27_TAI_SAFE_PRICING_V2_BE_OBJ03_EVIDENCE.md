---
title: TAI Safe Pricing V2 — BE OBJ03 Evidence Report
status: EVIDENCE_REPORT
goal: G-muju80oq-0a7566
collected_by: Claude Code (COLLECT role)
collected_date: 2026-09-27
review_required: GPT REVIEW REQUIRED
---

# WO-PRICING-V2-BE-OBJ03 Evidence Report

---

## 1. EXECUTION ANCHOR

```
BRANCH  = docs/pricing-canonical-20260927
HEAD    = 931589c419bf0d1b4a178fa1933b4ba8ca1cd62e
STATUS  = 3 untracked files pre-existing (docs/audit/, tools/shared_search/legal_bulk_activate.py, tools/test_universe/fc001_e2e_phase_b.py)
         — not related to this WO
```

---

## 2. FILES CREATED

| 파일 | 라인 수 | 역할 |
|---|---|---|
| `services/saas_pricing_composer_v2.py` | 196 | Pure Domain Engine |
| `tests/test_saas_pricing_composer_v2.py` | 296 | C01~C14 / W / T / R / Floor / Tier / CUSTOM / Integrity |
| `docs/2026-09-27_TAI_SAFE_PRICING_V2_BE_OBJ03_EVIDENCE.md` | — | 이 파일 |

기존 파일 수정: 0

---

## 3. COMPOSER CONTRACT

| 항목 | 구현 |
|---|---|
| Entry point | `calculate_saas_price_v2(selection, sites, policy)` |
| Site Input 별도 | `SaasSitePricingInput` (SaasSiteScope 미사용) |
| Calculation Status | `Literal["READY", "CUSTOM_REQUIRED", "TERM_DISCOUNT_UNRESOLVED"]` |
| Result model | `SaasPricingCalculationResult` |
| Internal breakdown | `SaasSitePricingBreakdown` (Composer 파일 내 정의) |
| Policy default | 함수 정의 시 생성 금지 → `policy=None` → 내부에서 `get_canonical_pricing_policy_v2()` |
| DB access | 0 |
| API endpoint | 0 |
| Runtime wiring | 0 |
| price_master 하드코딩 | 0 |

---

## 4. CALCULATION ORDER

```
1  pricing_mode == CUSTOM → CUSTOM_REQUIRED (Snapshot=None)
2  STANDARD sites == 0 → SaasPricingComposerError
3  Duplicate (entity_type, entity_id) → SaasPricingComposerError
4  Normal site amount per site
     MANAGER: base_amount
     FIELD:   base_amount + policy.field_uplift_amount
5  Canonical sort → Primary
     (-normal DESC, sector ASC, base_band_code ASC, entity_type ASC, str(entity_id) ASC)
6  Site rate 적용
     Primary:    normal × primary_site_rate_bps   // 10000
     Additional: normal × additional_site_rate_bps // 10000
7  site_monthly_total = sum(final_site_amount)
8  Worker 누진 (계약 전체 1회, 사업장 수 무관)
9  monthly_supply_amount = site_monthly_total + worker.amount
10 raw_prepaid_supply_amount = monthly_supply_amount × term_months
11 Term discount 조회 (해당 term 정확히 1개)
12 discount == None → TERM_DISCOUNT_UNRESOLVED (Snapshot=None)
13 READY: discount_amount = raw_prepaid × bps // 10000
          prepaid = raw_prepaid - discount_amount
          vat = prepaid × vat_bps // 10000
          total = prepaid + vat
14 SaasSiteScope 변환 (OBJ01 Contract)
15 SaasPricingSnapshotV2 생성
```

---

## 5. SITE CALCULATION

### MANAGER 3 sites (§49)

| 사업장 | base_amount | normal | rate_bps | final |
|---|---|---|---|---|
| Primary   | 499000 | 499000 | 10000 | 499000 |
| Additional | 299000 | 299000 | 8000  | 239200 |
| Additional | 149000 | 149000 | 8000  | 119200 |

```
site_monthly_total = 857400
```

### FIELD 3 sites (§50)

| 사업장 | base_amount | normal (base+uplift) | rate_bps | final |
|---|---|---|---|---|
| Primary   | 499000 | 599000 | 10000 | 599000 |
| Additional | 299000 | 399000 | 8000  | 319200 |
| Additional | 149000 | 249000 | 8000  | 199200 |

```
site_monthly_total = 1117400
```

### FIELD uplift 적용 원칙

```
additional final = (base_amount + uplift) × 80%
NOT: base_amount × 80% + uplift × 100%
```

---

## 6. WORKER CALCULATION

```
누진 구간 (policy에서 읽음, Composer 하드코딩 없음):
 1~ 20  : 3000/명
21~ 50  : 2500/명
51~100  : 2000/명
101~300 : 1500/명
301+    : 1200/명
```

| capacity | amount |
|---|---|
| 0    | 0 |
| 1    | 3,000 |
| 20   | 60,000 |
| 21   | 62,500 |
| 50   | 135,000 |
| 51   | 137,000 |
| 100  | 235,000 |
| 101  | 236,500 |
| 150  | 310,000 |
| 300  | 535,000 |
| 301  | 536,200 |
| 305  | 541,000 |
| 500  | 775,000 |
| 1000 | 1,375,000 |

Worker amount는 사업장 할인과 독립. monthly = site_total + worker.amount.

---

## 7. TERM HANDLING

```
Canonical policy: 전체 term_months(1,3,6,9,12) discount_rate_bps = None
→ 전부 TERM_DISCOUNT_UNRESOLVED
→ snapshot = None

테스트 전용 resolved policy:
term1 = 0bps  → READY
term12 = 1000bps → READY

None → 0 변환 없음.
```

---

## 8. READY SNAPSHOT

| Snapshot 필드 | 값 |
|---|---|
| schema_version | SCHEMA_VERSION (OBJ01 import) |
| policy_version | policy.policy_version |
| product_tier | selection.product_tier |
| pricing_mode | "STANDARD" |
| sites | canonical 정렬 SaasSiteScope 리스트 |
| worker | SaasWorkerPricingSnapshot |
| term_months | selection.term_months |
| term_discount_rate_bps | resolved integer |
| monthly_supply_amount | — |
| prepaid_supply_amount | raw - discount |
| vat_rate_bps | policy.vat_rate_bps |
| vat_amount | prepaid × vat_bps // 10000 |
| total_amount | prepaid + vat |

---

## 9. CUSTOM HANDLING

```
pricing_mode = CUSTOM:
  status = CUSTOM_REQUIRED
  snapshot = None
  site_breakdown = None
  worker_breakdown = None
  monthly_supply_amount = None

CUSTOM + sites=[] → 허용 (site guard보다 CUSTOM 먼저 처리)
```

---

## 10. TEST RESULT

| ID | 설명 | 결과 |
|---|---|---|
| C01 | STANDARD zero sites rejected | PASS |
| C02 | duplicate site rejected | PASS |
| C03 | MANAGER one site | PASS |
| C04 | FIELD one site | PASS |
| C05 | two equal-price deterministic primary | PASS |
| C06 | two unequal-price highest primary | PASS |
| C07 | three-site MANAGER site total = 857400 | PASS |
| C08 | three-site FIELD site total = 1117400 | PASS |
| C09 | input reorder same result | PASS |
| C10 | mixed sectors accepted | PASS |
| C11 | base_amount=0 rejected | PASS |
| C12 | negative base rejected | PASS |
| C13 | float base rejected | PASS |
| C14 | FIELD additional uplift discounted together | PASS |
| W00~W1000 | 14개 worker 누진 expected values | PASS |
| T01/T03/T06/T09/T12 | canonical term → UNRESOLVED / snapshot=None | PASS |
| R01 | term1 / 0bps → READY | PASS |
| R02 | term12 / 1000bps → READY | PASS |
| R03 | snapshot only READY | PASS |
| R04 | discount arithmetic | PASS |
| R05 | VAT arithmetic | PASS |
| R06 | total arithmetic | PASS |
| Floor-site | additional 101×8000//10000=80 (not 81) | PASS |
| Floor-vat | 101×1000//10000=10 (not 11) | PASS |
| Floor-discount | 11×1000//10000=1 (floor of 1.1) | PASS |
| Tier-manager | no uplift / no worker | PASS |
| Tier-field | per-site uplift / worker charge | PASS |
| Custom-zero | CUSTOM_REQUIRED / snapshot=None | PASS |
| Custom-sites | CUSTOM_REQUIRED / site_breakdown=None | PASS |
| Immutable | canonical policy not mutated | PASS |
| Mutation | input sites not mutated | PASS |
| Determinism | same input → same result.model_dump() | PASS |

```
OBJ03 테스트: 49 PASS / 0 FAIL
```

---

## 11. REGRESSION

```
python3 -m pytest -q \
  tests/test_saas_pricing_v2_contract.py \
  tests/test_saas_pricing_policy_v2.py \
  tests/test_saas_pricing_composer_v2.py
..........................................................................................................
142 passed in 0.16s

OBJ01 (48) + OBJ02 (45) + OBJ03 (49) = 142 PASS / 0 FAIL
```

---

## 12. RUNTIME CONSUMER SEARCH

```bash
grep -R "saas_pricing_composer_v2" \
  routers services --exclude="saas_pricing_composer_v2.py"

결과: 0 matches
```

---

## 13. FILES CHANGED

```
git status --short (신규 파일만):
?? services/saas_pricing_composer_v2.py
?? tests/test_saas_pricing_composer_v2.py
?? docs/2026-09-27_TAI_SAFE_PRICING_V2_BE_OBJ03_EVIDENCE.md

기존 파일 수정: 0
schemas/saas_pricing_v2.py         → 수정 없음
schemas/saas_pricing_policy_v2.py  → 수정 없음
```

---

## 14. NOT_FOUND

- `services/saas_pricing_composer_v2.py` 사전 존재 없음 (충돌 없음)
- `tests/test_saas_pricing_composer_v2.py` 사전 존재 없음 (충돌 없음)

---

## 15. UNVERIFIED

없음.

---

## EXIT CRITERIA CHECK

| 항목 | 결과 |
|---|---|
| Pure Composer 단일 entry point | PASS |
| 별도 Site Pricing Input | PASS |
| Base price 하드코딩 0 | PASS |
| STANDARD 최소 site 1개 | PASS |
| CUSTOM auto pricing 금지 | PASS |
| duplicate site 차단 | PASS |
| entity/sector mapping 유지 | PASS |
| MANAGER uplift 0 | PASS |
| FIELD uplift 사업장별 적용 | PASS |
| FIELD uplift 후 site discount 적용 | PASS |
| 최고 normal price가 Primary | PASS |
| deterministic tie-break | PASS |
| input order invariance | PASS |
| output site canonical order | PASS |
| Primary 100% | PASS |
| Additional 80% | PASS |
| integer flooring | PASS |
| Worker contract-wide 1회 | PASS |
| Progressive worker brackets | PASS |
| Worker 0~1000 boundary tests | PASS |
| Site discount가 worker에 영향 없음 | PASS |
| monthly supply 계산 | PASS |
| raw prepaid 계산 | PASS |
| term None ≠ 0 | PASS |
| canonical policy에서 TERM_DISCOUNT_UNRESOLVED | PASS |
| unresolved snapshot=None | PASS |
| test resolved policy에서 READY | PASS |
| discount 계산 | PASS |
| VAT 계산 | PASS |
| final total 계산 | PASS |
| READY에서만 Snapshot 생성 | PASS |
| policy mutation 0 | PASS |
| input mutation 0 | PASS |
| Runtime consumer 0 | PASS |
| DB read/write 0 | PASS |
| API 0 | PASS |
| Frontend 0 | PASS |
| 기존 93 tests PASS | PASS (93 PASS) |
| 신규 Composer tests PASS | PASS (49 PASS) |

---

```
GPT REVIEW REQUIRED
```
