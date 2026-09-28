---
title: "TAI Safe Pricing V2 BE-OBJ10-C Evidence"
work_order: WO-PRICING-V2-BE-OBJ10-C
objective: "Atomic Contract Persistence — apply_saas_v2_contract_atomic Postgres RPC"
author: Claude Code
date: 2026-09-28
status: PATCH4_COMPLETE
---

# TAI Safe Pricing V2 BE-OBJ10-C Evidence

## 1. EXECUTION ANCHOR

- Base commit: `001c0346` (OBJ10-B PATCH1 HEAD)
- OBJ10-C initial commit: `ceadcd5a`
- OBJ10-C PATCH1 commit: (see git log HEAD)
- Branch: `docs/pricing-canonical-20260927`
- New files: 4 (migration SQL, Python RPC adapter, tests, evidence)
- Existing file changes (initial): 0
- PATCH1 changes: migration SQL (3 fixes) + tests (P01-P22 추가) + evidence doc + service docstring

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
| `ALREADY_APPLIED` | 멱등성 — commercial v1 + STANDARD tiers의 site_scopes ≥1 완전 상태 |
| `V2_PAYMENT_NOT_FOUND` | 결제 행 없음 |
| `V2_PAYMENT_NOT_PAID` | status_code ∉ {PAID, SUCCESS} |
| `V2_ATOMIC_PARTIAL_STATE` | 부분 상태 탐지 — fail-closed (3 경로) |
| `V2_CONTRACT_ID_MISMATCH` | p_contract_row.id ≠ p_commercial_version.contract_id |
| `V2_VERSION_NO_INVALID` | version_no ≠ 1 |

### 내부 단계 (13 Steps — PATCH1 반영)

