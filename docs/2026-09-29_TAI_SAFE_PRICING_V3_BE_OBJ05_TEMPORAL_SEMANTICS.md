---
title: TAI Safe Pricing V3 BE OBJ05 — Temporal Semantics Design
date: 2026-09-29
status: REVIEW_REQUIRED
branch: docs/pricing-canonical-20260927
goal: WO-BE-V3-OBJ05-TEMPORAL-SEMANTICS-001
version: 1.1-PATCH1
---

# TAI Safe Pricing V3 BE OBJ05 — Temporal Semantics Design

## 1. 목적

`term_months`가 현재 구현에서 어떤 역할들을 동시에 수행하는지 사실 기반으로
문서화하고, V3에서 Owner 결정이 필요한 의미론적 경계를 식별한다.

**이 문서는 REVIEW_REQUIRED 상태이다. Owner 결정 전 어떤 항목도 FINAL로 취급
할 수 없다.**

---

## 2. 조사 대상 파일 목록 (OBSERVED)

| 파일 | 역할 |
|---|---|
| `services/saas_pricing_composer_v2.py` | term_months → discount_rate_bps 선택 |
| `schemas/saas_pricing_v2.py` | SaasPricingSnapshotV2.term_months, SaasCommercialSelection.term_months |
| `schemas/saas_pricing_policy_v2.py` | SaasTermDiscountPolicy.term_months, get_canonical_pricing_policy_v2 |
| `services/saas_payment_v2_adapter.py` | period_months=snap.term_months 전달 |
| `services/saas_payment_success_v2_adapter.py` | pay.period_months == snap.term_months 3-way guard |
| `services/saas_renewal_v2_adapter.py` | period_months=snap.term_months; future CV guard |
| `services/saas_renewal_runtime_v2.py` | first_apply: end_date→KST midnight; replay: target.effective_from |
| `services/saas_commercial_version_time_v2.py` | half-open interval [effective_from, superseded_at) |
| `services/payment_post_process.py` | _contract_end_date, _extend_contract_for_renewal (LEGACY) |
| `schemas/saas_contract_commercial_v2.py` | SaasContractCommercialVersionV2.term_months |
| `services/saas_contract_storage_mapper_v2.py` | term_months=selection.term_months 저장 |
| `services/time/tai_time.py` | business_today() = KST date; to_kst() |
| `migrations/…_atomic_apply.sql` | term_months 3-way guard (top-level == snapshot == payment) |
| `migrations/…_renewal_atomic_apply.sql` | new_end_date = old_end_date + term_months months |

---

## 3. Current Coupling Map (SOURCE FACT)

```
term_months (단일 int 값)
    │
    ├─[A] 할인 선택
    │     saas_pricing_composer_v2.py:
    │       selection.term_months → policy.term_discounts[term_months].discount_rate_bps
    │
    ├─[B] payments.period_months
    │     saas_payment_v2_adapter.py L160:
    │       period_months = snap.term_months
    │     3-way guard:
    │       pay.period_months == snap.term_months
    │       (success adapter + renewal adapter 모두 적용)
    │
    ├─[C] contract.end_date 산술
    │     신규: end_date = start_date + relativedelta(months=term_months)
    │     갱신: new_end_date = old_end_date + term_months months (SQL interval)
    │
    └─[D] Commercial Version 레코드 메타데이터
          SaasContractCommercialVersionV2.term_months (저장)
          SaasPricingSnapshotV2.term_months (snapshot)
          DB: saas_contract_commercial_versions.term_months
```

---

## 4. payment_months 의미 분리

### A. OBSERVED CURRENT IMPLEMENTATION (SOURCE FACT)

현재 동일한 숫자가 모든 위치에서 사용된다:
- pricing discount 선택
- snapshot.term_months
- payments.period_months
- contract end_date 연장
- commercial version term_months 저장

### B. FROZEN POLICY FACT

Pricing V3 Frozen Policy에서 확정된 사항:

```
payment_months ≠ contract commitment
```

따라서 `commercial_version.term_months`를 "약정 개월"로 서술하면 안 된다.
정확한 서술: **이 Commercial Version을 생성한 선결제의 서비스 기간 개월 메타데이터**.

