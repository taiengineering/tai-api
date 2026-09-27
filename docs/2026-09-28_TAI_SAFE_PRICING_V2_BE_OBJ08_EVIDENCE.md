---
title: "TAI Safe Pricing V2 BE-OBJ08 Evidence"
work_order: WO-PRICING-V2-BE-OBJ08
objective: "Public Pricing Preview API"
author: Claude Code
date: 2026-09-28
status: PASS
---

# TAI Safe Pricing V2 BE-OBJ08 Evidence

## 1. Objective

`POST /public/pricing/v2/preview` 공개 가격 Preview API 구현.
인증 불필요. price_master READ only. Contract/Quote/Payment 생성 없음.

## 2. Execution Anchor

- Base commit: `b6a2cdde`
- OBJ08 commit: `(pending — pre-commit)`
- Branch: `docs/pricing-canonical-20260927`

## 3. New Files

| 파일 | 역할 |
|------|------|
| `schemas/saas_pricing_preview_v2.py` | Request/Response 계약 |
| `services/saas_pricing_preview_v2.py` | Preview 도메인 서비스 |
| `routers/public_pricing_v2.py` | FastAPI 라우터 |
| `tests/test_saas_pricing_preview_v2.py` | 86 테스트 P01-P86 |

## 4. Modified Files

| 파일 | 변경 내용 |
|------|---------|
| `router_registry/public.py` | `routers.public_pricing_v2` 등록 추가 |

## 5. API Contract

```
POST /public/pricing/v2/preview
Request:  product_tier, worker_capacity, term_months, sites[{entity_id, sector, criteria_value}]
Response: status, product_tier, pricing_mode, worker_capacity, term_months, resolved_sites[], calculation, block_reason
```

금지 필드 (클라이언트 입력 불가):
- `pricing_mode`, `base_amount`, `base_band_code`, `tier_code`, `policy_version`

## 6. Preview Status 값

| Status | 조건 |
|--------|------|
| `READY` | price_master 해소 + term_discount_rate_bps 정의 |
| `TERM_DISCOUNT_UNRESOLVED` | price_master 해소 + discount_rate_bps=None |
| `CUSTOM_REQUIRED` | product_tier=CUSTOM |
| `COMPLIANCE_BASE_QUOTE_REQUIRED` | 사업장 amount=0 (Legacy CUSTOM band) |

## 7. Error HTTP Mapping

| code | HTTP |
|------|------|
| INVALID_SELECTION | 422 |
| STANDARD_SITE_REQUIRED | 422 |
| DUPLICATE_SITE | 422 |
| BASE_PRICE_NOT_FOUND | 503 |
| INVALID_BASE_PRICE_ROW | 503 |
| unknown SaasPricingPreviewError | 500 |
| Exception | 503 |

## 8. Service Logic (9-step)

1. Duplicate entity_id check → DUPLICATE_SITE
2. pricing_mode 서버 파생 (CUSTOM/STANDARD)
3. CUSTOM shortcut (resolver 0, composer empty-sites, CUSTOM_REQUIRED)
4. SaasCommercialSelection 생성 → INVALID_SELECTION on fail
5. sites 빈 체크 → STANDARD_SITE_REQUIRED
6. 사업장별 resolver 호출 + row 검증 + amount 변환
7. has_quote_required → COMPLIANCE_BASE_QUOTE_REQUIRED (calculation=None)
8. Composer 호출
9. 상태 매핑 READY/TERM_DISCOUNT_UNRESOLVED/CUSTOM_REQUIRED

## 9. 금지 규칙 준수

- DB 직접 query: 0 (pricing_resolver_svc 경유)
- 가격 수식 service 내 직접 계산: 0
- Contract/Quote/Payment 생성: 0
- DB Write (.insert/.update/.delete/.upsert): 0
- None 기간할인율 임의 0% 처리: 0
- pricing_mode 클라이언트 주입: 0
- V1 tier_upgrade_svc 의존: 0

## 10. Resolver 호출 패턴

```python
import services.pricing_resolver_svc as pricing_resolver_svc
# (not from-import — monkeypatch를 위해 module reference 유지)
result = pricing_resolver_svc.resolve_plan(supabase, "SAAS", sector, criteria_value)
```

## 11. 내부 헬퍼

