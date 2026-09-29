---
title: TAI Safe Pricing V3 BE OBJ05 — Temporal Semantics Design
date: 2026-09-29
status: DESIGN
branch: docs/pricing-canonical-20260927
goal: WO-BE-V3-OBJ05-TEMPORAL-SEMANTICS-001
version: 1.0
---

# TAI Safe Pricing V3 BE OBJ05 — Temporal Semantics Design

## 1. 목적

`term_months`가 현재 4가지 역할을 동시에 수행하고 있음을 문서화하고,
V3에서 각 역할에 대한 명시적 의미 정의와 DB 필드 결정, 그리고 Owner 판단이
필요한 항목을 식별한다.

---

## 2. 조사 대상 파일 목록 (OBSERVED)

| 파일 | 역할 |
|---|---|
| `services/saas_pricing_composer_v2.py` | term_months → discount_rate_bps 선택 |
| `schemas/saas_pricing_v2.py` | SaasPricingSnapshotV2.term_months 정의 |
| `services/saas_payment_v2_adapter.py` | period_months=snap.term_months 전달 |
| `services/saas_payment_success_v2_adapter.py` | pay.period_months == snap.term_months 3-way guard |
| `services/saas_renewal_v2_adapter.py` | period_months=snap.term_months; renewal effective_from = requested_effective_at |
| `services/saas_renewal_runtime_v2.py` | first_apply: end_date→KST midnight; replay: target.effective_from |
| `services/saas_commercial_version_time_v2.py` | half-open interval [effective_from, superseded_at) |
| `services/payment_post_process.py` | _contract_end_date, _extend_contract_for_renewal (LEGACY) |
| `schemas/saas_contract_commercial_v2.py` | SaasContractCommercialVersionV2.term_months |
| `services/saas_contract_storage_mapper_v2.py` | term_months=selection.term_months 저장 |
| `services/time/tai_time.py` | business_today() = KST date; to_kst() |
| `migrations/…_atomic_apply.sql` | term_months 3-way guard (top-level == snapshot == payment) |
| `migrations/…_renewal_atomic_apply.sql` | new_end_date = old_end_date + term_months months |

---

## 3. Current Coupling Map

```
term_months (단일 값)
    │
    ├─[A] 할인 선택          composer.py L204-전
    │     snap.term_months → policy.discount_rate_bps 선택
    │     V3: {1:0bps, 3:500bps, 6:1000bps, 9:1500bps, 12:2000bps}
    │
    ├─[B] payment.period_months
    │     saas_payment_v2_adapter.py L160: period_months=snap.term_months
    │     3-way guard: pay.period_months == snap.term_months (success/renewal adapter)
    │     DB: payments.period_months = term_months
    │
    ├─[C] contract.end_date 계산
    │     신규: end_date = start_date + relativedelta(months=term_months)
    │     갱신: new_end_date = old_end_date + term_months months (SQL)
    │
    └─[D] Commercial Version 레코드 메타데이터
          SaasContractCommercialVersionV2.term_months
          SaasPricingSnapshotV2.term_months
          DB: saas_contract_commercial_versions.term_months
```

---

## 4. 의미 정의 (V3 목표)

아래 4개 개념은 현재 모두 `term_months` 단일 값을 공유한다.
V3 Semantic-Integration 시점에 `payment_months`로 명시적 rename한다.

| 의미 이름 | 정의 | 현재 필드 | V3 rename 목표 |
|---|---|---|---|
| **payment_months** | 이 거래에서 선납하는 서비스 개월 수 | `term_months` | `payment_months` |
| **discount_basis_months** | 할인율 선택 기준 개월 수 | `term_months` | `payment_months` (동일) |
| **contract_extension_months** | contract.end_date 연장 개월 수 | `term_months` | `payment_months` (동일) |
| **cv_term** | Commercial Version 레코드의 약정 개월 메타데이터 | `term_months` | `payment_months` (동일) |

> **현재 모델에서는 4개 값이 항상 동일하다 (선납 전용 모델).** 결합은 의도적이며
> 깨뜨릴 근거가 없다. Rename 목표는 의미 명확성이며 값 분리가 아니다.

---

## 5. Temporal Boundary 규칙 (CONFIRMED)

### 5-A. 신규 계약

| 시점 | 계산 방법 | 소스 |
|---|---|---|
| `contracts.start_date` | `business_today()` (KST) | `payment_post_process._activate_existing_contract` |
| `contracts.end_date` | `start_date + relativedelta(months=term_months)` | `payment_post_process._contract_end_date` |
| `cv.effective_from` | `paid_at_dt` (결제 성공 타임스탬프, tz-aware) | `saas_payment_success_v2_adapter` Step 19 |

