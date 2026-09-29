---
title: TAI Safe Pricing V2 — Canonical Tier Correction PATCH1 Evidence Report
status: EVIDENCE_REPORT
goal: WO-PRICING-V2-CANONICAL-TIER-CORRECTION-001-PATCH1
collected_by: Claude Code (COLLECT role)
collected_date: 2026-09-27
review_required: GPT REVIEW REQUIRED
---

# WO-PRICING-V2-CANONICAL-TIER-CORRECTION-001-PATCH1 Evidence Report

---

## 1. 목적

WO-PRICING-V2-CANONICAL-TIER-CORRECTION-001 코드 정정 이후, 두 Canonical 문서에 남아 있던
2-Tier 언어를 3-Tier 모델로 정렬.

---

## 2. COMMIT

```
16778149
Branch: docs/pricing-canonical-20260927
Message: docs(pricing-v2): align canonical documents to three-tier model
Files: 2 changed, 67 insertions(+), 24 deletions(-)
```

---

## 3. FILES MODIFIED

| 파일 | 변경 내용 |
|---|---|
| `docs/2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md` | §1 Tier 3 제목·설명 / §3 FIELD uplift per-site 명시 / §10 공통 상품 코드명 / §15 Tier 3 헤딩·CTA / §17 Calculator 입력 4번 |
| `docs/2026-09-27_TAI_SAFE_PRICING_V2_MASTER_WORK_PLAN.md` | §3 CUSTOM 위치 / §8 Architecture / §14 BE-OBJ06 CUSTOM entitlement / §14 BE-OBJ07 Change Order 주의 / §15 FE-WWW-OBJ01 / §15 FE-WWW-OBJ02 / §19 Test Strategy E2E / §23 현재 상태 / §24 다음 순서 / §25 Exit Criteria |

기존 파일 수정 외 범위: 0
DB: 0 / Runtime: 0 / Frontend: 0

---

## 4. FINAL_CANONICAL 변경 상세

### §1 Tier 3 제목 (line 91)
```
이전: ### Tier 3. Custom / Enterprise
이후: ### Tier 3. 커스터마이징 (CUSTOM)
      CUSTOM은 세 번째 Product Tier다. 자동가격 없음. 별도 견적 전용.
```

### §3 FIELD uplift per-site 명시
```
추가:
uplift +100,000원은 사업장별로 각각 적용한다.

다사업장에서 추가 사업장 80% 할인을 적용할 때는 uplift를 포함한 금액에 할인을 적용한다:

  추가 사업장 현장참여형 금액
  = (관리자형 Compliance Base + 100,000원) × 80%
  ≠ (관리자형 Compliance Base × 80%) + 100,000원
```

### §10 공통 상품 코드명
```
이전:
관리자형
현장참여형
Custom / Enterprise

이후:
관리자형 (MANAGER)
현장참여형 (FIELD)
커스터마이징 (CUSTOM)
```

### §15 Tier 3 헤딩
```
이전: ### Custom / Enterprise
이후: ### 커스터마이징 (CUSTOM)
      CUSTOM = 세 번째 Product Tier. 자동가격 없음.
```

### §17 Calculator 입력 4번
```
이전: 4. 관리자형 / 현장참여형
이후: 4. 관리자형 / 현장참여형 / 커스터마이징
      커스터마이징 선택 시 자동 가격 계산 없음 — 별도 견적 CTA로 전환.
```

---

## 5. MASTER_WORK_PLAN 변경 상세

### §3 Custom의 위치
```
이전: Custom은 세 번째 Tier가 아니다.
      product_tier = MANAGER | FIELD
      pricing_mode = STANDARD | CUSTOM

이후: CUSTOM은 세 번째 Product Tier다.
      product_tier = MANAGER | FIELD | CUSTOM
      MANAGER → pricing_mode = STANDARD (자동가격)
      FIELD   → pricing_mode = STANDARD (자동가격)
      CUSTOM  → pricing_mode = CUSTOM   (자동가격 없음, 별도 견적)
```

### §8 Architecture 목표 구조
```
이전: Product Tier  ────────── MANAGER | FIELD
이후: Product Tier  ────────── MANAGER | FIELD | CUSTOM
                               (자동가격: MANAGER / FIELD  |  별도견적: CUSTOM)
```