contract commitment(약정기간)는 현재 V3에 별도 개념으로 정의되어 있지 않다.

### C. V3 SERVICE PERIOD MODEL (PROPOSED — Owner 승인 전 FINAL 아님)

`payment_months`와 `service_extension_months`를 별도 필드로 분리하지 않는 최소
모델을 권장한다:

```
payment_months == service_extension_months  (현재 구현과 동일)
```

선납 전용 모델에서 두 값은 항상 같으므로 분리할 실익이 없다. D-05 참조.

---

## 5. end_date Interval Semantics (OWNER DECISION REQUIRED)

### 현재 코드에서 관찰되는 사실

```python
# 신규 계약 (payment_post_process.py)
start_date = business_today()              # KST date
end_date   = start_date + relativedelta(months=term_months)

# 갱신 CV effective_from (saas_commercial_version_time_v2.py)
effective_from = end_date at 00:00:00 KST
```

갱신 CV가 `end_date 00:00 KST`부터 발효되므로, 이 boundary 이후로는 서비스
이용 권한이 새 CV 기준으로 전환된다.

### 권장 최소 모델 (PROPOSED)

```
service entitlement interval
= [start_date 00:00 KST,  end_date 00:00 KST)
                                 ↑
                           exclusive paid-through boundary
```

`end_date`는 "마지막 사용 가능 날짜"가 아니다. `end_date - 1 day`가 마지막
서비스 이용일이다.

예:
```
start_date = 2026-09-29
term_months = 1

서비스 이용 구간:
  2026-09-29 00:00 KST  ≤ t  <  2026-10-29 00:00 KST

갱신 CV 발효:
  2026-10-29 00:00:00+09:00
```

이 의미가 기존 half-open `[effective_from, superseded_at)` interval semantics와
정합한다: `old_cv.superseded_at = new_cv.effective_from = end_date midnight KST`.

**Owner Decision D-06**: end_date = exclusive boundary 확정 여부. 현재 구현과
반드시 일치 여부 확인 필요.

---

## 6. Month Addition Rule (VERIFIED)

### 구현 현황

| 경로 | 코드 |
|---|---|
| Python 신규 계약 | `date + relativedelta(months=N)` |
| Python LEGACY 갱신 | `date + relativedelta(months=period_months)` |
| Renewal Atomic SQL | `date + (N \|\| ' months')::interval)::date` |

### Edge Case 비교표

| input date | +N | Python relativedelta | PostgreSQL interval |
|---|---|---|---|
| 2026-01-31 | 1 | 2026-02-28 | 2026-02-28 |
| 2026-02-28 | 1 | 2026-03-28 | 2026-03-28 |
| 2028-02-29 | 12 | 2029-02-28 | 2029-02-28 |

Python 결과: 직접 실행 확인 (VERIFIED).
PostgreSQL 결과: 공식 문서 기반 end-of-month clamping 동작 일치 (PostgreSQL DB
쿼리 미실행 — 이 세션에서 DB 접근 없음).

**판정: CONSISTENT** — 두 방식 모두 end-of-month clamping을 적용하며 동일한
결과를 생성한다. 새 arithmetic 구현 불필요.

---

## 7. Temporal Boundary 규칙 (CONFIRMED SOURCE FACT)

### 7-A. 신규 계약

| 필드 | 값 | 소스 |
|---|---|---|
| `contracts.start_date` | `business_today()` (KST date) | `payment_post_process._activate_existing_contract` |
| `contracts.end_date` | `start_date + relativedelta(months=term_months)` | `payment_post_process._contract_end_date` |
| `cv.effective_from` | `paid_at_dt` (결제 성공 타임스탬프, tz-aware) | `saas_payment_success_v2_adapter` Step 19 |

**Semantic consequence**: `contract.start_date`(00:00 KST date)와
`cv.effective_from`(paid_at timestamp)은 동일 boundary가 아니다. 같은 날이어도:
- 계약 서비스 구간 기준: `start_date 00:00 KST`
- CV commercial 발효 시각: `paid_at` (실제 결제 완료 시각)

Owner Decision D-02 참조.

### 7-B. 갱신 계약 (First Apply)

