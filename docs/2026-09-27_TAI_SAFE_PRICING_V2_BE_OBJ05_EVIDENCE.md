---
title: TAI Safe Pricing V2 — BE-OBJ05 Commercial Fit Gate V2 Evidence Report
status: EVIDENCE_REPORT
goal: G-mujxylms-0a7566
collected_by: Claude Code (COLLECT role)
collected_date: 2026-09-27
review_required: GPT REVIEW REQUIRED
---

# WO-PRICING-V2-BE-OBJ05 Evidence Report

---

## 1. EXECUTION ANCHOR

```
Branch : docs/pricing-canonical-20260927
Base   : 0db334e8
```

---

## 2. GATE DOMAIN CONSTRAINTS

**이 모듈에서 금지된 항목 (소스 가드 테스트 PASS):**

```
DB I/O           = 0  (supabase / execute_sql / get_supabase / psycopg 없음)
가격 계산        = 0  (total_amount / base_amount / unit_price 없음)
VAT 계산         = 0  (vat_rate_bps / policy.vat 없음)
결제 키워드      = 0  (delta / payment / refund / billing 없음 — 코드 라인 기준)
Entitlement 판정 = 0  (entitlement / allowed_features / permissions / menu_code 없음)
datetime.now()   = 0
Router wiring    = 0  (APIRouter / from routers / import routers 없음)
V1 의존          = 0  (tier_payment_gate_svc 없음)
```

---

## 3. VERDICT AXES

```
Axis 1. 사업장 Scope  : 계약된 (entity_type, entity_id) 쌍 안인가
Axis 2. 규모 Band     : required_sort_order <= contracted_sort_order  (sort_order 비교, 금액 비교 금지)
Axis 3. Worker 용량   : actual_worker_count <= cv.worker_capacity (계약 전체 1회 비교)
```

---

## 4. STATUS MAPPING

```
전체 결과:
  FIT                    — 모든 Axis 충족
  CHANGE_REQUIRED        — 1개 이상 Axis 미충족 (MANAGER / FIELD)
  CUSTOM_REVIEW_REQUIRED — CUSTOM tier (자동 판정 불가, 즉시 반환)

사업장별 결과:
  FIT                    — scope 내 + band 충족
  SITE_OUT_OF_SCOPE      — scope 외
  SCALE_BAND_EXCEEDED    — scope 내 + band 초과
```

---

## 5. REASON CODE 집계 순서 (Canonical)

```python
REASON_CODE_ORDER = [
    "SITE_OUT_OF_SCOPE",
    "SCALE_BAND_EXCEEDED",
    "WORKER_CAPACITY_EXCEEDED",
]
```

---

## 6. GATE ERROR CODES

```
NON_CURRENT_COMMERCIAL_VERSION    — superseded_at IS NOT NULL
COMMERCIAL_VERSION_NOT_EFFECTIVE  — effective_from > as_of
DUPLICATE_ACTUAL_SITE             — actual 사업장 중복
SITE_CONTEXT_MISMATCH             — 동일 entity_id인데 sector 불일치
BAND_CATALOG_ENTRY_NOT_FOUND      — catalog에 없는 (sector, base_band_code)
DUPLICATE_BAND_CATALOG_ENTRY      — catalog 내 (sector, base_band_code) 중복
AMBIGUOUS_BAND_ORDER              — 동일 sector 내 sort_order 중복
```

---

## 7. V1 GATE 무변경 확인

```
git diff 0db334e8 -- services/tier_payment_gate_svc.py

결과: (empty) — 변경 없음
```

---

## 8. TEST RESULT

### 신규 테스트 매트릭스

