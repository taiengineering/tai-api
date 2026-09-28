# TAI SAFE Pricing V2 — BE-OBJ10-D-B2 Evidence
## Atomic Prepaid Renewal Persistence

**Date**: 2026-09-28  
**Branch**: docs/pricing-canonical-20260927  
**WO**: WO-PRICING-V2-BE-OBJ10D-B2-001  
**BASE (B1 PATCH1)**: `f0885eae`  
**B2 initial HEAD**: `2fd7ad9e`  
**B2 PATCH1 HEAD**: `0a5632cb`  
**B2 PATCH2 HEAD**: pending commit

---

## 1. Scope

B2 구현 범위:
- SQL artifact: `apply_saas_v2_renewal_atomic` PostgreSQL function
- Python adapter: `services/saas_renewal_atomic_apply_v2.py`
- Adapter/static tests: A01-A36 (`tests/test_saas_renewal_atomic_apply_v2.py`)
- PostgreSQL integration tests: I01-I29 (`tests/test_saas_renewal_atomic_apply_v2_postgres.py`)

**Production mutation = 0** (ARTIFACT ONLY — SQL migration not applied)  
**Schema artifact**: `renewal_payment_id uuid` ADD COLUMN (nullable, artifact only)  
**Runtime wiring = 0** (`payment_post_process.py` untouched)  
**OBJ10-C FREEZE = maintained** (4 files unchanged)

---

## 2. New Files

| File | Role |
|---|---|
| `migrations/2026-09-28_saas_contract_commercial_v2_renewal_atomic_apply.sql` | SQL artifact (ARTIFACT ONLY) |
| `services/saas_renewal_atomic_apply_v2.py` | Python adapter (RPC → plan) |
| `tests/test_saas_renewal_atomic_apply_v2.py` | A01-A36 adapter + SQL static |
| `tests/test_saas_renewal_atomic_apply_v2_postgres.py` | I01-I29 PostgreSQL integration |

---

## 3. SQL Function: `apply_saas_v2_renewal_atomic`

### Security
- `SECURITY INVOKER` (DEFINER 금지)
- `SET search_path = ''` (schema injection 방지)
- `REVOKE EXECUTE FROM PUBLIC, anon, authenticated`
- `GRANT EXECUTE TO service_role`
- Column-level: `GRANT UPDATE (superseded_at, renewal_payment_id) ON saas_contract_commercial_versions TO service_role`

### Lock Order (deadlock prevention)
1. `public.payments FOR UPDATE`
2. `public.contracts FOR UPDATE`
3. `public.saas_contract_commercial_versions FOR UPDATE` (old CV)

### Boundary Derivation
- `v_boundary := (v_con_end_date::timestamp AT TIME ZONE 'Asia/Seoul')`
- DB-derived: PostgreSQL이 authority, caller가 아님
- KST 00:00 boundary = `contract.end_date::timestamp AT TIME ZONE 'Asia/Seoul'`

### PATCH1: 4개 Blocker + P8 수정

| Blocker | 수정 내용 |
|---|---|
| BLOCKER 1 (Cross-payment) | `renewal_payment_id uuid` 컬럼 추가. 기존 new CV의 `renewal_payment_id != p_payment_id` → `V2_RENEWAL_CROSS_PAYMENT_COLLISION` |
| BLOCKER 2 (Term authority) | `new_cv.term_months (top-level) != payment.period_months` → `V2_RENEWAL_TERM_MISMATCH`. 3-way: snapshot.term + new_cv.term + payment.period_months 모두 일치 요구 |
| BLOCKER 3 (Created_by) | `new_cv.created_by != payment.user_id` → `V2_RENEWAL_CV_CREATED_BY_MISMATCH` |
| BLOCKER 4 (Scope completeness) | MANAGER/FIELD + empty scopes → `V2_RENEWAL_SCOPE_REQUIRED`. 중복 entity_id → `V2_RENEWAL_SCOPE_DUPLICATE` |
| P8 | version > N+1 이미 존재 → `V2_RENEWAL_PARTIAL_STATE (reason: unexpected_higher_version_exists)` |

### PATCH2: 3개 Blocker + DB Invariant 강화

| 항목 | 수정 내용 |
|---|---|
| BLOCKER 1 (Payment reuse) | Global consumed guard: `renewal_payment_id = p_payment_id` 전체 스캔. 다른 (contract/version) → `V2_RENEWAL_PAYMENT_ALREADY_CONSUMED` |
| BLOCKER 2 (Scope snapshot SSOT) | MANAGER/FIELD: scope set vs `pricing_snapshot.sites` exact-set 양방향 검증 → `V2_RENEWAL_SCOPE_SNAPSHOT_MISMATCH` |
| BLOCKER 3 (Old CV schema) | `v_old_cv_schema_ver != 'SAAS_CONTRACT_COMMERCIAL_V2'` → `V2_RENEWAL_CURRENT_CV_SCHEMA_INVALID` |
| User NULL guard | `payment.user_id IS NULL` → `V2_RENEWAL_USER_REQUIRED` |
| DB Invariant | `renewal_payment_id` + FK → `payments(id)` + `UNIQUE INDEX WHERE renewal_payment_id IS NOT NULL` |
| Composite duplicate | 중복 체크: `(entity_type, entity_id)` pair (entity_id 단독 → entity_type 포함으로 강화) |
| GRANT 정정 | `GRANT UPDATE (renewal_payment_id)` 제거 (INSERT-only column). `GRANT UPDATE (superseded_at)` 만 유지 |

