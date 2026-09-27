---
title: TAI Safe Pricing V2 — BE OBJ02 Evidence Report
status: EVIDENCE_REPORT
goal: G-muju80oq-0a7566
collected_by: Claude Code (COLLECT role)
collected_date: 2026-09-27
review_required: GPT REVIEW REQUIRED
---

# WO-PRICING-V2-BE-OBJ02 Evidence Report

---

## OBSERVED

### 신규 파일 생성

| 파일 | 라인 수 | 역할 |
|---|---|---|
| `schemas/saas_pricing_policy_v2.py` | 163 | Canonical Pricing Policy Contract V2 |
| `tests/test_saas_pricing_policy_v2.py` | 201 | P01~P37 테스트 |

### 정의된 도메인 계약

| 이름 | 역할 |
|---|---|
| `PRICING_POLICY_VERSION` | `"TAI_SAFE_PRICING_POLICY_2026_09_27"` |
| `VALID_TERM_MONTHS_POLICY` | `frozenset{1,3,6,9,12}` |
| `SaasWorkerRateBracketPolicy` | 작업자 단가 구간 정책 (frozen) |
| `SaasTermDiscountPolicy` | 계약기간별 할인율 정책 (frozen, None=미확정) |
| `SaasPricingPolicyV2` | 전체 가격정책 (frozen) |
| `get_canonical_pricing_policy_v2()` | Pure factory function — DB/env/API 없음 |

### Canonical Policy 값 (get_canonical_pricing_policy_v2() 반환)

| 필드 | 값 |
|---|---|
| policy_version | `TAI_SAFE_PRICING_POLICY_2026_09_27` |
| effective_from | `2026-09-27` |
| field_uplift_amount | `100000` |
| primary_site_rate_bps | `10000` |
| additional_site_rate_bps | `8000` |
| vat_rate_bps | `1000` |
| currency | `"KRW"` |

Worker Brackets:

| range_from | range_to | unit_rate |
|---|---|---|
| 1 | 20 | 3000 |
| 21 | 50 | 2500 |
| 51 | 100 | 2000 |
| 101 | 300 | 1500 |
| 301 | None | 1200 |

Term Discounts (전체 None — Owner 미확정):

| term_months | discount_rate_bps |
|---|---|
| 1 | None |
| 3 | None |
| 6 | None |
| 9 | None |
| 12 | None |

---

## IMPLEMENTED CONTRACT

### 설계 원칙 준수 항목

| 항목 | 구현 여부 |
|---|---|
| Price Master 값 복제 없음 | 소스 내 INDUSTRY_STARTER/BUILDING_BASIC/CONSTRUCTION_STANDARD 없음 (P34~P36 PASS) |
| Worker Pack 없음 | 브래킷 정책만 존재 |
| CUSTOM 가격 없음 | 소스 내 CUSTOM 관련 가격 정의 없음 |
| 가격 계산 없음 | 산술 연산 없음 |
| Runtime Wiring 없음 | 기존 서비스 import 없음 |
| StrictInt 유지 | BE-OBJ01 PATCH-1 원칙 동일 적용 |
| Bracket 연속성 검증 | `_validate_bracket_list()` — gap/overlap/null 규칙 |
| Term discount None = 미확정 | 0%와 구분, None 별도 의미 부여 |
| Frozen model | `ConfigDict(frozen=True)` 전체 모델 적용 |
| Pure factory | DB/env/API 호출 없음, 매 호출 신규 instance |

---

## TEST RESULT

