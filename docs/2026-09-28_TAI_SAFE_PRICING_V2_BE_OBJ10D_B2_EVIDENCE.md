# TAI SAFE Pricing V2 — BE-OBJ10-D-B2 Evidence
## Atomic Prepaid Renewal Persistence

**Date**: 2026-09-28  
**Branch**: docs/pricing-canonical-20260927  
**WO**: WO-PRICING-V2-BE-OBJ10D-B2-001  
**BASE (B1 PATCH1)**: `f0885eae`

---

## 1. Scope

B2 구현 범위:
- SQL artifact: `apply_saas_v2_renewal_atomic` PostgreSQL function
- Python adapter: `services/saas_renewal_atomic_apply_v2.py`
- Adapter/static tests: A01-A30 (`tests/test_saas_renewal_atomic_apply_v2.py`)
- PostgreSQL integration tests: I01-I25 (`tests/test_saas_renewal_atomic_apply_v2_postgres.py`)

**Production mutation = 0** (ARTIFACT ONLY — SQL migration not applied)  
**DDL = 0** (no schema change, function is `CREATE OR REPLACE`)  
**Runtime wiring = 0** (`payment_post_process.py` untouched)  
**OBJ10-C FREEZE = maintained** (4 files unchanged)

---

## 2. New Files

| File | Role |
|---|---|
| `migrations/2026-09-28_saas_contract_commercial_v2_renewal_atomic_apply.sql` | SQL artifact (ARTIFACT ONLY) |
| `services/saas_renewal_atomic_apply_v2.py` | Python adapter (RPC → plan) |
| `tests/test_saas_renewal_atomic_apply_v2.py` | A01-A30 adapter + SQL static |
| `tests/test_saas_renewal_atomic_apply_v2_postgres.py` | I01-I25 PostgreSQL integration |

---

## 3. SQL Function: `apply_saas_v2_renewal_atomic`

### Security
- `SECURITY INVOKER` (DEFINER 금지)
- `SET search_path = ''` (schema injection 방지)
- `REVOKE EXECUTE FROM PUBLIC, anon, authenticated`
- `GRANT EXECUTE TO service_role`
- Column-level: `GRANT UPDATE (superseded_at) ON saas_contract_commercial_versions TO service_role`

### Lock Order (deadlock prevention)
1. `public.payments FOR UPDATE`
2. `public.contracts FOR UPDATE`
3. `public.saas_contract_commercial_versions FOR UPDATE` (old CV)

### Boundary Derivation
- `v_boundary := (v_con_end_date::timestamp AT TIME ZONE 'Asia/Seoul')`
- DB-derived: PostgreSQL이 authority, caller가 아님
- KST 00:00 boundary = `contract.end_date::timestamp AT TIME ZONE 'Asia/Seoul'`

### Idempotency (ALREADY_APPLIED)
Existing new-version 감지 시 6-way 정합성 검사:
- A: `old.superseded_at == existing.effective_from`
- D: 13-field exact comparison (CV 필드)
- E: scope count + tuple match (NULL-safe base_band_code)
- F: `contract.end_date == orig_boundary_date + term_months`
→ ALREADY_APPLIED or V2_RENEWAL_PARTIAL_STATE

### Partial State Codes (P1-P8)
- P1-P4: old CV / new CV / scope / contract 불일치
- P5-P8: 복합 불일치
→ V2_RENEWAL_PARTIAL_STATE (fail-closed, auto-repair 없음)

