---
title: TAI Safe Pricing V3 — Policy Re-Canonical
kind: policy-canonical
status: FROZEN
version: V3-FROZEN
date: 2026-09-28
owner_gate_approved: true
owner_decision_date: 2026-09-28
supersedes: docs/2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md (일부 항목)
---

> **이 문서는 2026-09-28 Owner Decision으로 확정·FROZEN된 TAI Safe SaaS 가격정책 V3 정본이다.**
> `docs/2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md`(이하 "V2 정본")의 구체적으로
> 명시된 항목만 SUPERSEDED 처리하며, 나머지는 V2 정본을 그대로 따른다.
> **이 문서가 FROZEN된 이후 내용 변경은 새 버전 문서로만 가능하다.**

---

# TAI Safe Pricing V3 — Policy Re-Canonical

**작업일:** 2026-09-28
**버전:** V3-FROZEN
**이전 정본:** `docs/2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md`
**Owner Decision:** APPROVED 2026-09-28

---

## 1. SUPERSEDED 항목 — V2 정본 대비 실제 정책 변경

실제 정책 변경은 **2개**다. Section 1-C는 Frontend 구현 오류 수정이며 정책 변경이 아니다.

### 1-A. FIELD Base 계산식 (V2 정본 Section 3 → SUPERSEDED)

**V2 정본 (폐기):**

```
현장참여형 Base = 관리자형 Compliance Base + 100,000원
```

uplift +100,000원이 사업장별 규모 tier 가격과 연동되었다.

**V3 확정 (Owner Decision 2026-09-28):**

```
FIELD Base = 249,000원 / 시설 / 월 (고정)
```

FIELD Base는 사업장 섹터·규모 tier와 무관하다.
어떤 사업장(산업 20명 / 산업 300명 / 건물 3,000㎡ / 건설 100억)이든
FIELD Base 자체는 동일하다.

```
Primary Facility   = 249,000원
Additional Facility = 249,000 × 80% = 199,200원
```

---

### 1-B. 할인 기준축 (V2 정본 Section 14 → SUPERSEDED)

**V2 정본 (폐기):**

```
term_months ≈ 계약기간 ≈ 선불개월수 ≈ 할인기준
```

이 세 개념이 하나의 변수로 혼용되었다.

**V3 확정 (Owner Decision 2026-09-28):**

```
payment_months  ← 할인 기준 (이번에 몇 개월치를 선결제하는가)
contract term   ← 계약정책 (별도)
```

중요: **`payment_months`는 약정계약 기간이 아니다.**

```
12개월 결제 ≠ 12개월 약정계약
```

`payment_months`는 오직 할인율과 이용 가능기간 연장의 기준이 되는 결제 단위다.
`payment_months`가 서비스 이용 가능기간을 정확히 어떻게 연장하는지는
Phase 2 Backend 영향도 조사 (PRC-V3-BE-OBJ05)에서 별도 정의한다.
이 Policy 문서에서 임의 구현규칙 생성 금지.

Backend에서:
```
term_months  → payment_months 로 분리
contract.end_date extension = payment_months 기반 (정의는 OBJ05에서)
                             ≠ 할인 축
```

할인율 (payment_months 기준, Owner Decision 확정):

| payment_months | 할인율 |
|---------------|--------|
| 1  | 0% |
| 3  | 5% |
| 6  | 10% |
| 9  | 15% |
| 12 | 20% |

---

### 1-C. STARTER / BUSINESS / PRO — 정책 변경 없음 (Frontend 표현 오류 수정)

**이것은 V3의 정책 변경 항목이 아니다.**

V2 정본에서도 고객 상품 Tier는 이미 `MANAGER / FIELD / CUSTOM`이었다.
`STARTER / BUSINESS / PRO`는 V2 정본 Section 2에서도 MANAGER Compliance Base Band였다.

문제는 구형 Frontend(`saas.astro`)가 이 Compliance Base Band를
고객이 선택하는 상품처럼 노출하던 UI 구현 오류였다.

```
STARTER / BUSINESS / PRO
= MANAGER 시설 규모 판정을 위한 Compliance Base Band  ← V2·V3 공통
= 고객 상품 Tier 아님                                 ← V2·V3 공통

고객 상품 Tier
= MANAGER / FIELD / CUSTOM                            ← V2·V3 공통
```

