"""TAI Safe SaaS Pricing Composer V2 — Pure Domain Engine.

- DB access: 0
- API: 0
- Runtime wiring: 0
- Frontend: 0
- price_master 값 하드코딩: 0
"""
from __future__ import annotations

from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, StrictInt, field_validator, model_validator

from schemas.saas_pricing_policy_v2 import SaasPricingPolicyV2, get_canonical_pricing_policy_v2
from schemas.saas_pricing_v2 import (
    SCHEMA_VERSION,
    EntityType,
    SaasCommercialSelection,
    SaasSector,
    SaasSiteScope,
    SaasWorkerBracketLine,
    SaasWorkerPricingSnapshot,
    SaasPricingSnapshotV2,
)

# BE-OBJ01과 동일한 mapping — divergent 정의 금지
_SECTOR_ENTITY_MAP: dict[str, str] = {
    "INDUSTRY":     "factory",
    "BUILDING":     "factory",
    "CONSTRUCTION": "site",
}


# ── Site Pricing Input ─────────────────────────────────────────────────────────

class SaasSitePricingInput(BaseModel):
    """Composer 입력용 사업장. price_master Resolver가 확정해 전달한다."""

    entity_type: EntityType
    entity_id: UUID
    sector: SaasSector
    base_band_code: str
    base_amount: StrictInt

    @field_validator("base_band_code")
    @classmethod
    def _band_code_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("base_band_code는 빈 문자열일 수 없습니다.")
        return v

    @field_validator("base_amount")
    @classmethod
    def _base_amount_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("base_amount는 0보다 커야 합니다.")
        return v

    @model_validator(mode="after")
    def _entity_sector_match(self) -> "SaasSitePricingInput":
        expected = _SECTOR_ENTITY_MAP.get(self.sector)
        if self.entity_type != expected:
            raise ValueError(
                f"sector={self.sector}에는 entity_type='{expected}'이어야 합니다. "
                f"(받은 값: '{self.entity_type}')"
            )
        return self


# ── Calculation Status ─────────────────────────────────────────────────────────

CalculationStatus = Literal["READY", "CUSTOM_REQUIRED", "TERM_DISCOUNT_UNRESOLVED"]


# ── Internal Site Breakdown ────────────────────────────────────────────────────

class SaasSitePricingBreakdown(BaseModel):
    """사업장별 계산 결과 (내부 breakdown). normal_site_amount 포함."""

    entity_type: EntityType
    entity_id: UUID
    sector: SaasSector
    base_band_code: str
    base_amount: int
    normal_site_amount: int
    is_primary: bool
    applied_rate_bps: int
    final_site_amount: int


# ── Calculation Result ─────────────────────────────────────────────────────────

class SaasPricingCalculationResult(BaseModel):
    """가격 계산 결과. status에 따라 일부 필드가 None."""

    status: CalculationStatus
    policy_version: str

    site_breakdown: Optional[List[SaasSitePricingBreakdown]]
    worker_breakdown: Optional[SaasWorkerPricingSnapshot]

    monthly_supply_amount: Optional[int]
    raw_prepaid_supply_amount: Optional[int]

    term_months: int
    term_discount_rate_bps: Optional[int]  # None = TERM_DISCOUNT_UNRESOLVED

    snapshot: Optional[SaasPricingSnapshotV2]
    block_reason: Optional[str]


# ── Domain Exception ───────────────────────────────────────────────────────────

class SaasPricingComposerError(Exception):
    """Composer domain invariant violation."""


# ── Worker Progressive Calculation ────────────────────────────────────────────