| 필드 | 값 | 소스 |
|---|---|---|
| `new_cv.effective_from` | `contracts.end_date` at 00:00:00 KST | `saas_commercial_version_time_v2.contract_end_date_to_effective_at_v2` |
| `old_cv.superseded_at` | 동일한 boundary | renewal_atomic SQL Write 1 |
| `new_contracts.end_date` | `old_end_date + term_months months` (DATE 산술) | renewal_atomic SQL Write 4 |
| DB 정합 검증 | `new_cv.effective_from == v_boundary` | `V2_RENEWAL_BOUNDARY_MISMATCH` |

**신규 계약 vs 갱신 계약 핵심 차이 (SOURCE FACT):**
- 신규: `cv.effective_from = paid_at` (결제 타임스탬프)
- 갱신: `cv.effective_from = contracts.end_date midnight KST` (기존 계약 만료 시각)

### 7-C. 갱신 Replay

| 필드 | 값 | 소스 |
|---|---|---|
| `requested_effective_at` | `target_cv.effective_from` (DB 저장값) | `saas_renewal_runtime_v2._run_replay` L272 |

Replay는 `contracts.end_date`를 재계산하지 않는다. 이미 DB에 저장된
`target_cv.effective_from`을 고정 앵커로 사용한다. 이중 연장 방지.

---

## 8. DB 필드 역할 정리

```
payments
  period_months      = term_months at 결제 시점 (선납 개월)
  paid_at            = 결제 성공 타임스탬프 (tz-aware)

contracts
  start_date         = 서비스 시작일 (KST date)
  end_date           = 서비스 exclusive 만료 경계 (KST date)
                       신규: start + term_months
                       갱신: old_end + term_months
  paid_at            = 최근 결제 성공 타임스탬프 (갱신마다 갱신)

saas_contract_commercial_versions
  term_months        = 이 CV를 생성한 선결제의 서비스 기간 개월
                       (payment.period_months와 3-way 보장)
  effective_from     = CV 발효 타임스탬프
                       (신규 = paid_at,  갱신 = old_end_date midnight KST)
  superseded_at      = CV 폐기 타임스탬프
                       (갱신 시 old CV에 설정 = new_cv.effective_from)
  renewal_payment_id = 이 CV를 생성한 갱신 결제 (UNIQUE, nullable)

Half-open interval (saas_commercial_version_time_v2.py):
  CV is effective iff:
    effective_from <= as_of  AND
    (superseded_at IS NULL  OR  as_of < superseded_at)
```

---

## 9. V2 Atomic SQL 3-way Guard 정리

### 신규 계약 (apply_saas_v2_contract_atomic)
```
payment.period_months == snap.term_months    (Python adapter 사전 검증)
snap.term_months == top-level cv.term_months (SaasContractCommercialVersionV2 validator)
```

### 갱신 (apply_saas_v2_renewal_atomic)
```
snap.term_months         == pay.period_months   (V2_RENEWAL_AMOUNT_MISMATCH, field=term_months)
cv_top_level.term_months == pay.period_months   (V2_RENEWAL_TERM_MISMATCH)
new_cv.effective_from    == end_date midnight KST  (V2_RENEWAL_BOUNDARY_MISMATCH)
new_end_date             = old_end_date + cv.term_months months  (Write 4)
```

---

## 10. LEGACY vs V2 경로 분리 (CONFIRMED SOURCE FACT)

`payment_post_process.py`의 `_extend_contract_for_renewal`은 **LEGACY** 경로다.

```
LEGACY: base_start = max(current_end, business_today())
        → 조기(current_end) / 만료 후(today) 모두 처리

V2:     effective_from = contracts.end_date midnight KST (고정)
        contract.status_code = 'ACTIVE' 필수
        _extend_contract_for_renewal call count = 0
        (saas_renewal_runtime_v2.py 모듈 docstring 명시)
```

V3에서 LEGACY 동작은 참고자료일 뿐, V3 정책 근거로 사용하지 않는다.

---

## 11. Early Renewal 분석 (SOURCE FACT)

### 11-A. 단일 조기 갱신 (ONE EARLY RENEWAL)

