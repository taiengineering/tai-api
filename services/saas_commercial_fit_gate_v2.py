"""TAI Safe SaaS Commercial Fit Gate V2 — Pure Domain Gate.

판정 대상:
  1. 계약된 사업장 Scope 안인가
  2. 현재 사업장 규모가 계약 Compliance Base Band 안인가
  3. 현재 현장참여 인원이 계약 Worker Capacity 안인가

금지:
  - DB I/O
  - 가격 계산 (amount / delta / VAT / payment)
  - Entitlement 판정
  - datetime.now() 직접 호출 (as_of를 caller가 전달)
  - V1 tier_payment_gate_svc 의존
  - Router wiring
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from schemas.saas_commercial_fit_v2 import (
    REASON_CODE_ORDER,
    CommercialFitReasonCode,
    SaasCommercialActualStateV2,
    SaasCommercialFitResultV2,
    SaasCommercialSiteFitResultV2,
    SaasComplianceBandCatalogEntryV2,
)
from schemas.saas_contract_commercial_v2 import SaasContractStorageBundleV2
from services.saas_commercial_version_time_v2 import is_commercial_version_effective_at_v2


# ── Gate Error ────────────────────────────────────────────────────────────────

class SaasCommercialFitGateError(Exception):
    """Commercial Fit Gate domain invariant violation.

    code values:
      NON_CURRENT_COMMERCIAL_VERSION
      COMMERCIAL_VERSION_NOT_EFFECTIVE
      DUPLICATE_ACTUAL_SITE
      SITE_CONTEXT_MISMATCH
      BAND_CATALOG_ENTRY_NOT_FOUND
      DUPLICATE_BAND_CATALOG_ENTRY
      AMBIGUOUS_BAND_ORDER
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Gate Entry Point ──────────────────────────────────────────────────────────

