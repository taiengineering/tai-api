---
title: TAI Safe Pricing V2 — BE OBJ01 Evidence Report
status: EVIDENCE_REPORT
goal: G-muju80oq-0a7566
collected_by: Claude Code (COLLECT role)
collected_date: 2026-09-27
review_required: GPT REVIEW REQUIRED
---

# WO-PRICING-V2-BE-OBJ01 Evidence Report

---

## OBSERVED

### 신규 파일 생성

| 파일 | 라인 수 | 역할 |
|---|---|---|
| `schemas/saas_pricing_v2.py` | 159 | Commercial Domain Contract V2 (순수 Pydantic) |
| `tests/test_saas_pricing_v2_contract.py` | 240 | T01~T25 + 추가 guard 테스트 |

### 정의된 도메인 계약

| 이름 | 타입 | 역할 |
|---|---|---|
| `ProductTier` | `Literal["MANAGER", "FIELD"]` | 상품 Tier — 정확히 두 값만 허용 |
| `PricingMode` | `Literal["STANDARD", "CUSTOM"]` | 가격책정 모드 |
| `SaasSector` | `Literal["INDUSTRY", "BUILDING", "CONSTRUCTION"]` | 섹터 고정 3종 |
| `EntityType` | `Literal["factory", "site"]` | 사업장 엔티티 타입 |
| `VALID_TERM_MONTHS` | `frozenset{1,3,6,9,12}` | 허용 계약 기간 |
| `SCHEMA_VERSION` | `"SAAS_PRICING_V2"` | 스냅샷 스키마 버전 고정값 |
| `SaasCommercialSelection` | Pydantic BaseModel | 상품 조합 입력 계약 |
| `SaasSiteScope` | Pydantic BaseModel | 사업장 범위 + 가격 스냅샷 컨테이너 |
| `SaasWorkerBracketLine` | Pydantic BaseModel | 작업자 구간 스냅샷 한 줄 |
| `SaasWorkerPricingSnapshot` | Pydantic BaseModel | 작업자 선불 용량 + 요금 스냅샷 |
| `SaasPricingSnapshotV2` | Pydantic BaseModel | 계약 시점 불변 가격 스냅샷 전체 |

### 구현된 Validation 규칙 목록

| 규칙 | 구현 위치 |
|---|---|
| `MANAGER` → `worker_capacity == 0` | `SaasCommercialSelection.model_validator` |
| `term_months` ∈ {1,3,6,9,12} | `SaasCommercialSelection.field_validator` + `SaasPricingSnapshotV2.field_validator` |
| `entity_type` ↔ `sector` 매핑 검증 | `SaasSiteScope.model_validator` |
| `applied_rate_bps` 범위 0~10000 | `SaasSiteScope.field_validator` |
| 금액 0 이상 정수 | 각 모델 `field_validator` |
| `schema_version == "SAAS_PRICING_V2"` | `SaasPricingSnapshotV2.field_validator` |
| float 금액 → Pydantic int 타입 선언으로 ValidationError | `SaasSiteScope.base_amount: int` |

---

## EVIDENCE

### 파일 경로 및 코드

- `tai-api/schemas/saas_pricing_v2.py` — 신규 생성
- `tai-api/tests/test_saas_pricing_v2_contract.py` — 신규 생성

### 테스트 실행 결과

```
python3 -m pytest -q tests/test_saas_pricing_v2_contract.py
............................
28 passed in 0.09s
```

T01~T25 모두 PASS + 추가 guard 3개 PASS.

### 변경 범위 확인

```
git status --short (신규 파일만)
?? schemas/saas_pricing_v2.py
?? tests/test_saas_pricing_v2_contract.py
```

기존 파일 수정: 0

---

## TEST RESULT

| ID | 설명 | 결과 |
|---|---|---|
| T01 | MANAGER valid | PASS |
| T02 | FIELD valid | PASS |
| T03 | CUSTOM product_tier rejected | PASS |
| T04 | STARTER product_tier rejected | PASS |
| T05 | MANAGER + worker_capacity > 0 rejected | PASS |
| T06 | FIELD + worker_capacity 0 accepted | PASS |
| T07 | term 1 accepted | PASS |
| T08 | term 3 accepted | PASS |
| T09 | term 6 accepted | PASS |
| T10 | term 9 accepted | PASS |
| T11 | term 12 accepted | PASS |
| T12 | term 2 rejected | PASS |
| T13 | INDUSTRY + factory accepted | PASS |
| T14 | BUILDING + factory accepted | PASS |
| T15 | CONSTRUCTION + site accepted | PASS |
| T16 | INDUSTRY + site rejected | PASS |
| T17 | CONSTRUCTION + factory rejected | PASS |
| T18 | negative money rejected | PASS |
| T19 | float money rejected | PASS |
| T20 | applied_rate_bps > 10000 rejected | PASS |
| T21 | schema_version canonical value verified | PASS |
| T22 | policy_version independent from schema_version | PASS |
| T23 | worker bracket open-ended range_to=null accepted | PASS |
| T24 | pricing_mode STANDARD accepted | PASS |
| T25 | pricing_mode CUSTOM accepted | PASS |
| — | wrong schema_version rejected | PASS |
| — | snapshot negative total rejected | PASS |
| — | worker snapshot MANAGER capacity=0 | PASS |

총계: **28 PASS / 0 FAIL**

---

## NOT_FOUND

- `schemas/saas_pricing_v2.py` 사전 존재 없음 (충돌 없음)
- `tests/test_saas_pricing_v2_contract.py` 사전 존재 없음 (충돌 없음)

---

## UNVERIFIED

없음.

---

## FOLLOW-UP OBSERVED

```
PRC-FE-ADM-LEGACY-COMPAT:
tai-admin useAuth.ts PLAN_MAP에 _V2/_V3 suffix normalize 없음.
실제 ACTIVE 계약에 BUILDING_BASIC_V3, INDUSTRY_BUSINESS_V2 등 suffix 포함 plan_code 존재.
이 불일치는 tai-admin Commercial Context V2 전환 Object에서 처리 예정.
```

---

```
GPT REVIEW REQUIRED
```
