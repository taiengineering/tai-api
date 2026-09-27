"""TAI Safe SaaS Change Order V2 — Input/Output Contract.

이 모듈은 데이터 구조와 validation 계약만 정의한다.
- DB I/O: 0
- 결제 실행: 0
- Proration 계산: 0
- VAT 계산: 0
- Runtime wiring: 0
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional, Tuple
from uuid import UUID

from pydantic import BaseModel

from schemas.saas_pricing_v2 import EntityType, ProductTier, SaasSector

# ── Canonical Type Definitions ────────────────────────────────────────────────

ChangeOrderStatus = Literal[
    "NO_CHANGE",
    "CHANGE_READY",
    "RENEWAL_ONLY",
    "CUSTOM_QUOTE_REQUIRED",
]

ChangeType = Literal[
    "PRODUCT_TIER_UPGRADE",
    "WORKER_CAPACITY_INCREASE",
    "SITE_ADDED",
    "SCALE_BAND_INCREASE",
]

RenewalOnlyType = Literal[
    "PRODUCT_TIER_DECREASE",
    "WORKER_CAPACITY_DECREASE",
    "SITE_REMOVED",
    "SCALE_BAND_DECREASE",
    "TERM_CHANGE",
]

# Canonical orders (§72, §73)
CHANGE_TYPE_ORDER: Tuple[str, ...] = (
    "PRODUCT_TIER_UPGRADE",
    "SITE_ADDED",
    "SCALE_BAND_INCREASE",
    "WORKER_CAPACITY_INCREASE",
)

RENEWAL_ONLY_TYPE_ORDER: Tuple[str, ...] = (
    "PRODUCT_TIER_DECREASE",
    "SITE_REMOVED",
    "SCALE_BAND_DECREASE",
    "WORKER_CAPACITY_DECREASE",
    "TERM_CHANGE",
)


# ── Change Line ───────────────────────────────────────────────────────────────

class SaasCommercialChangeLineV2(BaseModel):
    """단일 상업적 변경 내역."""

    change_type: str  # ChangeType | RenewalOnlyType

    # Site identity (SITE_ADDED / SITE_REMOVED / SCALE_BAND_*)
    entity_type: Optional[EntityType] = None
    entity_id: Optional[UUID] = None
    sector: Optional[SaasSector] = None

    # Tier change
    from_product_tier: Optional[str] = None
    to_product_tier: Optional[str] = None

    # Worker change
    from_worker_capacity: Optional[int] = None
    to_worker_capacity: Optional[int] = None

    # Band change (SCALE_BAND_INCREASE / DECREASE / SITE_ADDED / SITE_REMOVED)
    from_base_band_code: Optional[str] = None
    to_base_band_code: Optional[str] = None
    from_sort_order: Optional[int] = None
    to_sort_order: Optional[int] = None

    # Term change
    from_term_months: Optional[int] = None
    to_term_months: Optional[int] = None


# ── Change Order Proposal ─────────────────────────────────────────────────────

class SaasChangeOrderProposalV2(BaseModel):
    """Change Order 제안 결과.

    결제 금액 / VAT / Proration 포함 금지.
    monthly_supply_delta = 월 기준 상업 Delta만 확정한다.
    """

    status: ChangeOrderStatus

    contract_id: UUID
    current_version_no: int
    proposed_next_version_no: int

    current_product_tier: str
    target_product_tier: str

    current_worker_capacity: int
    target_worker_capacity: int

    current_site_count: int
    target_site_count: Optional[int]

    change_types: List[ChangeType]
    renewal_only_types: List[RenewalOnlyType]
    change_lines: List[SaasCommercialChangeLineV2]

    # Monthly amounts — snapshot 기준 (None if CUSTOM)
    current_monthly_supply_amount: Optional[int]
    target_monthly_supply_amount: Optional[int]

    # Delta — CHANGE_READY: > 0 / NO_CHANGE: 0 / RENEWAL_ONLY: None / CUSTOM: None
    monthly_supply_delta: Optional[int]

    # Prepaid flag
    requires_remaining_term_prepaid: bool

    current_policy_version: Optional[str]
    target_policy_version: Optional[str]

    current_term_months: int
    target_term_months: int

    requested_effective_at: datetime