수정된 것:

```
구형 Frontend: STARTER / BUSINESS / PRO 를 상품처럼 노출
              → commit 0060d65c 에서 MANAGER / FIELD / CUSTOM 으로 교체
              → FE-WWW-OBJ01 (NOT FROZEN, 가격정책 재정비 후 완성 예정)
```

Backend plan_code(`INDUSTRY_STARTER_V3` 등)는 변경 없음.

---

## 2. Owner Gate — APPROVED (2026-09-28)

**TAI SAFE PRICING V3 — OWNER GATE APPROVED**
**DATE: 2026-09-28**

| Gate | 항목 | 확정값 |
|------|------|--------|
| OG-1 | FIELD 고정 Base (시설 1개 / 월) | **249,000원** |
| OG-2 | 추가시설 할인율 | **80% (= 20% 할인) 유지** |
| OG-3 | payment_months 전체 할인율 | 아래 표 |

**OG-3 확정 할인율:**

```
1개월  =  0%
3개월  =  5%
6개월  = 10%
9개월  = 15%
12개월 = 20%
```

할인 기준 = payment_months ≠ 계약기간

---

## 3. V2 정본에서 유지되는 항목

다음은 V2 정본 내용을 그대로 따른다. 재기술하지 않는다.

| V2 정본 Section | 내용 | 상태 |
|----------------|------|------|
| Section 1 | 상품 3-Tier 구조 (MANAGER/FIELD/CUSTOM) | **유지** |
| Section 2 | MANAGER 섹터·규모별 Compliance Base 가격표 | **유지** |
| Section 4 | Worker Capacity 누적구간 (1~20/21~50/51~100/101~300/301~) | **유지** |
| Section 5 | Pack 강제 없음. 실제 계약 Capacity로 계산 | **유지** |
| Section 6 | 선불 원칙 | **유지** |
| Section 7 | 계약기간 중 인원 변경 정책 | **유지** |
| Section 8 | 추가 사업장 고정 할인율: 첫 시설 100%, 추가 시설 80% (OG-2 확정) | **유지** |
| Section 9 | 가장 높은 정상가격 시설 1개 = 100%, 나머지 = 각 정상가격 × 80% | **유지** |
| Section 10 | 섹터별 Compliance Base 적용 구조 | **유지** |
| Section 11 | 건설 하도급 구조 (협력사 수 주요 과금축 아님) | **유지** |
| Section 12 | 표준 초기 세팅비 = 0원 | **유지** |
| Section 13 | 법령진단과 SaaS 가격 구분 | **유지** |

---

## 4. V3 확정 가격 공식

### MANAGER

```
시설별 MANAGER 가격
= 섹터·규모 판정 (유료 법령진단과 동일한 규모구간 판정 Rule)

  산업 STARTER  (49인 이하)    149,000원/월
  산업 BUSINESS (50~299인)     299,000원/월
  산업 PRO      (300~499인)    499,000원/월
  건물 정밀관리 (5,000㎡ 이하) 149,000원/월
  건물 대형건물 (5,000㎡ 초과) 349,000원/월
  건설 STANDARD (50억 미만)    249,000원/월
  건설 PREMIUM  (50억 이상)    499,000원/월

Primary Facility   = 최고가 시설 × 100%
Additional Facility = 각 정상가격 × 80%

Worker Capacity Fee = 0 (MANAGER에 없음)

MONTHLY SUPPLY
= Primary + sum(Additional)

RAW_PAYMENT   = MONTHLY_SUPPLY × payment_months
DISCOUNT      = RAW_PAYMENT × discount_rate(payment_months)
SUPPLY        = RAW_PAYMENT - DISCOUNT
VAT           = SUPPLY × 0.10
TOTAL         = SUPPLY + VAT
```

### FIELD