```
Step 1:   SELECT payments FOR UPDATE (concurrent lock)
Step 2:   NOT FOUND → V2_PAYMENT_NOT_FOUND 반환
Step 3:   status_code 검증 → V2_PAYMENT_NOT_PAID 반환
Step 4:   p_contract_row->>'id' → v_contract_id 추출
Step 5:   payment.contract_id IS NOT NULL 멱등성 분기 [PATCH1 강화]
            └ SELECT commercial v1 → NOT FOUND → V2_ATOMIC_PARTIAL_STATE
            └ MANAGER/FIELD: COUNT(site_scopes) = 0 → V2_ATOMIC_PARTIAL_STATE
            └ 완전 상태 → ALREADY_APPLIED
Step 6:   orphan contract 탐지 → V2_ATOMIC_PARTIAL_STATE
Step 6.5: contract_id 정합성 검증 [PATCH1 신규]
            └ p_contract_row.id ≠ p_commercial_version.contract_id → V2_CONTRACT_ID_MISMATCH
Step 6.6: version_no = 1 강제 [PATCH1 신규]
            └ version_no ≠ 1 → V2_VERSION_NO_INVALID
Step 7:   INSERT contracts (명시적 컬럼 목록) [PATCH1 수정: jsonb_populate_record → explicit]
Step 8:   UPDATE payments SET contract_id = v_contract_id
Step 9:   INSERT saas_contract_commercial_versions RETURNING id → v_commercial_id
Step 10:  JSONB array loop → INSERT saas_contract_site_scopes × N
Step 11:  RETURN APPLIED {payment_id, contract_id, commercial_version_id}
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

### PATCH1 (기존)

| 구분 | 통과 | 실패 |
|------|------|------|
| OBJ10-C 신규 (C01-C86) | 86 | 0 |
| OBJ10-C PATCH1 (P01-P22) | 22 | 0 |
| OBJ10-C 합계 (C01-C86 + P01-P22) | 108 | 0 |
| OBJ10-B 회귀 (B01-B95) | 95 | 0 |
| Pricing V2 + Payment 회귀 | 258 | 1 (PRE-EXISTING: gopaymethod) |

### PATCH2 (이전)

| 구분 | 통과 | 실패 | 파일 |
|------|------|------|------|
| C01-C86 + P01-P30 + I01-I15 | 131 | 0 | — |
| Pricing V2 + Payment 회귀 | 518 | 1 (PRE-EXISTING: gopaymethod) | — |

### PATCH3 (이전)

| 구분 | 통과 | 실패 |
|------|------|------|
| C01-C86 + P01-P35 + I01-I29 | 150 | 0 |

### PATCH4 (확정)

| 구분 | 통과 | 실패 | 파일 |
|------|------|------|------|
| C01-C86 (어댑터/목) | 86 | 0 | test_saas_contract_atomic_apply_v2.py |
| P01-P36 (SQL 구조 가드) | 36 | 0 | test_saas_contract_atomic_apply_v2.py |
| I01-I30 (Postgres 통합) | 30 | 0 | test_saas_contract_atomic_apply_v2_postgres.py |
| OBJ10-C 합계 | 152 | 0 | — |
| Pricing V2 + Payment 회귀 | 463 | 1 (PRE-EXISTING: gopaymethod) | — |

**Pre-existing failure**: `test_payment_svc.py::test_run_inicis_prepare_success_minimal` — `gopaymethod == "Card"` 검사 실패. OBJ10-C 변경과 무관.

**Test taxonomy (PATCH4 기준)**:
- C01-C86: Python 어댑터 단위 테스트 (FakeSupabase, DB 없음)
- P01-P36: Migration SQL 정적 구조 가드 (파일 읽기, 실행 없음)
- I01-I30: 실제 PostgreSQL@16 통합 테스트 (tai_test_v2_atomic, psycopg2)

## 8. PATCH1 수정 요약

GPT 독립검증(2026-09-28) 지적사항 5건에 대한 수정:

| 지적사항 | 수정 내용 |
|---------|----------|
| ALREADY_APPLIED 완전성 미흡 | Step 5: CV 조회 후 MANAGER/FIELD site_scopes COUNT ≥1 검증 추가 |
| contract_id 정합성 검증 없음 | Step 6.5 신규: p_contract_row.id ≠ CV.contract_id → V2_CONTRACT_ID_MISMATCH |
| version_no=1 강제 없음 | Step 6.6 신규: version_no ≠ 1 → V2_VERSION_NO_INVALID |
| jsonb_populate_record DB DEFAULT 미보존 | Step 7: 명시적 컬럼 목록 INSERT로 교체 |
| SQL 실행 테스트 없음 | P01-P22: SQL 파일 구조 + 보안 가드 + 신규 오류코드 검증 |

## 9. PATCH2 수정 요약 (GPT 2차 독립검증 지적 B1/B2/B3)

| Blocker | 수정 내용 |
|---------|----------|
| B1: ALREADY_APPLIED exact match 미흡 | Step 5: 4-check 교체 (stored=0 / duplicate entity / count / IS NOT DISTINCT FROM tuple) |
| B2: 실제 Postgres 실행 테스트 없음 | I01-I15: psycopg2 + tai_test_v2_atomic 통합 테스트 신규 |
| B3: ACL 불완전 (TRUNCATE 미차단) | Section 2: REVOKE ALL PRIVILEGES → GRANT SELECT,INSERT to service_role 교체 |

### B1 Step 5 변경 상세

| Check | 검증 내용 | 상태 코드 |
|-------|----------|----------|
| Check 1 | stored COUNT = 0 | V2_ATOMIC_PARTIAL_STATE |
| Check 2 | 입력 내 (entity_type, entity_id) 중복 | V2_ATOMIC_PARTIAL_STATE |
| Check 3 | stored COUNT ≠ jsonb_array_length(입력) | V2_ATOMIC_PARTIAL_STATE |
| Check 4 | 모든 expected tuple NOT EXISTS (NULL-safe base_band_code) | V2_ATOMIC_PARTIAL_STATE |

### B3 ACL 변경 상세

```sql
-- PATCH1 (불완전 — TRUNCATE 미차단):
REVOKE INSERT, UPDATE, DELETE ON public.saas_contract_commercial_versions FROM anon;
REVOKE INSERT, UPDATE, DELETE ON public.saas_contract_commercial_versions FROM authenticated;

-- PATCH2 (완전 — REVOKE ALL PRIVILEGES):
REVOKE ALL PRIVILEGES ON TABLE public.saas_contract_commercial_versions
    FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON TABLE public.saas_contract_commercial_versions TO service_role;
