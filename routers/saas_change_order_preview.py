"""POST /me/saas/change-orders/preview — 계약 변경 예상 견적 조회.

WO-SITE-SCOPE-CHANGE-ORDER-PREVIEW-CONTRACT-005

DB WRITE = 0 / PAYMENT = 0
인증: get_current_user(Bearer). 소유권: services.company_scope.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, field_validator

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from schemas.saas_pricing_v2 import ProductTier, SaasSector
from services.company_scope import require_company_id
from services.saas_change_order_runtime_v2 import (
    SaasChangeOrderRuntimeError,
    resolve_change_order_preview_v2,
)
from services.saas_pricing_composer_v2 import SaasSitePricingInput
from services.saas_pricing_preview_v2 import SaasPricingPreviewError, _call_resolver

router = APIRouter(prefix="/me/saas", tags=["saas-change-order"])

_SECTOR_ENTITY_TYPE: dict[str, str] = {
    "INDUSTRY":     "factory",
    "BUILDING":     "factory",
    "CONSTRUCTION": "site",
}

_RUNTIME_TO_HTTP: dict[str, int] = {
    "NO_ACTIVE_SAAS_CONTRACT":               404,
    "AMBIGUOUS_ACTIVE_SAAS_CONTRACT":        409,
    "CURRENT_CV_NOT_FOUND":                  422,
    "CURRENT_CV_AMBIGUOUS":                  409,
    "CHANGE_ORDER_POLICY_VERSION_UNAVAILABLE": 422,
    "CHANGE_ORDER_PRICING_ERROR":            422,
    "CHANGE_ORDER_DOMAIN_ERROR":             422,
}


# ── Request Schema ────────────────────────────────────────────────────────────

class SaasChangeOrderPreviewSiteV2(BaseModel):
    """변경 목표 사업장 요청."""

    model_config = ConfigDict(extra="forbid")

    entity_id: UUID
    sector: SaasSector
    criteria_value: Union[StrictInt, StrictFloat]

    @field_validator("criteria_value")
    @classmethod
    def _criteria_non_negative(cls, v: Union[int, float]) -> Union[int, float]:
        if v < 0:
            raise ValueError("criteria_value는 0 이상이어야 합니다.")
        return v


class SaasChangeOrderPreviewRequestV2(BaseModel):
    """계약 변경 예상 견적 요청.

    sites = 변경 후 전체 사업장 목록 (현재 + 신규).
    가격 권위값 포함 금지: base_amount / base_band_code / pricing_mode / policy_version.
    """

    model_config = ConfigDict(extra="forbid")

    product_tier: ProductTier
    worker_capacity: StrictInt
    payment_months: StrictInt
    sites: List[SaasChangeOrderPreviewSiteV2]
    requested_effective_at: datetime

    @field_validator("worker_capacity")
    @classmethod
    def _worker_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("worker_capacity는 0 이상이어야 합니다.")
        return v

    @field_validator("payment_months")
    @classmethod
    def _payment_months_check(cls, v: int) -> int:
        from schemas.saas_pricing_v2 import VALID_PAYMENT_MONTHS
        if v not in VALID_PAYMENT_MONTHS:
            raise ValueError(f"payment_months는 {sorted(VALID_PAYMENT_MONTHS)} 중 하나여야 합니다.")
        return v


# ── Auth helper ───────────────────────────────────────────────────────────────

def _require_member_company(current: dict, supabase) -> str:
    cid = require_company_id(current, supabase)
    if not cid:
        raise HTTPException(status_code=403, detail={
            "code": "COMPANY_REQUIRED",
            "message": "회사 등록이 필요합니다.",
        })
    return cid


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/change-orders/preview")
def preview_change_order(
    body: SaasChangeOrderPreviewRequestV2,
    current: dict = Depends(get_current_user),
):
    """계약 변경 예상 Proposal 조회. DB WRITE = 0, PAYMENT = 0."""
    supabase = get_supabase()
    company_id = _require_member_company(current, supabase)

    pricing_mode = "CUSTOM" if body.product_tier == "CUSTOM" else "STANDARD"

    from schemas.saas_pricing_v2 import SaasCommercialSelection
    try:
        target_selection = SaasCommercialSelection(
            product_tier=body.product_tier,
            pricing_mode=pricing_mode,
            worker_capacity=body.worker_capacity,
            payment_months=body.payment_months,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_SELECTION",
            "message": str(exc),
        })

    # Resolve target sites via price_master
    target_sites: List[SaasSitePricingInput] = []
    if body.product_tier != "CUSTOM":
        for site in body.sites:
            try:
                data = _call_resolver(supabase, site.sector, site.criteria_value)
            except SaasPricingPreviewError as exc:
                raise HTTPException(status_code=422, detail={
                    "code": exc.code,
                    "message": exc.message,
                })
            entity_type = _SECTOR_ENTITY_TYPE[site.sector]
            target_sites.append(SaasSitePricingInput(
                entity_type=entity_type,
                entity_id=site.entity_id,
                sector=site.sector,
                base_band_code=data["tier_code"],
                base_amount=int(data["amount"]),
            ))

    try:
        proposal = resolve_change_order_preview_v2(
            supabase=supabase,
            company_id=company_id,
            target_selection=target_selection,
            target_sites=target_sites,
            requested_effective_at=body.requested_effective_at,
        )
    except SaasChangeOrderRuntimeError as exc:
        status = _RUNTIME_TO_HTTP.get(exc.code, 422)
        detail: dict = {"code": exc.code, "message": exc.message}
        if exc.domain_code:
            detail["domain_code"] = exc.domain_code
        raise HTTPException(status_code=status, detail=detail)

    return {"status": "success", "data": proposal.model_dump(mode="json")}
