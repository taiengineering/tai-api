---
title: "TAI Safe Pricing V2 BE-OBJ09 Evidence"
work_order: WO-PRICING-V2-BE-OBJ09
objective: "Pricing V2 Quote Integration"
author: Claude Code
date: 2026-09-28
status: PASS
---

# TAI Safe Pricing V2 BE-OBJ09 Evidence

## 1. EXECUTION ANCHOR

- Base commit: `40d98ada`
- OBJ09 PATCH1 commit: `435cee7c`
- PATCH1 changes: PATCH-A (calc.status cross-validation) + PATCH-B (site identity/sector set validation)
- Branch: `docs/pricing-canonical-20260927`

## 2. EXISTING QUOTE V1 OBSERVED

| 항목 | 값 |
|------|-----|
| V1 자동견적 계산기 | `member_quote_svc.calc_quote(supabase, service_type, sector, tier_code, term_months)` |
| V1 삽입 helper | `member_quote_svc._insert_quote_with_unique_retry(supabase, base_row, retries=5)` |
| V1 회사명 | `member_quote_svc._company_name_snapshot(supabase, company_id)` |
| V1 연락처 정규화 | `member_quote_svc.normalize_contact_name(value)` |
| V1 소스 | `MEMBER_SOURCES = ("member_auto", "member_custom")` |
| V1 MemberQuoteError | `code, message, http_status` |
| 기존 endpoints | `/auto/preview`, `/auto`, `/custom`, `GET /`, `GET /{id}`, `POST /{id}/pdf` |

## 3. LIVE QUOTES SCHEMA OBSERVED

WO 실측 기재 내용과 일치:

| 필드 | 타입 |
|------|------|
| `items` | jsonb |
| `supply_amount` | numeric |
| `vat_amount` | numeric |
| `total_amount` | numeric |
| RLS | ENABLED |
| DDL (신규) | 0 |

## 4. QUOTE V2 TRUST BOUNDARY

클라이언트 신뢰 필드:
```
product_tier, worker_capacity, term_months, sites[].entity_id,
sites[].sector, sites[].criteria_value, contact_name
```

클라이언트 입력 금지 (extra="forbid" 상속으로 422 반환):
```
pricing_mode, base_amount, base_band_code, policy_version,
company_id, created_by, source, status_code,
monthly_supply_amount, prepaid_supply_amount, vat_amount, total_amount,
pricing_snapshot
```

## 5. SERVER REPRICING

```
POST /me/quotes/v2/issue
→ issue_saas_quote_v2(supabase, request, user_id, company_id)
→ preview_saas_price_v2(supabase, request)
→ pricing_resolver_svc (via Preview V2)
→ saas_pricing_composer_v2 (via Preview V2)
→ READY Snapshot
→ quotes INSERT
```

`calc_quote` 직접 호출: 0
`resolve_plan` 직접 호출: 0
`calculate_saas_price_v2` 직접 호출: 0

## 6. PRICING STATUS GATE

| Preview Status | 결과 |
|----------------|------|
| `READY` | quotes INSERT |
| `TERM_DISCOUNT_UNRESOLVED` | `QUOTE_PRICING_NOT_READY` / 409 / INSERT 0 |
| `CUSTOM_REQUIRED` | `CUSTOM_QUOTE_REQUIRED` / 409 / route_to_custom=true / INSERT 0 |
| `COMPLIANCE_BASE_QUOTE_REQUIRED` | `COMPLIANCE_BASE_QUOTE_REQUIRED` / 409 / route_to_custom=true / INSERT 0 |

## 7. QUOTE V2 ITEM CONTRACT

| 필드 | 값 |
|------|-----|
| `quote_schema_version` | `SAAS_QUOTE_V2` |
| `service_type` | `SAAS` |
| `billing_unit` | `MONTHLY` |
| `price_id` | `None` |
| `tier_code` | `None` |
| `display_name` (MANAGER) | `TAI Safe 관리자형` |
| `display_name` (FIELD) | `TAI Safe 현장참여형` |
| `unit_amount` | `snapshot.monthly_supply_amount` |
| `quantity` | `snapshot.term_months` |
| `supply_amount` | `snapshot.prepaid_supply_amount` |
| `vat_amount` | `snapshot.vat_amount` |
| `total_amount` | `snapshot.total_amount` |
| `vat_rate` | `snapshot.vat_rate_bps / 10000` |

## 8. FROZEN PRICING INPUT

`pricing_input` 포함:
- `product_tier`, `worker_capacity`, `term_months`
- `sites[].entity_id`, `sites[].sector`, `sites[].criteria_value`
- 금액 필드 없음
- canonical order: sector ASC, entity_id ASC

## 9. FROZEN PRICING SNAPSHOT

`pricing_snapshot` = `SaasPricingSnapshotV2.model_dump(mode="json")` 전체.

필수 키: `schema_version`, `policy_version`, `product_tier`, `pricing_mode`,
`sites`, `worker`, `term_months`, `term_discount_rate_bps`,
`monthly_supply_amount`, `prepaid_supply_amount`, `vat_rate_bps`,
`vat_amount`, `total_amount`

UUID → str JSON-safe 직렬화 (`mode="json"`).

## 10. TOP-LEVEL AMOUNT CONTRACT

```
quotes.supply_amount = snapshot.prepaid_supply_amount
quotes.vat_amount    = snapshot.vat_amount
quotes.total_amount  = snapshot.total_amount
```

