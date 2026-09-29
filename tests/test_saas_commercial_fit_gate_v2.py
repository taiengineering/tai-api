"""Tests for BE-OBJ05: Commercial Fit Gate V2.

F01-F53 : Gate evaluation tests
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from schemas.saas_commercial_fit_v2 import (
    SaasActualCommercialSiteV2,
    SaasCommercialActualStateV2,
    SaasCommercialFitResultV2,
    SaasComplianceBandCatalogEntryV2,
)
from schemas.saas_contract_commercial_v2 import (
    COMMERCIAL_STORAGE_SCHEMA_VERSION,
    SaasContractCommercialVersionV2,
    SaasContractSiteScopeV2,
    SaasContractStorageBundleV2,
)
from schemas.saas_pricing_policy_v2 import (
    SaasPricingPolicyV2,
    SaasTermDiscountPolicy,
    SaasWorkerRateBracketPolicy,
)
from schemas.saas_pricing_v2 import SaasCommercialSelection
from services.saas_commercial_fit_gate_v2 import (
    SaasCommercialFitGateError,
    evaluate_saas_commercial_fit_v2,
)
from services.saas_contract_storage_mapper_v2 import (
    build_custom_contract_storage_bundle_v2,
    build_standard_contract_storage_bundle_v2,
)
from services.saas_pricing_composer_v2 import SaasSitePricingInput, calculate_saas_price_v2

# ── Shared datetime ───────────────────────────────────────────────────────────

_BASE_DT = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)


def _now() -> datetime:
    return _BASE_DT


# ── Policy helper ─────────────────────────────────────────────────────────────

def _resolved_policy(version: str = "TEST_POLICY_V1") -> SaasPricingPolicyV2:
    return SaasPricingPolicyV2(
        policy_version=version,
        effective_from=date(2026, 9, 27),
        field_base_amount=249000,
        primary_site_rate_bps=10000,
        additional_site_rate_bps=8000,
        worker_brackets=[
            SaasWorkerRateBracketPolicy(range_from=1,   range_to=20,   unit_rate=3000),
            SaasWorkerRateBracketPolicy(range_from=21,  range_to=50,   unit_rate=2500),
            SaasWorkerRateBracketPolicy(range_from=51,  range_to=100,  unit_rate=2000),
            SaasWorkerRateBracketPolicy(range_from=101, range_to=300,  unit_rate=1500),
            SaasWorkerRateBracketPolicy(range_from=301, range_to=None, unit_rate=1200),
        ],
        vat_rate_bps=1000,
        term_discounts=[
            SaasTermDiscountPolicy(payment_months=1,  discount_rate_bps=0),
            SaasTermDiscountPolicy(payment_months=3,  discount_rate_bps=300),
            SaasTermDiscountPolicy(payment_months=6,  discount_rate_bps=500),
            SaasTermDiscountPolicy(payment_months=9,  discount_rate_bps=700),
            SaasTermDiscountPolicy(payment_months=12, discount_rate_bps=1000),
        ],
    )


# ── Catalog helpers ───────────────────────────────────────────────────────────

def _cat(*entries) -> List[SaasComplianceBandCatalogEntryV2]:
    return list(entries)


def _entry(sector: str, bbc: str, order: int) -> SaasComplianceBandCatalogEntryV2:
    return SaasComplianceBandCatalogEntryV2(sector=sector, base_band_code=bbc, sort_order=order)


def _std_catalog() -> List[SaasComplianceBandCatalogEntryV2]:
    """Standard 3-band INDUSTRY catalog."""
    return [
        _entry("INDUSTRY", "STARTER",  1),
        _entry("INDUSTRY", "BUSINESS", 2),
        _entry("INDUSTRY", "PRO",       3),
    ]


def _full_catalog() -> List[SaasComplianceBandCatalogEntryV2]:
    """Multi-sector catalog for mixed tests."""
    return [
        _entry("INDUSTRY",    "STARTER",   1),
        _entry("INDUSTRY",    "BUSINESS",  2),
        _entry("INDUSTRY",    "PRO",        3),
        _entry("BUILDING",    "BASIC",      1),
        _entry("BUILDING",    "STANDARD",   2),
        _entry("CONSTRUCTION","STD",        1),
        _entry("CONSTRUCTION","PREMIUM",    2),
    ]


# ── Site input helpers ────────────────────────────────────────────────────────

def _site_input(
    entity_id: UUID,
    sector: str = "INDUSTRY",
    bbc: str = "STARTER",
    base_amount: int = 149000,
) -> SaasSitePricingInput:
    etype = "site" if sector == "CONSTRUCTION" else "factory"
    return SaasSitePricingInput(
        entity_type=etype, entity_id=entity_id,
        sector=sector, base_band_code=bbc, base_amount=base_amount,
    )


# ── Actual site helpers ───────────────────────────────────────────────────────

def _actual(
    entity_id: UUID,
    sector: str = "INDUSTRY",
    required_bbc: str = "STARTER",
) -> SaasActualCommercialSiteV2:
    etype = "site" if sector == "CONSTRUCTION" else "factory"
    return SaasActualCommercialSiteV2(
        entity_type=etype, entity_id=entity_id,
        sector=sector, required_base_band_code=required_bbc,
    )


def _state(
    sites: List[SaasActualCommercialSiteV2],
    workers: int = 0,
    as_of: Optional[datetime] = None,
) -> SaasCommercialActualStateV2:
    return SaasCommercialActualStateV2(
        sites=sites,
        actual_worker_count=workers,
        as_of=as_of or _now(),
    )


# ── Contract bundle builders ──────────────────────────────────────────────────

def _mgr_bundle(
    site_inputs: List[SaasSitePricingInput],
    effective_from: Optional[datetime] = None,
    superseded_at: Optional[datetime] = None,
) -> SaasContractStorageBundleV2:
    policy = _resolved_policy()
    sel = SaasCommercialSelection(
        product_tier="MANAGER", pricing_mode="STANDARD",
        worker_capacity=0, payment_months=1,
    )
    result = calculate_saas_price_v2(sel, site_inputs, policy)
    assert result.status == "READY"
    bundle = build_standard_contract_storage_bundle_v2(
        contract_id=uuid4(), version_no=1, selection=sel,
        calculation_result=result, effective_from=effective_from or _now(),
    )
    if superseded_at is not None:
        # Rebuild with superseded_at set
        cv = bundle.commercial_version
        new_cv = SaasContractCommercialVersionV2(
            commercial_schema_version=cv.commercial_schema_version,
            contract_id=cv.contract_id,
            version_no=cv.version_no,
            product_tier=cv.product_tier,
            pricing_mode=cv.pricing_mode,
            worker_capacity=cv.worker_capacity,
            payment_months=cv.payment_months,
            pricing_result_status=cv.pricing_result_status,
            pricing_policy_version=cv.pricing_policy_version,
            pricing_snapshot=cv.pricing_snapshot,
            effective_from=cv.effective_from,
            superseded_at=superseded_at,
        )
        bundle = SaasContractStorageBundleV2(
            commercial_version=new_cv,
            site_scopes=bundle.site_scopes,
        )
    return bundle


def _field_bundle(
    site_inputs: List[SaasSitePricingInput],
    workers: int = 5,
    effective_from: Optional[datetime] = None,
) -> SaasContractStorageBundleV2:
    policy = _resolved_policy()
    sel = SaasCommercialSelection(
        product_tier="FIELD", pricing_mode="STANDARD",
        worker_capacity=workers, payment_months=1,
    )
    result = calculate_saas_price_v2(sel, site_inputs, policy)
    assert result.status == "READY"
    return build_standard_contract_storage_bundle_v2(
        contract_id=uuid4(), version_no=1, selection=sel,
        calculation_result=result, effective_from=effective_from or _now(),
    )


def _custom_bundle(
    site_scopes: Optional[List[SaasContractSiteScopeV2]] = None,
    workers: int = 0,
) -> SaasContractStorageBundleV2:
    sel = SaasCommercialSelection(
        product_tier="CUSTOM", pricing_mode="CUSTOM",
        worker_capacity=workers, payment_months=1,
    )
    return build_custom_contract_storage_bundle_v2(
        contract_id=uuid4(), version_no=1, selection=sel,
        effective_from=_now(), site_scopes=site_scopes,
    )


# ── Evaluate shorthand ────────────────────────────────────────────────────────

def _eval(
    bundle: SaasContractStorageBundleV2,
    actual_sites: List[SaasActualCommercialSiteV2],
    workers: int = 0,
    catalog: Optional[List[SaasComplianceBandCatalogEntryV2]] = None,
    as_of: Optional[datetime] = None,
) -> SaasCommercialFitResultV2:
    state = _state(actual_sites, workers=workers, as_of=as_of)
    return evaluate_saas_commercial_fit_v2(bundle, state, catalog or _std_catalog())


# ═════════════════════════════════════════════════════════════════════════════
# F01-F08: Basic Fit
# ═════════════════════════════════════════════════════════════════════════════

def test_F01_one_site_same_band_fit():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, bbc="STARTER")])
    result = _eval(bundle, [_actual(eid, required_bbc="STARTER")])
    assert result.status == "FIT"
    assert result.reason_codes == []


def test_F02_required_band_lower_than_contracted_fit():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, bbc="PRO", base_amount=499000)])
    catalog = _std_catalog()  # STARTER=1, BUSINESS=2, PRO=3
    result = _eval(bundle, [_actual(eid, required_bbc="STARTER")], catalog=catalog)
    assert result.status == "FIT"
    assert result.site_results[0].status == "FIT"


def test_F03_required_band_higher_change_required():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, bbc="STARTER")])
    result = _eval(bundle, [_actual(eid, required_bbc="BUSINESS")])
    assert result.status == "CHANGE_REQUIRED"
    assert "SCALE_BAND_EXCEEDED" in result.reason_codes


def test_F04_uncontracted_site_change_required():
    contracted_eid = uuid4()
    extra_eid = uuid4()
    bundle = _mgr_bundle([_site_input(contracted_eid, bbc="STARTER")])
    result = _eval(bundle, [_actual(extra_eid, required_bbc="STARTER")])
    assert result.status == "CHANGE_REQUIRED"
    assert "SITE_OUT_OF_SCOPE" in result.reason_codes


def test_F05_multiple_sites_all_fit():
    eid1, eid2 = uuid4(), uuid4()
    bundle = _mgr_bundle([
        _site_input(eid1, bbc="STARTER"),
        _site_input(eid2, bbc="BUSINESS", base_amount=299000),
    ])
    result = _eval(bundle, [
        _actual(eid1, required_bbc="STARTER"),
        _actual(eid2, required_bbc="BUSINESS"),
    ])
    assert result.status == "FIT"
    assert result.reason_codes == []


def test_F06_multiple_sites_one_scale_exceeded():
    eid1, eid2 = uuid4(), uuid4()
    bundle = _mgr_bundle([
        _site_input(eid1, bbc="STARTER"),
        _site_input(eid2, bbc="STARTER", base_amount=149001),
    ])
    result = _eval(bundle, [
        _actual(eid1, required_bbc="STARTER"),   # fits
        _actual(eid2, required_bbc="BUSINESS"),  # exceeds
    ])
    assert result.status == "CHANGE_REQUIRED"
    assert "SCALE_BAND_EXCEEDED" in result.reason_codes
    fit_sites = [s for s in result.site_results if s.status == "FIT"]
    bad_sites = [s for s in result.site_results if s.status == "SCALE_BAND_EXCEEDED"]
    assert len(fit_sites) == 1
    assert len(bad_sites) == 1


def test_F07_contracted_site_unused_fit():
    eid1, eid2, eid3 = uuid4(), uuid4(), uuid4()
    bundle = _mgr_bundle([
        _site_input(eid1, bbc="STARTER"),
        _site_input(eid2, bbc="STARTER", base_amount=149001),
        _site_input(eid3, bbc="STARTER", base_amount=149002),
    ])
    # Only use eid1 and eid2 — eid3 contracted but unused
    result = _eval(bundle, [
        _actual(eid1, required_bbc="STARTER"),
        _actual(eid2, required_bbc="STARTER"),
    ])
    assert result.status == "FIT"
    assert result.actual_site_count == 2
    assert result.contracted_site_count == 3


def test_F08_actual_input_reorder_invariant():
    eid1, eid2 = uuid4(), uuid4()
    bundle = _mgr_bundle([
        _site_input(eid1, bbc="STARTER"),
        _site_input(eid2, bbc="BUSINESS", base_amount=299000),
    ])
    actual_forward = [_actual(eid1), _actual(eid2, required_bbc="BUSINESS")]
    actual_reversed = [_actual(eid2, required_bbc="BUSINESS"), _actual(eid1)]
    result_a = _eval(bundle, actual_forward)
    result_b = _eval(bundle, actual_reversed)
    assert result_a.status == result_b.status
    assert result_a.reason_codes == result_b.reason_codes
    # site_results sorted deterministically
    assert len(result_a.site_results) == len(result_b.site_results)
    for ra, rb in zip(result_a.site_results, result_b.site_results):
        assert ra.entity_id == rb.entity_id
        assert ra.status == rb.status


# ═════════════════════════════════════════════════════════════════════════════
# F09-F14: Site Scope / Entity Type
# ═════════════════════════════════════════════════════════════════════════════

def test_F09_extra_site_site_out_of_scope():
    eid_contracted = uuid4()
    eid_extra = uuid4()
    bundle = _mgr_bundle([_site_input(eid_contracted)])
    result = _eval(bundle, [_actual(eid_contracted), _actual(eid_extra)])
    assert result.status == "CHANGE_REQUIRED"
    extra_results = [s for s in result.site_results if s.entity_id == eid_extra]
    assert len(extra_results) == 1
    assert extra_results[0].status == "SITE_OUT_OF_SCOPE"
    assert extra_results[0].contracted_base_band_code is None
    assert extra_results[0].contracted_sort_order is None


def test_F10_duplicate_actual_site_rejected():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid)])
    with pytest.raises(SaasCommercialFitGateError) as exc_info:
        _eval(bundle, [_actual(eid), _actual(eid)])
    assert exc_info.value.code == "DUPLICATE_ACTUAL_SITE"


def test_F11_same_identity_sector_mismatch_rejected():
    eid = uuid4()
    # Contract: INDUSTRY/factory
    bundle = _mgr_bundle([_site_input(eid, sector="INDUSTRY")])
    # Actual: same entity_id but BUILDING/factory
    actual_site = SaasActualCommercialSiteV2(
        entity_type="factory", entity_id=eid,
        sector="BUILDING", required_base_band_code="BASIC",
    )
    catalog = _full_catalog()
    with pytest.raises(SaasCommercialFitGateError) as exc_info:
        _eval(bundle, [actual_site], catalog=catalog)
    assert exc_info.value.code == "SITE_CONTEXT_MISMATCH"


def test_F12_industry_factory_accepted():
    eid = uuid4()
    site = SaasActualCommercialSiteV2(
        entity_type="factory", entity_id=eid,
        sector="INDUSTRY", required_base_band_code="STARTER",
    )
    assert site.entity_type == "factory"


def test_F13_building_factory_accepted():
    eid = uuid4()
    site = SaasActualCommercialSiteV2(
        entity_type="factory", entity_id=eid,
        sector="BUILDING", required_base_band_code="BASIC",
    )
    assert site.entity_type == "factory"


def test_F14_construction_site_accepted():
    eid = uuid4()
    site = SaasActualCommercialSiteV2(
        entity_type="site", entity_id=eid,
        sector="CONSTRUCTION", required_base_band_code="STD",
    )
    assert site.entity_type == "site"


# ═════════════════════════════════════════════════════════════════════════════
# F15-F20: Band Catalog
# ═════════════════════════════════════════════════════════════════════════════

def test_F15_missing_contracted_band_entry_rejected():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, bbc="STARTER")])
    # Catalog without STARTER
    catalog = [_entry("INDUSTRY", "BUSINESS", 2), _entry("INDUSTRY", "PRO", 3)]
    with pytest.raises(SaasCommercialFitGateError) as exc_info:
        _eval(bundle, [_actual(eid, required_bbc="BUSINESS")], catalog=catalog)
    assert exc_info.value.code == "BAND_CATALOG_ENTRY_NOT_FOUND"


def test_F16_missing_required_band_entry_rejected():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, bbc="STARTER")])
    # Catalog has STARTER but not ULTRA (required)
    with pytest.raises(SaasCommercialFitGateError) as exc_info:
        _eval(bundle, [_actual(eid, required_bbc="ULTRA")])  # ULTRA not in catalog
    assert exc_info.value.code == "BAND_CATALOG_ENTRY_NOT_FOUND"


def test_F17_duplicate_catalog_key_rejected():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid)])
    catalog = [
        _entry("INDUSTRY", "STARTER", 1),
        _entry("INDUSTRY", "STARTER", 2),  # duplicate (sector, bbc)
    ]
    with pytest.raises(SaasCommercialFitGateError) as exc_info:
        _eval(bundle, [_actual(eid)], catalog=catalog)
    assert exc_info.value.code == "DUPLICATE_BAND_CATALOG_ENTRY"


def test_F18_duplicate_sort_order_within_same_sector_rejected():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid)])
    catalog = [
        _entry("INDUSTRY", "STARTER",  1),
        _entry("INDUSTRY", "BUSINESS", 1),  # same sector, same sort_order
    ]
    with pytest.raises(SaasCommercialFitGateError) as exc_info:
        _eval(bundle, [_actual(eid)], catalog=catalog)
    assert exc_info.value.code == "AMBIGUOUS_BAND_ORDER"


def test_F19_same_sort_order_across_different_sectors_allowed():
    """서로 다른 Sector는 동일 sort_order를 공유할 수 있다."""
    catalog = [
        _entry("INDUSTRY",    "STARTER", 1),
        _entry("CONSTRUCTION", "STD",    1),  # same sort_order, different sector → OK
    ]
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, sector="INDUSTRY", bbc="STARTER")])
    result = _eval(bundle, [_actual(eid, required_bbc="STARTER")], catalog=catalog)
    assert result.status == "FIT"


def test_F20_same_code_name_across_different_sectors_no_collision():
    """동일 code 이름이 다른 Sector에 있어도 충돌하지 않는다."""
    catalog = [
        _entry("INDUSTRY",    "STANDARD_CODE", 1),
        _entry("CONSTRUCTION", "STANDARD_CODE", 1),  # same bbc name, different sector
    ]
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, sector="INDUSTRY", bbc="STANDARD_CODE")])
    result = _eval(bundle, [_actual(eid, required_bbc="STANDARD_CODE")], catalog=catalog)
    assert result.status == "FIT"


# ═════════════════════════════════════════════════════════════════════════════
# F21-F23: Scale Direction
# ═════════════════════════════════════════════════════════════════════════════

def test_F21_required_order_equals_contracted_fit():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, bbc="BUSINESS", base_amount=299000)])
    result = _eval(bundle, [_actual(eid, required_bbc="BUSINESS")])  # same order
    assert result.status == "FIT"
    assert result.site_results[0].status == "FIT"


def test_F22_required_order_less_than_contracted_fit():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, bbc="PRO", base_amount=499000)])
    result = _eval(bundle, [_actual(eid, required_bbc="STARTER")])  # STARTER(1) < PRO(3)
    assert result.status == "FIT"
    assert result.site_results[0].status == "FIT"
    assert result.site_results[0].required_sort_order == 1
    assert result.site_results[0].contracted_sort_order == 3


def test_F23_required_order_greater_than_contracted_scale_band_exceeded():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, bbc="STARTER")])
    result = _eval(bundle, [_actual(eid, required_bbc="PRO")])  # PRO(3) > STARTER(1)
    assert result.status == "CHANGE_REQUIRED"
    assert result.site_results[0].status == "SCALE_BAND_EXCEEDED"


# ═════════════════════════════════════════════════════════════════════════════
# F24-F30: Worker Capacity
# ═════════════════════════════════════════════════════════════════════════════

def test_F24_field_below_capacity_fit():
    eid = uuid4()
    bundle = _field_bundle([_site_input(eid)], workers=100)
    result = _eval(bundle, [_actual(eid)], workers=80)
    assert result.status == "FIT"
    assert "WORKER_CAPACITY_EXCEEDED" not in result.reason_codes


def test_F25_field_equal_capacity_fit():
    eid = uuid4()
    bundle = _field_bundle([_site_input(eid)], workers=100)
    result = _eval(bundle, [_actual(eid)], workers=100)
    assert result.status == "FIT"
    assert "WORKER_CAPACITY_EXCEEDED" not in result.reason_codes


def test_F26_field_over_capacity_change_required():
    eid = uuid4()
    bundle = _field_bundle([_site_input(eid)], workers=100)
    result = _eval(bundle, [_actual(eid)], workers=101)
    assert result.status == "CHANGE_REQUIRED"
    assert "WORKER_CAPACITY_EXCEEDED" in result.reason_codes


def test_F27_field_capacity_0_actual_0_fit():
    eid = uuid4()
    bundle = _field_bundle([_site_input(eid)], workers=0)
    result = _eval(bundle, [_actual(eid)], workers=0)
    assert result.status == "FIT"


def test_F28_field_capacity_0_actual_1_change_required():
    eid = uuid4()
    bundle = _field_bundle([_site_input(eid)], workers=0)
    result = _eval(bundle, [_actual(eid)], workers=1)
    assert result.status == "CHANGE_REQUIRED"
    assert "WORKER_CAPACITY_EXCEEDED" in result.reason_codes


def test_F29_manager_actual_worker_0_fit():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid)])
    result = _eval(bundle, [_actual(eid)], workers=0)
    assert result.status == "FIT"
    assert result.contracted_worker_capacity == 0


def test_F30_manager_actual_worker_positive_no_worker_reason():
    """MANAGER worker axis = not applicable. actual_worker_count > 0 → FIT (no worker reason)."""
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid)])
    result = _eval(bundle, [_actual(eid)], workers=1)
    assert result.status == "FIT"
    assert "WORKER_CAPACITY_EXCEEDED" not in result.reason_codes


# ═════════════════════════════════════════════════════════════════════════════
# F31-F32: Contract-wide Worker (not multiplied by site count)
# ═════════════════════════════════════════════════════════════════════════════

def test_F31_one_site_worker_100_equals_capacity_fit():
    eid = uuid4()
    bundle = _field_bundle([_site_input(eid)], workers=100)
    result = _eval(bundle, [_actual(eid)], workers=100)
    assert result.status == "FIT"
    assert result.contracted_worker_capacity == 100


def test_F32_ten_sites_worker_100_same_judgment():
    """Worker capacity는 사업장 수를 곱하지 않는다."""
    eids = [uuid4() for _ in range(10)]
    site_inputs = [
        _site_input(eid, bbc="STARTER", base_amount=149000 + i)
        for i, eid in enumerate(eids)
    ]
    bundle = _field_bundle(site_inputs, workers=100)
    actual_sites = [_actual(eid) for eid in eids]
    result = _eval(bundle, actual_sites, workers=100, catalog=_std_catalog())
    assert result.status == "FIT"
    # 사업장 10개지만 worker capacity = 100 × 1 (계약 전체)
    assert result.contracted_worker_capacity == 100
    assert result.actual_site_count == 10


# ═════════════════════════════════════════════════════════════════════════════
# F33-F35: Multiple Violations
# ═════════════════════════════════════════════════════════════════════════════

def test_F33_site_out_of_scope_and_worker_exceeded():
    contracted_eid = uuid4()
    extra_eid = uuid4()
    bundle = _field_bundle([_site_input(contracted_eid)], workers=5)
    result = _eval(bundle, [
        _actual(contracted_eid),
        _actual(extra_eid),  # out of scope
    ], workers=10)  # exceeds capacity 5
    assert result.status == "CHANGE_REQUIRED"
    assert "SITE_OUT_OF_SCOPE" in result.reason_codes
    assert "WORKER_CAPACITY_EXCEEDED" in result.reason_codes
    assert "SCALE_BAND_EXCEEDED" not in result.reason_codes


def test_F34_field_scale_ignored_worker_exceeded():
    """FIELD scale band = not commercial axis. band increase + worker exceeded → worker reason only."""
    eid = uuid4()
    bundle = _field_bundle([_site_input(eid, bbc="STARTER")], workers=5)
    result = _eval(bundle, [_actual(eid, required_bbc="PRO")], workers=10)
    assert result.status == "CHANGE_REQUIRED"
    assert "WORKER_CAPACITY_EXCEEDED" in result.reason_codes
    assert "SCALE_BAND_EXCEEDED" not in result.reason_codes
    assert "SITE_OUT_OF_SCOPE" not in result.reason_codes


def test_F35_field_site_scope_and_worker_exceeded_no_scale():
    """FIELD: scale band not applicable. site OOS + worker exceeded → 2 reasons (no SCALE_BAND)."""
    contracted_eid = uuid4()
    extra_eid = uuid4()
    bundle = _field_bundle([_site_input(contracted_eid, bbc="STARTER")], workers=5)
    result = _eval(bundle, [
        _actual(contracted_eid, required_bbc="PRO"),  # band increase — no reason for FIELD
        _actual(extra_eid),                           # out of scope
    ], workers=10)
    assert result.status == "CHANGE_REQUIRED"
    assert result.reason_codes == [
        "SITE_OUT_OF_SCOPE",
        "WORKER_CAPACITY_EXCEEDED",
    ]


# ═════════════════════════════════════════════════════════════════════════════
# F36-F39: CUSTOM
# ═════════════════════════════════════════════════════════════════════════════

def test_F36_custom_returns_custom_review_required():
    bundle = _custom_bundle()
    result = _eval(bundle, [])
    assert result.status == "CUSTOM_REVIEW_REQUIRED"
    assert result.product_tier == "CUSTOM"


def test_F37_custom_with_zero_sites_custom_review_required():
    bundle = _custom_bundle(site_scopes=None)
    result = _eval(bundle, [])
    assert result.status == "CUSTOM_REVIEW_REQUIRED"


def test_F38_custom_with_site_scopes_custom_review_required():
    scope = SaasContractSiteScopeV2(
        entity_type="factory", entity_id=uuid4(), sector="INDUSTRY", base_band_code=None,
    )
    bundle = _custom_bundle(site_scopes=[scope])
    result = _eval(bundle, [_actual(uuid4())])
    assert result.status == "CUSTOM_REVIEW_REQUIRED"


def test_F39_custom_with_worker_usage_custom_review_required():
    bundle = _custom_bundle(workers=50)
    result = _eval(bundle, [], workers=30)
    assert result.status == "CUSTOM_REVIEW_REQUIRED"


# ═════════════════════════════════════════════════════════════════════════════
# F40-F43: Version Time
# ═════════════════════════════════════════════════════════════════════════════

def test_F40_superseded_version_at_boundary_rejected():
    """as_of == superseded_at → NON_CURRENT_COMMERCIAL_VERSION (half-open interval)."""
    eid = uuid4()
    # superseded_at = _now() = as_of → boundary → NOT effective
    superseded_dt = _now()
    bundle = _mgr_bundle(
        [_site_input(eid)],
        superseded_at=superseded_dt,
    )
    with pytest.raises(SaasCommercialFitGateError) as exc_info:
        _eval(bundle, [_actual(eid)], as_of=_now())
    assert exc_info.value.code == "NON_CURRENT_COMMERCIAL_VERSION"


def test_F41_effective_from_after_as_of_rejected():
    eid = uuid4()
    future_effective = _now() + timedelta(hours=1)
    bundle = _mgr_bundle([_site_input(eid)], effective_from=future_effective)
    with pytest.raises(SaasCommercialFitGateError) as exc_info:
        _eval(bundle, [_actual(eid)], as_of=_now())
    assert exc_info.value.code == "COMMERCIAL_VERSION_NOT_EFFECTIVE"


def test_F42_effective_from_equals_as_of_accepted():
    eid = uuid4()
    dt = _now()
    bundle = _mgr_bundle([_site_input(eid)], effective_from=dt)
    result = _eval(bundle, [_actual(eid)], as_of=dt)
    assert result.status == "FIT"


def test_F43_effective_from_before_as_of_accepted():
    eid = uuid4()
    past_effective = _now() - timedelta(days=30)
    bundle = _mgr_bundle([_site_input(eid)], effective_from=past_effective)
    result = _eval(bundle, [_actual(eid)], as_of=_now())
    assert result.status == "FIT"


# ═════════════════════════════════════════════════════════════════════════════
# F44-F47: Determinism / Input Mutation
# ═════════════════════════════════════════════════════════════════════════════

def test_F44_same_input_same_output():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid)])
    state = _state([_actual(eid)])
    cat = _std_catalog()
    r1 = evaluate_saas_commercial_fit_v2(bundle, state, cat)
    r2 = evaluate_saas_commercial_fit_v2(bundle, state, cat)
    assert r1.status == r2.status
    assert r1.reason_codes == r2.reason_codes


def test_F45_actual_site_order_changed_same_output():
    eid1, eid2 = uuid4(), uuid4()
    bundle = _mgr_bundle([
        _site_input(eid1, bbc="STARTER"),
        _site_input(eid2, bbc="STARTER", base_amount=149001),
    ])
    actual_a = [_actual(eid1), _actual(eid2)]
    actual_b = [_actual(eid2), _actual(eid1)]  # reversed
    r_a = _eval(bundle, actual_a)
    r_b = _eval(bundle, actual_b)
    assert r_a.status == r_b.status
    # Same site results in same order (deterministic sort)
    ids_a = [str(s.entity_id) for s in r_a.site_results]
    ids_b = [str(s.entity_id) for s in r_b.site_results]
    assert ids_a == ids_b


def test_F46_catalog_order_changed_same_output():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, bbc="BUSINESS", base_amount=299000)])
    cat_normal = [_entry("INDUSTRY", "STARTER", 1), _entry("INDUSTRY", "BUSINESS", 2), _entry("INDUSTRY", "PRO", 3)]
    cat_reversed = [_entry("INDUSTRY", "PRO", 3), _entry("INDUSTRY", "BUSINESS", 2), _entry("INDUSTRY", "STARTER", 1)]
    r_a = _eval(bundle, [_actual(eid, required_bbc="BUSINESS")], catalog=cat_normal)
    r_b = _eval(bundle, [_actual(eid, required_bbc="BUSINESS")], catalog=cat_reversed)
    assert r_a.status == r_b.status
    assert r_a.site_results[0].status == r_b.site_results[0].status


def test_F47_input_objects_unchanged_after_evaluation():
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid)])
    state = _state([_actual(eid)])
    catalog = _std_catalog()

    site_count_before = len(bundle.site_scopes)
    actual_count_before = len(state.sites)
    catalog_count_before = len(catalog)

    evaluate_saas_commercial_fit_v2(bundle, state, catalog)

    assert len(bundle.site_scopes) == site_count_before
    assert len(state.sites) == actual_count_before
    assert len(catalog) == catalog_count_before


# ═════════════════════════════════════════════════════════════════════════════
# F48-F53: Separation / Source Guard
# ═════════════════════════════════════════════════════════════════════════════

_GATE_SRC = Path(__file__).parent.parent / "services" / "saas_commercial_fit_gate_v2.py"
_SCHEMA_SRC = Path(__file__).parent.parent / "schemas" / "saas_commercial_fit_v2.py"


def test_F48_no_price_amount_calculation():
    source = _GATE_SRC.read_text()
    forbidden = ["monthly_supply", "prepaid_supply", "vat_amount", "total_amount"]
    for kw in forbidden:
        assert kw not in source, f"가격 계산 키워드 발견: {kw}"


def test_F49_no_vat_calculation():
    source = _GATE_SRC.read_text()
    assert "vat_rate_bps" not in source
    assert "* policy.vat" not in source


def test_F50_no_payment_delta():
    lines = _GATE_SRC.read_text().splitlines()
    code_lines = "\n".join(
        ln for ln in lines if not ln.lstrip().startswith(("#", "\"\"\"", "- "))
    )
    for kw in ["delta", "payment", "refund", "billing"]:
        assert kw not in code_lines, f"결제 키워드 발견: {kw}"


def test_F51_no_entitlement_fields():
    gate_src = _GATE_SRC.read_text()
    schema_src = _SCHEMA_SRC.read_text()
    for kw in ["entitlement", "allowed_features", "permissions", "menu_code"]:
        assert kw not in gate_src, f"Entitlement 키워드 발견 in gate: {kw}"
        assert kw not in schema_src, f"Entitlement 키워드 발견 in schema: {kw}"


def test_F52_no_db_io():
    source = _GATE_SRC.read_text()
    for kw in ["supabase", "execute_sql", "get_supabase", "psycopg"]:
        assert kw not in source, f"DB I/O 키워드 발견: {kw}"


def test_F53_no_api_router():
    source = _GATE_SRC.read_text()
    for kw in ["APIRouter", "from routers", "import routers"]:
        assert kw not in source, f"API/Router 키워드 발견: {kw}"


# ═════════════════════════════════════════════════════════════════════════════
# F58-F61: V3 Product Tier Axis Separation
# ═════════════════════════════════════════════════════════════════════════════

def test_F58_field_band_increase_only_fit():
    """FIELD scale band ≠ commercial axis. band increase, worker within capacity → FIT."""
    eid = uuid4()
    bundle = _field_bundle([_site_input(eid, bbc="STARTER")], workers=10)
    result = _eval(bundle, [_actual(eid, required_bbc="PRO")], workers=5)
    assert result.status == "FIT"
    assert "SCALE_BAND_EXCEEDED" not in result.reason_codes
    assert result.site_results[0].status == "FIT"


def test_F59_field_site_out_of_scope_worker_in_range_no_scale_reason():
    """FIELD: extra site (OOS) + worker within capacity → SITE_OUT_OF_SCOPE only."""
    contracted_eid = uuid4()
    extra_eid = uuid4()
    bundle = _field_bundle([_site_input(contracted_eid)], workers=10)
    result = _eval(bundle, [
        _actual(contracted_eid),
        _actual(extra_eid),  # out of scope
    ], workers=5)
    assert result.status == "CHANGE_REQUIRED"
    assert result.reason_codes == ["SITE_OUT_OF_SCOPE"]
    assert "SCALE_BAND_EXCEEDED" not in result.reason_codes


def test_F60_manager_worker_positive_same_site_band_fit():
    """MANAGER worker axis = not applicable. site fits, band fits, actual_worker > 0 → FIT."""
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, bbc="STARTER")])
    result = _eval(bundle, [_actual(eid, required_bbc="STARTER")], workers=50)
    assert result.status == "FIT"
    assert result.reason_codes == []
    assert "WORKER_CAPACITY_EXCEEDED" not in result.reason_codes


def test_F61_manager_scale_exceeded_worker_positive_scale_reason_only():
    """MANAGER scale exceeded + actual_worker > 0 → SCALE_BAND_EXCEEDED only, no worker reason."""
    eid = uuid4()
    bundle = _mgr_bundle([_site_input(eid, bbc="STARTER")])
    result = _eval(bundle, [_actual(eid, required_bbc="PRO")], workers=20)
    assert result.status == "CHANGE_REQUIRED"
    assert result.reason_codes == ["SCALE_BAND_EXCEEDED"]
    assert "WORKER_CAPACITY_EXCEEDED" not in result.reason_codes


# ═════════════════════════════════════════════════════════════════════════════
# F54-F57: Temporal migration — CF-T1 through CF-T4
# B1 Owner Policy: [effective_from, superseded_at)
# ═════════════════════════════════════════════════════════════════════════════

def test_F54_future_superseded_before_boundary_accepted():
    """CF-T1: superseded_at=tomorrow, as_of=today → still effective (PASS)."""
    eid = uuid4()
    boundary = _now() + timedelta(days=1)  # tomorrow
    bundle = _mgr_bundle([_site_input(eid)], superseded_at=boundary)
    result = _eval(bundle, [_actual(eid)], as_of=_now())
    assert result.status == "FIT"


def test_F55_superseded_past_boundary_rejected():
    """CF-T2 extension: superseded_at=past, as_of=now → NON_CURRENT."""
    eid = uuid4()
    far_past = _now() - timedelta(hours=2)
    past = _now() - timedelta(seconds=1)  # after far_past, before now
    bundle = _mgr_bundle([_site_input(eid)], effective_from=far_past, superseded_at=past)
    with pytest.raises(SaasCommercialFitGateError) as exc_info:
        _eval(bundle, [_actual(eid)], as_of=_now())
    assert exc_info.value.code == "NON_CURRENT_COMMERCIAL_VERSION"


def test_F56_new_cv_before_effective_from_rejected():
    """CF-T3: new CV not yet effective → COMMERCIAL_VERSION_NOT_EFFECTIVE."""
    eid = uuid4()
    future_eff = _now() + timedelta(hours=1)
    bundle = _mgr_bundle([_site_input(eid)], effective_from=future_eff)
    with pytest.raises(SaasCommercialFitGateError) as exc_info:
        _eval(bundle, [_actual(eid)], as_of=_now())
    assert exc_info.value.code == "COMMERCIAL_VERSION_NOT_EFFECTIVE"


def test_F57_new_cv_exactly_at_effective_from_accepted():
    """CF-T4: new CV effective_from == as_of → PASS."""
    eid = uuid4()
    boundary = _now()
    bundle = _mgr_bundle([_site_input(eid)], effective_from=boundary)
    result = _eval(bundle, [_actual(eid)], as_of=boundary)
    assert result.status == "FIT"