| ID | 설명 | 결과 |
|---|---|---|
| P01 | policy_version exact | PASS |
| P02 | effective_from = 2026-09-27 | PASS |
| P03 | field_uplift_amount = 100000 | PASS |
| P04 | field_uplift float rejected | PASS |
| P05 | field_uplift bool rejected | PASS |
| P06 | primary rate = 10000 | PASS |
| P07 | additional rate = 8000 | PASS |
| P08 | rate >10000 rejected | PASS |
| P09 | float rate rejected | PASS |
| P10 | bool rate rejected | PASS |
| P11 | bracket count = 5 | PASS |
| P12 | 1~20 / 3000 | PASS |
| P13 | 21~50 / 2500 | PASS |
| P14 | 51~100 / 2000 | PASS |
| P15 | 101~300 / 1500 | PASS |
| P16 | 301~null / 1200 | PASS |
| P17 | gap rejected | PASS |
| P18 | overlap rejected | PASS |
| P19 | first range !=1 rejected | PASS |
| P20 | middle null rejected | PASS |
| P21 | last non-null rejected | PASS |
| P22 | range_to < range_from rejected | PASS |
| P23 | float unit_rate rejected | PASS |
| P24 | bool unit_rate rejected | PASS |
| P25 | vat_rate_bps = 1000 | PASS |
| P26 | VAT float rejected | PASS |
| P27 | terms exactly {1,3,6,9,12} | PASS |
| P28 | term 2 rejected | PASS |
| P29 | float term rejected | PASS |
| P30 | all canonical discount_rate_bps = None | PASS |
| P31 | None accepted | PASS |
| P32 | explicit valid discount bps structurally accepted | PASS |
| P33 | discount >10000 rejected | PASS |
| P34 | source no INDUSTRY_STARTER | PASS |
| P35 | source no BUILDING_BASIC | PASS |
| P36 | source no CONSTRUCTION_STANDARD | PASS |
| P37 | canonical policy immutable and isolated | PASS |

```
OBJ02 테스트:  37 PASS / 0 FAIL

OBJ01 regression (48) + OBJ02 (37) 합산:
python3 -m pytest -q tests/test_saas_pricing_v2_contract.py tests/test_saas_pricing_policy_v2.py
........................................................................
.............
85 passed in 0.13s
```

---

## FILES CHANGED

```
git status --short
?? schemas/saas_pricing_policy_v2.py
?? tests/test_saas_pricing_policy_v2.py
```

기존 파일 수정: 0

---

## NOT_FOUND

- `schemas/saas_pricing_policy_v2.py` 사전 존재 없음 (충돌 없음)
- `tests/test_saas_pricing_policy_v2.py` 사전 존재 없음 (충돌 없음)

---

## UNVERIFIED

없음.

---

---

## PATCH-1 — Canonical Policy Collection Integrity (2026-09-27)

### GPT SOURCE VERIFY FINDINGS

```
BLOCKER-1: DUPLICATE TERM ENTRY CAN PASS
  기존 validator: set 비교만 수행.
  1,1,3,6,9,12 → set={1,3,6,9,12} → 통과 가능.

BLOCKER-2: OUT-OF-ORDER WORKER BRACKETS CAN PASS
  기존 validator: sorted(v)로 검증 후 원본 v 반환.
  21~50, 1~20, ... 순서 입력이 검증을 통과하고 원본 순서로 저장 가능.
```

### PATCH APPLIED

`schemas/saas_pricing_policy_v2.py`:

**_validate_term_discounts 보정:**
- count == 5 명시적 검사 추가
- canonical order [1,3,6,9,12] 입력 일치 검사 추가 → duplicate + out-of-order 동시 차단

**_validate_worker_brackets 보정:**
- 입력 순서 = range_from 오름차순 여부 사전 검사 추가 → out-of-order REJECT
- 검증 후 원본 v 반환 (canonical order 보장됨)

`tests/test_saas_pricing_policy_v2.py`:
- Q01~Q08 신규 추가

### TEST RESULT

```
OBJ01 regression : 48 PASS
OBJ02 original   : 37 PASS
PATCH-1 Q01~Q08  :  8 PASS
합계             : 93 PASS / 0 FAIL

python3 -m pytest -q tests/test_saas_pricing_v2_contract.py tests/test_saas_pricing_policy_v2.py
........................................................................
.....................
93 passed in 0.17s
```

| ID | 설명 | 결과 |
|---|---|---|
| Q01 | duplicate term 1 rejected | PASS |
| Q02 | duplicate term 12 rejected | PASS |
| Q03 | six entries with same valid set rejected | PASS |
| Q04 | term out-of-order rejected | PASS |
| Q05 | canonical term order accepted | PASS |
| Q06 | worker bracket out-of-order rejected | PASS |
| Q07 | canonical worker order accepted | PASS |
| Q08 | duplicate worker range_from rejected (overlap 경로) | PASS |

Q08 Note: 동일 range_from 입력은 out-of-order 검사(입력순서=동일 range_from→정렬불변) 이후
overlap 검사 경로에서 거부됨. 별도 duplicate 검사 없이 기존 연속성 검증으로 포착됨.

### FILES MODIFIED

```
schemas/saas_pricing_policy_v2.py   (+17 lines)
tests/test_saas_pricing_policy_v2.py (+104 lines)
```

---

```
GPT REVIEW REQUIRED
```
