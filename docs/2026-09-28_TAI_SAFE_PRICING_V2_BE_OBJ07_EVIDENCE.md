---
title: TAI Safe Pricing V2 — BE-OBJ07 Change Order Domain V2 Evidence Report
status: EVIDENCE_REPORT
goal: G-mujxylms-0a7566
collected_by: Claude Code (COLLECT role)
collected_date: 2026-09-28
review_required: GPT REVIEW REQUIRED
---

# WO-PRICING-V2-BE-OBJ07 Evidence Report

---

## 1. EXECUTION ANCHOR

```
Branch : docs/pricing-canonical-20260927
Base   : f9573f51
PATCH1 : 33758549
```

---

## 2. DOMAIN BOUNDARY

Change Order Domain — Current Contract Snapshot vs Target Pricing Result 비교.

월 기준 Commercial Delta만 계산한다.
잔여기간 청구액 / Proration / VAT 계산 금지.

---

## 3. STATUS TAXONOMY

```
NO_CHANGE             — 동일 (tier / site / worker / term 전부)
CHANGE_READY          — 순수 확장만 존재, delta > 0
RENEWAL_ONLY          — 축소 또는 혼합 (확장+축소) 포함
CUSTOM_QUOTE_REQUIRED — current 또는 target CUSTOM
```

---

## 4. CHANGE TYPE ORDER (§72)

```python
CHANGE_TYPE_ORDER: Tuple[str, ...] = (
    "PRODUCT_TIER_UPGRADE",
    "SITE_ADDED",
    "SCALE_BAND_INCREASE",
    "WORKER_CAPACITY_INCREASE",
)
```

immutable tuple. 가변 List 금지.

---

## 5. RENEWAL_ONLY TYPE ORDER (§73)

```python
RENEWAL_ONLY_TYPE_ORDER: Tuple[str, ...] = (
    "PRODUCT_TIER_DECREASE",
    "SITE_REMOVED",
    "SCALE_BAND_DECREASE",
    "WORKER_CAPACITY_DECREASE",
    "TERM_CHANGE",
)
```

immutable tuple. 가변 List 금지.

---

## 6. FROZEN SNAPSHOT PRINCIPLE

현재 계약 가격: `cv.pricing_snapshot.monthly_supply_amount` 사용.
`contracts.contract_amount` DB 필드 직접 참조 금지.

---

## 7. POLICY VERSION GATE

```
current_policy_version != target_policy_version → POLICY_VERSION_MISMATCH
```

교차 정책 버전 delta 계산 금지.

---

## 8. BAND COMPARISON

`SaasComplianceBandCatalogEntryV2` (schemas/saas_commercial_fit_v2.py) 재사용.
`sort_order` 비교로 SCALE_BAND_INCREASE / DECREASE 판정.
금액 비교 금지.

---

## 9. DELTA VALIDATION

```
CHANGE_READY 경우: delta = target_monthly - current_monthly
delta <= 0 → INVALID_CHANGE_DELTA
```

---

## 10. CUSTOM_QUOTE_REQUIRED

```
current product_tier == "CUSTOM" → CUSTOM_QUOTE_REQUIRED
target product_tier == "CUSTOM"  → CUSTOM_QUOTE_REQUIRED
target status == "CUSTOM_REQUIRED" → CUSTOM_QUOTE_REQUIRED
```

---

## 11. TARGET PRICING NOT READY

```
target status == "TERM_DISCOUNT_UNRESOLVED" → TARGET_PRICING_NOT_READY
target snapshot is None (but status == READY) → TARGET_PRICING_NOT_READY
```

---

## 12. CHANGE LINE ORDERING

```
1. Tier change line (PRODUCT_TIER_UPGRADE / DECREASE)
2. Site lines — 추가/제거/band변경 (sector → entity_type → entity_id 정렬)
3. Worker line
4. Term line
```

---

## 13. TEST RESULT

### 신규 테스트 매트릭스