```

## 10. PATCH3 수정 요약 (GPT 3차 독립검증 지적 B1/B2)

| Blocker | 수정 내용 |
|---------|----------|
| B1: CUSTOM tier exact scope 미적용 | Step 5: scope COUNT + Check 2/3/4를 모든 tier로 확장 (MANAGER/FIELD AND check만 분기) |
| B1: idempotent path contract/version guard 부재 | Step 5 진입 직후 Guard 1 (contract_id) + Guard 2 (version_no) 추가 |
| B2: DB DEFAULT 실행 증거 없음 | I16: addon_codes={} / items=[] DB DEFAULT 검증 |
| B2: FOR UPDATE 동시성 증거 없음 | I17: 2 connections threading → APPLIED+ALREADY_APPLIED |
| B2: 전체 롤백 어서션 미흡 | I18: contracts/cv/payment.contract_id 모두 확인 |
| B2: service_role positive ACL 없음 | I19: service_role EXECUTE RPC → APPLIED (BYPASSRLS 포함) |
| B2: UPDATE/TRUNCATE/EXECUTE ACL 없음 | I20-I25: anon/authenticated 6종 denied |
| B2: duplicate scope 실행 증거 없음 | I26: duplicate entity_id 재호출 → V2_ATOMIC_PARTIAL_STATE |
| B2: CUSTOM scope 불일치 실행 증거 없음 | I27: CUSTOM 0→1 count mismatch → V2_ATOMIC_PARTIAL_STATE |
| B2: idempotent guard 실행 증거 없음 | I28-I29: wrong contract_id / version_no → mismatch status |

### PATCH3 Step 5 최종 구조

```
IF v_payment_contract_id IS NOT NULL THEN
    Guard 1: v_contract_id ≠ v_payment_contract_id → V2_CONTRACT_ID_MISMATCH
    Guard 2: version_no ≠ 1 → V2_VERSION_NO_INVALID
    CV lookup → NOT FOUND → V2_ATOMIC_PARTIAL_STATE
    COUNT(scope) → all tiers
    Check 1: MANAGER/FIELD AND count=0 → V2_ATOMIC_PARTIAL_STATE
    Check 2: duplicate input (all tiers) → V2_ATOMIC_PARTIAL_STATE
    Check 3: count mismatch (all tiers) → V2_ATOMIC_PARTIAL_STATE
    Check 4: tuple NOT DISTINCT FROM mismatch (all tiers, count>0) → V2_ATOMIC_PARTIAL_STATE
    RETURN ALREADY_APPLIED
END IF;
```

## 11. PATCH4 수정 요약 (GPT 4차 독립검증 지적)

| 변경 | 내용 |
|------|------|
| Step 5 Guard 3 추가 | idempotent retry에서 `p_commercial_version.contract_id ≠ v_payment_contract_id` → V2_CONTRACT_ID_MISMATCH |
| I30 추가 | contract_row.id=A 정상 + CV.contract_id=B 불일치 → V2_CONTRACT_ID_MISMATCH 실제 실행 검증 |
| P36 추가 | Guard 3 정적 구조 가드 |

**Guard 3 필요성**: 기존 Guard 1은 `p_contract_row.id ≠ payment.contract_id` 검사. Step 6.5는 신규 적용 경로에서 `p_commercial_version.contract_id ≠ v_contract_id` 검사. 하지만 idempotent retry 경로에서 `p_commercial_version.contract_id ≠ payment.contract_id` 검사가 없었음. 이 hole로 `contract_row.id=A, CV.contract_id=B`인 잘못된 retry가 ALREADY_APPLIED로 통과 가능.

## 12. 불변 조건 확인

| 조건 | 상태 |
|------|------|
| Production DB Mutation | 0 |
| DDL 적용 | 0 (artifact only) |
| contracts 테이블 직접 변경 | 0 |
| 기존 파일 변경 | 0 (서비스/스키마/기존 라우터 변경 없음) |
| V1 결제 처리 경로 영향 | 0 |
| SECURITY DEFINER 사용 | 0 (INVOKER 전용) |
| anon/authenticated 직접 write 경로 | 0 |
| service_role UPDATE/DELETE 부여 | 0 (SELECT+INSERT 최소권한) |

## Step 5 최종 Guard 구조 (PATCH4 완료)

```
IF v_payment_contract_id IS NOT NULL THEN
    Guard 1: v_contract_id ≠ v_payment_contract_id → V2_CONTRACT_ID_MISMATCH
    Guard 2: version_no ≠ 1 → V2_VERSION_NO_INVALID
    Guard 3: CV.contract_id ≠ v_payment_contract_id → V2_CONTRACT_ID_MISMATCH [PATCH4]
    CV lookup → NOT FOUND → V2_ATOMIC_PARTIAL_STATE
    Count + 4-check exact scope match
    RETURN ALREADY_APPLIED
END IF;
```
