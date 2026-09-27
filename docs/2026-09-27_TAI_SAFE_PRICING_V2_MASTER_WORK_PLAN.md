---
title: TAI Safe Pricing V2 — Master Work Plan
status: MASTER_PLAN
created: 2026-09-27
owner_approved: 2026-09-27
policy_ref: 2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md
---

# TAI Safe Pricing V2 — Master Work Plan

**작성일:** 2026-09-27
**상태:** MASTER PLAN
**대상:** TAI Safe SaaS 가격·Tier·계약·결제·Frontend·Backend 전체 전환
**기준정책:** 2026-09-27 Owner 확정 Pricing Canonical

---

# 1. 목적

TAI Safe의 기존 가격구조를 다음 최종정책으로 전환한다.

```
공개 상품 구조

1. 관리자형
2. 현장참여형
3. Custom / Enterprise 별도
```

가격은 단순 Tier 정액제가 아니라 다음 조합으로 산정한다.

```
상품 Tier
+
사업장 규모
+
사업장 수
+
현장참여 인원
+
계약기간
+
필요 시 Custom
```

TAI는 선불 구조를 유지한다.

---

# 2. 최종 가격정책

## 2.1 Product Tier

정식 Tier는 두 개뿐이다.

```
MANAGER
FIELD
```

### MANAGER

안전관리자가 중심이 되어 법령의무·점검·일정·문서·수행·증빙을 관리한다.

### FIELD

MANAGER 기능에 더해 현장 작업자가 직접 참여한다.
(TBM, 위험성평가, 점검, 전자확인, 위험제보, 사진/증빙)

---

# 3. Custom의 위치

Custom은 세 번째 Tier가 아니다.

```
product_tier = MANAGER | FIELD
pricing_mode = STANDARD | CUSTOM
```

Custom 대상: ERP, SSO, API, On-premise, 대량 Migration, 고객전용 Workflow, 전용 문서양식, 별도 SLA, 대규모 특수구조

---

# 4. 사업장 규모 가격

기존 `price_master`의 SaaS 가격은 폐기하지 않는다.

기존 `tier_code`를 Product Tier가 아니라 **Compliance Base Band**로 의미를 고정한다.

```
INDUSTRY_STARTER / INDUSTRY_BUSINESS / INDUSTRY_PRO
BUILDING_BASIC / BUILDING_STANDARD
CONSTRUCTION_STANDARD / CONSTRUCTION_PREMIUM
```

= 사업장 규모에 따른 Compliance Base 가격구간 (기능등급 아님)

---

# 5. 현장참여 가격

FIELD = 해당 사업장 MANAGER Base + 100,000원 + 현장참여 Capacity

현장참여 인원 누적구간:

```
1~20명     : 3,000원/인/월
21~50명    : 2,500원/인/월
51~100명   : 2,000원/인/월
101~300명  : 1,500원/인/월
301명+     : 1,200원/인/월
```

Pack 강제구매 없음.

---

# 6. 사업장 가격

- 첫 사업장: 정상가 100%
- 추가 사업장: 각 사업장 정상가 × 80%

가입순서에 따라 가격이 달라지지 않는다.

---

# 7. 선불 계약

계약기간: 1 / 3 / 6 / 9 / 12개월 — 모두 선불

기간별 할인율: 미확정 — 별도 Object에서 Owner Decision 후 적용

계약 중 확대 (Tier Upgrade, Capacity 증가, 사업장 추가, Compliance Scope 증가) = 잔여기간 추가 선불결제

감소 = 기본적으로 다음 갱신 시 반영

---

# 8. Architecture 원칙

현재 구조 (문제):
```
사업장 규모 = Plan = Price = Feature Level = LEG Gate
```

목표 구조:
```
Product Tier  ────────── MANAGER | FIELD
Compliance Base ──────── Sector + Scale
Site Scope ──────────── 사업장별 가격
Worker Capacity ─────── FIELD 참여인원
Contract Term ───────── 선불기간
Commercial Snapshot ─── 계약시점 가격 Freeze
```

---

# 9. 개발 Governance

| 역할 | 담당 |
|---|---|
| 분석·설계·Object 분해·작업지시·독립검증·PASS 판정 | GPT |
| 증거수집·지정 구현·테스트·Diff·Commit·증거보고 | Claude Code |
| 정책 결정·Owner Approval·Production 변경 승인 | Owner |

---

# 10. 공통 실행 Cycle

모든 Object:

```
1. GPT Object 설계
2. Owner 확인
3. GPT 작업지시서
4. Claude 실행
5. Claude Evidence 제출
6. GPT 독립검증
7. PASS / BLOCKED
8. Commit/PR Gate
9. 다음 Object Open
```

Object Skip 금지.

---

# 11. 전체 Object Map

5개 Stream:

```
A. DISCOVERY / GOVERNANCE
B. BACKEND DOMAIN
C. BACKEND COMMERCIAL RUNTIME
D. FRONTEND
E. MIGRATION / RELEASE
```

---