ACTIVE 계약에서 `paid_at < contract.end_date`인 경우:
- `_run_first_apply` → `select_effective_commercial_version_v2(all_cvs, paid_at)` → CV v1 선택
- `find_future_commercial_versions_v2(all_cvs, paid_at)` → `[]` (미래 CV 없음)
- `requested_effective_at = contract_end_date_to_effective_at_v2(end_date)` = 현재 end_date midnight KST
- atomic apply: old CV.superseded_at = future boundary, new CV.effective_from = future boundary, contract.end_date = old_end + term_months

**판정: 구조적으로 지원 가능 (STRUCTURALLY SUPPORTED CANDIDATE)**

단, 결제 시각과 서비스 발효 시각이 분리된다:
- 결제 완료: `paid_at` (현재 시각)
- 새 서비스 발효: `contract.end_date midnight KST` (미래)

### 11-B. 조기 갱신 후 추가 조기 갱신 (STACKED EARLY RENEWAL)

첫 번째 조기 갱신 완료 후 상태:
- CV v1: effective_from=T, superseded_at=T+6M midnight
- CV v2: effective_from=T+6M midnight, superseded_at=NULL
- contract.end_date = T+12M

`paid_at2 < T+6M`에서 두 번째 갱신 시도:
- `_fetch_and_validate_contract` → `find_future_commercial_versions_v2(all_cvs, paid_at2)`
- CV v2의 `effective_from(T+6M midnight) > paid_at2` → `future_cvs = [CV v2]`
- → `RENEWAL_ALREADY_SCHEDULED` raise (`saas_renewal_v2_adapter.py` L231-237)

**판정: BLOCKED (어댑터 레벨)**

현재 V2 런타임은 미래 예약 CV가 1건이라도 존재하면 추가 갱신을 차단한다.
D-04B Owner 결정 필요.

---

## 12. Late Renewal (만료 후 갱신) (CONFIRMED SOURCE FACT)

V2 소스 사실:
```
saas_renewal_v2_adapter._fetch_and_validate_contract:
  contract.status_code != 'ACTIVE' → CONTRACT_NOT_ACTIVE

saas_renewal_atomic SQL:
  v_con_status_code != 'ACTIVE' OR NOT v_con_is_active
  → V2_RENEWAL_CONTRACT_NOT_ACTIVE
```

**결론: 만료 후 갱신은 현재 V3 Renewal 경로에서 불가.**

Owner 선택안 (D-01 참조):
- A. REACTIVATION flow: 신규 계약 생성, 서비스 시작 = 결제일 (소급 금지)
- B. RENEWAL 확장: 만료 계약도 허용, 별도 atomic design 필요

---

## 13. Replay Invariant (CONFIRMED)

```
Replay anchor = target_cv.effective_from (DB 저장값, 재계산 금지)
Same renewal payment = exactly one mutation
Race recovery = existing invariant 유지
```

`_run_replay`는 `contract.end_date`로 boundary를 재계산하지 않는다.
`_build_and_apply`를 거쳐 `build_saas_v2_renewal_apply_plan`을 호출하지만,
이미 commit된 `target_cv`를 source로 사용하므로 `future_cv guard`가 동일 payment에
재적용되어도 idempotency가 유지된다.

---

## 14. Semantic-Integration Rename Scope

`term_months` → `payment_months` rename 대상 (OBJ02 consumer chain 기준 전수 목록):

**실행 전 필수**: `git grep -n "term_months"` 전수검색으로 최종 목록 확정.

최소 포함 파일:
```
schemas/saas_pricing_v2.py
  SaasCommercialSelection.term_months
  SaasPricingSnapshotV2.term_months
  VALID_TERM_MONTHS

schemas/saas_pricing_policy_v2.py
  SaasTermDiscountPolicy.term_months
  get_canonical_pricing_policy_v2 factory

services/saas_pricing_composer_v2.py

schemas/saas_pricing_preview_v2.py
services/saas_pricing_preview_v2.py

schemas/saas_quote_v2.py
services/saas_quote_v2.py

services/saas_payment_v2_adapter.py
services/saas_payment_success_v2_adapter.py

schemas/saas_contract_commercial_v2.py
services/saas_contract_storage_mapper_v2.py

services/saas_change_order_v2.py

services/saas_renewal_v2_adapter.py
services/saas_renewal_runtime_v2.py

migrations/2026-09-28_saas_contract_commercial_v2_atomic_apply.sql
migrations/2026-09-28_saas_contract_commercial_v2_renewal_atomic_apply.sql

관련 테스트 파일 (7개 이상)
```

