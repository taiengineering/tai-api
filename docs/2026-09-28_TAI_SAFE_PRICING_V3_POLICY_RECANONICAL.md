---
title: TAI Safe Pricing V3 — Policy Re-Canonical
kind: policy-canonical
status: CANDIDATE
version: V3-PATCH1-CANDIDATE
date: 2026-09-28
owner_gate_approved: true
owner_decision_date: 2026-09-28
supersedes: docs/2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md (일부 항목)
---

> **이 문서는 2026-09-28 Owner Decision으로 승인된 TAI Safe SaaS 가격정책 V3 정본 후보다.**
> `docs/2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md`(이하 "V2 정본")의 구체적으로
> 명시된 항목만 SUPERSEDED 처리하며, 나머지는 V2 정본을 그대로 따른다.
> **status = CANDIDATE. GPT 독립검증 PASS 후에만 FROZEN으로 승격된다.**

---

# TAI Safe Pricing V3 — Policy Re-Canonical

**작업일:** 2026-09-28
**버전:** V3-PATCH1-CANDIDATE
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
FIELD Base = 249,000원 / 시설 / 월 (고정, VAT 별도 공급가)
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

`payment_months`는 할인율 결정 단위다.

`payment_months`와 다음 3개의 관계는 **UNRESOLVED**이며,
이 Policy 문서에서 임의로 확정하지 않는다:

```
payment_months ↔ service effective period    → UNRESOLVED
payment_months ↔ contract.end_date           → UNRESOLVED
payment_months ↔ renewal boundary            → UNRESOLVED
```

위 3개 관계는 후속 Backend Impact Object (PRC-V3-BE-OBJ05)에서 정의한다.

Backend에서:

```
term_months → payment_months 로 분리
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
구형 Frontend: STARTER / BUSINESS / PRO를 상품처럼 노출
              → commit 0060d65c 에서 MANAGER / FIELD / CUSTOM으로 교체
              → FE-WWW-OBJ01 (NOT FROZEN, 가격정책 재정비 후 완성 예정)
```

Backend plan_code(`INDUSTRY_STARTER_V3` 등)는 변경 없음.

---

## 2. Owner Gate — APPROVED (2026-09-28)

**TAI SAFE PRICING V3 — OWNER GATE APPROVED**
**DATE: 2026-09-28**

| Gate | 항목 | 확정값 |
|------|------|--------|
| OG-1 | FIELD 고정 Base (시설 1개 / 월, VAT 별도 공급가) | **249,000원** |
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
| Section 2 | MANAGER 섹터·규모별 Compliance Base 가격 금액 | **유지 (INDUSTRY 범위 경계는 V3에서 유료진단 Rule과 동일하게 조정됨 — Section 4 참조)** |
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

모든 가격은 **VAT 별도 공급가** 기준이다.

### MANAGER

```
시설별 MANAGER 가격
= 섹터·규모 판정 (유료 법령진단과 동일한 규모구간 판정 Rule)

  산업 (49인 이하)     149,000원/월
  산업 (50~299인)      299,000원/월
  산업 (300인 이상)    499,000원/월
  건물 (5,000㎡ 이하)  149,000원/월
  건물 (5,000㎡ 초과)  349,000원/월
  건설 (50억 미만)     249,000원/월
  건설 (50억 이상)     499,000원/월
```

CUSTOM은 규모 Band가 아니다.
500인 이상이라는 이유만으로 CUSTOM으로 보내지 않는다.
CUSTOM은 별도 Product Tier (ERP 연동, SSO, On-premise, 별도 SLA 등)다.

```
Primary Facility   = 가장 높은 정상가격 시설 × 100%
Additional Facility = 각 정상가격 × 80%
Worker Fee         = 0 (MANAGER에 없음)

MONTHLY_SUPPLY     = Primary + sum(Additional)
```

### FIELD

```
FIELD Base         = 249,000원 / 시설 / 월 (고정, VAT 별도 공급가)

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

MONTHLY_SUPPLY = Primary + sum(Additional) + Worker Fee
```

### CUSTOM

```
auto price preview     = 0
automatic calculation  = 0
standard quote issue   = 0

route: CUSTOM 선택 → 별도 견적 요청 흐름
```

### 공통 결제 공식