| ID | 설명 | 결과 |
|---|---|---|
| C01 | MANAGER 동일 → NO_CHANGE | PASS |
| C02 | FIELD 동일 → NO_CHANGE | PASS |
| C03 | NO_CHANGE delta = 0 | PASS |
| C04 | NO_CHANGE prepaid = False | PASS |
| C05 | MANAGER→FIELD CHANGE_READY | PASS |
| C06 | tier_upgrade in change_types | PASS |
| C07 | FIELD→MANAGER RENEWAL_ONLY + PRODUCT_TIER_DECREASE | PASS |
| C08 | MANAGER→CUSTOM CUSTOM_QUOTE_REQUIRED | PASS |
| C09 | FIELD→CUSTOM CUSTOM_QUOTE_REQUIRED | PASS |
| C10 | current CUSTOM → CUSTOM_QUOTE_REQUIRED | PASS |
| C11 | worker 증가 CHANGE_READY + WORKER_CAPACITY_INCREASE | PASS |
| C12 | worker 동일 NO_CHANGE | PASS |
| C13 | worker 감소 RENEWAL_ONLY + WORKER_CAPACITY_DECREASE | PASS |
| C14 | MANAGER worker = 0 유지 | PASS |
| C15 | site 추가 CHANGE_READY + SITE_ADDED | PASS |
| C16 | 복수 site 추가 → 정렬된 SITE_ADDED lines | PASS |
| C17 | site 제거 RENEWAL_ONLY + SITE_REMOVED | PASS |
| C18 | 현재⊂목표 → CHANGE_READY | PASS |
| C19 | 목표⊂현재 → RENEWAL_ONLY | PASS |
| C20 | 동일 entity_id, sector 불일치 → SITE_CONTEXT_MISMATCH | PASS |
| C21 | 동일 band → scale change 없음 | PASS |
| C22 | 높은 sort_order → SCALE_BAND_INCREASE + CHANGE_READY | PASS |
| C23 | 낮은 sort_order → SCALE_BAND_DECREASE + RENEWAL_ONLY | PASS |
| C24 | 현재 band 카탈로그 미포함 → BAND_CATALOG_ENTRY_NOT_FOUND | PASS |
| C25 | 목표 band 카탈로그 미포함 → BAND_CATALOG_ENTRY_NOT_FOUND | PASS |
| C26 | 중복 카탈로그 키 → DUPLICATE_BAND_CATALOG_ENTRY | PASS |
| C27 | 동일 sort_order 중복 → AMBIGUOUS_BAND_ORDER | PASS |
| C28 | 동일 term → NO_CHANGE | PASS |
| C29 | term 12→6 RENEWAL_ONLY + TERM_CHANGE | PASS |
| C30 | term 6→12 RENEWAL_ONLY + TERM_CHANGE | PASS |
| C31 | term 변경은 CHANGE_READY 불가 | PASS |
| C32 | 동일 policy version 허용 | PASS |
| C33 | policy version 불일치 → POLICY_VERSION_MISMATCH | PASS |
| C34 | READY target 수용 | PASS |
| C35 | TERM_DISCOUNT_UNRESOLVED → TARGET_PRICING_NOT_READY | PASS |
| C36 | CUSTOM_REQUIRED target → CUSTOM_QUOTE_REQUIRED | PASS |
| C37 | READY + snapshot None → TARGET_PRICING_NOT_READY | PASS |
| C38 | selection tier ≠ snapshot tier → TARGET_SNAPSHOT_MISMATCH | PASS |
| C39 | selection worker ≠ snapshot worker → TARGET_SNAPSHOT_MISMATCH | PASS |
| C40 | selection term ≠ snapshot term → TARGET_SNAPSHOT_MISMATCH | PASS |
| C41 | result monthly ≠ snapshot monthly → TARGET_SNAPSHOT_MISMATCH | PASS |
| C42 | delta = target - current 수식 검증 | PASS |
| C43 | 유효 확장 delta > 0 | PASS |
| C44 | delta = 0 (강제) → INVALID_CHANGE_DELTA | PASS |
| C45 | delta < 0 (강제) → INVALID_CHANGE_DELTA | PASS |
| C46 | tier + site 복합 CHANGE_READY | PASS |
| C47 | site + band 복합 CHANGE_READY | PASS |
| C48 | band + worker 복합 CHANGE_READY | PASS |
| C49 | 4종 확장 전부 | PASS |
| C50 | change_types 정렬 순서 검증 | PASS |
| C51 | site 추가 + worker 감소 → RENEWAL_ONLY | PASS |
| C52 | scale 증가 + site 제거 → RENEWAL_ONLY | PASS |
| C53 | RENEWAL_ONLY renewal_types 보존 | PASS |
| C54 | RENEWAL_ONLY monthly_supply_delta = None | PASS |
| C55 | superseded current version → NON_CURRENT_COMMERCIAL_VERSION | PASS |
| C56 | effective_at < current effective_from → CHANGE_EFFECTIVE_BEFORE_CURRENT_VERSION | PASS |
| C57 | site 입력 순서 변경 → 동일 결과 | PASS |
| C58 | catalog 순서 변경 → 동일 결과 | PASS |
| C59 | 동일 입력 2회 → 완전 동일 출력 | PASS |
| C60 | 입력 객체 mutation 없음 | PASS |
| C61 | DB I/O 없음 | PASS |
| C62 | Payment prepare 없음 | PASS |
| C63 | payment_svc 없음 | PASS |
| C64 | VAT 계산 없음 | PASS |
| C65 | Proration 없음 | PASS |
| C66 | tier_upgrade_svc 없음 | PASS |
| C67 | saas_commercial_fit_gate_v2 호출 없음 | PASS |
| C68 | APIRouter 없음 | PASS |
| C69 | datetime.now() 없음 | PASS |
| C70 | CHANGE_TYPE_ORDER immutable tuple | PASS |
| C71 | pricing_mode 불일치 → TARGET_SNAPSHOT_MISMATCH | PASS |
| C72 | pricing_mode 일치 → accepted | PASS |
| C73 | 임의 change_type 문자열 → ValidationError | PASS |
| C74 | proposal 유효하지 않은 product_tier → ValidationError | PASS |
| C75 | change line 유효하지 않은 from/to product_tier → ValidationError | PASS |