### Idempotency (ALREADY_APPLIED)
Existing new-version 감지 시 순서:
1. BLOCKER 1: `renewal_payment_id == p_payment_id` (다르면 `V2_RENEWAL_CROSS_PAYMENT_COLLISION`)
2. A: `old.superseded_at == existing.effective_from`
3. D: 13-field exact comparison (CV 필드)
4. E: scope count + tuple match (NULL-safe base_band_code)
5. F: `contract.end_date == orig_boundary_date + term_months`
→ ALREADY_APPLIED or V2_RENEWAL_PARTIAL_STATE

### Error Codes (PATCH1 + PATCH2 추가 포함)
| Code | Condition |
|---|---|
| V2_RENEWAL_PAYMENT_NOT_FOUND | payment 없음 |
| V2_RENEWAL_PAYMENT_NOT_PAID | 결제 상태 불일치 |
| V2_RENEWAL_PAYMENT_TYPE_INVALID | payment_type != RENEWAL |
| V2_RENEWAL_PRODUCT_INVALID | product_type != SAAS |
| V2_RENEWAL_LEGACY_PLAN_CODE_FORBIDDEN | plan_code IS NOT NULL |
| V2_RENEWAL_CONTRACT_MISMATCH | payment.contract_id != p_contract_id |
| V2_RENEWAL_QUOTE_MISMATCH | payment.quote_id != p_quote_id |
| **V2_RENEWAL_USER_REQUIRED** | payment.user_id IS NULL |
| V2_RENEWAL_CONTRACT_NOT_FOUND | contract 없음 |
| V2_RENEWAL_COMPANY_MISMATCH | company_id 불일치 |
| V2_RENEWAL_CONTRACT_NOT_SAAS | service_type != SAAS |
| V2_RENEWAL_CONTRACT_NOT_ACTIVE | is_active = false |
| V2_RENEWAL_END_DATE_REQUIRED | end_date IS NULL |
| **V2_RENEWAL_CURRENT_CV_SCHEMA_INVALID** | old CV commercial_schema_version != V2 |
| **V2_RENEWAL_PAYMENT_ALREADY_CONSUMED** | 동일 payment가 다른 contract/version에 이미 소비됨 |
| V2_RENEWAL_CV_SCHEMA_INVALID | new_cv commercial_schema_version 불일치 |
| V2_RENEWAL_CV_CONTRACT_MISMATCH | new_cv.contract_id != p_contract_id |
| V2_RENEWAL_VERSION_MISMATCH | new_cv.version_no != p_current_version_no + 1 |
| V2_RENEWAL_CV_SUPERSEDED_AT_MUST_BE_NULL | new CV에 superseded_at 설정됨 |
| V2_RENEWAL_AMOUNT_MISMATCH | snapshot amount vs payment amount 불일치 |
| **V2_RENEWAL_TERM_MISMATCH** | new_cv.term_months (top-level) != payment.period_months |
| **V2_RENEWAL_CV_CREATED_BY_MISMATCH** | new_cv.created_by != payment.user_id |
| **V2_RENEWAL_SCOPE_REQUIRED** | MANAGER/FIELD + 0 scopes |
| **V2_RENEWAL_SCOPE_DUPLICATE** | 중복 (entity_type, entity_id) composite key in scopes |
| **V2_RENEWAL_SCOPE_SNAPSHOT_MISMATCH** | scope set != pricing_snapshot.sites exact-set (MANAGER/FIELD) |
| **V2_RENEWAL_CROSS_PAYMENT_COLLISION** | 다른 payment가 이미 이 CV를 생성함 |
| V2_RENEWAL_CURRENT_CV_NOT_FOUND | old CV (p_current_version_no) 없음 |
| V2_RENEWAL_PARTIAL_STATE | 부분 적용 상태 (fail-closed) |
| V2_RENEWAL_BOUNDARY_MISMATCH | new_cv.effective_from != DB-derived boundary |
| ALREADY_APPLIED | 멱등성 분기 (동일 payment 재호출) |
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

### B2 Adapter/Static (A01-A42)

| Range | Description |
|---|---|
| A01-A12 | Adapter 동작 (RPC 호출 계약) |
| A13-A18 | 금지 항목 static 검사 |
| A19-A30 | SQL static 검사 (security/lock/ACL/KST/partial state) |
| A31-A36 | PATCH1 static 검사 (cross-payment/term/created_by/scope) |
| A37-A42 | PATCH2 static 검사 (unique index/FK/consumed/snapshot-mismatch/composite-dup/old-cv-schema) |