---

## 15. Production DDL 상태 및 전략

### 현재 Production 사실 (CONFIRMED)

```
saas_contract_commercial_versions = NOT APPLIED
saas_contract_site_scopes         = NOT APPLIED
V2 stored quotes/payments         = 0
V2 Legacy contracts                = 8
```

### Semantic-Integration 시 DDL 전략

**기본 전략: Production V2 테이블이 아직 미생성이므로,
기존 migration artifact를 V3 canonical schema 기준으로 수정 후 최초 적용.**

```
WRONG approach:
  1. term_months로 V2 테이블 생성 (apply)
  2. payment_months로 ALTER

CORRECT approach:
  migration artifact 자체를 payment_months 기준으로 재작성
  → 단일 최초 apply

V3 column rename 범위:
  saas_contract_commercial_versions.term_months → payment_months
  관련 CHECK constraint 업데이트
  atomic functions 파라미터 및 내부 변수명 업데이트
```

실제 Production DDL 실행: 별도 Owner Gate 필요.

---

## 16. Owner Decision Matrix

| # | 항목 | CURRENT SOURCE FACT | OPTION | RECOMMENDATION (PROPOSED) | OWNER DECISION |
|---|---|---|---|---|---|
| D-01 | 만료 후 갱신 | V2: ACTIVE 필수 → 만료 계약 갱신 불가 | A. REACTIVATION (신규 계약) / B. RENEWAL 확장 (별도 atomic) | A. REACTIVATION (소급 금지) | PENDING |
| D-02 | 신규 CV effective_from | `paid_at_dt` (결제 타임스탬프) | A. 현행 유지 (paid_at) / B. start_date midnight KST로 통일 | A. 현행 유지 (최소 변경) | PENDING |
| D-03 | Semantic rename 시점 | term_months 전 파일 사용 중 | A. Semantic-Integration WO 일괄 / B. defer | A. Semantic-Integration에서 일괄 | PENDING |
| D-04A | 조기 갱신 허용 기간 | 현재 end_date 이전 어느 시점도 가능 (코드 제한 없음) | A. 제한 없음 / B. N일 전부터만 허용 | 임의 window 추가 안 함 (UI 정책 별도) | PENDING |
| D-04B | 미래 예약 CV 상태에서 추가 갱신 | BLOCKED (RENEWAL_ALREADY_SCHEDULED) | A. 1 pending only 유지 / B. multiple prepayments / C. 해제 후 재갱신 | A. 1 pending only 유지 | PENDING |
| D-05 | payment_months ↔ service_months 분리 | 현재 동일 (선납 전용) | A. 동일 유지 / B. 별도 field 분리 | A. 동일 유지 (contract commitment field 없음) | PENDING |
| D-06 | end_date semantics | renewal CV가 end_date 00:00 KST부터 발효 → exclusive boundary 암시 | A. exclusive boundary 확정 / B. inclusive final day | A. exclusive (현재 구현과 정합) | PENDING |

---

## 17. 권장 최소 모델 요약 (PROPOSED — Owner 승인 전 FINAL 아님)

```
D-01: Expired → REACTIVATION (소급 연장 금지)
D-02: cv.effective_from = paid_at 유지 (최소 변경)
D-03: Semantic-Integration WO에서 term_months → payment_months 일괄 rename
D-04A: 별도 갱신 window 제한 없음 (UI 정책 별도 결정)
D-04B: 미래 예약 CV 1건 한정 — RENEWAL_ALREADY_SCHEDULED 유지
D-05: payment_months == service_extension_months (분리 불필요)
D-06: end_date = exclusive service boundary (현재 구현과 정합)
```

---

## 18. OBJ05 범위 외

- price_master DATA WO — V3 cutover 후
- OBJ07 FIELD commercial scope 결정
- Semantic-Integration WO 구현 (rename + DDL)
- 분납/혼합 선납 모델
