"""TAI Safe SaaS Commercial Contract Storage Mapper V2 — Pure Domain Mapper.

- DB I/O: 0
- Runtime wiring: 0
- 입력 objects mutate 금지
- STANDARD: Site Scopes는 반드시 snapshot.sites에서 derive
- CUSTOM: pricing_snapshot=None, pricing_policy_version=None
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from schemas.saas_contract_commercial_v2 import (
    COMMERCIAL_STORAGE_SCHEMA_VERSION,
    SaasContractCommercialVersionV2,
    SaasContractSiteScopeV2,
    SaasContractStorageBundleV2,
)
from schemas.saas_pricing_v2 import SaasCommercialSelection
from services.saas_pricing_composer_v2 import SaasPricingCalculationResult


class SaasContractStorageMapperError(Exception):
    """Mapper domain invariant violation."""


def build_standard_contract_storage_bundle_v2(
    contract_id: UUID,
    version_no: int,
    selection: SaasCommercialSelection,
    calculation_result: SaasPricingCalculationResult,
    effective_from: datetime,
    created_by: Optional[UUID] = None,
) -> SaasContractStorageBundleV2:
    """READY SaasPricingCalculationResult를 STANDARD Commercial Storage Bundle로 변환.

    Site Scopes는 calculation_result.snapshot.sites에서 derive한다.
    Caller가 site_scopes를 직접 조립하지 않는다.
    입력 objects를 mutate하지 않는다.
    """
    if calculation_result.status != "READY":
        raise SaasContractStorageMapperError(
            f"STANDARD mapper는 status=READY인 결과만 처리합니다. "
            f"(받은 값: {calculation_result.status})"
        )
    if calculation_result.snapshot is None:
        raise SaasContractStorageMapperError(
            "STANDARD mapper: calculation_result.snapshot이 None입니다."
        )

    snap = calculation_result.snapshot

    # Site Scopes를 Snapshot에서 derive — 새 list 생성, 입력 mutate 없음
    site_scopes = [
        SaasContractSiteScopeV2(
            entity_type=s.entity_type,
            entity_id=s.entity_id,
            sector=s.sector,
            base_band_code=s.base_band_code,
        )
        for s in snap.sites
    ]

    commercial_version = SaasContractCommercialVersionV2(
        commercial_schema_version=COMMERCIAL_STORAGE_SCHEMA_VERSION,
        contract_id=contract_id,
        version_no=version_no,
        product_tier=selection.product_tier,
        pricing_mode=selection.pricing_mode,
        worker_capacity=selection.worker_capacity,
        term_months=selection.term_months,
        pricing_result_status="READY",
        pricing_policy_version=snap.policy_version,
        pricing_snapshot=snap,
        effective_from=effective_from,
        created_by=created_by,
    )

    return SaasContractStorageBundleV2(
        commercial_version=commercial_version,
        site_scopes=site_scopes,
    )


def build_custom_contract_storage_bundle_v2(
    contract_id: UUID,
    version_no: int,
    selection: SaasCommercialSelection,
    effective_from: datetime,
    site_scopes: Optional[List[SaasContractSiteScopeV2]] = None,
    created_by: Optional[UUID] = None,
) -> SaasContractStorageBundleV2:
    """CUSTOM selection을 Custom Storage Bundle로 변환.

    pricing_snapshot = None, pricing_policy_version = None.
    site_scopes는 선택적 (견적 Context용).
    입력 objects를 mutate하지 않는다.
    """
    if selection.product_tier != "CUSTOM":
        raise SaasContractStorageMapperError(
            f"CUSTOM mapper는 product_tier=CUSTOM인 selection만 처리합니다. "
            f"(받은 값: {selection.product_tier})"
        )

    commercial_version = SaasContractCommercialVersionV2(
        commercial_schema_version=COMMERCIAL_STORAGE_SCHEMA_VERSION,
        contract_id=contract_id,
        version_no=version_no,
        product_tier=selection.product_tier,
        pricing_mode=selection.pricing_mode,
        worker_capacity=selection.worker_capacity,
        term_months=selection.term_months,
        pricing_result_status="CUSTOM_REQUIRED",
        pricing_policy_version=None,
        pricing_snapshot=None,
        effective_from=effective_from,
        created_by=created_by,
    )

    return SaasContractStorageBundleV2(
        commercial_version=commercial_version,
        site_scopes=list(site_scopes) if site_scopes else [],
    )
