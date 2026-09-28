# TAI SAFE Pricing V2 — BE-OBJ10-D-B1 Evidence
## Temporal Commercial Version Semantics

**Date**: 2026-09-28  
**Branch**: docs/pricing-canonical-20260927  
**WO**: WO-PRICING-V2-BE-OBJ10D-B1-001  
**HEAD (B1 initial)**: `794d5559`  
**HEAD (B1 PATCH1)**: `f0885eae` ← FREEZE READY

---

## 1. Owner Policy (CONFIRMED)

- **RENEWAL_EFFECTIVE_POLICY**: `CURRENT_CONTRACT_END_DATE`
- **Interval**: `[effective_from, superseded_at)` (half-open)
- **Timezone**: `Asia/Seoul` for `contract.end_date` → `effective_at` conversion
- **B2 deferred**: Atomic CV INSERT/UPDATE in separate WO

---

## 2. New Module: `services/saas_commercial_version_time_v2.py`

Pure temporal helpers. No DB I/O, no production mutation.

| Function | Purpose |
|---|---|
| `is_commercial_version_effective_at_v2(cv, as_of)` | Half-open interval check |
| `select_effective_commercial_version_v2(versions, as_of)` | 0→NOT_FOUND / 1→return / 2+→AMBIGUOUS |
| `find_future_commercial_versions_v2(versions, as_of)` | CVs with `effective_from > as_of` |
| `contract_end_date_to_effective_at_v2(end_date)` | DATE → Asia/Seoul 00:00 |

Error codes: `TEMPORAL_NAIVE_DATETIME` / `TEMPORAL_CURRENT_NOT_FOUND` / `TEMPORAL_CURRENT_AMBIGUOUS`

---

## 3. Consumer Migration

### 3.1 `services/saas_commercial_fit_gate_v2.py`

- **Before**: `if cv.superseded_at is not None: raise NON_CURRENT`
- **After**: `is_commercial_version_effective_at_v2(cv, as_of)` — future `superseded_at > as_of` now PASSES

### 3.2 `services/saas_change_order_v2.py`

- **Before**: `if cv.superseded_at is not None: raise NON_CURRENT`
- **After**: `is_commercial_version_effective_at_v2(cv, requested_effective_at)` — temporal anchor = `requested_effective_at`

### 3.3 `services/saas_renewal_v2_adapter.py`

- **Before**: `.is_("superseded_at", "null").limit(1)` DB query
- **After**: fetch all CVs → `select_effective_commercial_version_v2` + `find_future_commercial_versions_v2`
- **New param**: `as_of: datetime` (required, tz-aware) on `prepare_saas_v2_renewal_payment_from_quote`
- **New guard**: `RENEWAL_ALREADY_SCHEDULED` if future-scheduled CV exists
- **New error**: `CURRENT_CV_AMBIGUOUS` if 2+ CVs effective at `as_of`
- **Plan builder (PATCH1)**: transition-source 3-way 판정
  - `superseded_at IS NULL` → PRE-APPLY PASS
  - `superseded_at == requested_effective_at` → IDEMPOTENT REBUILD PASS
  - `superseded_at < requested_effective_at` → `CURRENT_CV_SUPERSEDED`
  - `superseded_at > requested_effective_at` → `RENEWAL_BOUNDARY_CONFLICT` (신규)
- **PATCH1**: timezone-aware 검증을 `superseded_at` 비교 전 선행 이동 → naive+aware `TypeError` 방지

---

## 4. Consumer Inventory — Residual Check

```
grep -rn 'superseded_at.*null|superseded_at.*None|is_("superseded_at"' services/ --include="*.py"
```

**RESULT**: No remaining `superseded_at IS NULL = current` direct interpretation in `services/`.

---

## 5. OBJ10-C FREEZE Verification

Files with CHANGE=0:

| File | Status |
|---|---|
| `migrations/2026-09-28_saas_contract_commercial_v2_atomic_apply.sql` | UNCHANGED |
| `services/saas_contract_atomic_apply_v2.py` | UNCHANGED |
| `tests/test_saas_contract_atomic_apply_v2.py` | UNCHANGED |
| `tests/test_saas_contract_atomic_apply_v2_postgres.py` | UNCHANGED |

---

## 6. Test Results

### New: `tests/test_saas_commercial_version_time_v2.py`

29 tests — **29 PASS / 0 FAIL**

| Range | Description |
|---|---|
| T01–T07 | `is_commercial_version_effective_at_v2` boundary / open-ended |
| T08–T10 | `select_effective_commercial_version_v2` selector |
| T11–T13 | Naive datetime fail-closed |
| T14–T15 | `contract_end_date_to_effective_at_v2` KST boundary |
| CF-T1–T5 | Commercial Fit temporal migration |
| CO-T1–T2 | Change Order temporal migration |
| RN-T1–T5 | Renewal selector (pure) |
| model / string | Duck-typing compatibility |

### B1 Consumer Tests (PATCH1 기준 최종)

| File | Tests | Result |
|---|---|---|
| `test_saas_commercial_version_time_v2.py` | 29 | 29 PASS |
| `test_saas_commercial_fit_gate_v2.py` | 57 | 57 PASS |
| `test_saas_change_order_v2.py` | 77 | 77 PASS |
| `test_saas_renewal_v2_adapter.py` | 62 | 62 PASS |
| `test_saas_contract_atomic_apply_v2.py` | 110 | 110 PASS |
| `test_saas_pricing_preview_v2.py` | 109 | 109 PASS |
| **TOTAL** | **444** | **444 PASS** |

Renewal adapter 62개 = R01-R53 (53) + RN-T1~T5 (5) + RN-T6~T9 (4, PATCH1 신규/갱신).

RN-T6: `superseded_at == requested_effective_at` → PASS (idempotent rebuild)  
RN-T7: `superseded_at < requested_effective_at` → `CURRENT_CV_SUPERSEDED`  
RN-T8: `superseded_at > requested_effective_at` → `RENEWAL_BOUNDARY_CONFLICT`  
RN-T9: naive `requested_effective_at` + aware `superseded_at` → `RENEWAL_EFFECTIVE_AT_INVALID` (no TypeError)

---

## 7. Production Safety

- **Production mutation = 0** (no DB write)
- **DDL = 0** (no schema change)
- **OBJ10-C FREEZE = maintained**
- **B2 (atomic CV INSERT/UPDATE) = NOT in scope of B1**
