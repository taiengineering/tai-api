---
title: TAI Safe Pricing V2 — Canonical Tier Correction Evidence Report
status: EVIDENCE_REPORT
goal: G-muju80oq-0a7566
collected_by: Claude Code (COLLECT role)
collected_date: 2026-09-27
review_required: GPT REVIEW REQUIRED
---

# WO-PRICING-V2-CANONICAL-TIER-CORRECTION-001 Evidence Report

---

## 1. OWNER DECISION

```
ProductTier 3개 확정:

  MANAGER  = 안전관리자용
  FIELD    = 작업자참여형
  CUSTOM   = 커스터마이징 (자동가격 없음, 별도 견적)

CUSTOM은 PricingMode가 아니라 세 번째 Product Tier다.
```

---

## 2. PREVIOUS CONTRACT

```
ProductTier = Literal["MANAGER", "FIELD"]

pricing_mode = STANDARD | CUSTOM
→ CUSTOM은 PricingMode 값이었음
→ MANAGER/FIELD에도 pricing_mode=CUSTOM 입력 가능했음
```

---

## 3. CORRECTED CONTRACT

```
ProductTier = Literal["MANAGER", "FIELD", "CUSTOM"]

Valid combinations:
  MANAGER + STANDARD  = ACCEPT
  FIELD   + STANDARD  = ACCEPT
  CUSTOM  + CUSTOM    = ACCEPT

Invalid combinations (REJECT):
  MANAGER + CUSTOM
  FIELD   + CUSTOM
  CUSTOM  + STANDARD

SaasPricingSnapshotV2:
  product_tier = CUSTOM → REJECT
  pricing_mode ≠ STANDARD → REJECT
```

---

## 4. FILES MODIFIED

| 파일 | 변경 내용 |
|---|---|
| `schemas/saas_pricing_v2.py` | ProductTier 3값, `_tier_mode_combination` 추가, Snapshot validators 추가 |
| `services/saas_pricing_composer_v2.py` | CUSTOM 판정: pricing_mode → product_tier로 변경, block_reason 갱신 |
| `tests/test_saas_pricing_v2_contract.py` | T03 의미 변경, T25 반전, K01~K14 추가 |
| `tests/test_saas_pricing_policy_v2.py` | K15 추가 |
| `tests/test_saas_pricing_composer_v2.py` | 기존 CUSTOM 테스트 2개 보정, K16~K24 추가 |

기존 파일 수정 외 범위: 0

---

## 5. OBJ01 CORRECTION

### schemas/saas_pricing_v2.py 변경사항

**ProductTier:**
```python
# 이전
ProductTier = Literal["MANAGER", "FIELD"]

# 정정
ProductTier = Literal["MANAGER", "FIELD", "CUSTOM"]
```

**SaasCommercialSelection — 신규 validator:**
```python
@model_validator(mode="after")
def _tier_mode_combination(self) -> "SaasCommercialSelection":
    valid_pairs = {("MANAGER", "STANDARD"), ("FIELD", "STANDARD"), ("CUSTOM", "CUSTOM")}
    if (self.product_tier, self.pricing_mode) not in valid_pairs:
        raise ValueError(...)
    return self
```

**SaasPricingSnapshotV2 — 신규 validators:**
```python
@field_validator("product_tier")
def _not_custom_tier → CUSTOM → REJECT

@field_validator("pricing_mode")
def _standard_pricing_mode_only → ≠STANDARD → REJECT
```

**CUSTOM worker_capacity:**
- MANAGER: worker_capacity == 0 (기존 _manager_no_workers 유지)
- FIELD:   worker_capacity >= 0
- CUSTOM:  worker_capacity >= 0 (자동가격 미사용)

**T03 의미 변경:**
```
이전: test_T03_custom_product_tier_rejected
      → ProductTier="CUSTOM" 자체가 invalid
이후: test_T03_custom_standard_rejected
      → CUSTOM+STANDARD 조합이 invalid
(테스트 코드는 동일, REJECT 경로가 Literal→combination으로 변경)
```

**T25 반전:**
```
이전: test_T25_pricing_mode_custom_accepted
      → MANAGER+CUSTOM 허용 (AssertionError 없음)
이후: test_T25_manager_custom_rejected
      → MANAGER+CUSTOM REJECT (ValidationError 발생)
```

---

## 6. OBJ02 REGRESSION

Pricing Policy 값 변경 없음.

```
field_uplift_amount    = 100000
primary_site_rate_bps  = 10000
additional_site_rate_bps = 8000
worker_brackets: 1~20:3000 / 21~50:2500 / 51~100:2000 / 101~300:1500 / 301+:1200
vat_rate_bps           = 1000
term_discounts          = None (전부 미확정)
```