| 헬퍼 | 역할 |
|------|------|
| `_validate_resolver_row(data, sector)` | tier_code/billing_unit/service_type 검증 |
| `_call_resolver(supabase, sector, criteria_value)` | resolve_plan 호출 + not_found 처리 |
| `_to_int_amount(amount_raw, sector, tier_code)` | amount StrictInt 변환 |

## 12. 테스트 구성 P01-P86

| 구간 | 내용 | 수 |
|------|------|----|
| P01-P05 | Router Contract | 5 |
| P06-P15 | Request Authority (클라이언트 필드 금지) | 10 |
| P16-P21 | Selection Validation | 6 |
| P22-P26 | Site Validation | 5 |
| P27-P30 | Resolver Invocation | 4 |
| P31-P34 | Resolver Failure | 4 |
| P35-P37 | Positive Base Price Flow | 3 |
| P38-P41 | Legacy Compliance Custom | 4 |
| P42-P46 | Product CUSTOM Path | 5 |
| P47-P50 | Composer Integration | 4 |
| P51-P53 | Canonical Policy TERM_DISCOUNT_UNRESOLVED | 3 |
| P54-P56 | No Fake Final Price | 3 |
| P57-P60 | READY (test policy) | 4 |
| P61-P64 | Multi-site | 4 |
| P65-P67 | FIELD Pricing | 3 |
| P68-P72 | Error HTTP Mapping (TestClient) | 5 |
| P73-P74 | Public Error Safety | 2 |
| P75-P79 | Read-only Source Guard | 5 |
| P80-P84 | No Commercial Side Effects | 5 |
| P85-P86 | V1 Guard | 2 |

## 13. 주요 테스트 수정 사항 (디버깅 결과)

두 가지 monkeypatch 대상 오류를 발견하여 수정:

1. **supabase patch 대상**: `"db.supabase_client.get_supabase"` → `"routers.public_pricing_v2.get_supabase"`
   - 원인: router가 `from db.supabase_client import get_supabase` 방식으로 import하므로 module attribute 패치가 로컬 바인딩에 반영되지 않음

2. **canonical policy patch 대상**: `"schemas.saas_pricing_policy_v2.get_canonical_pricing_policy_v2"` → `"services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2"`
   - 원인: composer가 `from schemas.saas_pricing_policy_v2 import get_canonical_pricing_policy_v2`로 import하므로 동일한 이유로 module attribute 패치 무효

## 14. 테스트 실행 결과

```
OBJ08 단독:  86 PASS / 0 FAIL
전체 회귀:  497 PASS / 0 FAIL
  (기존 411 + OBJ08 86 = 497)
```

## 15. Router Registry 등록 확인

```python
# router_registry/public.py
{"module": "routers.public_pricing_v2"},  # WO-PRICING-V2-BE-OBJ08 Preview API
```

## 16. 접근 제한 확인

- 인증 dependency: 없음 (공개 API)
- prefix: `/public/pricing/v2`
- method: POST only

## 17. TERM_DISCOUNT_UNRESOLVED = HTTP 200 확인

정책 정합성: 현재 canonical policy는 모든 term_months에 `discount_rate_bps=None` → 정상 MANAGER/FIELD 호출은 TERM_DISCOUNT_UNRESOLVED 반환. 이는 오류가 아니라 정상 상태 (P51-P53 확인).

## 18. CUSTOM vs COMPLIANCE_BASE_QUOTE_REQUIRED 구분

| 구분 | 조건 | calculation | block_reason |
|------|------|-------------|-------------|
| CUSTOM_REQUIRED | product_tier=CUSTOM | 있음 (빈 sites compose) | CUSTOM_REQUIRED |
| COMPLIANCE_BASE_QUOTE_REQUIRED | resolver amount=0 | None | COMPLIANCE_BASE_QUOTE_REQUIRED |

P46 (distinct statuses) 확인.

## 19. V1 비간섭 확인

- `routers/public_pricing.py`: 변경 없음 (P85)
- `services/pricing_resolver_svc.py`: 변경 없음 (P86)

## 20. 소스 가드 확인

service 코드 내 금지 패턴 부재 확인 (P75-P84):
- `.table(`, `.insert(`, `.update(`, `.delete(`, `.upsert(`
- `contracts`, `subscriptions`, `quote_write`, `payment_svc`, `change_order`

## 21. 다음 단계

BE-OBJ09 Quote Integration — Claude Code는 시작하지 않는다 (WO §111).
