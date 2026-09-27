"""TAI Safe SaaS Change Order V2 — Pure Commercial Change Order Domain.

판정 대상:
  CURRENT CONTRACT SNAPSHOT → TARGET PRICING RESULT → CHANGE DIFF → PROPOSAL

금지:
  - DB I/O
  - 결제 실행 (Payment Prepare / PG 호출 / 결제 저장)
  - 잔여기간 청구액 확정 (Proration / 기간할인 임의계산)
  - VAT 계산
  - contracts / subscriptions mutation
  - V1 tier_upgrade_svc 의존
  - Commercial Fit / Entitlement 호출
  - Router wiring
  - datetime.now() 직접 호출
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from schemas.saas_change_order_v2 import (
    CHANGE_TYPE_ORDER,
    RENEWAL_ONLY_TYPE_ORDER,
    ChangeType,
    RenewalOnlyType,
    SaasChangeOrderProposalV2,
    SaasCommercialChangeLineV2,
)
from schemas.saas_commercial_fit_v2 import SaasComplianceBandCatalogEntryV2
from schemas.saas_contract_commercial_v2 import SaasContractStorageBundleV2
from schemas.saas_pricing_v2 import SaasCommercialSelection
from services.saas_pricing_composer_v2 import SaasPricingCalculationResult


# ── Gate Error ────────────────────────────────────────────────────────────────

class SaasChangeOrderError(Exception):
    """Change Order domain invariant violation.

    code values:
      NON_CURRENT_COMMERCIAL_VERSION
      CHANGE_EFFECTIVE_BEFORE_CURRENT_VERSION
      TARGET_PRICING_NOT_READY
      TARGET_SNAPSHOT_MISMATCH
      POLICY_VERSION_MISMATCH
      BAND_CATALOG_ENTRY_NOT_FOUND
      DUPLICATE_BAND_CATALOG_ENTRY
      AMBIGUOUS_BAND_ORDER
      SITE_CONTEXT_MISMATCH
      INVALID_CHANGE_DELTA
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _canonical_type_list(collected: Set[str], order: Tuple[str, ...]) -> List[str]:
    return [t for t in order if t in collected]


def _custom_quote_proposal(
    cv,
    target_selection: SaasCommercialSelection,
    current_site_count: int,
    requested_effective_at: datetime,
) -> SaasChangeOrderProposalV2:
    return SaasChangeOrderProposalV2(
        status="CUSTOM_QUOTE_REQUIRED",
        contract_id=cv.contract_id,
        current_version_no=cv.version_no,
        proposed_next_version_no=cv.version_no + 1,
        current_product_tier=cv.product_tier,
        target_product_tier=target_selection.product_tier,
        current_worker_capacity=cv.worker_capacity,
        target_worker_capacity=target_selection.worker_capacity,
        current_site_count=current_site_count,
        target_site_count=None,
        change_types=[],
        renewal_only_types=[],
        change_lines=[],
        current_monthly_supply_amount=None,
        target_monthly_supply_amount=None,
        monthly_supply_delta=None,
        requires_remaining_term_prepaid=False,
        current_policy_version=None,
        target_policy_version=None,
        current_term_months=cv.term_months,
        target_term_months=target_selection.term_months,
        requested_effective_at=requested_effective_at,
    )


def _build_band_lookup(
    band_catalog: List[SaasComplianceBandCatalogEntryV2],
) -> Dict[Tuple[str, str], int]:
    """(sector, base_band_code) → sort_order. Validates catalog invariants."""
    band_lookup: Dict[Tuple[str, str], int] = {}
    order_lookup: Dict[Tuple[str, int], str] = {}

    for entry in band_catalog:
        band_key = (entry.sector, entry.base_band_code)
        if band_key in band_lookup:
            raise SaasChangeOrderError(
                "DUPLICATE_BAND_CATALOG_ENTRY",
                f"Catalog 중복: sector={entry.sector}, base_band_code={entry.base_band_code}",
            )
        order_key = (entry.sector, entry.sort_order)
        if order_key in order_lookup:
            raise SaasChangeOrderError(
                "AMBIGUOUS_BAND_ORDER",
                f"동일 Sector 내 sort_order 중복: sector={entry.sector}, sort_order={entry.sort_order}",
            )
        band_lookup[band_key] = entry.sort_order
        order_lookup[order_key] = entry.base_band_code

    return band_lookup