### 5-B. 갱신 계약 (First Apply)

| 시점 | 계산 방법 | 소스 |
|---|---|---|
| `new_cv.effective_from` | `contracts.end_date` at 00:00:00 KST | `saas_commercial_version_time_v2.contract_end_date_to_effective_at_v2` |
| `old_cv.superseded_at` | 동일한 boundary | renewal_atomic SQL Write 1 |
| `new_contracts.end_date` | `old_end_date + term_months months` (DATE 산술) | renewal_atomic SQL Write 4 |
| DB 정합 검증 | `new_cv.effective_from == v_boundary` | V2_RENEWAL_BOUNDARY_MISMATCH |

**신규 계약 vs 갱신 계약 핵심 차이:**
- 신규: `cv.effective_from = paid_at` (결제 타임스탬프)
- 갱신: `cv.effective_from = contracts.end_date midnight KST` (기존 계약 만료 시각)

### 5-C. 갱신 Replay

| 시점 | 계산 방법 | 소스 |
|---|---|---|
| `requested_effective_at` | `target_cv.effective_from` (DB에서 읽음) | `saas_renewal_runtime_v2._run_replay` L272 |

> Replay는 `contracts.end_date`를 재계산하지 않는다. 이미 DB에 저장된
> `target_cv.effective_from`을 고정 앵커로 사용한다. 이중 연장 방지.

---

## 6. DB 필드 역할 정리

```
payments
  period_months   = term_months at 결제 시점 (선납 개월)
  paid_at         = 결제 성공 타임스탬프

contracts
  start_date      = 서비스 시작일 (KST date) — 신규 활성화 시 business_today()
  end_date        = 서비스 만료일 (KST date) — 신규: start+term_months, 갱신: old_end+term_months
  paid_at         = 최근 결제 성공 타임스탬프 (갱신마다 갱신)

saas_contract_commercial_versions
  term_months     = 이 CV 버전의 약정 개월 (= payment.period_months, 3-way 보장)
  effective_from  = CV 발효 타임스탬프 (신규=paid_at, 갱신=old_end_date midnight KST)
  superseded_at   = CV 폐기 타임스탬프 (갱신 시 old CV에 설정 = new CV.effective_from)
  renewal_payment_id = 이 CV를 생성한 갱신 결제 (UNIQUE, nullable)

Half-open interval: CV is effective iff effective_from <= as_of < superseded_at
```

---

## 7. 비즈니스 시나리오 매트릭스

| 시나리오 | start/boundary | end_date | cv.effective_from | cv.superseded_at |
|---|---|---|---|---|
| 신규 계약 (6개월) | T = business_today() | T + 6M | paid_at | NULL |
| 갱신 (동일 6개월) | 기존 end_date | old_end + 6M | old_end midnight KST | NULL |
| 갱신 replay | — | (변경 없음) | target_cv.effective_from (고정) | — |
| 조기 갱신 (레거시 경로) | base_start = current_end | base_start + period_months | N/A (레거시) | N/A |
| 만료 후 갱신 (레거시 경로) | base_start = business_today() | base_start + period_months | N/A (레거시) | N/A |

---

## 8. V2 Atomic SQL 3-way Guard 정리

### 신규 계약 (apply_saas_v2_contract_atomic)
```
payment.period_months == snap.term_months    ← Python adapter 사전 검증
snap.term_months == top-level cv.term_months ← SaasContractCommercialVersionV2 model validator
```

### 갱신 (apply_saas_v2_renewal_atomic)
```
snap.term_months          == pay.period_months   (V2_RENEWAL_AMOUNT_MISMATCH field=term_months)
cv_top_level.term_months  == pay.period_months   (V2_RENEWAL_TERM_MISMATCH)
new_cv.effective_from     == contracts.end_date midnight KST  (V2_RENEWAL_BOUNDARY_MISMATCH)
new_end_date              = old_end_date + cv.term_months     (Write 4)
```

> 3-way guard 의미: 견적(snap) ↔ 결제(pay) ↔ CV(저장) 세 값이
> 항상 일치해야 함. 값 분리 시 이 guard 전체를 재설계해야 한다.

---

## 9. LEGACY vs V2 경로 분리 (CONFIRMED)

`payment_post_process.py`의 `_extend_contract_for_renewal`은 **LEGACY** 경로이다.