**42 PASS / 0 FAIL**

### Full Regression (B1 + B2 PATCH2)

| File | Tests | Result |
|---|---|---|
| `test_saas_commercial_version_time_v2.py` | 29 | 29 PASS |
| `test_saas_commercial_fit_gate_v2.py` | 57 | 57 PASS |
| `test_saas_change_order_v2.py` | 77 | 77 PASS |
| `test_saas_renewal_v2_adapter.py` | 62 | 62 PASS |
| `test_saas_contract_atomic_apply_v2.py` | 110 | 110 PASS |
| `test_saas_pricing_preview_v2.py` | 109 | 109 PASS |
| `test_saas_renewal_atomic_apply_v2.py` | 42 | 42 PASS |
| **TOTAL** | **486** | **486 PASS** |

### B2 PostgreSQL Integration (I01-I36)

`tests/test_saas_renewal_atomic_apply_v2_postgres.py`  
PENDING — DB `tai_test_v2_renewal_atomic` 필요 (GPT 환경에서 실행)

PATCH1 추가: I26 (term mismatch), I27 (created_by mismatch), I28 (scope required), I29 (P8 unexpected version)  
PATCH1 수정: I19 (rollback + scope + paid_amount + paid_at + payment 불변), I25 (→ `V2_RENEWAL_CROSS_PAYMENT_COLLISION`)  
PATCH2 수정: I12-I16 (`renewal_payment_id=pid` on manually inserted new CV), I29 (version 3 closed, non-null superseded_at)  
PATCH2 추가: I30 (same payment consumed), I31 (unique violation), I32 (entity mismatch), I33 (sector mismatch), I34 (composite non-dup), I35 (old CV schema), I36 (user_id NULL)

---

## 7. Fix Log

### Initial (A01-A36 실행 중 발견)
| 문제 | 원인 | 수정 |
|---|---|---|
| A01-A12 TypeError | `_valid_plan_args()`에 `next_version_no=2` 포함 | 제거 |
| A15 FAIL | 어댑터 docstring에 `saas_contract_commercial_versions` | 축약 |
| A17 FAIL | 모듈 docstring에 `_extend_contract_for_renewal` | 변경 |
| A18 FAIL | 모듈 docstring에 `payment_post_process` | 변경 |

### PATCH1 (GPT B2 독립검증 → PATCH1 REQUIRED)
| Blocker | SQL 수정 | Test 수정 |
|---|---|---|
| BLOCKER 1 (Cross-payment) | `renewal_payment_id` ADD COLUMN + idempotency BLOCKER 1 check | I25: `== V2_RENEWAL_CROSS_PAYMENT_COLLISION` |
| BLOCKER 2 (Term authority) | `V2_RENEWAL_TERM_MISMATCH` guard | I26 신규 |
| BLOCKER 3 (Created_by) | `V2_RENEWAL_CV_CREATED_BY_MISMATCH` guard | I27 신규 |
| BLOCKER 4 (Scope completeness) | `V2_RENEWAL_SCOPE_REQUIRED` + `V2_RENEWAL_SCOPE_DUPLICATE` | I28 신규 |
| P8 | unexpected_higher_version_exists guard | I29 신규 |
| I19 incomplete | — | scope count + paid_amount + paid_at + payment 불변 추가 |

### PATCH2 (GPT B2 독립검증 → PATCH2 REQUIRED)
| Blocker | SQL 수정 | Test 수정 |
|---|---|---|
| BLOCKER 1 (Payment reuse) | Global consumed guard + FK + UNIQUE INDEX | I30 신규 (consumed), I31 신규 (unique violation) |
| BLOCKER 2 (Scope snapshot SSOT) | `V2_RENEWAL_SCOPE_SNAPSHOT_MISMATCH` exact-set 양방향 | I32 신규 (entity mismatch), I33 신규 (sector mismatch), I34 신규 (composite non-dup) |
| BLOCKER 3 (Old CV schema) | `V2_RENEWAL_CURRENT_CV_SCHEMA_INVALID` guard | I35 신규 |
| User NULL guard | `V2_RENEWAL_USER_REQUIRED` | I36 신규 |
| GRANT 정정 | `GRANT UPDATE (renewal_payment_id)` 제거 | — |
| Composite duplicate fix | `entity_id` 단독 → `(entity_type, entity_id)` | A41 static 검증 |
| I12-I16 fixture fix | — | `renewal_payment_id=pid` on manually inserted new CV |
| I29 fixture fix | — | version 3 closed (non-null superseded_at) — uq_saas_ccv_current_version 위반 방지 |

---

## 8. Production Safety

- **Production mutation = 0** (no DB write)
- **Schema artifact only**: `renewal_payment_id` column = artifact, not applied
- **OBJ10-C FREEZE = maintained**
- **B3 (runtime wiring) = NOT in scope of B2**
- SQL migration header: `ARTIFACT ONLY — PRODUCTION APPLY = 0 — OWNER APPROVAL REQUIRED`
