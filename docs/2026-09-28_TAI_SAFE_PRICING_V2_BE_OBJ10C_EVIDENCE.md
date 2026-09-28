---
title: "TAI Safe Pricing V2 BE-OBJ10-C Evidence"
work_order: WO-PRICING-V2-BE-OBJ10-C
objective: "Atomic Contract Persistence — apply_saas_v2_contract_atomic Postgres RPC"
author: Claude Code
date: 2026-09-28
status: PASS
---

# TAI Safe Pricing V2 BE-OBJ10-C Evidence

## 1. EXECUTION ANCHOR

- Base commit: `001c0346` (OBJ10-B PATCH1 HEAD)
- Branch: `docs/pricing-canonical-20260927`
- New files: 4 (migration SQL, Python RPC adapter, tests, evidence)
- Existing file changes: 0

## 2. NEW FILES

| 파일 | 역할 |
|------|------|
| `migrations/2026-09-28_saas_contract_commercial_v2_atomic_apply.sql` | DDL artifact + Postgres RPC 함수 |
| `services/saas_contract_atomic_apply_v2.py` | Python RPC 어댑터 |
| `tests/test_saas_contract_atomic_apply_v2.py` | C01-C86 (86개) |
| `docs/2026-09-28_TAI_SAFE_PRICING_V2_BE_OBJ10C_EVIDENCE.md` | 이 문서 |

## 3. EXISTING FILE CHANGES

```
services/payment_post_process.py           — 변경 없음
services/saas_payment_success_v2_adapter.py — 변경 없음
schemas/saas_contract_commercial_v2.py     — 변경 없음
schemas/saas_pricing_v2.py                 — 변경 없음
tests/test_saas_payment_success_v2_adapter.py — 변경 없음
```

## 4. MIGRATION SQL — SECTION 구조

| Section | 내용 |
|---------|------|
| Header | `ARTIFACT ONLY / PRODUCTION APPLY = 0 / OWNER APPROVAL REQUIRED` |
| Section 1 | OBJ04 DDL 그대로 승격: `saas_contract_commercial_versions` + `saas_contract_site_scopes` |
| Section 2 | DML 권한 잠금: anon/authenticated에 INSERT/UPDATE/DELETE REVOKE |
| Section 3 | `apply_saas_v2_contract_atomic` 함수 (SECURITY INVOKER, `search_path = ''`) |
| Section 4 | EXECUTE 권한: PUBLIC/anon/authenticated REVOKE, service_role GRANT |

## 5. apply_saas_v2_contract_atomic 함수 설계

```
FUNCTION apply_saas_v2_contract_atomic(
    p_payment_id          uuid,
    p_contract_row        jsonb,
    p_commercial_version  jsonb,
    p_site_scopes         jsonb
)
RETURNS jsonb
SECURITY INVOKER
SET search_path = ''
```

### 반환 status 코드

| status | 의미 |
|--------|------|
| `APPLIED` | 신규 계약 원자 저장 성공 |
| `ALREADY_APPLIED` | 멱등성 — 이미 완료 상태 (v1 commercial 존재) |
| `V2_PAYMENT_NOT_FOUND` | 결제 행 없음 |
| `V2_PAYMENT_NOT_PAID` | status_code ∉ {PAID, SUCCESS} |
| `V2_ATOMIC_PARTIAL_STATE` | 부분 상태 탐지 — fail-closed |

### 내부 단계 (11 Steps)