```
FIELD Base = 249,000원 / 시설 / 월 (고정)

Primary Facility   = 249,000 × 100% = 249,000원
Additional Facility = 249,000 × 80% = 199,200원

Worker Fee = progressive_worker_fee(worker_capacity)
  1~20명     3,000원/인/월
  21~50명    2,500원/인/월
  51~100명   2,000원/인/월
  101~300명  1,500원/인/월
  301명 이상 1,200원/인/월
  (누적구간 방식)

Worker Fee는 계약 전체에서 1회만 계산 (시설별 중복 없음)

MONTHLY_SUPPLY
= Primary + sum(Additional) + Worker Fee

RAW_PAYMENT   = MONTHLY_SUPPLY × payment_months
DISCOUNT      = RAW_PAYMENT × discount_rate(payment_months)
SUPPLY        = RAW_PAYMENT - DISCOUNT
VAT           = SUPPLY × 0.10
TOTAL         = SUPPLY + VAT
```

### discount_rate(payment_months)

```
1  → 0%
3  → 5%
6  → 10%
9  → 15%
12 → 20%
```

### 계산 예시 — FIELD / 시설 2개 / Worker 100명 / 6개월 결제

```
Primary Facility       249,000원
Additional Facility    199,200원
Worker 100명           235,000원
                      ─────────
MONTHLY_SUPPLY         683,200원

6개월 RAW            4,099,200원
10% 할인              -409,920원
                      ─────────
공급가액             3,689,280원
VAT (10%)              368,928원
                      ─────────
이번 결제금액        4,058,208원
```

(Worker 100명 = 20×3,000 + 30×2,500 + 50×2,000 = 60,000 + 75,000 + 100,000 = 235,000원)

---

## 5. FE-WWW-OBJ01 상태

| 항목 | 상태 |
|------|------|
| `feat/pricing-v2-frontend-20260928` commit `0060d65c` | NOT FROZEN — 구조 참고용으로 보존 |
| FE-WWW-OBJ01 이후 PATCH WO | SUPERSEDED / 실행 금지 |
| PR | BLOCKED |
| Merge | BLOCKED |
| Deploy | BLOCKED |

이 브랜치의 MANAGER/FIELD/CUSTOM 마케팅 카드 구조는 참고용으로 보존하되,
가격표시·CTA·설명 문구는 Phase 8에서 다시 작성한다.

---

## 6. Backend Frozen 자산 상태

기존 Frozen Backend 자산은 **구현 증거로 보존**한다.
V3 정책 변경이 영향을 주는 Object만 선별적으로 REOPEN한다.

**보존 (FROZEN 유지):**

| 자산 | 이유 |
|------|------|
| OBJ10-A (Quote V2 → INICIS Payment Adapter) | payment 경로 — 직접 영향 없음 |
| OBJ10-B (Contract Row Builder) | 구조 유지 — snapshot 필드 정합화는 OBJ04에서 |
| OBJ10-C (Atomic Contract Persistence) | DDL 미적용 유지 |
| OBJ10-D-A (Renewal Plan Builder) | 구조 유지 |
| OBJ10-D-B1 (Renewal 시간축) | 유지 |
| OBJ10-D-B2 (Atomic Renewal Persistence) | 유지 |
| OBJ10-D-B3 (Renewal Runtime Branch Wiring) | 유지 |

**REOPEN 예정 (Phase 2 조사 후 범위 확정):**

| 대상 | 이유 |
|------|------|
| `saas_pricing_policy_v2.py` | FIELD uplift 계산식 변경 |
| `saas_pricing_composer_v2.py` | FIELD base, payment_months 할인 |
| Quote snapshot 필드 | payment_months 분리 |
| Contract commercial version | term_months / payment_months 분리 |
| Renewal 계산 | payment_months → effective period 연결 |

---

## 7. 고객용 가격 계산기 UX — 정본 플로우

### 전체 흐름

```
Marketing SaaS
  → [내 이용료 확인]
    → STEP 1: 이용방식 선택 (관리자형 / 현장참여형 / 커스터마이징)
      → STEP 2: 시설 입력 (섹터 + 규모) + [시설 추가]
        → STEP 3: (FIELD인 경우) Worker Capacity 입력
          → STEP 4: 결제월수 선택 (1 / 3 / 6 / 9 / 12개월)
            → Backend Preview
              → 가격 Breakdown 표시
                → [이 조건으로 견적서 발행]
                  → Frozen Quote
                    → [PDF] [결제하기]
```

Frontend 계산 금지. 가격 계산은 Backend Preview만 사용.

### 화면별 입력 정의

**STEP 2 — 시설 입력**