# 12. STREAM A — Discovery / Governance

## OBJ00 — Current-State Evidence Inventory

현재 가격·계약·결제·Gate·Frontend 의존관계를 고정.

```
CLAUDE EXECUTION  = COMPLETE
COMMIT            = 34a6b51a
GPT VERIFY        = COMPLETE (6개 항목 검토)
STATUS            = CLOSED
```

---

# 13. STREAM B — Backend Domain

## BE-OBJ01 — Commercial Domain Contract V2

Product Tier / Pricing Mode / Compliance Base Band / Site Scope / Worker Capacity / Term / Pricing Snapshot 개념 코드 수준 분리.

```
CLAUDE EXECUTION  = PASS
COMMIT            = f7025efd
TEST              = 28 PASS
GPT SOURCE VERIFY = PENDING
```

## BE-OBJ02 — Pricing Policy Model

가격정책값을 버전 가능한 정책으로 정의.

대상: FIELD uplift / additional site discount / worker brackets / VAT / term policy / policy version / effective period

```
STATUS = NOT OPENED
선행조건 = BE-OBJ01 GPT VERIFY PASS
```

## BE-OBJ03 — Pricing Composer

TAI Pricing V2 단일 가격 계산엔진.

- Input: product_tier, sites, worker_capacity, term
- Output: site breakdown, worker breakdown, monthly supply, prepaid supply, VAT, total, policy version

가격 계산 SSOT는 반드시 Backend 하나. Frontend 계산 금지.

```
STATUS = NOT OPENED
```

## BE-OBJ04 — Commercial Contract Storage

Pricing V2 계약 DB 표현.

필요 개념: product_tier / worker_capacity / term / policy_version / site scope / price snapshot

기존 `max_user_count`를 Worker Capacity로 임의 재사용 금지.

```
STATUS = NOT OPENED
```

---

# 14. STREAM C — Backend Commercial Runtime

## BE-OBJ05 — Commercial Fit Gate

판정 대상: 계약 사업장 수 / 규모 Band / 현재 실제 규모 / Worker Capacity

```
STATUS = NOT OPENED
```

## BE-OBJ06 — Entitlement Gate

기능권한을 Product Tier 기준으로 분리.

```
MANAGER: COMPLIANCE_CORE
FIELD:   COMPLIANCE_CORE + FIELD_TBM + FIELD_RA + FIELD_INSPECTION + FIELD_SIGN + FIELD_HAZARD_REPORT
```

LEG Core = MANAGER + FIELD 모두 가능.

```
STATUS = NOT OPENED
```

## BE-OBJ07 — Change Order / Expansion

MANAGER→FIELD / Capacity 증가 / 사업장 추가 / Compliance Base 증가를 Commercial Change 개념으로 처리.

```
구조: CURRENT SNAPSHOT → TARGET SNAPSHOT → DELTA → PREPAID PAYMENT → APPLY
STATUS = NOT OPENED
```

## BE-OBJ08 — Pricing Preview API

Frontend 가격 계산 금지. Backend Preview API 제공.

```
예: POST /pricing/v2/preview
STATUS = NOT OPENED
```

## BE-OBJ09 — Quote Integration

견적 구조를 Pricing V2 Snapshot 기반으로 변경.

```
STATUS = NOT OPENED
```

## BE-OBJ10 — Payment / Billing / Renewal

신규 계약 / 추가결제 / 갱신 / 기간연장 / Subscription / Payment post-process

기존 `plan_code → 단일 amount` 의존 제거.

```
STATUS = NOT OPENED
```

---

# 15. STREAM D — Frontend / tai-www

## FE-WWW-OBJ01 — Pricing Page

기존 STARTER/BUSINESS/PRO 카드 제거.

표시: 관리자형(149,000원부터) / 현장참여형(249,000원부터) / Custom(별도문의)

```
STATUS = NOT OPENED
```

## FE-WWW-OBJ02 — Price Calculator

입력: 업종 / 사업장 규모 / 사업장 수 / Tier / 현장참여 인원 / 계약기간

Backend Preview 호출. Frontend 계산 금지.

```
STATUS = NOT OPENED
```

## FE-WWW-OBJ03 — Purchase Flow

가격계산 결과 Snapshot 기준 결제. Frontend 금액 재조립 금지.

```
STATUS = NOT OPENED
```

## FE-WWW-OBJ04 — MyPage Quote / Contract

고객 언어로 표시. 내부 Plan Code 노출 최소화.

```
STATUS = NOT OPENED
```

---

# 16. STREAM D — Frontend / tai-admin

## FE-ADM-OBJ01 — Commercial Context V2

contract_plan_code / contract_level / contract_sector 의존을 product_tier / worker_capacity / site_scope / pricing_version / entitlements로 전환.

```
STATUS = NOT OPENED
```

## FE-ADM-OBJ02 — Legacy Plan Compatibility

OBJ00 확인 실제 이슈: PLAN_MAP exact match, _V2/_V3 suffix 미처리.

```
STATUS = NOT OPENED
선행조건 = V2 전환 전 필수
```