```
Step 1: SELECT payments FOR UPDATE (concurrent lock)
Step 2: NOT FOUND → V2_PAYMENT_NOT_FOUND 반환
Step 3: status_code 검증 → V2_PAYMENT_NOT_PAID 반환
Step 4: p_contract_row->>'id' → v_contract_id 추출
Step 5: payment.contract_id IS NOT NULL 멱등성 분기
          └ commercial_version_no=1 존재 → ALREADY_APPLIED
          └ 없음 → V2_ATOMIC_PARTIAL_STATE
Step 6: 반대 방향 부분 상태 탐지 (orphan contract) → V2_ATOMIC_PARTIAL_STATE
Step 7: INSERT contracts (jsonb_populate_record)
Step 8: UPDATE payments SET contract_id = v_contract_id
Step 9: INSERT saas_contract_commercial_versions RETURNING id → v_commercial_id
Step 10: JSONB array loop → INSERT saas_contract_site_scopes × N
Step 11: RETURN APPLIED {payment_id, contract_id, commercial_version_id}
```

### 보안 설계

| 항목 | 결정 |
|------|------|
| SECURITY | INVOKER (DEFINER 금지) |
| search_path | `''` (schema injection 방지) |
| EXECUTE 권한 | service_role 전용 |
| anon/authenticated | DML + EXECUTE 모두 REVOKE |
| RLS | 두 테이블 ENABLE (정책 미설정 — 별도 WO) |

### pricing_snapshot NULL 처리

```sql
NULLIF(p_commercial_version->'pricing_snapshot', 'null'::jsonb)
```

- JSON null (`'null'::jsonb`) → SQL NULL
- 실제 JSONB 객체 → 그대로 저장

## 6. Python RPC 어댑터 설계

```
apply_saas_v2_contract_plan_atomic(supabase, plan: SaasV2ApplyPlan) -> dict
```

| 단계 | 내용 |
|------|------|
| 직렬화 | `commercial_version.model_dump(mode="json")`, `[s.model_dump(mode="json") for s in site_scopes]` |
| RPC 호출 | `supabase.rpc("apply_saas_v2_contract_atomic", {...}).execute()` |
| 반환 검증 | `result.data`가 dict이고 `status ∈ _TERMINAL_STATUSES` |
| 오류 | `SaasV2AtomicApplyError(code, message)` |

### _TERMINAL_STATUSES

```python
_TERMINAL_STATUSES: frozenset[str] = frozenset({"APPLIED", "ALREADY_APPLIED"})
```

### SaasV2AtomicApplyError 코드

| code | 발생 조건 |
|------|----------|
| `V2_RPC_ERROR` | supabase.rpc() 예외 또는 result.data가 dict 아님 |
| `V2_PAYMENT_NOT_FOUND` | RPC 반환 status |
| `V2_PAYMENT_NOT_PAID` | RPC 반환 status |
| `V2_ATOMIC_PARTIAL_STATE` | RPC 반환 status |
| `V2_UNEXPECTED_STATUS` | 알 수 없는 status 또는 빈 status |

### 금지 항목 (어댑터 내)

```
DB I/O (직접 .table() / .from_()) = 0
apply_saas_v2_contract_atomic 외 RPC = 0
Python-side retry / partial rollback = 0
Router import = 0
Price engine import = 0
```

## 7. 테스트 결과

| 구분 | 통과 | 실패 |
|------|------|------|
| OBJ10-C 신규 (C01-C86) | 86 | 0 |
| OBJ10-B 회귀 (B01-B95) | 95 | 0 |
| Pricing V2 회귀 | 260+ | 0 |
| Payment 회귀 | 191 | 1 (PRE-EXISTING: gopaymethod) |

**Pre-existing failure**: `test_payment_svc.py::test_run_inicis_prepare_success_minimal` — `gopaymethod == "Card"` 검사 실패. `git stash`로 이전 커밋에서도 동일 실패 확인. OBJ10-C 변경과 무관.

## 8. 불변 조건 확인

| 조건 | 상태 |
|------|------|
| Production DB Mutation | 0 |
| DDL 적용 | 0 (artifact only) |
| contracts 테이블 직접 변경 | 0 |
| 기존 파일 변경 | 0 |
| V1 결제 처리 경로 영향 | 0 |
| SECURITY DEFINER 사용 | 0 (INVOKER 전용) |
| anon/authenticated 직접 write 경로 | 0 |