### Error Codes
| Code | Condition |
|---|---|
| V2_RENEWAL_PAYMENT_NOT_FOUND | payment 없음 |
| V2_RENEWAL_NOT_PAID | 결제 상태 불일치 |
| V2_RENEWAL_PAYMENT_TYPE | payment_type != RENEWAL |
| V2_RENEWAL_PRODUCT_TYPE | product_type != SAAS |
| V2_RENEWAL_PLAN_CODE | plan_code IS NOT NULL |
| V2_RENEWAL_CONTRACT_MISMATCH | payment.contract_id != p_contract_id |
| V2_RENEWAL_QUOTE_MISMATCH | payment.quote_id != p_quote_id |
| V2_RENEWAL_CONTRACT_NOT_FOUND | contract 없음 |
| V2_RENEWAL_COMPANY_MISMATCH | company_id 불일치 |
| V2_RENEWAL_NOT_SAAS | service_type != SAAS |
| V2_RENEWAL_NOT_ACTIVE | is_active = false |
| V2_RENEWAL_END_DATE_REQUIRED | end_date IS NULL |
| V2_RENEWAL_PARTIAL_STATE | 부분 적용 상태 |
| ALREADY_APPLIED | 멱등성 분기 |
| APPLIED | 정상 적용 |

---

## 4. Python Adapter: `services/saas_renewal_atomic_apply_v2.py`

```python
_RPC_NAME = "apply_saas_v2_renewal_atomic"

def apply_saas_v2_renewal_plan_atomic(supabase, plan: SaasV2RenewalApplyPlan) -> dict:
    # Single RPC call — no direct table writes
    # Returns {'status': 'APPLIED', ...} or {'status': 'ALREADY_APPLIED', ...}
    # Raises SaasV2RenewalAtomicApplyError on non-success or RPC exception
```

금지 항목 (A13-A18 static 검증):
- 직접 table INSERT/UPDATE 없음
- pricing engine import 없음
- legacy renewal helper 참조 없음
- payment_post_process import 없음

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

### B2 Adapter/Static (A01-A30)

| Range | Description |
|---|---|
| A01-A12 | Adapter 동작 (RPC 호출 계약) |
| A13-A18 | 금지 항목 static 검사 |
| A19-A30 | SQL static 검사 (security/lock/ACL/KST/partial state) |

**30 PASS / 0 FAIL**

### Full Regression (B1 + B2)

| File | Tests | Result |
|---|---|---|
| `test_saas_commercial_version_time_v2.py` | 29 | 29 PASS |
| `test_saas_commercial_fit_gate_v2.py` | 57 | 57 PASS |
| `test_saas_change_order_v2.py` | 77 | 77 PASS |
| `test_saas_renewal_v2_adapter.py` | 62 | 62 PASS |
| `test_saas_contract_atomic_apply_v2.py` | 110 | 110 PASS |
| `test_saas_pricing_preview_v2.py` | 109 | 109 PASS |
| `test_saas_renewal_atomic_apply_v2.py` | 30 | 30 PASS |
| **TOTAL** | **474** | **474 PASS** |

### B2 PostgreSQL Integration (I01-I25)

`tests/test_saas_renewal_atomic_apply_v2_postgres.py`  
PENDING — DB `tai_test_v2_renewal_atomic` 필요 (GPT 환경에서 실행)

---

## 7. Fix Log (A01-A30 실행 중 발견)

| 문제 | 원인 | 수정 |
|---|---|---|
| A01-A12 TypeError | `_valid_plan_args()`에 `next_version_no=2` 포함 — 함수가 내부 계산 | 테스트에서 `next_version_no` 제거 |
| A15 FAIL | 어댑터 함수 docstring에 `saas_contract_commercial_versions` 포함 | docstring에서 "commercial_versions"로 축약 |
| A17 FAIL | 모듈 docstring에 `_extend_contract_for_renewal` 참조 | docstring에서 "legacy renewal helper"로 변경 |
| A18 FAIL | 모듈 docstring에 `payment_post_process` 참조 | docstring에서 "post-process import"로 변경 |

---

## 8. Production Safety

- **Production mutation = 0** (no DB write)
- **DDL = 0** (no schema change)
- **OBJ10-C FREEZE = maintained**
- **B3 (runtime wiring) = NOT in scope of B2**
- SQL migration header: `ARTIFACT ONLY — PRODUCTION APPLY = 0 — OWNER APPROVAL REQUIRED`