def evaluate_saas_commercial_fit_v2(
    contract_bundle: SaasContractStorageBundleV2,
    actual_state: SaasCommercialActualStateV2,
    band_catalog: List[SaasComplianceBandCatalogEntryV2],
) -> SaasCommercialFitResultV2:
    """현재 실제 사용상태가 Commercial Contract 범위 안에 있는지 판정.

    입력 objects를 mutate하지 않는다.
    datetime.now() 사용 금지 — actual_state.as_of를 사용한다.
    """
    cv = contract_bundle.commercial_version
    as_of = actual_state.as_of

    # ── Step 1+2: Temporal version check ─────────────────────────────────────
    # Interval: [effective_from, superseded_at)
    # future superseded_at (as_of < superseded_at) = still effective.
    if not is_commercial_version_effective_at_v2(cv, as_of):
        if cv.effective_from > as_of:
            raise SaasCommercialFitGateError(
                "COMMERCIAL_VERSION_NOT_EFFECTIVE",
                f"contract_id={cv.contract_id} version_no={cv.version_no}: "
                f"effective_from={cv.effective_from} > as_of={as_of}",
            )
        raise SaasCommercialFitGateError(
            "NON_CURRENT_COMMERCIAL_VERSION",
            f"contract_id={cv.contract_id} version_no={cv.version_no}: "
            f"as_of={as_of} >= superseded_at={cv.superseded_at} — 이미 supersede된 Version입니다.",
        )

    # ── Step 3: CUSTOM → immediate result ────────────────────────────────────
    if cv.product_tier == "CUSTOM":
        return SaasCommercialFitResultV2(
            status="CUSTOM_REVIEW_REQUIRED",
            contract_id=cv.contract_id,
            commercial_version_no=cv.version_no,
            product_tier="CUSTOM",
            contracted_site_count=len(contract_bundle.site_scopes),
            actual_site_count=len(actual_state.sites),
            contracted_worker_capacity=cv.worker_capacity,
            actual_worker_count=actual_state.actual_worker_count,
            site_results=[],
            reason_codes=[],
        )

    # ── Step 4: Validate band catalog ────────────────────────────────────────
    # (sector, base_band_code) → sort_order
    band_lookup: Dict[Tuple[str, str], int] = {}
    # (sector, sort_order) → base_band_code  — ambiguity detection within same sector
    order_lookup: Dict[Tuple[str, int], str] = {}

    for entry in band_catalog:
        band_key = (entry.sector, entry.base_band_code)
        if band_key in band_lookup:
            raise SaasCommercialFitGateError(
                "DUPLICATE_BAND_CATALOG_ENTRY",
                f"Catalog 중복: sector={entry.sector}, base_band_code={entry.base_band_code}",
            )
        order_key = (entry.sector, entry.sort_order)
        if order_key in order_lookup:
            raise SaasCommercialFitGateError(
                "AMBIGUOUS_BAND_ORDER",
                f"동일 Sector 내 sort_order 중복: sector={entry.sector}, sort_order={entry.sort_order}",
            )
        band_lookup[band_key] = entry.sort_order
        order_lookup[order_key] = entry.base_band_code

    # ── Step 5: Validate actual sites — no duplicates ────────────────────────
    seen_actual: Set[Tuple[str, str]] = set()
    for site in actual_state.sites:
        key = (site.entity_type, str(site.entity_id))
        if key in seen_actual:
            raise SaasCommercialFitGateError(
                "DUPLICATE_ACTUAL_SITE",
                f"Actual 사업장 중복: entity_type={site.entity_type}, entity_id={site.entity_id}",
            )
        seen_actual.add(key)

    # ── Step 6: Build contracted scope map ───────────────────────────────────
    contracted_scope: Dict[Tuple[str, str], object] = {
        (s.entity_type, str(s.entity_id)): s
        for s in contract_bundle.site_scopes
    }

    # ── Step 7: Evaluate each actual site (deterministic order) ──────────────
    # sort: sector ASC, entity_type ASC, entity_id ASC
    sorted_actual = sorted(
        actual_state.sites,
        key=lambda s: (s.sector, s.entity_type, str(s.entity_id)),
    )

    site_results: List[SaasCommercialSiteFitResultV2] = []
    active_reasons: Set[str] = set()

    for site in sorted_actual:
        identity_key = (site.entity_type, str(site.entity_id))

        # Resolve required band sort_order from catalog
        req_catalog_key = (site.sector, site.required_base_band_code)
        if req_catalog_key not in band_lookup:
            raise SaasCommercialFitGateError(
                "BAND_CATALOG_ENTRY_NOT_FOUND",
                f"Catalog에 없음: sector={site.sector}, "
                f"base_band_code={site.required_base_band_code}",
            )
        required_sort = band_lookup[req_catalog_key]

        # Site not in contracted scope
        if identity_key not in contracted_scope:
            site_results.append(SaasCommercialSiteFitResultV2(
                entity_type=site.entity_type,
                entity_id=site.entity_id,
                sector=site.sector,
                status="SITE_OUT_OF_SCOPE",
                contracted_base_band_code=None,
                required_base_band_code=site.required_base_band_code,
                contracted_sort_order=None,
                required_sort_order=required_sort,
                reason_code="SITE_OUT_OF_SCOPE",
            ))
            active_reasons.add("SITE_OUT_OF_SCOPE")
            continue

        contracted = contracted_scope[identity_key]

        # Sector mismatch → data integrity error
        if contracted.sector != site.sector:
            raise SaasCommercialFitGateError(
                "SITE_CONTEXT_MISMATCH",
                f"entity_id={site.entity_id}: sector 불일치 "
                f"(contracted={contracted.sector}, actual={site.sector})",
            )

        # Resolve contracted band sort_order
        contracted_bbc: Optional[str] = contracted.base_band_code
        if contracted_bbc is None:
            raise SaasCommercialFitGateError(
                "BAND_CATALOG_ENTRY_NOT_FOUND",
                f"계약 사업장에 base_band_code 없음: entity_id={site.entity_id}",
            )
        contracted_catalog_key = (contracted.sector, contracted_bbc)
        if contracted_catalog_key not in band_lookup:
            raise SaasCommercialFitGateError(
                "BAND_CATALOG_ENTRY_NOT_FOUND",
                f"Catalog에 없음: sector={contracted.sector}, "
                f"base_band_code={contracted_bbc}",
            )
        contracted_sort = band_lookup[contracted_catalog_key]

        # Band comparison — sort_order 기준, 금액 비교 금지
        # FIELD: scale band ≠ commercial pricing axis (249K 고정). evidence 보존, reason 미발행.
        if cv.product_tier == "FIELD" or required_sort <= contracted_sort:
            site_results.append(SaasCommercialSiteFitResultV2(
                entity_type=site.entity_type,
                entity_id=site.entity_id,
                sector=site.sector,
                status="FIT",
                contracted_base_band_code=contracted_bbc,
                required_base_band_code=site.required_base_band_code,
                contracted_sort_order=contracted_sort,
                required_sort_order=required_sort,
                reason_code=None,
            ))
        else:
            site_results.append(SaasCommercialSiteFitResultV2(
                entity_type=site.entity_type,
                entity_id=site.entity_id,
                sector=site.sector,
                status="SCALE_BAND_EXCEEDED",
                contracted_base_band_code=contracted_bbc,
                required_base_band_code=site.required_base_band_code,
                contracted_sort_order=contracted_sort,
                required_sort_order=required_sort,
                reason_code="SCALE_BAND_EXCEEDED",
            ))
            active_reasons.add("SCALE_BAND_EXCEEDED")

    # ── Step 8: Worker capacity check (FIELD 전용 — contract-wide, 1회) ──────
    # MANAGER: worker_capacity=0 은 sentinel. worker axis = commercial fit 미적용.
    if cv.product_tier == "FIELD" and actual_state.actual_worker_count > cv.worker_capacity:
        active_reasons.add("WORKER_CAPACITY_EXCEEDED")

    # ── Step 9: Aggregate — canonical reason code order ──────────────────────
    canonical_reasons: List[CommercialFitReasonCode] = [
        r for r in REASON_CODE_ORDER if r in active_reasons  # type: ignore[misc]
    ]
    overall_status = "CHANGE_REQUIRED" if canonical_reasons else "FIT"

    return SaasCommercialFitResultV2(
        status=overall_status,
        contract_id=cv.contract_id,
        commercial_version_no=cv.version_no,
        product_tier=cv.product_tier,
        contracted_site_count=len(contract_bundle.site_scopes),
        actual_site_count=len(actual_state.sites),
        contracted_worker_capacity=cv.worker_capacity,
        actual_worker_count=actual_state.actual_worker_count,
        site_results=site_results,
        reason_codes=canonical_reasons,
    )
