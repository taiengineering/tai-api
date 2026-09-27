"""TAI Safe SaaS Pricing Preview V2 — Preview Domain Service.

역할:
  Request → Selection → price_master Resolve → SaasSitePricingInput
  → Pricing Composer → Preview Response

금지:
  - DB 직접 query (price_master 직접 참조 금지 — pricing_resolver_svc 경유)
  - 가격 수식 (Site Uplift / Worker 누진 / VAT / 기간할인 계산 금지)
  - Contract / Quote / Payment 생성
  - DB Write
  - None 기간할인율 임의 0% 처리
  - pricing_mode 클라이언트 주입
  - V1 tier_upgrade_svc 의존
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import ValidationError

import services.pricing_resolver_svc as pricing_resolver_svc
from schemas.saas_pricing_preview_v2 import (
    SaasPricingPreviewRequestV2,
    SaasPricingPreviewResolvedSiteV2,
    SaasPricingPreviewResponseV2,
)
from schemas.saas_pricing_v2 import SaasCommercialSelection
from services.saas_pricing_composer_v2 import (
    SaasSitePricingInput,
    calculate_saas_price_v2,
)

# Sector → entity_type (canonical — composer와 동일 규칙, 복제 아님)
_SECTOR_ENTITY_TYPE: dict[str, str] = {
    "INDUSTRY":     "factory",
    "BUILDING":     "factory",
    "CONSTRUCTION": "site",
}


# ── Domain Error ──────────────────────────────────────────────────────────────

class SaasPricingPreviewError(Exception):
    """Preview domain invariant violation.

    code values:
      INVALID_SELECTION         — product_tier / worker_capacity / term_months 조합 오류
      STANDARD_SITE_REQUIRED    — MANAGER/FIELD에 sites 없음
      DUPLICATE_SITE            — 동일 entity_id 중복
      BASE_PRICE_NOT_FOUND      — price_master 미발견
      INVALID_BASE_PRICE_ROW    — price_master row 정합성 오류
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _validate_resolver_row(data: dict, sector: str) -> None:
    """Resolver row 최소 정합성 검증."""
    if not data.get("tier_code"):
        raise SaasPricingPreviewError(
            "INVALID_BASE_PRICE_ROW",
            f"tier_code 없음: sector={sector}",
        )
    if data.get("billing_unit") != "MONTHLY":
        raise SaasPricingPreviewError(
            "INVALID_BASE_PRICE_ROW",
            f"billing_unit=MONTHLY 아님: billing_unit={data.get('billing_unit')}",
        )
    if data.get("service_type") != "SAAS":
        raise SaasPricingPreviewError(
            "INVALID_BASE_PRICE_ROW",
            f"service_type=SAAS 아님: {data.get('service_type')}",
        )


def _call_resolver(supabase, sector: str, criteria_value) -> dict:
    """pricing_resolver_svc.resolve_plan 호출 및 not_found 처리."""
    result = pricing_resolver_svc.resolve_plan(supabase, "SAAS", sector, criteria_value)
    if result.get("status") != "success" or result.get("data") is None:
        raise SaasPricingPreviewError(
            "BASE_PRICE_NOT_FOUND",
            f"sector={sector}, criteria_value={criteria_value}: price_master 미발견",
        )
    return result["data"]


def _to_int_amount(amount_raw, sector: str, tier_code: str) -> int:
    """amount를 StrictInt로 변환. 실패 시 INVALID_BASE_PRICE_ROW."""
    if amount_raw is None:
        raise SaasPricingPreviewError(
            "INVALID_BASE_PRICE_ROW",
            f"amount 없음: sector={sector}, tier_code={tier_code}",
        )
    try:
        amount_int = int(amount_raw)
        if amount_int != amount_raw:
            raise ValueError("non-integer amount")
    except (TypeError, ValueError) as exc:
        raise SaasPricingPreviewError(
            "INVALID_BASE_PRICE_ROW",
            f"amount 정수 변환 실패: {amount_raw}",
        ) from exc
    return amount_int


# ── Gate Entry Point ──────────────────────────────────────────────────────────