**K15:** `SaasPricingPolicyV2.model_fields`에 "custom" 포함 필드 = 0 ✓

---

## 7. OBJ03 CORRECTION

### services/saas_pricing_composer_v2.py 변경사항

**CUSTOM 판정 기준:**
```python
# 이전
if selection.pricing_mode == "CUSTOM":

# 정정
if selection.product_tier == "CUSTOM":
```

**block_reason:**
```python
# 이전
"pricing_mode=CUSTOM: 자동 가격 계산 불가"

# 정정
"product_tier=CUSTOM: 자동 가격 계산 불가, 별도 견적 필요"
```

**기존 Composer tests 보정:**
```python
# 이전 (MANAGER + CUSTOM → 이제 ValidationError)
_sel(pricing_mode="CUSTOM")

# 정정 (CUSTOM + CUSTOM)
_sel(product_tier="CUSTOM", pricing_mode="CUSTOM")
```

---

## 8. TEST RESULT

### 신규 테스트 매트릭스

| ID | 설명 | 결과 |
|---|---|---|
| K01 | MANAGER + STANDARD accepted | PASS |
| K02 | FIELD + STANDARD accepted | PASS |
| K03 | CUSTOM + CUSTOM accepted | PASS |
| K04 | MANAGER + CUSTOM rejected | PASS |
| K05 | FIELD + CUSTOM rejected | PASS |
| K06 | CUSTOM + STANDARD rejected | PASS |
| K07 | CUSTOM worker_capacity=0 accepted | PASS |
| K08 | CUSTOM worker_capacity>0 accepted | PASS |
| K09 | STARTER still rejected | PASS |
| K10 | BUSINESS rejected | PASS |
| K11 | PRO rejected | PASS |
| K12 | CUSTOM snapshot rejected | PASS |
| K13 | MANAGER+STANDARD snapshot accepted | PASS |
| K14 | FIELD+STANDARD snapshot accepted | PASS |
| K15 | Policy no CUSTOM amount fields | PASS |
| K16 | CUSTOM zero sites → CUSTOM_REQUIRED | PASS |
| K17 | CUSTOM with sites → CUSTOM_REQUIRED | PASS |
| K18 | CUSTOM worker>0 → worker_breakdown=None | PASS |
| K19 | CUSTOM snapshot=None | PASS |
| K20 | CUSTOM monthly_supply_amount=None | PASS |
| K21 | CUSTOM raw_prepaid_supply_amount=None | PASS |
| K22 | MANAGER 3-site regression (857400) | PASS |
| K23 | FIELD 3-site regression (1117400) | PASS |
| K24 | Composer CUSTOM 분기 product_tier 기반 | PASS |

```
python3 -m pytest -q \
  tests/test_saas_pricing_v2_contract.py \
  tests/test_saas_pricing_policy_v2.py \
  tests/test_saas_pricing_composer_v2.py
......................................................................
......................................................................
......................
166 passed in 0.26s

이전 142 + 신규 24 = 166 PASS / 0 FAIL
```

---

## 9. DB DELTA

```
0
```

---

## 10. RUNTIME DELTA

```
수정된 Runtime consumer: 0
```

---

## 11. FRONTEND DELTA

```
0
```

---

## 12. SOURCE SEARCHES

### 2-Tier 정의 잔존 여부

```bash
grep -R 'Literal\["MANAGER", "FIELD"\]' schemas services tests
→ 0 matches — clean
```

### CUSTOM 0원 패턴 (§39)

Production 파일 내 CUSTOM 관련 occurrences 전수:

| 위치 | 내용 | 판정 |
|---|---|---|
| `schemas/saas_pricing_v2.py:23` | `Literal["MANAGER","FIELD","CUSTOM"]` | 타입 정의 |
| `schemas/saas_pricing_v2.py:24` | `Literal["STANDARD","CUSTOM"]` | 타입 정의 |
| `schemas/saas_pricing_v2.py:70` | valid_pairs CUSTOM+CUSTOM | Validation |
| `schemas/saas_pricing_v2.py:216` | CUSTOM → REJECT Snapshot | Guard |
| `services/saas_pricing_composer_v2.py:74` | `CUSTOM_REQUIRED` status | Status literal |
| `services/saas_pricing_composer_v2.py:170` | product_tier == "CUSTOM" | 판정 분기 |
| `services/saas_pricing_composer_v2.py:172` | status="CUSTOM_REQUIRED" | Return value |
| `services/saas_pricing_composer_v2.py:181` | block_reason | 설명 문자열 |

```
CUSTOM amount = 0 패턴: 없음
CUSTOM price 하드코딩: 없음
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
