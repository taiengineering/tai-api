---
title: TAI Safe Pricing V2 — BE-OBJ06 Product Tier Entitlement Gate V2 Evidence Report
status: EVIDENCE_REPORT
goal: G-mujxylms-0a7566
collected_by: Claude Code (COLLECT role)
collected_date: 2026-09-28
review_required: GPT REVIEW REQUIRED
---

# WO-PRICING-V2-BE-OBJ06 Evidence Report

---

## 1. EXECUTION ANCHOR

```
Branch : docs/pricing-canonical-20260927
Base   : 0371d958
```

---

## 2. CANONICAL PRODUCT TIERS

```
MANAGER
FIELD
CUSTOM
```

---

## 3. ENTITLEMENT UNIVERSE

정확히 6개:

```
COMPLIANCE_CORE
FIELD_TBM
FIELD_RA
FIELD_INSPECTION
FIELD_SIGN
FIELD_HAZARD_REPORT
```

추가 코드 없음.

---

## 4. MANAGER POLICY

```
MANAGER_ENTITLEMENTS = (
    "COMPLIANCE_CORE",
)
```

FIELD_* 전부 DENIED.

---

## 5. FIELD POLICY

```
FIELD_ENTITLEMENTS = (
    *MANAGER_ENTITLEMENTS,
    "FIELD_TBM",
    "FIELD_RA",
    "FIELD_INSPECTION",
    "FIELD_SIGN",
    "FIELD_HAZARD_REPORT",
)
```

MANAGER set의 상위집합. 6개 전부 ALLOWED.

---

## 6. CUSTOM POLICY

```
CUSTOM + None → CUSTOM_CONTEXT_REQUIRED (모든 요청)
CUSTOM + []   → DENIED (모든 요청)
CUSTOM + [explicit] → explicit set 기준 ALLOWED/DENIED
```

자동 전체허용 없음. 자동 FIELD 상속 없음.

---

## 7. CUSTOM CONTEXT BOUNDARY

현재 BE-OBJ04 Commercial Storage에 `custom_entitlements` 영구저장 필드 없음.

이번 Object:
- Pure Gate 입력 Contract 정의까지만 수행
- BE-OBJ04 수정 = 0
- `contracts.items` / `addon_codes` / `notes` 사용 = 0

CUSTOM 영구저장은 후속 Runtime/Contract integration Object에서 별도 확정.

---

## 8. SINGLE EVALUATION

```python
evaluate_saas_entitlement_v2(context, requested_entitlement)
→ SaasEntitlementDecisionV2
```

---

## 9. BATCH EVALUATION

```python
evaluate_saas_entitlements_v2(context, requested_entitlements)
→ SaasEntitlementBatchDecisionV2
```

- Duplicate request → SaasEntitlementGateError(DUPLICATE_REQUESTED_ENTITLEMENT)
- 결과 순서 = canonical order (입력 순서 무관)

---

## 10. COMMERCIAL FIT SEPARATION

```
Commercial Fit 의존 = 0
site_scope 필드 = 0
worker_capacity 필드 = 0
Fit status 조건분기 = 0
```

---

## 11. LEG CORE CONTRACT

```
MANAGER → COMPLIANCE_CORE = ALLOWED  (E49 PASS)
FIELD   → COMPLIANCE_CORE = ALLOWED  (E50 PASS)
```

별도 LEG tier gate 호출 없음.

---

## 12. TEST RESULT

### 신규 테스트 매트릭스