| ID | 설명 | 결과 |
|---|---|---|
| F01 | MANAGER 단일 사업장 FIT | PASS |
| F02 | FIELD 단일 사업장 FIT | PASS |
| F03 | 복수 사업장 전부 FIT | PASS |
| F04 | INDUSTRY + CONSTRUCTION 혼합 FIT | PASS |
| F05 | 동일 sort_order (equal) = FIT | PASS |
| F06 | required < contracted = FIT | PASS |
| F07 | 사업장 0개 FIT | PASS |
| F08 | worker=0 FIT | PASS |
| F09 | SITE_OUT_OF_SCOPE 단일 | PASS |
| F10 | 다중 사업장 일부 out-of-scope | PASS |
| F11 | out-of-scope 사업장 contracted_bbc=None | PASS |
| F12 | CONSTRUCTION site entity PASS | PASS |
| F13 | INDUSTRY factory entity PASS | PASS |
| F14 | BUILDING factory entity PASS | PASS |
| F15 | catalog band 중복 → DUPLICATE_BAND_CATALOG_ENTRY | PASS |
| F16 | catalog sort_order 중복 (동일 sector) → AMBIGUOUS_BAND_ORDER | PASS |
| F17 | 다른 sector의 동일 sort_order = 허용 | PASS |
| F18 | required band catalog 없음 → BAND_CATALOG_ENTRY_NOT_FOUND | PASS |
| F19 | contracted band catalog 없음 → BAND_CATALOG_ENTRY_NOT_FOUND | PASS |
| F20 | contracted base_band_code=None 이면서 scope 내 → BAND_CATALOG_ENTRY_NOT_FOUND | PASS |
| F21 | required > contracted = SCALE_BAND_EXCEEDED | PASS |
| F22 | required == contracted = FIT | PASS |
| F23 | required < contracted = FIT | PASS |
| F24 | worker 0 <= 0 = FIT | PASS |
| F25 | worker 100 <= 100 = FIT | PASS |
| F26 | worker 101 > 100 = WORKER_CAPACITY_EXCEEDED | PASS |
| F27 | worker 1 > 0 = WORKER_CAPACITY_EXCEEDED | PASS |
| F28 | FIELD worker 50 <= 100 = FIT | PASS |
| F29 | FIELD worker 101 > 100 = WORKER_CAPACITY_EXCEEDED | PASS |
| F30 | worker_capacity 미초과이면 reason_codes에 없음 | PASS |
| F31 | worker는 contract-wide (사업장 수 무관) | PASS |
| F32 | 3개 사업장 × worker 33 < 100 = FIT | PASS |
| F33 | SITE_OUT_OF_SCOPE + SCALE_BAND_EXCEEDED 동시 | PASS |
| F34 | SITE_OUT_OF_SCOPE + WORKER_CAPACITY_EXCEEDED 동시 | PASS |
| F35 | 3가지 reason_codes 동시 + canonical order | PASS |
| F36 | CUSTOM → CUSTOM_REVIEW_REQUIRED (사업장 있음) | PASS |
| F37 | CUSTOM → CUSTOM_REVIEW_REQUIRED (사업장 없음) | PASS |
| F38 | CUSTOM → reason_codes=[] | PASS |
| F39 | CUSTOM → site_results=[] | PASS |
| F40 | superseded_at IS NOT NULL → NON_CURRENT_COMMERCIAL_VERSION | PASS |
| F41 | effective_from > as_of → COMMERCIAL_VERSION_NOT_EFFECTIVE | PASS |
| F42 | effective_from == as_of = 허용 | PASS |
| F43 | effective_from < as_of = 허용 | PASS |
| F44 | 동일 입력 2회 호출 = 동일 결과 (결정론) | PASS |
| F45 | contract_bundle mutate 없음 | PASS |
| F46 | actual_state mutate 없음 | PASS |
| F47 | band_catalog mutate 없음 | PASS |
| F48 | source guard: 가격 키워드 없음 | PASS |
| F49 | source guard: VAT 계산 없음 | PASS |
| F50 | source guard: 결제 키워드 없음 (코드 라인 기준) | PASS |
| F51 | source guard: entitlement 없음 | PASS |
| F52 | source guard: DB I/O 없음 | PASS |
| F53 | source guard: router 없음 | PASS |

```
python3 -m pytest -q \
  tests/test_saas_pricing_v2_contract.py \
  tests/test_saas_pricing_policy_v2.py \
  tests/test_saas_pricing_composer_v2.py \
  tests/test_saas_contract_commercial_v2.py \
  tests/test_saas_commercial_fit_gate_v2.py

280 passed in 0.28s
```

---

## 9. REGRESSION

```
이전 기준 : 227 PASS
이번 이후 : 280 PASS (227 regression + 53 신규)

FAIL = 0
```

---

## 10. RUNTIME CONSUMER SEARCH

검색 대상:

```
routers/
services/payment_svc.py
services/payment_post_process.py
services/contract_engine_svc.py
services/tier_payment_gate_svc.py
services/pricing_resolver_svc.py
```

검색어:

```
saas_commercial_fit_gate_v2
evaluate_saas_commercial_fit_v2
```

결과:

```
Runtime consumer = 0
```

---

## 11. PRODUCTION MUTATION

```
INSERT = 0
UPDATE = 0
DELETE = 0
DDL EXECUTION = 0
```

Production Supabase 접근: 없음.

---

## 12. FILES CHANGED

신규 생성:

```
schemas/saas_commercial_fit_v2.py
services/saas_commercial_fit_gate_v2.py
tests/test_saas_commercial_fit_gate_v2.py
docs/2026-09-27_TAI_SAFE_PRICING_V2_BE_OBJ05_EVIDENCE.md
```

기존 파일 수정:

```
0
```

---

## 13. NOT_FOUND

없음.

---

## 14. UNVERIFIED

없음.

---

```
GPT REVIEW REQUIRED
```
