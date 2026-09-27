"""TAI Safe SaaS Pricing V2 — Commercial Domain Contract.

이 모듈은 데이터 구조와 validation 계약만 정의한다.
- 가격 계산 없음
- DB lookup 없음
- Runtime wiring 없음
- API endpoint 없음
- Legacy plan_code mapping 없음
"""
from __future__ import annotations

from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

# ── Schema Version ─────────────────────────────────────────────────────────────

SCHEMA_VERSION = "SAAS_PRICING_V2"

# ── Domain Value Enumerations ──────────────────────────────────────────────────

ProductTier = Literal["MANAGER", "FIELD"]
PricingMode = Literal["STANDARD", "CUSTOM"]
SaasSector = Literal["INDUSTRY", "BUILDING", "CONSTRUCTION"]
EntityType = Literal["factory", "site"]

VALID_TERM_MONTHS: frozenset[int] = frozenset({1, 3, 6, 9, 12})

# Sector → expected EntityType canonical mapping
_SECTOR_ENTITY_MAP: dict[str, EntityType] = {
    "INDUSTRY":     "factory",
    "BUILDING":     "factory",
    "CONSTRUCTION": "site",
}


# ── Commercial Selection ───────────────────────────────────────────────────────

class SaasCommercialSelection(BaseModel):
    """고객이 선택한 상품 조합 (가격 계산 전 입력 계약)."""

    product_tier: ProductTier
    pricing_mode: PricingMode
    worker_capacity: int
    term_months: int

    @field_validator("worker_capacity")
    @classmethod
    def _worker_capacity_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("worker_capacity는 0 이상이어야 합니다.")
        return v

    @field_validator("term_months")
    @classmethod
    def _term_months_allowed(cls, v: int) -> int:
        if v not in VALID_TERM_MONTHS:
            raise ValueError(f"term_months는 {sorted(VALID_TERM_MONTHS)} 중 하나여야 합니다.")
        return v

    @model_validator(mode="after")
    def _manager_no_workers(self) -> "SaasCommercialSelection":
        if self.product_tier == "MANAGER" and self.worker_capacity != 0:
            raise ValueError("MANAGER tier는 worker_capacity가 0이어야 합니다.")
        return self


# ── Site Scope ─────────────────────────────────────────────────────────────────

class SaasSiteScope(BaseModel):
    """계약 대상 사업장 범위 및 가격 스냅샷 컨테이너."""

    entity_type: EntityType
    entity_id: UUID
    sector: SaasSector
    base_band_code: str
    base_amount: int
    is_primary: bool
    applied_rate_bps: int
    final_site_amount: int

    @field_validator("base_amount", "final_site_amount")
    @classmethod
    def _amount_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("금액은 0 이상 정수여야 합니다.")
        return v

    @field_validator("applied_rate_bps")
    @classmethod
    def _rate_bps_range(cls, v: int) -> int:
        if not (0 <= v <= 10000):
            raise ValueError("applied_rate_bps는 0~10000 범위여야 합니다.")
        return v

    @model_validator(mode="after")
    def _entity_sector_match(self) -> "SaasSiteScope":
        expected = _SECTOR_ENTITY_MAP.get(self.sector)
        if self.entity_type != expected:
            raise ValueError(
                f"sector={self.sector}에는 entity_type='{expected}'이어야 합니다. "
                f"(받은 값: '{self.entity_type}')"
            )
        return self


# ── Worker Bracket ─────────────────────────────────────────────────────────────

class SaasWorkerBracketLine(BaseModel):
    """단위 작업자 구간 스냅샷 한 줄."""

    range_from: int
    range_to: Optional[int]
    unit_rate: int
    units: int
    amount: int

    @field_validator("range_from")
    @classmethod
    def _range_from_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("range_from은 1 이상이어야 합니다.")
        return v

    @field_validator("unit_rate", "units", "amount")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("unit_rate, units, amount는 0 이상이어야 합니다.")
        return v


# ── Worker Pricing Snapshot ────────────────────────────────────────────────────

class SaasWorkerPricingSnapshot(BaseModel):
    """작업자 선불 용량 및 요금 스냅샷."""

    capacity: int
    amount: int
    brackets: List[SaasWorkerBracketLine]

    @field_validator("capacity", "amount")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("capacity, amount는 0 이상이어야 합니다.")
        return v


# ── Full Pricing Snapshot V2 ───────────────────────────────────────────────────

class SaasPricingSnapshotV2(BaseModel):
    """계약 시점 불변 가격 스냅샷 V2."""

    schema_version: str
    policy_version: str

    product_tier: ProductTier
    pricing_mode: PricingMode

    sites: List[SaasSiteScope]
    worker: SaasWorkerPricingSnapshot

    term_months: int
    term_discount_rate_bps: int

    monthly_supply_amount: int
    prepaid_supply_amount: int

    vat_rate_bps: int
    vat_amount: int
    total_amount: int

    @field_validator("term_months")
    @classmethod
    def _term_months_allowed(cls, v: int) -> int:
        if v not in VALID_TERM_MONTHS:
            raise ValueError(f"term_months는 {sorted(VALID_TERM_MONTHS)} 중 하나여야 합니다.")
        return v

    @field_validator(
        "term_discount_rate_bps",
        "monthly_supply_amount",
        "prepaid_supply_amount",
        "vat_rate_bps",
        "vat_amount",
        "total_amount",
    )
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("금액 및 rate는 0 이상이어야 합니다.")
        return v

    @field_validator("schema_version")
    @classmethod
    def _schema_version_canonical(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(f"schema_version은 '{SCHEMA_VERSION}'이어야 합니다.")
        return v