## FE-ADM-OBJ03 — Entitlement Consumer Migration

`contract_level` 기반 기능 판단 → `entitlements` 기준으로 변경.

```
STATUS = NOT OPENED
```

## FE-ADM-OBJ04 — Commercial Fit UX

업그레이드 UX → 계약 범위 변경 UX (규모 증가 / 사업장 추가 / Capacity 증가 / Field 전환).

```
STATUS = NOT OPENED
```

## FE-ADM-OBJ05 — Expansion Payment UX

Admin 내부에서 MANAGER→FIELD / 사업장 추가 / Capacity 증가 가능.

Backend Preview/Change Order만 소비.

```
STATUS = NOT OPENED
```

---

# 17. STREAM E — Legacy / Migration

## MIG-OBJ01 — Legacy Contract Classification

현재 계약을 MIGRATE / KEEP_LEGACY / MANUAL_REVIEW / TEST / INVALID로 분류. 자동 변환 금지.

```
STATUS = NOT OPENED
```

## MIG-OBJ02 — Contract Migration Dry Run

Production write 없이 V1→V2 mapping 결과 생성.

```
STATUS = NOT OPENED
```

## MIG-OBJ03 — Owner Migration Approval

Owner가 변환대상 승인.

```
STATUS = NOT OPENED
```

## MIG-OBJ04 — Production Migration

승인된 대상만 변환. Rollback evidence 필수.

```
STATUS = NOT OPENED
```

---

# 18. 별도 Stream — Diagnosis Legacy Pricing

SaaS Pricing V2와 분리. 별도 Object: `DIAG-PRICE-LEGACY-OBJ01`

OBJ00 확인 실제 이슈:
- `tai-admin/vue3/src/utils/diagnosis-purchaseFormat.ts` 구 가격 hardcode
- `tai-www/src/pages/free-diagnosis.astro` 구 가격 fallback (79K/99K/145K)

```
STATUS = NOT OPENED
SaaS Pricing V2 진행을 막지 않음
```

---

# 19. Test Strategy

| 레벨 | 대상 |
|---|---|
| Unit | Tier validation / Worker brackets / Site discount / Term / VAT / Snapshot |
| Contract | API request / response / DB snapshot |
| Integration | Pricing / Quote / Contract / Payment / Upgrade / Renewal / Entitlement |
| E2E | 3 sectors × 2 tiers × scale boundaries × site counts × worker boundaries × contract terms |

Critical Boundary Cases:
- INDUSTRY: 49/50, 299/300, 499/500
- BUILDING: 5,000㎡ boundary
- CONSTRUCTION: 50억 boundary
- WORKER: 0/1, 20/21, 50/51, 100/101, 300/301/305
- SITE: 1/2/3/10

---

# 20. Release 원칙

Big Bang 금지.

순서: Domain → Policy → Pricing Composer → Contract → Gate → Change Order → API → Quote/Payment → Frontend → Migration → E2E → Cutover

Frontend 선행 금지.

---

# 21. Production Freeze 원칙

최소 BE-OBJ03 Pricing Composer PASS + BE-OBJ04 Contract Model PASS + BE-OBJ08 Preview API PASS 이후에만 Production 가격 데이터 변경 여부 논의.

---

# 22. Object 완료 정의

```
CLAUDE EXECUTION PASS ≠ GPT VERIFY PASS ≠ OWNER APPROVAL
```

Claude PASS 보고 = 자동 CLOSED 아님.

---

# 23. 현재 상태 (2026-09-27)

| Object | 상태 |
|---|---|
| OBJ00 | CLOSED |
| BE-OBJ01 | CLAUDE EXECUTION PASS / GPT SOURCE VERIFY PENDING |
| BE-OBJ02+ | NOT OPENED |
| Frontend | NOT STARTED |
| DB Migration | NOT STARTED |
| Production Price Change | 0 |

---

# 24. 다음 순서

```
STEP 1: BE-OBJ01 remote/source independent verification
STEP 2: BE-OBJ01 CLOSED (PASS 시)
STEP 3: BE-OBJ02 Pricing Policy Model 작업지시
```

BE-OBJ01 검증 전에 BE-OBJ02를 열지 않는다.

---

# 25. Master Exit Criteria

- [ ] 2 Tier 구조
- [ ] Custom 별도
- [ ] Compliance Base와 Product Tier 분리
- [ ] Worker Capacity 과금
- [ ] 다사업장 20% 할인
- [ ] 선불 계약
- [ ] Server 가격계산 단일화
- [ ] 계약가격 Snapshot
- [ ] Commercial Fit 분리
- [ ] Entitlement 분리
- [ ] Quote V2
- [ ] Payment V2
- [ ] Renewal V2
- [ ] tai-www V2
- [ ] tai-admin V2
- [ ] Legacy 호환
- [ ] Migration
- [ ] E2E PASS
- [ ] Owner Production Approval

완료 후에만: `TAI SAFE PRICING V2 = PRODUCTION CANONICAL`