top-level == item amounts 일치.

## 11. SOURCE COMPATIBILITY

```
source = "member_auto"
```

기존 `MEMBER_SOURCES = ("member_auto", "member_custom")`에 포함.
V1 GET `/me/quotes`, admin list, PDF eligibility 호환.

## 12. MEMBER LIST/DETAIL COMPATIBILITY

- `GET /me/quotes` — `source in MEMBER_SOURCES` 필터 → V2 자동 포함
- `GET /me/quotes/{id}` — company_id 소유권 확인 → 정상 작동
- `list_member_quotes`, `get_member_quote` 수정 없음

## 13. PDF COMPATIBILITY

`_validate_snapshot` 요구 필드 모두 V2 item에 존재:
- `display_name`, `billing_unit`, `unit_amount`, `quantity`
- `supply_amount`, `vat_amount`, `total_amount`

source="member_auto" + status_code="ISSUED" → PDF eligibility 통과.
`member_quote_pdf_svc.py` 수정 없음.

## 14. CUSTOM ROUTING

| 경우 | code | route_to_custom |
|------|------|----------------|
| product_tier=CUSTOM | CUSTOM_QUOTE_REQUIRED | true |
| compliance base=0 | COMPLIANCE_BASE_QUOTE_REQUIRED | true |

기존 `POST /me/quotes/custom` 그대로 유지.

## 15. TERM DISCOUNT UNRESOLVED

현재 canonical policy = `discount_rate_bps=None` for all terms.
실제 STANDARD 호출 → TERM_DISCOUNT_UNRESOLVED → QUOTE_PRICING_NOT_READY / 409.
이것이 정상 동작 (§129).

## 16. DB WRITE SCOPE

허용 1종: `quotes INSERT` (`_insert_quote_with_unique_retry` 재사용).
직접 `supabase.table("quotes").insert(...)` 없음.

## 17. TEST RESULT

```
OBJ09 PATCH1 단독: 97 PASS / 0 FAIL  (Q01-Q90 + Q91-Q97)
```

PATCH-A 추가 테스트:
- Q91: preview.status=READY + calc.status=TERM_DISCOUNT_UNRESOLVED → QUOTE_SNAPSHOT_INVALID / INSERT 0

PATCH-B 추가 테스트:
- Q92: request에 snapshot 없는 site → QUOTE_SNAPSHOT_INVALID / INSERT 0
- Q93: snapshot에 request 없는 site → QUOTE_SNAPSHOT_INVALID / INSERT 0
- Q94: 동일 entity_id, INDUSTRY→CONSTRUCTION sector 변경 → QUOTE_SNAPSHOT_INVALID / INSERT 0
- Q95: 동일 entity_id, INDUSTRY→BUILDING (entity_type 동일, sector 상이) → QUOTE_SNAPSHOT_INVALID / INSERT 0
- Q96: request sites 역순 → set 비교로 순서 무관 → READY (정상 발행)
- Q97: 단일 site 정확 일치 → READY (정상 발행)

## 18. PREVIOUS REGRESSION

```
Pricing V2 회귀 (8 파일): 508 PASS / 0 FAIL
OBJ09 포함 전체 Pricing: 605 PASS / 0 FAIL  (508 + 97)
```

## 19. EXISTING QUOTE REGRESSION

```
test_member_quotes.py + test_admin_quotes.py + test_member_quote_pdf.py:
206 PASS / 0 FAIL
```

## 20. SOURCE GUARDS

| 항목 | 결과 |
|------|------|
| `calc_quote(` 직접 호출 | NOT_FOUND |
| `resolve_plan(` 직접 호출 | NOT_FOUND |
| `price_master` 직접 조회 | NOT_FOUND |
| 가격 수식 (uplift/vat/term/worker) | NOT_FOUND |
| `contracts` write | NOT_FOUND |
| `subscriptions` write | NOT_FOUND |
| `payments` write | NOT_FOUND |
| `send_slack` | NOT_FOUND |

## 21. PRODUCTION MUTATION

```
Production quotes INSERT = 0
Production UPDATE = 0
Production DELETE = 0
DDL = 0
```

## 22. FILES CHANGED

Created:
- `schemas/saas_quote_v2.py`
- `services/saas_quote_v2.py`
- `tests/test_saas_quote_v2.py`
- `docs/2026-09-28_TAI_SAFE_PRICING_V2_BE_OBJ09_EVIDENCE.md`

Modified:
- `routers/member_quotes.py` (POST /v2/issue 추가)

PATCH1 Modified:
- `services/saas_quote_v2.py`
  - PATCH-A: `calc.status != "READY"` 검증 추가 (model_validate 직후)
  - PATCH-B: `_SECTOR_ENTITY_TYPE` import + `_validate_snapshot_against_request`에 site identity/sector set 교차검증 추가
- `tests/test_saas_quote_v2.py`: Q91-Q97 추가 (90→97)

## 23. NOT_FOUND

- V1 `tier_code` 기반 단가 계산: NOT_FOUND in V2 service
- `saas_pricing_composer_v2` 직접 import: NOT_FOUND in quote service
- CUSTOM product_tier 자동 견적 INSERT: NOT_FOUND (gate에서 차단)

## 24. UNVERIFIED

- Live DB에서 RLS policy 내용 실측 (기존 WO 실측 내용 신뢰)
- Production quotes INSERT → GET list 확인 (E2E — 이번 단계 불필요)

## 25. GPT REVIEW REQUIRED
