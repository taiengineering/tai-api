"""TAI Safe SaaS Pricing Preview V2 — API Request/Response Contract.

이 모듈은 데이터 구조와 validation 계약만 정의한다.
- DB I/O: 0
- 가격 계산: 0
- Runtime wiring: 0
- base_amount / base_band_code / tier_code 클라이언트 입력 금지
- pricing_mode 클라이언트 입력 금지 (서버 파생)
- policy_version 클라이언트 입력 금지
"""
from __future__ import annotations

from typing import Any, List, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, field_validator

from schemas.saas_pricing_v2 import EntityType, PricingMode, ProductTier, SaasSector

# ── Preview Status ─────────────────────────────────────────────────────────────

PreviewStatus = Literal[
    "READY",
    "TERM_DISCOUNT_UNRESOLVED",
    "CUSTOM_REQUIRED",
    "COMPLIANCE_BASE_QUOTE_REQUIRED",
]


# ── Request ───────────────────────────────────────────────────────────────────

class SaasPricingPreviewSiteRequestV2(BaseModel):
    """단일 사업장 Preview 요청."""

    model_config = ConfigDict(extra="forbid")

    entity_id: UUID
    sector: SaasSector
    criteria_value: Union[StrictInt, StrictFloat]

    @field_validator("criteria_value")
    @classmethod
    def _criteria_value_non_negative(cls, v: Union[int, float]) -> Union[int, float]:
        if v < 0:
            raise ValueError("criteria_value는 0 이상이어야 합니다.")
        return v


class SaasPricingPreviewRequestV2(BaseModel):
    """SaaS 가격 Preview 요청.

    가격 권위값 포함 금지:
    - base_amount / base_band_code / tier_code 없음
    - pricing_mode 없음 (서버 파생)
    - sort_order / monthly_supply_amount 없음
    - policy_version 없음
    """

    model_config = ConfigDict(extra="forbid")

    product_tier: ProductTier
    worker_capacity: StrictInt
    payment_months: StrictInt
    sites: List[SaasPricingPreviewSiteRequestV2]


# ── Response ──────────────────────────────────────────────────────────────────

class SaasPricingPreviewResolvedSiteV2(BaseModel):
    """Resolver가 결정한 사업장 정보."""

    entity_id: UUID
    entity_type: EntityType
    sector: SaasSector
    criteria_value: Union[int, float]
    base_band_code: str
    base_amount: Optional[int]  # None = compliance quote required


class SaasPricingPreviewResponseV2(BaseModel):
    """SaaS 가격 Preview 응답.

    - 결제 금액 없음
    - 잔여기간 청구액 없음
    - TERM_DISCOUNT_UNRESOLVED는 HTTP 200으로 반환
    - calculation = SaasPricingCalculationResult | None
    """

    status: PreviewStatus
    product_tier: ProductTier
    pricing_mode: PricingMode
    worker_capacity: int
    payment_months: int
    resolved_sites: List[SaasPricingPreviewResolvedSiteV2]
    calculation: Optional[Any]  # SaasPricingCalculationResult
    block_reason: Optional[str]