def preview_saas_price_v2(
    supabase,
    request: SaasPricingPreviewRequestV2,
) -> SaasPricingPreviewResponseV2:
    """SaaS 가격 Preview 계산.

    입력 objects를 mutate하지 않는다.
    DB Write 0. Contract 생성 0. Payment 0.
    """
    # ── Step 1: Duplicate entity_id check ──────────────────────────────────────
    seen_ids: set = set()
    for s in request.sites:
        sid = str(s.entity_id)
        if sid in seen_ids:
            raise SaasPricingPreviewError(
                "DUPLICATE_SITE",
                f"entity_id={s.entity_id} 중복",
            )
        seen_ids.add(sid)

    # ── Step 2: pricing_mode 서버 파생 ────────────────────────────────────────
    pricing_mode = "CUSTOM" if request.product_tier == "CUSTOM" else "STANDARD"

    # ── Step 3: CUSTOM shortcut (resolver call 0) ─────────────────────────────
    if request.product_tier == "CUSTOM":
        try:
            selection = SaasCommercialSelection(
                product_tier="CUSTOM",
                pricing_mode="CUSTOM",
                worker_capacity=0,
                term_months=request.term_months,
            )
        except ValidationError as exc:
            raise SaasPricingPreviewError("INVALID_SELECTION", str(exc)) from exc

        calc = calculate_saas_price_v2(selection, [])
        return SaasPricingPreviewResponseV2(
            status="CUSTOM_REQUIRED",
            product_tier="CUSTOM",
            pricing_mode="CUSTOM",
            worker_capacity=request.worker_capacity,
            term_months=request.term_months,
            resolved_sites=[],
            calculation=calc,
            block_reason=calc.block_reason,
        )

    # ── Step 4: SaasCommercialSelection 생성 (MANAGER / FIELD) ────────────────
    try:
        selection = SaasCommercialSelection(
            product_tier=request.product_tier,
            pricing_mode="STANDARD",
            worker_capacity=request.worker_capacity,
            term_months=request.term_months,
        )
    except ValidationError as exc:
        raise SaasPricingPreviewError("INVALID_SELECTION", str(exc)) from exc

    # ── Step 5: 최소 사업장 체크 ──────────────────────────────────────────────
    if not request.sites:
        raise SaasPricingPreviewError(
            "STANDARD_SITE_REQUIRED",
            "MANAGER/FIELD Preview는 최소 1개의 사업장이 필요합니다.",
        )

    # ── Step 6: 사업장별 price_master Resolve ─────────────────────────────────
    resolved_sites: List[SaasPricingPreviewResolvedSiteV2] = []
    composer_inputs: List[SaasSitePricingInput] = []
    has_quote_required = False

    for site in request.sites:
        data = _call_resolver(supabase, site.sector, site.criteria_value)
        _validate_resolver_row(data, site.sector)

        tier_code: str = data["tier_code"]
        entity_type = _SECTOR_ENTITY_TYPE[site.sector]
        amount_int = _to_int_amount(data.get("amount"), site.sector, tier_code)

        if amount_int > 0:
            base_amount: Optional[int] = amount_int
            composer_inputs.append(SaasSitePricingInput(
                entity_type=entity_type,
                entity_id=site.entity_id,
                sector=site.sector,
                base_band_code=tier_code,
                base_amount=amount_int,
            ))
        else:
            base_amount = None
            has_quote_required = True

        resolved_sites.append(SaasPricingPreviewResolvedSiteV2(
            entity_id=site.entity_id,
            entity_type=entity_type,
            sector=site.sector,
            criteria_value=site.criteria_value,
            base_band_code=tier_code,
            base_amount=base_amount,
        ))

    # ── Step 7: Compliance Base quote-required ────────────────────────────────
    if has_quote_required:
        return SaasPricingPreviewResponseV2(
            status="COMPLIANCE_BASE_QUOTE_REQUIRED",
            product_tier=request.product_tier,
            pricing_mode="STANDARD",
            worker_capacity=request.worker_capacity,
            term_months=request.term_months,
            resolved_sites=resolved_sites,
            calculation=None,
            block_reason="COMPLIANCE_BASE_QUOTE_REQUIRED",
        )

    # ── Step 8: Pricing Composer 호출 ─────────────────────────────────────────
    calc = calculate_saas_price_v2(selection, composer_inputs)

    # ── Step 9: 상태 매핑 ─────────────────────────────────────────────────────
    if calc.status == "READY":
        out_status = "READY"
    elif calc.status == "TERM_DISCOUNT_UNRESOLVED":
        out_status = "TERM_DISCOUNT_UNRESOLVED"
    else:
        out_status = "CUSTOM_REQUIRED"

    return SaasPricingPreviewResponseV2(
        status=out_status,
        product_tier=request.product_tier,
        pricing_mode="STANDARD",
        worker_capacity=request.worker_capacity,
        term_months=request.term_months,
        resolved_sites=resolved_sites,
        calculation=calc,
        block_reason=calc.block_reason,
    )