```
RAW_PAYMENT_SUPPLY
= MONTHLY_SUPPLY × payment_months

DISCOUNT_AMOUNT
= RAW_PAYMENT_SUPPLY × discount_rate(payment_months)

PAYMENT_SUPPLY
= RAW_PAYMENT_SUPPLY - DISCOUNT_AMOUNT

VAT
= PAYMENT_SUPPLY × 10%

TOTAL_PAYMENT
= PAYMENT_SUPPLY + VAT
```

`TOTAL_PAYMENT` = VAT 포함 최종 결제금액.

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
Worker 100명:
  20 × 3,000  =  60,000원
  30 × 2,500  =  75,000원
  50 × 2,000  = 100,000원
               ─────────
Worker Total           235,000원
               ─────────
MONTHLY_SUPPLY         683,200원  (VAT 별도)

6개월 RAW            4,099,200원
10% 할인              -409,920원
               ─────────
공급가액 (PAYMENT_SUPPLY) 3,689,280원
VAT 10%                368,928원
               ─────────
최종 결제금액        4,058,208원  (VAT 포함)
```

---

## 5. VAT 표시정책 (Owner Decision 2026-09-28 추가)

### A. 기준가격

모든 상품 기준가격은 **VAT 별도 공급가**다.

```
MANAGER 149,000원 / MANAGER 299,000원 / MANAGER 499,000원
FIELD Base 249,000원 / FIELD Additional 199,200원
Worker Capacity 요금
→ 전부 공급가 기준
```

### B. 마케팅 가격표

공개 시작가격 표시 시 반드시 "VAT 별도"를 함께 표시한다.

```
관리자형  월 149,000원부터 (VAT 별도)
현장참여형 월 249,000원부터 (VAT 별도)
```

### C. 월 이용료

```
MONTHLY_SUPPLY = VAT 별도 공급가
```

### D. 할인 적용 순서

할인은 **VAT 계산 전** 공급가에 적용한다.

```
RAW_PAYMENT_SUPPLY → DISCOUNT → PAYMENT_SUPPLY → VAT → TOTAL
```

### E. 견적서 / 결제 화면

반드시 아래 항목을 구분하여 표시한다:

```
월 이용료 (VAT 별도)
결제월수
할인율 / 할인금액
공급가액
VAT
────────────────────
최종 결제금액 (VAT 포함)
```

결제 CTA 직전에 **VAT 포함 최종 결제금액**을 가장 명확하게 표시한다.
공급가를 최종금액처럼 표시 금지.

---

## 6. Backend Frozen 자산 상태

기존 Frozen Backend 자산은 **V2 구현 증거로 보존**한다.

**V3 호환성은 현재 UNVERIFIED**이다.
아래 Object 중 어느 것도 V3 compatibility PASS로 선판정하지 않는다.

실제 V2 source에는 다음이 존재한다:

```
saas_payment_v2_adapter.py       → period_months = snap.term_months
saas_payment_success_v2_adapter.py → payment.period_months == snapshot.term_months
saas_renewal_v2_adapter.py       → period_months = snap.term_months
commercial schema                → term_months
OBJ10-C Atomic                   → commercial_version.term_months
B2 Renewal Atomic                → snapshot.term_months / payment.period_months
                                   CV.term_months / contract.end_date extension
```

이 모든 연결이 V3 정책의 `payment_months` 분리와 얼마나 충돌하는지는
**BE-V3-OBJ01 Backend Impact Inventory**에서 전수조사한다.

**현재 판정:**

| 자산 | V3 호환성 |
|------|----------|
| OBJ10-A (Quote V2 → INICIS Payment Adapter) | UNVERIFIED |
| OBJ10-B (Contract Row Builder) | UNVERIFIED |
| OBJ10-C (Atomic Contract Persistence) | UNVERIFIED |
| OBJ10-D-A (Renewal Plan Builder) | UNVERIFIED |
| OBJ10-D-B1 (Renewal 시간축) | UNVERIFIED |
| OBJ10-D-B2 (Atomic Renewal Persistence) | UNVERIFIED |
| OBJ10-D-B3 (Renewal Runtime Branch Wiring) | UNVERIFIED |
| `saas_pricing_policy_v2.py` | UNVERIFIED |
| `saas_pricing_composer_v2.py` | UNVERIFIED |

각 Object의 PRESERVE / REOPEN / SUCCESSOR REQUIRED 판정은
BE-V3-OBJ01에서 수행한다.

---

## 7. 고객용 가격 계산기 UX — 정본 플로우

### 전체 흐름

```
Marketing SaaS
  → [내 이용료 확인]
    → STEP 1: 이용방식 선택

        MANAGER / FIELD → 표준 가격 확인 흐름
        CUSTOM         → 별도 견적 요청 흐름 (이하 STEP 2~4 해당 없음)

      → STEP 2: 시설 입력 (섹터 + 규모) + [시설 추가]
        → STEP 3: (FIELD인 경우) Worker Capacity 입력
          → STEP 4: 결제월수 선택 (1 / 3 / 6 / 9 / 12개월)
            → Backend Preview
              → 가격 Breakdown 표시
                → [이 조건으로 견적서 발행]
                  → Frozen Quote
                    → [PDF] [결제하기]