### §14 BE-OBJ06 Entitlement
```
추가: CUSTOM: contract-specific entitlement composition (별도 Object에서 구체화)
```

### §14 BE-OBJ07 Change Order
```
추가: CUSTOM 계약의 Change Order는 별도 견적 경로를 따른다. 자동 Change Order 적용 금지.
```

### §15 FE-WWW-OBJ01
```
이전: Custom(별도문의)
이후: 커스터마이징(별도 견적) + CUSTOM = 세 번째 Product Tier 주석
```

### §15 FE-WWW-OBJ02
```
이전: Tier
이후: Tier (관리자형 / 현장참여형 / 커스터마이징)
      커스터마이징 선택 시: 자동 가격 계산 없음 → 별도 견적 CTA로 전환.
```

### §19 Test Strategy E2E
```
이전: 3 sectors × 2 tiers × ...
이후: 3 sectors × 2 priced tiers (MANAGER/FIELD) × ...
      추가: CUSTOM E2E 행
```

### §23 현재 상태
```
이전:
OBJ00       | CLOSED
BE-OBJ01    | CLAUDE EXECUTION PASS / GPT SOURCE VERIFY PENDING
BE-OBJ02+   | NOT OPENED

이후:
OBJ00       | CLOSED (34a6b51a)
BE-OBJ01    | CLAUDE EXECUTION PASS (f7025efd → d1bbfc91) / GPT VERIFY PENDING
BE-OBJ02    | CLAUDE EXECUTION PASS (d1bbfc91) / GPT VERIFY PENDING
BE-OBJ03    | CLAUDE EXECUTION PASS (894aa020 → d1bbfc91) / GPT VERIFY PENDING
WO-CANONICAL-TIER-CORRECTION-001 PATCH1 | IN PROGRESS → (이번 커밋으로 완료)
BE-OBJ04+   | NOT OPENED
```

### §24 다음 순서
```
이전:
STEP 1: BE-OBJ01 remote/source independent verification
STEP 2: BE-OBJ01 CLOSED (PASS 시)
STEP 3: BE-OBJ02 Pricing Policy Model 작업지시
BE-OBJ01 검증 전에 BE-OBJ02를 열지 않는다.

이후:
STEP 1: WO-CANONICAL-TIER-CORRECTION-001 PATCH1 완료 및 commit
STEP 2: BE-OBJ01 + BE-OBJ02 + BE-OBJ03 + PATCH1 GPT 독립검증
STEP 3: 전체 GPT VERIFY PASS → 각 Object CLOSED
STEP 4: BE-OBJ04 Commercial Contract Storage 작업지시
GPT 독립검증 없이 BE-OBJ04를 열지 않는다.
```

### §25 Exit Criteria
```
이전:
- [ ] 2 Tier 구조
- [ ] Custom 별도

이후:
- [ ] 3 Product Tier 구조 (MANAGER / FIELD / CUSTOM)
- [ ] CUSTOM 자동가격 없음 / 별도 견적
```

---

## 6. 잔존 2-Tier 언어 검색

```bash
grep -n "2개 Tier\|두 개뿐\|MANAGER | FIELD\"" \
  docs/2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md \
  docs/2026-09-27_TAI_SAFE_PRICING_V2_MASTER_WORK_PLAN.md
→ 0 matches
```

```bash
grep -n "Custom / Enterprise" \
  docs/2026-09-27_TAI_SAFE_PRICING_FINAL_CANONICAL.md \
  docs/2026-09-27_TAI_SAFE_PRICING_V2_MASTER_WORK_PLAN.md
→ 0 matches
```

---

## 7. NOT_FOUND

없음.

---

## 8. UNVERIFIED

없음.

---

## 9. COMPLETE COMMIT CHAIN (WO-CANONICAL-TIER-CORRECTION-001)

| 커밋 | 내용 |
|---|---|
| d1bbfc91 | 코드 정정: ProductTier 3값 / 조합 validator / Composer CUSTOM 분기 / 166 PASS |
| 16778149 | PATCH1: 두 Canonical 문서 3-Tier 정렬 |

---

```
GPT REVIEW REQUIRED
```
