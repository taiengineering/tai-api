"""TAI Safe SaaS Change Order Runtime V2 — Change Order Preview Domain Service.

WO-SITE-SCOPE-CHANGE-ORDER-PREVIEW-CONTRACT-005

역할:
  company_id + target_selection + target_sites + requested_effective_at
  → ACTIVE SaaS contract
  → current commercial version (temporal selection)
  → current site scopes
  → SaasContractStorageBundleV2 (model_construct — DB-validated data)
  → target pricing calculation
  → canonical policy version gate
  → evaluate_saas_change_order_v2()
  → SaasChangeOrderProposalV2

금지:
  - DB INSERT / UPDATE / DELETE
  - 결제 실행 (Payment Prepare / PG / 결제 저장)
  - Commercial Version 생성/수정
  - Site Scope 생성/수정
  - datetime.now() 직접 호출
  - superseded_at IS NULL LIMIT 1 shortcut
  - pricing_mode 클라이언트 주입
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from schemas.saas_change_order_v2 import SaasChangeOrderProposalV2
from schemas.saas_commercial_fit_v2 import SaasComplianceBandCatalogEntryV2
from schemas.saas_contract_commercial_v2 import (
    COMMERCIAL_STORAGE_SCHEMA_VERSION,
    SaasContractCommercialVersionV2,
    SaasContractSiteScopeV2,
    SaasContractStorageBundleV2,
)
from schemas.saas_pricing_policy_v2 import (
    PRICING_POLICY_VERSION,
    SaasPricingPolicyV2,
    get_canonical_pricing_policy_v2,
)
from schemas.saas_pricing_v2 import SaasCommercialSelection, SaasPricingSnapshotV2
from services.saas_change_order_v2 import SaasChangeOrderError, evaluate_saas_change_order_v2
from services.saas_commercial_version_time_v2 import (
    TemporalVersionError,
    select_effective_commercial_version_v2,
)
from services.saas_pricing_composer_v2 import (
    SaasPricingCalculationResult,
    SaasSitePricingInput,
    calculate_saas_price_v2,
)


# ── Domain Error ──────────────────────────────────────────────────────────────

class SaasChangeOrderRuntimeError(Exception):
    """Change Order Preview Runtime domain error (fail-closed).

    code values:
      NO_ACTIVE_SAAS_CONTRACT          — company_id에 활성 SaaS 계약 없음
      AMBIGUOUS_ACTIVE_SAAS_CONTRACT   — 활성 SaaS 계약 2건 이상
      CURRENT_CV_NOT_FOUND             — as_of 시점 effective CV 없음
      CURRENT_CV_AMBIGUOUS             — as_of 시점 effective CV 2건 이상
      CHANGE_ORDER_POLICY_VERSION_UNAVAILABLE
                                       — current CV policy_version != canonical
      CHANGE_ORDER_PRICING_ERROR       — target pricing 계산 실패
      CHANGE_ORDER_DOMAIN_ERROR        — evaluate_saas_change_order_v2 오류 (code 포함)
    """

    def __init__(self, code: str, message: str = "", domain_code: Optional[str] = None) -> None:
        self.code = code
        self.domain_code = domain_code  # wrapped SaasChangeOrderError.code if applicable
        self.message = message or code
        super().__init__(self.message)


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _fetch_active_saas_contracts(supabase, company_id: str) -> List[dict]:
    res = (
        supabase.table("contracts")
        .select("id, company_id, service_type, status_code")
        .eq("company_id", company_id)
        .eq("service_type", "SAAS")
        .eq("status_code", "ACTIVE")
        .eq("is_active", True)
        .execute()
    )
    return res.data or []


def _fetch_all_cvs(supabase, contract_id: str) -> List[dict]:
    res = (
        supabase.table("saas_contract_commercial_versions")
        .select("*")
        .eq("contract_id", contract_id)
        .execute()
    )
    return res.data or []


def _fetch_current_site_scopes(supabase, commercial_version_id: str) -> List[dict]:
    res = (
        supabase.table("saas_contract_site_scopes")
        .select("entity_type, entity_id, sector, base_band_code")
        .eq("commercial_version_id", commercial_version_id)
        .execute()
    )
    return res.data or []


def _build_band_catalog_from_price_master(supabase) -> List[SaasComplianceBandCatalogEntryV2]:
    """price_master SAAS 활성 행 → SaasComplianceBandCatalogEntryV2 목록.

    sort_order는 price_master.sort_order 값을 그대로 사용한다 (≥ 1 보장).
    """
    res = (
        supabase.table("price_master")
        .select("sector, tier_code, sort_order")
        .eq("service_type", "SAAS")
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    rows = res.data or []

    catalog: List[SaasComplianceBandCatalogEntryV2] = []
    seen: set = set()
    for idx, row in enumerate(rows):
        sector = row.get("sector")
        tier_code = row.get("tier_code")
        sort_order_raw = row.get("sort_order")
        if not sector or not tier_code:
            continue
        key = (sector, tier_code)
        if key in seen:
            continue
        seen.add(key)
        sort_order = int(sort_order_raw) if sort_order_raw is not None else (idx + 1)
        if sort_order < 1:
            sort_order = idx + 1
        try:
            catalog.append(SaasComplianceBandCatalogEntryV2(
                sector=sector,
                base_band_code=tier_code,
                sort_order=sort_order,
            ))
        except Exception:
            continue
    return catalog


def _build_bundle(current_cv_row: dict, site_scope_rows: List[dict]) -> SaasContractStorageBundleV2:
    """DB rows → SaasContractStorageBundleV2.

    model_construct() 사용 — DB 저장 시 이미 검증됐으므로 재검증 불필요.
    pricing_snapshot JSONB → SaasPricingSnapshotV2 파싱.
    """
    snap_raw = current_cv_row.get("pricing_snapshot")
    pricing_snapshot: Optional[SaasPricingSnapshotV2] = None
    if snap_raw is not None:
        pricing_snapshot = SaasPricingSnapshotV2.model_validate(snap_raw)

    cv_model = SaasContractCommercialVersionV2.model_construct(
        commercial_schema_version=(
            current_cv_row.get("commercial_schema_version")
            or COMMERCIAL_STORAGE_SCHEMA_VERSION
        ),
        contract_id=uuid.UUID(str(current_cv_row["contract_id"])),
        version_no=int(current_cv_row["version_no"]),
        product_tier=current_cv_row["product_tier"],
        pricing_mode=current_cv_row["pricing_mode"],
        worker_capacity=int(current_cv_row.get("worker_capacity") or 0),
        payment_months=int(current_cv_row["payment_months"]),
        pricing_result_status=current_cv_row.get("pricing_result_status") or "READY",
        pricing_policy_version=current_cv_row.get("pricing_policy_version"),
        pricing_snapshot=pricing_snapshot,
        effective_from=current_cv_row["effective_from"],
        superseded_at=current_cv_row.get("superseded_at"),
        created_by=None,
    )

    site_scopes = [
        SaasContractSiteScopeV2.model_construct(
            entity_type=row["entity_type"],
            entity_id=uuid.UUID(str(row["entity_id"])),
            sector=row["sector"],
            base_band_code=row.get("base_band_code"),
        )
        for row in site_scope_rows
    ]

    return SaasContractStorageBundleV2.model_construct(
        commercial_version=cv_model,
        site_scopes=site_scopes,
    )


# ── Public Entry Point ────────────────────────────────────────────────────────

def resolve_change_order_preview_v2(
    supabase,
    company_id: str,
    target_selection: SaasCommercialSelection,
    target_sites: List[SaasSitePricingInput],
    requested_effective_at: datetime,
    policy: Optional[SaasPricingPolicyV2] = None,
) -> SaasChangeOrderProposalV2:
    """Company의 현재 계약 대비 변경 예상 Proposal을 반환한다.

    DB Read:  contracts + saas_contract_commercial_versions
              + saas_contract_site_scopes + price_master
    DB Write: 0
    Payment:  0

    Raises:
      SaasChangeOrderRuntimeError(NO_ACTIVE_SAAS_CONTRACT)
      SaasChangeOrderRuntimeError(AMBIGUOUS_ACTIVE_SAAS_CONTRACT)
      SaasChangeOrderRuntimeError(CURRENT_CV_NOT_FOUND)
      SaasChangeOrderRuntimeError(CURRENT_CV_AMBIGUOUS)
      SaasChangeOrderRuntimeError(CHANGE_ORDER_POLICY_VERSION_UNAVAILABLE)
      SaasChangeOrderRuntimeError(CHANGE_ORDER_PRICING_ERROR)
      SaasChangeOrderRuntimeError(CHANGE_ORDER_DOMAIN_ERROR)
    """
    # Step 1: ACTIVE SaaS contract — exactly 1
    contracts = _fetch_active_saas_contracts(supabase, company_id)
    if not contracts:
        raise SaasChangeOrderRuntimeError(
            "NO_ACTIVE_SAAS_CONTRACT",
            f"company_id={company_id}에 활성 SaaS 계약 없음",
        )
    if len(contracts) > 1:
        raise SaasChangeOrderRuntimeError(
            "AMBIGUOUS_ACTIVE_SAAS_CONTRACT",
            f"company_id={company_id} 활성 SaaS 계약 {len(contracts)}건 — 중복 불허",
        )
    contract_id = str(_get(contracts[0], "id") or "")

    # Step 2: All CVs → temporal selection
    all_cvs = _fetch_all_cvs(supabase, contract_id)
    try:
        current_cv = select_effective_commercial_version_v2(all_cvs, requested_effective_at)
    except TemporalVersionError as exc:
        if exc.code == "TEMPORAL_CURRENT_NOT_FOUND":
            raise SaasChangeOrderRuntimeError(
                "CURRENT_CV_NOT_FOUND",
                f"requested_effective_at={requested_effective_at} 시점 effective CV 없음: {exc}",
            ) from exc
        raise SaasChangeOrderRuntimeError(
            "CURRENT_CV_AMBIGUOUS",
            f"requested_effective_at={requested_effective_at} 시점 effective CV 중복: {exc}",
        ) from exc

    commercial_version_id = str(_get(current_cv, "id") or "")

    # Step 3: Policy version gate — current must match canonical to proceed
    current_policy_version = _get(current_cv, "pricing_policy_version")
    if policy is None:
        policy = get_canonical_pricing_policy_v2()
    canonical_version = policy.policy_version
    if current_policy_version != canonical_version:
        raise SaasChangeOrderRuntimeError(
            "CHANGE_ORDER_POLICY_VERSION_UNAVAILABLE",
            f"current CV policy_version={current_policy_version!r} != "
            f"canonical={canonical_version!r}. "
            f"변경주문은 동일 정책 버전에서만 허용됩니다.",
        )

    # Step 4: Current site scopes
    site_scope_rows = _fetch_current_site_scopes(supabase, commercial_version_id)

    # Step 5: Build SaasContractStorageBundleV2 from DB rows
    current_bundle = _build_bundle(current_cv, site_scope_rows)

    # Step 6: Target pricing calculation
    try:
        target_calc = calculate_saas_price_v2(target_selection, target_sites, policy)
    except Exception as exc:
        raise SaasChangeOrderRuntimeError(
            "CHANGE_ORDER_PRICING_ERROR",
            f"target 가격 계산 실패: {exc}",
        ) from exc

    # Step 7: Band catalog from price_master
    band_catalog = _build_band_catalog_from_price_master(supabase)

    # Step 8: Domain evaluation
    try:
        proposal = evaluate_saas_change_order_v2(
            current_bundle=current_bundle,
            target_selection=target_selection,
            target_calculation_result=target_calc,
            band_catalog=band_catalog,
            requested_effective_at=requested_effective_at,
        )
    except SaasChangeOrderError as exc:
        raise SaasChangeOrderRuntimeError(
            "CHANGE_ORDER_DOMAIN_ERROR",
            f"change order domain error: {exc.code} — {exc.message}",
            domain_code=exc.code,
        ) from exc

    return proposal