```
시설 N
  시설 유형 [ 산업 / 건물 / 건설 ▼ ]
  산업 → 상시근로자 수
  건물 → 연면적
  건설 → 공사금액
[+ 시설 추가]
```

**STEP 3 — Worker Capacity (FIELD 전용)**

```
현장참여 Capacity
[ 100명 ]
현재 계약 Capacity 안에서 참여자를 자유롭게 교체할 수 있습니다.
```

**STEP 4 — 결제월수**

```
몇 개월치를 선결제하시겠습니까?

○ 1개월
○ 3개월   5% 할인
○ 6개월  10% 할인
○ 9개월  15% 할인
○ 12개월 20% 할인
```

화면 문구:
> **몇 개월치를 선결제하시겠습니까?** (NOT "계약기간을 선택하세요")

### 가격 Breakdown 예시

**MANAGER — A공장(산업 85명) + B건물(7,500㎡) / 12개월:**

```
관리자형

A공장 · 산업 · 85명 → BUSINESS
  월 정상가격             299,000원

B건물 · 7,500㎡ → 대형건물
  월 정상가격             349,000원
  추가시설 할인 20%       -69,800원
─────────────────────────────────
월 이용료                 578,200원

12개월 RAW             6,938,400원
결제기간 할인 20%      -1,387,680원
─────────────────────────────────
공급가액               5,550,720원
VAT (10%)               555,072원
─────────────────────────────────
이번 결제금액          6,105,792원

[이 조건으로 견적서 발행]
```

**FIELD — 시설 2개 / Worker 100명 / 6개월:**

```
현장참여형

시설 1 기본요금          249,000원
시설 2 추가시설 80%      199,200원

현장참여 Capacity 100명
  20명 × 3,000        =  60,000원
  30명 × 2,500        =  75,000원
  50명 × 2,000        = 100,000원
                      = 235,000원
─────────────────────────────────
월 이용료                683,200원

6개월 RAW             4,099,200원
결제기간 할인 10%       -409,920원
─────────────────────────────────
공급가액              3,689,280원
VAT (10%)              368,928원
─────────────────────────────────
이번 결제금액         4,058,208원

[이 조건으로 견적서 발행]
```

---

## 8. 기존 견적 메뉴 역할 변경

```
기존 /mypage/contracts/ 역할
  견적 생성페이지  →  가격확인 화면으로 통합

기존 /mypage/contracts/ 재정의
  견적 보관함:
    - 발행 견적 목록
    - 견적 상세
    - PDF 다운로드
    - 과거 견적 확인
    - CUSTOM 개별견적
```

---

## 9. 작업 Phase 계획

### PHASE 0 — 기존 Frontend 작업 중단 (완료)

```
FE-WWW-OBJ01 commit 0060d65c → NOT FROZEN
이후 PATCH WO → SUPERSEDED
PR/Merge/Deploy → BLOCKED
```

### PHASE 1 — Pricing Policy Re-Canonical (이 문서 — COMPLETE)

```
완료: Owner Gate 3개 확인 → POLICY FROZEN 선언
```

### PHASE 2 — Backend 영향도 조사 (PRC-V3-BE-OBJ01) ← 다음 단계

```
조사 대상:
  saas_pricing_policy_v2
  saas_pricing_composer_v2
  preview / quote / payment
  commercial snapshot
  atomic apply / change order
  renewal / runtime wiring
  tests

조사 포인트:
  term_months 사용처 전수
  FIELD uplift (+100,000) 사용처 전수
  worker capacity 위치
  site pricing calculation
  quote snapshot fields
  contract commercial version fields

목표: FROZEN을 전부 갈아엎지 않고
      변경 정책에 직접 영향받는 Object만 식별
```

### PHASE 3 — Backend Pricing Core PATCH (PRC-V3-BE-OBJ02/03)

```
OBJ02 — Policy
  FIELD fixed base = 249,000
  payment_months discount policy (0/5/10/15/20%)
  additional facility = 80%

OBJ03 — Composer
  MANAGER: sector/scale tier price
  FIELD: 249,000 base
  additional facilities × 80%
  worker capacity (누적구간)
  payment_months discount

경계 테스트:
  MANAGER 섹터 전체 tier
  FIELD 1/2/10 시설
  Workers: 0/1/20/21/50/51/100/101/300/301
  payment_months: 1/3/6/9/12
```