def _calculate_worker_pricing(
    capacity: int,
    brackets: list,
) -> SaasWorkerPricingSnapshot:
    """Worker 누진 계산. brackets는 range_from 오름차순 보장됨."""
    if capacity == 0:
        return SaasWorkerPricingSnapshot(capacity=0, amount=0, brackets=[])

    lines: list[SaasWorkerBracketLine] = []
    remaining = capacity

    for bracket in brackets:
        if remaining <= 0:
            break
        if bracket.range_to is None:
            units = remaining
        else:
            bracket_size = bracket.range_to - bracket.range_from + 1
            units = min(remaining, bracket_size)
        if units > 0:
            lines.append(SaasWorkerBracketLine(
                range_from=bracket.range_from,
                range_to=bracket.range_to,
                unit_rate=bracket.unit_rate,
                units=units,
                amount=units * bracket.unit_rate,
            ))
            remaining -= units

    total = sum(line.amount for line in lines)
    return SaasWorkerPricingSnapshot(capacity=capacity, amount=total, brackets=lines)


# ── Main Entry Point ───────────────────────────────────────────────────────────

def calculate_saas_price_v2(
    selection: SaasCommercialSelection,
    sites: List[SaasSitePricingInput],
    policy: Optional[SaasPricingPolicyV2] = None,
) -> SaasPricingCalculationResult:
    """TAI Safe SaaS V2 가격 계산. 입력을 mutate하지 않는다.

    policy=None이면 canonical policy를 생성해 사용한다.
    """
    if policy is None:
        policy = get_canonical_pricing_policy_v2()

    # Step 1: CUSTOM — 자동 가격 계산 불가
    if selection.pricing_mode == "CUSTOM":
        return SaasPricingCalculationResult(
            status="CUSTOM_REQUIRED",
            policy_version=policy.policy_version,
            site_breakdown=None,
            worker_breakdown=None,
            monthly_supply_amount=None,
            raw_prepaid_supply_amount=None,
            term_months=selection.term_months,
            term_discount_rate_bps=None,
            snapshot=None,
            block_reason="pricing_mode=CUSTOM: 자동 가격 계산 불가",
        )

    # Step 2: STANDARD site guard
    if not sites:
        raise SaasPricingComposerError("STANDARD 계산에는 최소 1개의 사업장이 필요합니다.")

    # Step 3: Duplicate site guard — (entity_type, entity_id) canonical identity
    seen: set[tuple] = set()
    for s in sites:
        key = (s.entity_type, str(s.entity_id))
        if key in seen:
            raise SaasPricingComposerError(
                f"중복 사업장: (entity_type={s.entity_type}, entity_id={s.entity_id})"
            )
        seen.add(key)

    # Step 4: Normal site amount — input list를 in-place 수정하지 않음
    site_normals: list[tuple] = []
    for s in sites:
        if selection.product_tier == "MANAGER":
            normal = s.base_amount
        else:  # FIELD: uplift는 policy에서 읽음, 하드코딩 금지
            normal = s.base_amount + policy.field_uplift_amount
        site_normals.append((s, normal))

    # Step 5: Canonical sort → Primary 결정
    sorted_pairs = sorted(
        site_normals,
        key=lambda x: (
            -x[1],                   # normal_site_amount DESC
            x[0].sector,             # sector ASC
            x[0].base_band_code,     # base_band_code ASC
            x[0].entity_type,        # entity_type ASC
            str(x[0].entity_id),     # entity_id ASC (deterministic)
        ),
    )

    # Step 6: Site rate 적용 및 breakdown 생성
    site_breakdowns: list[SaasSitePricingBreakdown] = []
    for i, (s, normal) in enumerate(sorted_pairs):
        is_primary = i == 0
        rate_bps = (
            policy.primary_site_rate_bps if is_primary
            else policy.additional_site_rate_bps
        )
        final_amount = normal * rate_bps // 10000  # integer floor
        site_breakdowns.append(SaasSitePricingBreakdown(
            entity_type=s.entity_type,
            entity_id=s.entity_id,
            sector=s.sector,
            base_band_code=s.base_band_code,
            base_amount=s.base_amount,
            normal_site_amount=normal,
            is_primary=is_primary,
            applied_rate_bps=rate_bps,
            final_site_amount=final_amount,
        ))

    # Step 7: Site monthly total
    site_monthly_total = sum(bd.final_site_amount for bd in site_breakdowns)

    # Step 8: Worker — 계약 전체에 1회, site 수와 무관
    worker_snapshot = _calculate_worker_pricing(
        capacity=selection.worker_capacity,
        brackets=list(policy.worker_brackets),
    )

    # Step 9: Monthly supply
    monthly_supply_amount = site_monthly_total + worker_snapshot.amount

    # Step 10: Raw prepaid
    raw_prepaid_supply_amount = monthly_supply_amount * selection.term_months

    # Step 11: Term discount 조회
    matching = [
        td for td in policy.term_discounts
        if td.term_months == selection.term_months
    ]
    if len(matching) != 1:
        raise SaasPricingComposerError(
            f"term_months={selection.term_months}에 해당하는 discount가 Policy에 없거나 중복입니다. "
            f"(found={len(matching)})"
        )
    term_discount_policy = matching[0]

    # Step 12: None → TERM_DISCOUNT_UNRESOLVED — None을 0으로 처리하지 않는다
    if term_discount_policy.discount_rate_bps is None:
        return SaasPricingCalculationResult(
            status="TERM_DISCOUNT_UNRESOLVED",
            policy_version=policy.policy_version,
            site_breakdown=site_breakdowns,
            worker_breakdown=worker_snapshot,
            monthly_supply_amount=monthly_supply_amount,
            raw_prepaid_supply_amount=raw_prepaid_supply_amount,
            term_months=selection.term_months,
            term_discount_rate_bps=None,
            snapshot=None,
            block_reason="term_discount_rate_bps=None: Owner 미확정, Snapshot 생성 불가",
        )

    # Step 13: READY 계산 — integer floor 일관 적용
    discount_rate_bps = term_discount_policy.discount_rate_bps
    discount_amount = raw_prepaid_supply_amount * discount_rate_bps // 10000
    prepaid_supply_amount = raw_prepaid_supply_amount - discount_amount
    vat_amount = prepaid_supply_amount * policy.vat_rate_bps // 10000
    total_amount = prepaid_supply_amount + vat_amount

    # Step 14: Snapshot용 SaasSiteScope 변환
    site_scopes = [
        SaasSiteScope(
            entity_type=bd.entity_type,
            entity_id=bd.entity_id,
            sector=bd.sector,
            base_band_code=bd.base_band_code,
            base_amount=bd.base_amount,
            is_primary=bd.is_primary,
            applied_rate_bps=bd.applied_rate_bps,
            final_site_amount=bd.final_site_amount,
        )
        for bd in site_breakdowns
    ]

    # Step 15: Snapshot 생성 — READY에서만
    snapshot = SaasPricingSnapshotV2(
        schema_version=SCHEMA_VERSION,
        policy_version=policy.policy_version,
        product_tier=selection.product_tier,
        pricing_mode="STANDARD",
        sites=site_scopes,
        worker=worker_snapshot,
        term_months=selection.term_months,
        term_discount_rate_bps=discount_rate_bps,
        monthly_supply_amount=monthly_supply_amount,
        prepaid_supply_amount=prepaid_supply_amount,
        vat_rate_bps=policy.vat_rate_bps,
        vat_amount=vat_amount,
        total_amount=total_amount,
    )

    return SaasPricingCalculationResult(
        status="READY",
        policy_version=policy.policy_version,
        site_breakdown=site_breakdowns,
        worker_breakdown=worker_snapshot,
        monthly_supply_amount=monthly_supply_amount,
        raw_prepaid_supply_amount=raw_prepaid_supply_amount,
        term_months=selection.term_months,
        term_discount_rate_bps=discount_rate_bps,
        snapshot=snapshot,
        block_reason=None,
    )