# ── Gate Entry Point ──────────────────────────────────────────────────────────

def evaluate_saas_change_order_v2(
    current_bundle: SaasContractStorageBundleV2,
    target_selection: SaasCommercialSelection,
    target_calculation_result: SaasPricingCalculationResult,
    band_catalog: List[SaasComplianceBandCatalogEntryV2],
    requested_effective_at: datetime,
) -> SaasChangeOrderProposalV2:
    """Current Contract와 Target Pricing 간 Change Order Proposal 생성.

    입력 objects를 mutate하지 않는다.
    월 기준 Commercial Delta만 계산한다.
    잔여기간 청구액 / Proration / VAT 계산 금지.
    """
    cv = current_bundle.commercial_version
    current_site_count = len(current_bundle.site_scopes)

    # ── Step 1: Current version currency ─────────────────────────────────────
    if cv.superseded_at is not None:
        raise SaasChangeOrderError(
            "NON_CURRENT_COMMERCIAL_VERSION",
            f"contract_id={cv.contract_id} version_no={cv.version_no}: "
            f"superseded_at={cv.superseded_at}",
        )

    # ── Step 2: Effective date ────────────────────────────────────────────────
    if requested_effective_at < cv.effective_from:
        raise SaasChangeOrderError(
            "CHANGE_EFFECTIVE_BEFORE_CURRENT_VERSION",
            f"requested_effective_at={requested_effective_at} < "
            f"current effective_from={cv.effective_from}",
        )

    # ── Step 3: CUSTOM current → CUSTOM_QUOTE_REQUIRED ───────────────────────
    if cv.product_tier == "CUSTOM":
        return _custom_quote_proposal(cv, target_selection, current_site_count, requested_effective_at)

    # ── Step 4: CUSTOM target → CUSTOM_QUOTE_REQUIRED ────────────────────────
    if (
        target_selection.product_tier == "CUSTOM"
        or target_calculation_result.status == "CUSTOM_REQUIRED"
    ):
        return _custom_quote_proposal(cv, target_selection, current_site_count, requested_effective_at)

    # ── Step 5: TERM_DISCOUNT_UNRESOLVED ─────────────────────────────────────
    if target_calculation_result.status == "TERM_DISCOUNT_UNRESOLVED":
        raise SaasChangeOrderError(
            "TARGET_PRICING_NOT_READY",
            f"target result status={target_calculation_result.status}",
        )

    # ── Step 6: Target snapshot None ─────────────────────────────────────────
    if target_calculation_result.snapshot is None:
        raise SaasChangeOrderError(
            "TARGET_PRICING_NOT_READY",
            "target result가 READY이지만 snapshot이 None입니다.",
        )

    target_snap = target_calculation_result.snapshot
    current_snap = cv.pricing_snapshot  # STANDARD READY는 항상 non-None

    # ── Step 7: Target selection ↔ snapshot consistency ───────────────────────
    if target_selection.product_tier != target_snap.product_tier:
        raise SaasChangeOrderError(
            "TARGET_SNAPSHOT_MISMATCH",
            f"selection.product_tier={target_selection.product_tier} != "
            f"snapshot.product_tier={target_snap.product_tier}",
        )
    if target_selection.worker_capacity != target_snap.worker.capacity:
        raise SaasChangeOrderError(
            "TARGET_SNAPSHOT_MISMATCH",
            f"selection.worker_capacity={target_selection.worker_capacity} != "
            f"snapshot.worker.capacity={target_snap.worker.capacity}",
        )
    if target_selection.term_months != target_snap.term_months:
        raise SaasChangeOrderError(
            "TARGET_SNAPSHOT_MISMATCH",
            f"selection.term_months={target_selection.term_months} != "
            f"snapshot.term_months={target_snap.term_months}",
        )

    # ── Step 8: Result monthly ↔ snapshot monthly ─────────────────────────────
    if target_calculation_result.monthly_supply_amount != target_snap.monthly_supply_amount:
        raise SaasChangeOrderError(
            "TARGET_SNAPSHOT_MISMATCH",
            f"result.monthly_supply_amount={target_calculation_result.monthly_supply_amount} != "
            f"snapshot.monthly_supply_amount={target_snap.monthly_supply_amount}",
        )

    # ── Step 9: Policy version match ─────────────────────────────────────────
    current_policy_version = current_snap.policy_version  # type: ignore[union-attr]
    target_policy_version = target_snap.policy_version
    if current_policy_version != target_policy_version:
        raise SaasChangeOrderError(
            "POLICY_VERSION_MISMATCH",
            f"current policy_version={current_policy_version} != "
            f"target policy_version={target_policy_version}",
        )

    # ── Step 10: Band catalog validation ─────────────────────────────────────
    band_lookup = _build_band_lookup(band_catalog)

    # ── Step 11: Compare attributes ──────────────────────────────────────────
    expansion_types: Set[str] = set()
    renewal_types: Set[str] = set()
    change_lines: List[SaasCommercialChangeLineV2] = []

    # Tier comparison
    current_tier = cv.product_tier
    target_tier = target_selection.product_tier
    tier_line: Optional[SaasCommercialChangeLineV2] = None
    if current_tier != target_tier:
        if current_tier == "MANAGER" and target_tier == "FIELD":
            expansion_types.add("PRODUCT_TIER_UPGRADE")
            tier_line = SaasCommercialChangeLineV2(
                change_type="PRODUCT_TIER_UPGRADE",
                from_product_tier="MANAGER",
                to_product_tier="FIELD",
            )
        elif current_tier == "FIELD" and target_tier == "MANAGER":
            renewal_types.add("PRODUCT_TIER_DECREASE")
            tier_line = SaasCommercialChangeLineV2(
                change_type="PRODUCT_TIER_DECREASE",
                from_product_tier="FIELD",
                to_product_tier="MANAGER",
            )

    # Term comparison
    current_term = cv.term_months
    target_term = target_selection.term_months
    term_line: Optional[SaasCommercialChangeLineV2] = None
    if current_term != target_term:
        renewal_types.add("TERM_CHANGE")
        term_line = SaasCommercialChangeLineV2(
            change_type="TERM_CHANGE",
            from_term_months=current_term,
            to_term_months=target_term,
        )

    # Worker comparison
    current_workers = cv.worker_capacity
    target_workers = target_selection.worker_capacity
    worker_line: Optional[SaasCommercialChangeLineV2] = None
    if target_workers > current_workers:
        expansion_types.add("WORKER_CAPACITY_INCREASE")
        worker_line = SaasCommercialChangeLineV2(
            change_type="WORKER_CAPACITY_INCREASE",
            from_worker_capacity=current_workers,
            to_worker_capacity=target_workers,
        )
    elif target_workers < current_workers:
        renewal_types.add("WORKER_CAPACITY_DECREASE")
        worker_line = SaasCommercialChangeLineV2(
            change_type="WORKER_CAPACITY_DECREASE",
            from_worker_capacity=current_workers,
            to_worker_capacity=target_workers,
        )

    # Site comparison
    current_site_map: Dict[Tuple[str, str], object] = {
        (s.entity_type, str(s.entity_id)): s for s in current_bundle.site_scopes
    }
    target_site_map: Dict[Tuple[str, str], object] = {
        (s.entity_type, str(s.entity_id)): s for s in target_snap.sites
    }

    cur_keys = set(current_site_map.keys())
    tgt_keys = set(target_site_map.keys())
    added_keys = tgt_keys - cur_keys
    removed_keys = cur_keys - tgt_keys
    common_keys = cur_keys & tgt_keys

    site_lines: List[SaasCommercialChangeLineV2] = []

    def _site_sort_key(k: Tuple[str, str], site_map) -> Tuple[str, str, str]:
        s = site_map[k]
        return (s.sector, k[0], k[1])

    # Added sites (only in target)
    for key in sorted(added_keys, key=lambda k: _site_sort_key(k, target_site_map)):
        tgt_s = target_site_map[key]
        cat_key = (tgt_s.sector, tgt_s.base_band_code)
        if cat_key not in band_lookup:
            raise SaasChangeOrderError(
                "BAND_CATALOG_ENTRY_NOT_FOUND",
                f"Target 사업장 band Catalog 없음: sector={tgt_s.sector}, "
                f"base_band_code={tgt_s.base_band_code}",
            )
        tgt_sort = band_lookup[cat_key]
        expansion_types.add("SITE_ADDED")
        site_lines.append(SaasCommercialChangeLineV2(
            change_type="SITE_ADDED",
            entity_type=tgt_s.entity_type,
            entity_id=tgt_s.entity_id,
            sector=tgt_s.sector,
            to_base_band_code=tgt_s.base_band_code,
            to_sort_order=tgt_sort,
        ))

    # Removed sites (only in current)
    for key in sorted(removed_keys, key=lambda k: _site_sort_key(k, current_site_map)):
        cur_s = current_site_map[key]
        cat_key = (cur_s.sector, cur_s.base_band_code)
        if cat_key not in band_lookup:
            raise SaasChangeOrderError(
                "BAND_CATALOG_ENTRY_NOT_FOUND",
                f"Current 사업장 band Catalog 없음: sector={cur_s.sector}, "
                f"base_band_code={cur_s.base_band_code}",
            )
        cur_sort = band_lookup[cat_key]
        renewal_types.add("SITE_REMOVED")
        site_lines.append(SaasCommercialChangeLineV2(
            change_type="SITE_REMOVED",
            entity_type=cur_s.entity_type,
            entity_id=cur_s.entity_id,
            sector=cur_s.sector,
            from_base_band_code=cur_s.base_band_code,
            from_sort_order=cur_sort,
        ))

    # Common sites — sector mismatch check + band comparison
    for key in sorted(common_keys, key=lambda k: _site_sort_key(k, current_site_map)):
        cur_s = current_site_map[key]
        tgt_s = target_site_map[key]
        if cur_s.sector != tgt_s.sector:
            raise SaasChangeOrderError(
                "SITE_CONTEXT_MISMATCH",
                f"entity_id={key[1]}: sector 불일치 "
                f"(current={cur_s.sector}, target={tgt_s.sector})",
            )
        cur_cat = (cur_s.sector, cur_s.base_band_code)
        tgt_cat = (tgt_s.sector, tgt_s.base_band_code)
        if cur_cat not in band_lookup:
            raise SaasChangeOrderError(
                "BAND_CATALOG_ENTRY_NOT_FOUND",
                f"Current 사업장 band Catalog 없음: sector={cur_s.sector}, "
                f"base_band_code={cur_s.base_band_code}",
            )
        if tgt_cat not in band_lookup:
            raise SaasChangeOrderError(
                "BAND_CATALOG_ENTRY_NOT_FOUND",
                f"Target 사업장 band Catalog 없음: sector={tgt_s.sector}, "
                f"base_band_code={tgt_s.base_band_code}",
            )
        cur_sort = band_lookup[cur_cat]
        tgt_sort = band_lookup[tgt_cat]
        if tgt_sort > cur_sort:
            expansion_types.add("SCALE_BAND_INCREASE")
            site_lines.append(SaasCommercialChangeLineV2(
                change_type="SCALE_BAND_INCREASE",
                entity_type=cur_s.entity_type,
                entity_id=cur_s.entity_id,
                sector=cur_s.sector,
                from_base_band_code=cur_s.base_band_code,
                to_base_band_code=tgt_s.base_band_code,
                from_sort_order=cur_sort,
                to_sort_order=tgt_sort,
            ))
        elif tgt_sort < cur_sort:
            renewal_types.add("SCALE_BAND_DECREASE")
            site_lines.append(SaasCommercialChangeLineV2(
                change_type="SCALE_BAND_DECREASE",
                entity_type=cur_s.entity_type,
                entity_id=cur_s.entity_id,
                sector=cur_s.sector,
                from_base_band_code=cur_s.base_band_code,
                to_base_band_code=tgt_s.base_band_code,
                from_sort_order=cur_sort,
                to_sort_order=tgt_sort,
            ))

    # Build ordered change_lines: tier first → site lines → worker → term
    if tier_line:
        change_lines.append(tier_line)
    change_lines.extend(site_lines)
    if worker_line:
        change_lines.append(worker_line)
    if term_line:
        change_lines.append(term_line)

    # Canonical type lists
    ordered_change_types: List[ChangeType] = _canonical_type_list(expansion_types, CHANGE_TYPE_ORDER)  # type: ignore[assignment]
    ordered_renewal_types: List[RenewalOnlyType] = _canonical_type_list(renewal_types, RENEWAL_ONLY_TYPE_ORDER)  # type: ignore[assignment]

    current_monthly = current_snap.monthly_supply_amount  # type: ignore[union-attr]
    target_monthly = target_snap.monthly_supply_amount

    # ── Step 12: Status determination ────────────────────────────────────────
    has_expansions = bool(expansion_types)
    has_renewals = bool(renewal_types)

    if not has_expansions and not has_renewals:
        return SaasChangeOrderProposalV2(
            status="NO_CHANGE",
            contract_id=cv.contract_id,
            current_version_no=cv.version_no,
            proposed_next_version_no=cv.version_no + 1,
            current_product_tier=current_tier,
            target_product_tier=target_tier,
            current_worker_capacity=current_workers,
            target_worker_capacity=target_workers,
            current_site_count=current_site_count,
            target_site_count=len(target_snap.sites),
            change_types=[],
            renewal_only_types=[],
            change_lines=[],
            current_monthly_supply_amount=current_monthly,
            target_monthly_supply_amount=target_monthly,
            monthly_supply_delta=0,
            requires_remaining_term_prepaid=False,
            current_policy_version=current_policy_version,
            target_policy_version=target_policy_version,
            current_term_months=current_term,
            target_term_months=target_term,
            requested_effective_at=requested_effective_at,
        )

    if has_renewals:
        return SaasChangeOrderProposalV2(
            status="RENEWAL_ONLY",
            contract_id=cv.contract_id,
            current_version_no=cv.version_no,
            proposed_next_version_no=cv.version_no + 1,
            current_product_tier=current_tier,
            target_product_tier=target_tier,
            current_worker_capacity=current_workers,
            target_worker_capacity=target_workers,
            current_site_count=current_site_count,
            target_site_count=len(target_snap.sites),
            change_types=ordered_change_types,
            renewal_only_types=ordered_renewal_types,
            change_lines=change_lines,
            current_monthly_supply_amount=current_monthly,
            target_monthly_supply_amount=target_monthly,
            monthly_supply_delta=None,
            requires_remaining_term_prepaid=False,
            current_policy_version=current_policy_version,
            target_policy_version=target_policy_version,
            current_term_months=current_term,
            target_term_months=target_term,
            requested_effective_at=requested_effective_at,
        )

    # ── Step 13: CHANGE_READY — delta validation ──────────────────────────────
    delta = target_monthly - current_monthly
    if delta <= 0:
        raise SaasChangeOrderError(
            "INVALID_CHANGE_DELTA",
            f"CHANGE_READY이지만 monthly delta={delta} (0 이하 금지)",
        )

    return SaasChangeOrderProposalV2(
        status="CHANGE_READY",
        contract_id=cv.contract_id,
        current_version_no=cv.version_no,
        proposed_next_version_no=cv.version_no + 1,
        current_product_tier=current_tier,
        target_product_tier=target_tier,
        current_worker_capacity=current_workers,
        target_worker_capacity=target_workers,
        current_site_count=current_site_count,
        target_site_count=len(target_snap.sites),
        change_types=ordered_change_types,
        renewal_only_types=[],
        change_lines=change_lines,
        current_monthly_supply_amount=current_monthly,
        target_monthly_supply_amount=target_monthly,
        monthly_supply_delta=delta,
        requires_remaining_term_prepaid=True,
        current_policy_version=current_policy_version,
        target_policy_version=target_policy_version,
        current_term_months=current_term,
        target_term_months=target_term,
        requested_effective_at=requested_effective_at,
    )