```
python3 -m pytest -q \
  tests/test_saas_pricing_v2_contract.py \
  tests/test_saas_pricing_policy_v2.py \
  tests/test_saas_pricing_composer_v2.py \
  tests/test_saas_contract_commercial_v2.py \
  tests/test_saas_commercial_fit_gate_v2.py \
  tests/test_saas_entitlement_gate_v2.py \
  tests/test_saas_change_order_v2.py

411 passed in 0.38s
```

---

## 14. PREVIOUS REGRESSION

```
이전 기준 : 336 PASS (OBJ07 이전)
OBJ07     : 406 PASS (336 regression + 70 OBJ07)
PATCH1    : 411 PASS (406 regression + 5 PATCH1)

FAIL = 0
```

---

## 14b. PATCH1 CHANGES

GPT 독립검증 결과 2건 보정:

**PATCH-A — pricing_mode cross validation 추가 (service):**
```
Step 7에 target_selection.pricing_mode != target_snap.pricing_mode
→ TARGET_SNAPSHOT_MISMATCH 추가
```

**PATCH-B — Change Line type hardening (schema):**
```
SaasCommercialChangeLineV2.change_type: str
→ change_type: ChangeLineType (9종 canonical Literal)

임의 문자열 "UPGRADE", "FOO" 등 차단
```

**Section 6 — ProductTier strict (schema):**
```
SaasCommercialChangeLineV2.from_product_tier/to_product_tier: Optional[str]
→ Optional[ProductTier]

SaasChangeOrderProposalV2.current_product_tier/target_product_tier: str
→ ProductTier
```

---

## 15. TEST FIX NOTES

3가지 테스트 수정:

1. **C22/C34/C42/C58/C59/C60**: `_site(_SITE_A, "BUSINESS")` → `_site(_SITE_A, "BUSINESS", 200_000)`
   - STARTER/BUSINESS 모두 `base_amount=149_000` 기본값 사용 시 delta=0 → INVALID_CHANGE_DELTA
   - BUSINESS 사이트에 더 높은 금액 지정하여 delta > 0 보장

2. **C35**: `SaasPricingPolicyV2` 5개 필수 제약 + `SaasTermDiscountPolicy.term_months ∈ [1,3,6,9,12]` 제약으로 term_months=1 미포함 정책 생성 불가
   - `calculate_saas_price_v2` 직접 호출 대신 `model_copy(update={"status": "TERM_DISCOUNT_UNRESOLVED"})` 사용

---

## 16. SOURCE GUARDS

```
DB I/O           = 0  (supabase / execute_sql / get_supabase / psycopg 없음)
Payment          = 0  (payment / billing / refund / paid_amount 없음)
VAT 계산         = 0  (vat_rate_bps / vat_amount 없음 — code_lines 기준)
Proration        = 0  (days_remaining / months_remaining / daily_rate / prorated_amount 없음)
V1 의존          = 0  (tier_upgrade_svc / tier_payment_gate 없음 — code_lines 기준)
Router wiring    = 0  (APIRouter / from routers / import routers 없음)
datetime.now()   = 0
```

---

## 17. RUNTIME CONSUMER SEARCH

```bash
grep -R "saas_change_order_v2" routers/ services/ \
  --exclude="saas_change_order_v2.py"
```

결과:

```
Runtime consumer = 0
```

---

## 18. V1 GUARD

```
git diff HEAD -- services/tier_upgrade_svc.py
```

결과: 변경 없음.

---

## 19. PRODUCTION MUTATION

```
INSERT = 0
UPDATE = 0
DELETE = 0
DDL EXECUTION = 0
```

Supabase 접근: 없음.

---

## 20. FILES CHANGED

신규 생성:

```
schemas/saas_change_order_v2.py
services/saas_change_order_v2.py
tests/test_saas_change_order_v2.py
docs/2026-09-28_TAI_SAFE_PRICING_V2_BE_OBJ07_EVIDENCE.md
```

기존 파일 수정:

```
0
```

---

## 21. NOT_FOUND

없음.

---

## 22. UNVERIFIED

없음.

---

```
GPT REVIEW REQUIRED
```