```

Frontend 자체 가격 계산 = 0. 가격 계산은 Backend Preview만 사용.

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

### 가격 표시 계층

| 화면 | 표시 내용 |
|------|----------|
| 마케팅 | 월 149,000원부터 (VAT 별도) |
| 가격 확인 결과 | 월 이용료 683,200원 (VAT 별도) |
| 견적 / 결제 | 공급가액 / VAT / 최종 결제금액 (VAT 포함) 구분 표시 |

### 가격 Breakdown 예시

**MANAGER — A공장(산업 85명) + B건물(7,500㎡) / 12개월:**

```
관리자형

A공장 · 산업 · 85명 → 50~299인 구간
  월 정상가격             299,000원

B건물 · 7,500㎡ → 5,000㎡ 초과 구간
  월 정상가격             349,000원
  추가시설 할인 20%       -69,800원
─────────────────────────────────
월 이용료                 578,200원  (VAT 별도)

12개월 RAW             6,938,400원
결제기간 할인 20%      -1,387,680원
─────────────────────────────────
공급가액               5,550,720원
VAT (10%)               555,072원
─────────────────────────────────
최종 결제금액          6,105,792원  (VAT 포함)

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
월 이용료                683,200원  (VAT 별도)

6개월 RAW             4,099,200원
결제기간 할인 10%       -409,920원
─────────────────────────────────
공급가액              3,689,280원
VAT (10%)              368,928원
─────────────────────────────────
최종 결제금액         4,058,208원  (VAT 포함)

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

### PHASE 1 — Pricing Policy Re-Canonical (이 문서 — GPT 검증 대기)

```
Owner Decision 반영 완료
GPT 독립검증 → PASS 후 FROZEN 승격
```

### PHASE 2 — Backend 영향도 조사 (BE-V3-OBJ01) ← 다음 단계

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
  MANAGER INDUSTRY: 49이하 / 50~299 / 300이상

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
payment_months ↔ service effective period 정의
payment_months ↔ contract.end_date 정의
payment_months ↔ renewal boundary 정의

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
  시설 / 현장참여 Capacity / 결제월수 / 최종 결제금액
```

### PHASE 8 — Marketing Pricing (FE-WWW-OBJ01 재개)

```
관리자형:  월 149,000원부터 (VAT 별도)
현장참여형: 월 249,000원부터 (VAT 별도)
CUSTOM:   별도견적

CTA: [내 이용료 확인]
직접 결제 없음
```

### PHASE 9 — 가격확인 + 견적발행 (FE-WWW-OBJ02)

```
한 화면:
  Tier → 시설 추가 → 규모 → Capacity → 결제월수
  → Backend Preview → Breakdown (VAT 포함 최종 결제금액 표시)
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
= CANDIDATE (GPT 독립검증 대기)

기존 Pricing V2 Backend Frozen 자산
= 구현 증거 보존
= V3 호환성 전체 UNVERIFIED
= 판정: BE-V3-OBJ01 Backend Impact Inventory

FE-WWW-OBJ01 (commit 0060d65c)
= NOT FROZEN
= 이후 PATCH WO = SUPERSEDED
= PR / MERGE / DEPLOY = BLOCKED
──────────────────────────────────────────
다음 Gate (Policy PASS 후):
  BE-V3-OBJ01 Backend Impact Inventory
  = 코드 수정 없이 영향받는 Object 전수조사
  = 조사 완료 → REOPEN 범위 확정 → PHASE 3 개방
──────────────────────────────────────────

production DDL      = 0
production mutation = 0
deploy              = 0
PR                  = 0
merge               = 0
```