| ID | 설명 | 결과 |
|---|---|---|
| E01 | MANAGER COMPLIANCE_CORE → ALLOWED | PASS |
| E02 | MANAGER FIELD_TBM → DENIED | PASS |
| E03 | MANAGER FIELD_RA → DENIED | PASS |
| E04 | MANAGER FIELD_INSPECTION → DENIED | PASS |
| E05 | MANAGER FIELD_SIGN → DENIED | PASS |
| E06 | MANAGER FIELD_HAZARD_REPORT → DENIED | PASS |
| E07 | FIELD COMPLIANCE_CORE → ALLOWED | PASS |
| E08 | FIELD FIELD_TBM → ALLOWED | PASS |
| E09 | FIELD FIELD_RA → ALLOWED | PASS |
| E10 | FIELD FIELD_INSPECTION → ALLOWED | PASS |
| E11 | FIELD FIELD_SIGN → ALLOWED | PASS |
| E12 | FIELD FIELD_HAZARD_REPORT → ALLOWED | PASS |
| E13 | MANAGER effective set exact | PASS |
| E14 | FIELD effective set exact | PASS |
| E15 | MANAGER set ⊂ FIELD set | PASS |
| E16 | CUSTOM None + COMPLIANCE_CORE → CUSTOM_CONTEXT_REQUIRED | PASS |
| E17 | CUSTOM None + FIELD_TBM → CUSTOM_CONTEXT_REQUIRED | PASS |
| E18 | CUSTOM None effective set → [] | PASS |
| E19 | CUSTOM [COMPLIANCE_CORE] → ALLOWED | PASS |
| E20 | same context FIELD_TBM → DENIED | PASS |
| E21 | CUSTOM [FIELD_TBM] → ALLOWED | PASS |
| E22 | CUSTOM explicit mixed composition | PASS |
| E23 | CUSTOM [] COMPLIANCE_CORE → DENIED | PASS |
| E24 | CUSTOM [] FIELD_TBM → DENIED | PASS |
| E25 | CUSTOM [] ≠ CUSTOM_CONTEXT_REQUIRED | PASS |
| E26 | MANAGER + custom_entitlements → rejected | PASS |
| E27 | FIELD + custom_entitlements → rejected | PASS |
| E28 | CUSTOM duplicate entitlement → rejected | PASS |
| E29 | unknown requested entitlement → rejected | PASS |
| E30 | unknown custom entitlement → rejected | PASS |
| E31 | MANAGER batch exact results | PASS |
| E32 | FIELD batch exact results | PASS |
| E33 | CUSTOM None batch → all CUSTOM_CONTEXT_REQUIRED | PASS |
| E34 | CUSTOM explicit batch → membership-based | PASS |
| E35 | batch duplicate request → rejected | PASS |
| E36 | custom entitlement input reorder → same effective order | PASS |
| E37 | requested entitlement reorder → same batch result order | PASS |
| E38 | same input twice → exact same output | PASS |
| E39 | no Commercial Fit import | PASS |
| E40 | no Site Scope | PASS |
| E41 | no worker_capacity | PASS |
| E42 | no pricing resolver (코드 라인 기준) | PASS |
| E43 | no plan_code (코드 라인 기준) | PASS |
| E44 | no contract_level (코드 라인 기준) | PASS |
| E45 | no price calculation | PASS |
| E46 | no payment | PASS |
| E47 | no DB I/O | PASS |
| E48 | no router | PASS |
| E49 | MANAGER COMPLIANCE_CORE LEG contract | PASS |
| E50 | FIELD COMPLIANCE_CORE LEG contract | PASS |

```
python3 -m pytest -q \
  tests/test_saas_pricing_v2_contract.py \
  tests/test_saas_pricing_policy_v2.py \
  tests/test_saas_pricing_composer_v2.py \
  tests/test_saas_contract_commercial_v2.py \
  tests/test_saas_commercial_fit_gate_v2.py \
  tests/test_saas_entitlement_gate_v2.py

330 passed in 0.30s
```

---

## 13. PREVIOUS REGRESSION

```
이전 기준 : 280 PASS
이번 이후 : 330 PASS (280 regression + 50 신규)

FAIL = 0
```

---

## 14. SOURCE GUARDS

```
DB I/O           = 0  (supabase / execute_sql / get_supabase / psycopg 없음)
가격 계산        = 0  (total_amount / base_amount / unit_price 없음)
결제 키워드      = 0  (payment / billing / refund 없음 — 코드 라인 기준)
Commercial Fit   = 0  (commercial_fit / saas_commercial_fit 없음)
Site Scope       = 0  (site_scope / entity_type / entity_id 없음)
Worker           = 0  (worker_capacity / actual_worker_count 없음)
V1 의존          = 0  (pricing_resolver / tier_payment_gate / tier_upgrade_svc 없음 — 코드 라인 기준)
plan_code        = 0  (코드 라인 기준)
contract_level   = 0  (코드 라인 기준)
datetime.now()   = 0
Router wiring    = 0  (APIRouter / from routers / import routers 없음)
```

---

## 15. RUNTIME CONSUMER SEARCH

```bash
grep -R "saas_entitlement_gate_v2" routers/ services/ \
  --exclude="saas_entitlement_gate_v2.py"
```

결과:

```
Runtime consumer = 0
```

---

## 16. PRODUCTION MUTATION

```
INSERT = 0
UPDATE = 0
DELETE = 0
DDL EXECUTION = 0
```

Supabase 접근: 없음.

---

## 17. FILES CHANGED

신규 생성:

```
schemas/saas_entitlement_v2.py
services/saas_entitlement_gate_v2.py
tests/test_saas_entitlement_gate_v2.py
docs/2026-09-28_TAI_SAFE_PRICING_V2_BE_OBJ06_EVIDENCE.md
```

기존 파일 수정:

```
0
```

---

## 18. NOT_FOUND

없음.

---

## 19. UNVERIFIED

없음.

---

```
GPT REVIEW REQUIRED
```