### PHASE 4 — Snapshot / Quote 정합화 (PRC-V3-BE-OBJ04)

```
term_months 의미 분리
payment_months 필드 추가 (필요 시)

가격증거 필드 Freeze:
  product_tier
  facilities[]
  worker_capacity
  monthly_supply
  payment_months
  discount_rate
  discount_amount
  supply_amount
  vat
  total
```

### PHASE 5 — Payment / Renewal 정합화 (PRC-V3-BE-OBJ05)

```
payment_months → effective period 연결 정의
contract.end_date extension 기준 재정의
renewal boundary 확인

Atomic transaction 원칙 유지
```

### PHASE 6 — Backend Re-Freeze

```
PHASE 2-5 완료 → 전체 회귀
→ GPT 독립검증
→ Backend FROZEN
```

---

### PHASE 7 — Frontend UX Canonical (FE-OBJ00)

```
설계 대상:
  Marketing (tai-www)
  가격확인 + 견적발행 (tai-www)
  Safe MyPage (tai-admin)

공통 언어:
  관리자형 / 현장참여형 / 커스터마이징
  시설 / 현장참여 Capacity / 결제월수 / 이번 결제금액
```

### PHASE 8 — Marketing Pricing (FE-WWW-OBJ01 재개)

```
관리자형: 월 149,000원부터
현장참여형: 월 249,000원 + 참여인원
CUSTOM: 별도견적

CTA: [내 이용료 확인]
직접 결제 없음
```

### PHASE 9 — 가격확인 + 견적발행 (FE-WWW-OBJ02)

```
한 화면:
  Tier → 시설 추가 → 규모 → Capacity → 결제월수
  → Backend Preview → Breakdown
  → [이 조건으로 견적서 발행]
  → Frozen Quote → [PDF] [결제하기]

Frontend 계산 = 0 (Backend Preview만 사용)
```

### PHASE 10 — 견적 보관함 (FE-WWW-OBJ03)

```
기존 /mypage/contracts/ 재활용
견적 생성 X → 견적 관리 O
```

### PHASE 11 — 결제 Flow (FE-WWW-OBJ04)

```
Frozen Quote → Payment Prepare → INICIS
→ Atomic Contract → Onboarding
가격 재계산 0
```

### PHASE 12 — SaaS MyPage (FE-ADM-OBJ01)

```
현재 계약 표시:
  상품형태 / 시설 Scope / Worker Capacity
  월 기준가격 / 최근 결제월수 / 현재 유효기간
```

### PHASE 13 — Renewal UX (FE-ADM-OBJ02)

```
정기결제 UI 제거
대신: 몇 개월치를 미리 결제하시겠습니까?
  1 / 3 / 6 / 9 / 12

가격 Preview → Quote → Payment
Frontend 가격 계산 0
```

### PHASE 14 — 통합 E2E

```
E01 MANAGER 산업 1시설
E02 MANAGER 산업 2시설
E03 MANAGER mixed sector
E04 FIELD 1시설 + 20명
E05 FIELD 2시설 + 100명
E06 FIELD 3시설 + 305명
E07 3개월 결제
E08 12개월 결제
E09 Quote 발행
E10 Quote → 결제
E11 Atomic 신규계약
E12 Renewal 선결제
E13 Renewal replay
E14 CUSTOM
```

---

## 10. Gate 상태

```
──────────────────────────────────────────
PRICING V3 POLICY
= FROZEN (Owner Decision 2026-09-28)

기존 Pricing V2 Backend Frozen 자산
= 구현 증거 보존
= 정책변경 영향 Object는 PHASE 2 조사 후 REOPEN

FE-WWW-OBJ01 (commit 0060d65c)
= NOT FROZEN
= 이후 PATCH WO = SUPERSEDED
= PR / MERGE / DEPLOY = BLOCKED
──────────────────────────────────────────
다음 Gate: BE-V3-OBJ01 Backend Impact Inventory
= 코드 수정 없이 영향받는 Object만 전수조사
= 조사 완료 → REOPEN 범위 확정 → PHASE 3 개방
──────────────────────────────────────────

production DDL    = 0
production mutation = 0
deploy            = 0
```
