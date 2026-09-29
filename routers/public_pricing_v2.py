"""Public SaaS Pricing Preview V2 Router.

POST /public/pricing/v2/preview — 공개 가격 Preview (인증 불필요).

Production DB READ   = price_master only (via pricing_resolver_svc)
Production DB WRITE  = 0
Contract write       = 0
Payment              = 0
"""
from fastapi import APIRouter, HTTPException

from db.supabase_client import get_supabase
from schemas.saas_pricing_preview_v2 import (
    SaasPricingPreviewRequestV2,
    SaasPricingPreviewResponseV2,
)
from services.saas_pricing_preview_v2 import (
    SaasPricingPreviewError,
    preview_saas_price_v2,
)

router = APIRouter(
    prefix="/public/pricing/v2",
    tags=["공개 가격 V2"],
)

_CLIENT_ERROR_CODES = frozenset({
    "INVALID_SELECTION",
    "STANDARD_SITE_REQUIRED",
    "DUPLICATE_SITE",
})

_SERVER_ERROR_CODES = frozenset({
    "BASE_PRICE_NOT_FOUND",
    "INVALID_BASE_PRICE_ROW",
})


@router.post("/preview", response_model=SaasPricingPreviewResponseV2)
def preview_pricing(request: SaasPricingPreviewRequestV2):
    """SaaS 구독 가격 Preview.

    - 인증 불필요
    - price_master READ only (pricing_resolver_svc 경유)
    - Contract / Quote / Payment 생성 없음
    """
    try:
        supabase = get_supabase()
        return preview_saas_price_v2(supabase, request)
    except SaasPricingPreviewError as exc:
        if exc.code in _CLIENT_ERROR_CODES:
            raise HTTPException(
                status_code=422,
                detail={"code": exc.code, "message": exc.message},
            )
        if exc.code in _SERVER_ERROR_CODES:
            raise HTTPException(
                status_code=503,
                detail={"code": exc.code, "message": exc.message},
            )
        raise HTTPException(status_code=500, detail={"code": exc.code})
    except Exception:
        raise HTTPException(status_code=503, detail={"code": "INTERNAL_ERROR"})