- **LEGACY**: `base_start = max(current_end, business_today())` → 조기/지연 갱신 모두 허용
- **V2**: `effective_from = contracts.end_date midnight KST` 고정; `contract.status_code = 'ACTIVE'` 필수
- V2 경로에서 `_extend_contract_for_renewal` 호출 = 0 (`saas_renewal_runtime_v2.py` 주석 명시)

---

## 10. `payment_months` Rename 범위 (Semantic-Integration 시점 실행)

rename 대상: `term_months` → `payment_months` (13개 이상 파일)

| 파일 | 변경 유형 |
|---|---|
| `schemas/saas_pricing_v2.py` | `SaasCommercialSelection.term_months`, `SaasPricingSnapshotV2.term_months`, `VALID_TERM_MONTHS` |
| `schemas/saas_pricing_policy_v2.py` | `_canonical_term_discount_rates()` key rename |
| `services/saas_pricing_composer_v2.py` | `selection.term_months`, `snap.term_months` |
| `services/saas_payment_v2_adapter.py` | `period_months=snap.term_months` → `period_months=snap.payment_months` |
| `services/saas_payment_success_v2_adapter.py` | `snap.term_months` 3곳 |
| `services/saas_renewal_v2_adapter.py` | `snap.term_months`, `period_months` |
| `services/saas_renewal_runtime_v2.py` | `v_snap_term` 참조 |
| `schemas/saas_contract_commercial_v2.py` | `SaasContractCommercialVersionV2.term_months` |
| `services/saas_contract_storage_mapper_v2.py` | `term_months=selection.term_months` |
| `migrations/…_renewal_atomic.sql` | `term_months` 컬럼 → `payment_months` (DDL ALTER) |
| `migrations/…_atomic_apply.sql` | 동일 |
| 7개 테스트 파일 | `field_base_amount` 처럼 일괄 rename |

> **OBJ03에서 이 rename을 시도하지 않았음.** DB 컬럼명 변경이 수반되므로
> Semantic-Integration WO에서 DDL + 코드 + 테스트를 한 번에 처리해야 한다.

---

## 11. Owner 판단 필요 항목

| # | 항목 | 현재 상태 | 결정 필요 내용 |
|---|---|---|---|
| D-01 | 만료 후 V2 갱신 | V2 SQL: `contract.status_code = 'ACTIVE'` 필수 → 만료 계약은 갱신 불가 | 만료 후 재계약 허용 여부 (REACTIVATION WO 별도?) |
| D-02 | 신규 계약 `cv.effective_from` | 현재: `paid_at_dt` (결제 타임스탬프) | `start_date midnight KST`로 통일 여부 |
| D-03 | `payment_months` rename 시점 | 현재: OBJ05 이후 Semantic-Integration 대기 | Semantic-Integration WO 발행 시점 결정 |
| D-04 | 조기 갱신 V2 지원 | 현재: V2는 `contracts.end_date`만 boundary로 허용 | 조기 갱신창 (예: 30일 전) 허용 여부 |
| D-05 | `payment_months` 과 `service_months` 분리 | 현재: 항상 동일 | 분납/연장 모델 도입 시 분리 필요 여부 |

---

## 12. 권고 모델 (V3 현재 범위 내)

V3 선납 전용 모델에서:

1. **`payment_months` = `discount_basis_months` = `contract_extension_months`** — 분리 불필요, rename만 진행
2. **신규 계약 경계**: `start_date = business_today()`, `end_date = start + payment_months`
3. **갱신 경계**: `effective_from = old_end_date midnight KST` (DB enforced via V2_RENEWAL_BOUNDARY_MISMATCH)
4. **Replay 앵커**: `target_cv.effective_from` — DB에서 읽는 값, 재계산 금지
5. **V2 atomic SQL 3-way guard 유지**: `snap.payment_months == pay.period_months == cv.payment_months`
6. **Semantic-Integration 전까지** `term_months` 유지 — 중간 부분 rename 금지 (불일치 발생)

---

## 13. OBJ05 범위 외 (이 문서에서 결정하지 않음)

- price_master DATA WO (INDUSTRY_PRO criteria_max→NULL, INDUSTRY_CUSTOM 비활성화) — V3 cutover 후
- OBJ07 FIELD commercial scope 결정 (scale band가 계약 용량인지 여부)
- Semantic-Integration WO 구현 (13개 이상 파일 rename + DDL)
- 분납/선납 혼합 모델
