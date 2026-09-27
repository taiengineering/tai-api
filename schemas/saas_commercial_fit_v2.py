"""TAI Safe SaaS Commercial Fit Gate V2 — Input/Output Contract.

이 모듈은 데이터 구조와 validation 계약만 정의한다.
- DB I/O: 0
- 가격 계산: 0
- Entitlement 판정: 0
- Runtime wiring: 0
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, StrictInt, field_validator, model_validator

from schemas.saas_pricing_v2 import EntityType, SaasSector

# ── Canonical Type Definitions ────────────────────────────────────────────────

CommercialFitStatus = Literal["FIT", "CHANGE_REQUIRED", "CUSTOM_REVIEW_REQUIRED"]
SiteFitStatus = Literal["FIT", "SITE_OUT_OF_SCOPE", "SCALE_BAND_EXCEEDED"]
CommercialFitReasonCode = Literal[
    "SITE_OUT_OF_SCOPE", "SCALE_BAND_EXCEEDED", "WORKER_CAPACITY_EXCEEDED"
]

# Canonical reason code order for aggregated results
REASON_CODE_ORDER: List[str] = [
    "SITE_OUT_OF_SCOPE",
    "SCALE_BAND_EXCEEDED",
    "WORKER_CAPACITY_EXCEEDED",
]

# Sector → expected EntityType canonical mapping
_SECTOR_ENTITY_MAP: Dict[str, str] = {
    "INDUSTRY":     "factory",
    "BUILDING":     "factory",
    "CONSTRUCTION": "site",
}


# ── Input: Actual Site ────────────────────────────────────────────────────────

class SaasActualCommercialSiteV2(BaseModel):
    """현재 실제 사용 중인 사업장. required_base_band_code는 Resolver가 이미 확정한 값."""

    entity_type: EntityType
    entity_id: UUID
    sector: SaasSector
    required_base_band_code: str

    @field_validator("required_base_band_code")
    @classmethod
    def _band_code_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("required_base_band_code는 빈 문자열일 수 없습니다.")
        return v

    @model_validator(mode="after")
    def _entity_sector_match(self) -> "SaasActualCommercialSiteV2":
        expected = _SECTOR_ENTITY_MAP.get(self.sector)
        if self.entity_type != expected:
            raise ValueError(
                f"sector={self.sector}에는 entity_type='{expected}'이어야 합니다. "
                f"(받은 값: '{self.entity_type}')"
            )
        return self


# ── Input: Band Catalog Entry ─────────────────────────────────────────────────

class SaasComplianceBandCatalogEntryV2(BaseModel):
    """규모 Band 비교를 위한 Catalog 항목. sort_order로만 비교한다."""

    sector: SaasSector
    base_band_code: str
    sort_order: StrictInt

    @field_validator("base_band_code")
    @classmethod
    def _band_code_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("base_band_code는 빈 문자열일 수 없습니다.")
        return v

    @field_validator("sort_order")
    @classmethod
    def _sort_order_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("sort_order는 1 이상이어야 합니다.")
        return v


# ── Input: Actual Commercial State ───────────────────────────────────────────

class SaasCommercialActualStateV2(BaseModel):
    """현재 실제 상업적 사용 상태. as_of는 caller가 명시적으로 전달한다."""

    sites: List[SaasActualCommercialSiteV2]
    actual_worker_count: StrictInt
    as_of: datetime

    @field_validator("actual_worker_count")
    @classmethod
    def _worker_count_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("actual_worker_count는 0 이상이어야 합니다.")
        return v


# ── Output: Per-Site Fit Result ───────────────────────────────────────────────

class SaasCommercialSiteFitResultV2(BaseModel):
    """사업장별 Commercial Fit 판정 결과."""

    entity_type: EntityType
    entity_id: UUID
    sector: SaasSector

    status: SiteFitStatus

    contracted_base_band_code: Optional[str]
    required_base_band_code: str

    contracted_sort_order: Optional[int]
    required_sort_order: int

    reason_code: Optional[CommercialFitReasonCode]


# ── Output: Overall Fit Result ────────────────────────────────────────────────

class SaasCommercialFitResultV2(BaseModel):
    """전체 Commercial Fit 판정 결과.

    Entitlement 판정 포함 금지. 가격/금액 포함 금지.
    """

    status: CommercialFitStatus

    contract_id: UUID
    commercial_version_no: int
    product_tier: str

    contracted_site_count: int
    actual_site_count: int

    contracted_worker_capacity: int
    actual_worker_count: int

    site_results: List[SaasCommercialSiteFitResultV2]
    reason_codes: List[CommercialFitReasonCode]
