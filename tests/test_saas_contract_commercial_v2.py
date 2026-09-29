"""Tests for BE-OBJ04: Commercial Contract Storage V2.

S01-S44 : Schema/Model validation
M01-M08 : Mapper
D01-D09 : DDL Proposal source
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

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
from schemas.saas_pricing_v2 import SaasCommercialSelection, SaasPricingSnapshotV2
from services.saas_contract_storage_mapper_v2 import (
    SaasContractStorageMapperError,
    build_custom_contract_storage_bundle_v2,
    build_standard_contract_storage_bundle_v2,
)
from services.saas_pricing_composer_v2 import SaasSitePricingInput, calculate_saas_price_v2

# ── Test-only Policy (term discounts all resolved) ────────────────────────────

def _resolved_policy(policy_version: str = "TEST_POLICY_V1") -> SaasPricingPolicyV2:
    return SaasPricingPolicyV2(
        policy_version=policy_version,
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mgr_sel(term: int = 1) -> SaasCommercialSelection:
    return SaasCommercialSelection(
        product_tier="MANAGER", pricing_mode="STANDARD",
        worker_capacity=0, payment_months=term,
    )


def _field_sel(workers: int = 5, term: int = 1) -> SaasCommercialSelection:
    return SaasCommercialSelection(
        product_tier="FIELD", pricing_mode="STANDARD",
        worker_capacity=workers, payment_months=term,
    )


def _custom_sel(workers: int = 0, term: int = 1) -> SaasCommercialSelection:
    return SaasCommercialSelection(
        product_tier="CUSTOM", pricing_mode="CUSTOM",
        worker_capacity=workers, payment_months=term,
    )


def _site(
    sector: str = "INDUSTRY",
    base_band_code: str = "INDUSTRY_STARTER_V3",
    base_amount: int = 149000,
    entity_id: Optional[UUID] = None,
) -> SaasSitePricingInput:
    etype = "site" if sector == "CONSTRUCTION" else "factory"
    return SaasSitePricingInput(
        entity_type=etype,
        entity_id=entity_id or uuid4(),
        sector=sector,
        base_band_code=base_band_code,
        base_amount=base_amount,
    )


def _ready_result(sel: SaasCommercialSelection, sites=None, policy=None):
    """READY calculation result를 반환."""
    p = policy or _resolved_policy()
    s = sites or [_site()]
    result = calculate_saas_price_v2(sel, s, p)
    assert result.status == "READY", f"Expected READY, got {result.status}"
    return result


def _now() -> datetime:
    return datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)


def _make_commercial_version(
    product_tier: str = "MANAGER",
    pricing_mode: str = "STANDARD",
    worker_capacity: int = 0,
    payment_months: int = 1,
    pricing_result_status: str = "READY",
    pricing_policy_version: Optional[str] = "TEST_POLICY_V1",
    pricing_snapshot: Optional[SaasPricingSnapshotV2] = None,
    version_no: int = 1,
    contract_id: Optional[UUID] = None,
    superseded_at: Optional[datetime] = None,
) -> SaasContractCommercialVersionV2:
    """SaasContractCommercialVersionV2 생성 helper."""
    return SaasContractCommercialVersionV2(
        commercial_schema_version=COMMERCIAL_STORAGE_SCHEMA_VERSION,
        contract_id=contract_id or uuid4(),
        version_no=version_no,
        product_tier=product_tier,
        pricing_mode=pricing_mode,
        worker_capacity=worker_capacity,
        payment_months=payment_months,
        pricing_result_status=pricing_result_status,
        pricing_policy_version=pricing_policy_version,
        pricing_snapshot=pricing_snapshot,
        effective_from=_now(),
        superseded_at=superseded_at,
    )


def _valid_mgr_version(term: int = 1) -> SaasContractCommercialVersionV2:
    """유효한 MANAGER Commercial Version 반환."""
    sel = _mgr_sel(term=term)
    result = _ready_result(sel)
    snap = result.snapshot
    return _make_commercial_version(
        product_tier="MANAGER",
        pricing_mode="STANDARD",
        worker_capacity=0,
        payment_months=term,
        pricing_policy_version=snap.policy_version,
        pricing_snapshot=snap,
    )


def _valid_field_version(workers: int = 5, term: int = 1) -> SaasContractCommercialVersionV2:
    """유효한 FIELD Commercial Version 반환."""
    sel = _field_sel(workers=workers, term=term)
    result = _ready_result(sel)
    snap = result.snapshot
    return _make_commercial_version(
        product_tier="FIELD",
        pricing_mode="STANDARD",
        worker_capacity=workers,
        payment_months=term,
        pricing_policy_version=snap.policy_version,
        pricing_snapshot=snap,
    )


def _valid_custom_version(workers: int = 0) -> SaasContractCommercialVersionV2:
    """유효한 CUSTOM Commercial Version 반환."""
    return _make_commercial_version(
        product_tier="CUSTOM",
        pricing_mode="CUSTOM",
        worker_capacity=workers,
        payment_months=1,
        pricing_result_status="CUSTOM_REQUIRED",
        pricing_policy_version=None,
        pricing_snapshot=None,
    )


# ── S01-S06: Tier/Mode combination ────────────────────────────────────────────

def test_S01_manager_standard_accepted():
    cv = _valid_mgr_version()
    assert cv.product_tier == "MANAGER"
    assert cv.pricing_mode == "STANDARD"


def test_S02_field_standard_accepted():
    cv = _valid_field_version()
    assert cv.product_tier == "FIELD"
    assert cv.pricing_mode == "STANDARD"


def test_S03_custom_custom_accepted():
    cv = _valid_custom_version()
    assert cv.product_tier == "CUSTOM"
    assert cv.pricing_mode == "CUSTOM"


def test_S04_manager_custom_rejected():
    with pytest.raises(ValidationError):
        SaasContractCommercialVersionV2(
            commercial_schema_version=COMMERCIAL_STORAGE_SCHEMA_VERSION,
            contract_id=uuid4(),
            version_no=1,
            product_tier="MANAGER",
            pricing_mode="CUSTOM",
            worker_capacity=0,
            payment_months=1,
            pricing_result_status="CUSTOM_REQUIRED",
            pricing_policy_version=None,
            pricing_snapshot=None,
            effective_from=_now(),
        )


def test_S05_field_custom_rejected():
    with pytest.raises(ValidationError):
        SaasContractCommercialVersionV2(
            commercial_schema_version=COMMERCIAL_STORAGE_SCHEMA_VERSION,
            contract_id=uuid4(),
            version_no=1,
            product_tier="FIELD",
            pricing_mode="CUSTOM",
            worker_capacity=5,
            payment_months=1,
            pricing_result_status="CUSTOM_REQUIRED",
            pricing_policy_version=None,
            pricing_snapshot=None,
            effective_from=_now(),
        )


def test_S06_custom_standard_rejected():
    with pytest.raises(ValidationError):
        SaasContractCommercialVersionV2(
            commercial_schema_version=COMMERCIAL_STORAGE_SCHEMA_VERSION,
            contract_id=uuid4(),
            version_no=1,
            product_tier="CUSTOM",
            pricing_mode="STANDARD",
            worker_capacity=0,
            payment_months=1,
            pricing_result_status="CUSTOM_REQUIRED",
            pricing_policy_version=None,
            pricing_snapshot=None,
            effective_from=_now(),
        )


# ── S07-S10: Worker Capacity ──────────────────────────────────────────────────

def test_S07_manager_worker_zero_accepted():
    cv = _make_commercial_version(
        product_tier="MANAGER",
        worker_capacity=0,
        pricing_snapshot=_ready_result(_mgr_sel()).snapshot,
        pricing_policy_version="TEST_POLICY_V1",
    )
    assert cv.worker_capacity == 0


def test_S08_manager_worker_positive_rejected():
    snap = _ready_result(_mgr_sel()).snapshot
    with pytest.raises(ValidationError):
        _make_commercial_version(
            product_tier="MANAGER",
            worker_capacity=1,
            pricing_snapshot=snap,
            pricing_policy_version=snap.policy_version,
        )


def test_S09_field_worker_non_negative_accepted():
    cv = _valid_field_version(workers=0)
    assert cv.worker_capacity == 0
    cv2 = _valid_field_version(workers=100)
    assert cv2.worker_capacity == 100


def test_S10_custom_worker_non_negative_accepted():
    cv_zero = _valid_custom_version(workers=0)
    assert cv_zero.worker_capacity == 0
    cv_pos = _valid_custom_version(workers=50)
    assert cv_pos.worker_capacity == 50


# ── S11-S18: Term Months ──────────────────────────────────────────────────────

def test_S11_term_1_accepted():
    cv = _valid_mgr_version(term=1)
    assert cv.payment_months == 1


def test_S12_term_3_accepted():
    cv = _valid_mgr_version(term=3)
    assert cv.payment_months == 3


def test_S13_term_6_accepted():
    cv = _valid_mgr_version(term=6)
    assert cv.payment_months == 6


def test_S14_term_9_accepted():
    cv = _valid_mgr_version(term=9)
    assert cv.payment_months == 9


def test_S15_term_12_accepted():
    cv = _valid_mgr_version(term=12)
    assert cv.payment_months == 12


def test_S16_invalid_term_rejected():
    snap = _ready_result(_mgr_sel()).snapshot
    with pytest.raises(ValidationError):
        _make_commercial_version(
            payment_months=2,
            pricing_snapshot=snap,
            pricing_policy_version=snap.policy_version,
        )


def test_S17_float_term_rejected():
    snap = _ready_result(_mgr_sel()).snapshot
    with pytest.raises(ValidationError):
        _make_commercial_version(
            payment_months=1.0,  # type: ignore[arg-type]
            pricing_snapshot=snap,
            pricing_policy_version=snap.policy_version,
        )


def test_S18_bool_term_rejected():
    snap = _ready_result(_mgr_sel()).snapshot
    with pytest.raises(ValidationError):
        _make_commercial_version(
            payment_months=True,  # type: ignore[arg-type]
            pricing_snapshot=snap,
            pricing_policy_version=snap.policy_version,
        )


# ── S19-S22: STANDARD Snapshot Requirements ───────────────────────────────────

def test_S19_standard_ready_snapshot_accepted():
    cv = _valid_mgr_version()
    assert cv.pricing_result_status == "READY"
    assert cv.pricing_snapshot is not None
    assert cv.pricing_policy_version is not None


def test_S20_standard_snapshot_none_rejected():
    with pytest.raises(ValidationError):
        _make_commercial_version(
            product_tier="MANAGER",
            pricing_result_status="READY",
            pricing_policy_version="TEST_POLICY_V1",
            pricing_snapshot=None,  # required for STANDARD
        )


def test_S21_standard_policy_version_none_rejected():
    snap = _ready_result(_mgr_sel()).snapshot
    with pytest.raises(ValidationError):
        _make_commercial_version(
            product_tier="MANAGER",
            pricing_result_status="READY",
            pricing_policy_version=None,  # required for STANDARD
            pricing_snapshot=snap,
        )


def test_S22_standard_status_custom_required_rejected():
    snap = _ready_result(_mgr_sel()).snapshot
    with pytest.raises(ValidationError):
        _make_commercial_version(
            product_tier="MANAGER",
            pricing_result_status="CUSTOM_REQUIRED",  # invalid for STANDARD
            pricing_policy_version=snap.policy_version,
            pricing_snapshot=snap,
        )


# ── S23-S26: Snapshot Cross-Validation ───────────────────────────────────────

def test_S23_tier_mismatch_rejected():
    """FIELD snapshot을 MANAGER version에 사용하면 거부."""
    field_snap = _ready_result(_field_sel()).snapshot
    with pytest.raises(ValidationError):
        _make_commercial_version(
            product_tier="MANAGER",
            worker_capacity=0,
            pricing_result_status="READY",
            pricing_policy_version=field_snap.policy_version,
            pricing_snapshot=field_snap,  # product_tier=FIELD in snapshot
        )


def test_S24_pricing_mode_mismatch_rejected():
    """pricing_mode 불일치: snapshot의 pricing_mode가 version과 다르면 거부.

    SaasPricingSnapshotV2 자체 validator가 pricing_mode=STANDARD만 허용하므로
    model_construct로 인위적 불일치 상태를 만들어 cross-validation을 검증한다.
    """
    snap = _ready_result(_field_sel()).snapshot
    # Bypass Snapshot validators to create artificial pricing_mode mismatch
    bad_snap = SaasPricingSnapshotV2.model_construct(
        **{**snap.model_dump(), "pricing_mode": "CUSTOM"}
    )
    with pytest.raises(ValidationError, match="pricing_mode"):
        _make_commercial_version(
            product_tier="FIELD",
            worker_capacity=5,
            pricing_mode="STANDARD",
            pricing_result_status="READY",
            pricing_policy_version=snap.policy_version,
            pricing_snapshot=bad_snap,
        )


def test_S25_term_mismatch_rejected():
    """snapshot.payment_months ≠ version.payment_months → 거부."""
    sel_term3 = _field_sel(term=3)
    snap_term3 = _ready_result(sel_term3).snapshot
    assert snap_term3.payment_months == 3
    with pytest.raises(ValidationError, match="payment_months"):
        # version.payment_months=1 but snapshot.payment_months=3
        SaasContractCommercialVersionV2(
            commercial_schema_version=COMMERCIAL_STORAGE_SCHEMA_VERSION,
            contract_id=uuid4(),
            version_no=1,
            product_tier="FIELD",
            pricing_mode="STANDARD",
            worker_capacity=5,
            payment_months=1,  # version says 1
            pricing_result_status="READY",
            pricing_policy_version=snap_term3.policy_version,
            pricing_snapshot=snap_term3,  # snapshot says 3
            effective_from=_now(),
        )


def test_S26_policy_version_mismatch_rejected():
    """snapshot.policy_version ≠ version.pricing_policy_version → 거부."""
    snap = _ready_result(_mgr_sel()).snapshot
    with pytest.raises(ValidationError, match="policy_version"):
        _make_commercial_version(
            product_tier="MANAGER",
            pricing_result_status="READY",
            pricing_policy_version="WRONG_POLICY_V9",  # mismatch
            pricing_snapshot=snap,  # has policy_version=TEST_POLICY_V1
        )


# ── S27-S31: CUSTOM Rules ─────────────────────────────────────────────────────

def test_S27_custom_status_custom_required_accepted():
    cv = _valid_custom_version()
    assert cv.pricing_result_status == "CUSTOM_REQUIRED"


def test_S28_custom_snapshot_none_accepted():
    cv = _valid_custom_version()
    assert cv.pricing_snapshot is None


def test_S29_custom_snapshot_present_rejected():
    snap = _ready_result(_field_sel()).snapshot
    with pytest.raises(ValidationError):
        _make_commercial_version(
            product_tier="CUSTOM",
            pricing_mode="CUSTOM",
            worker_capacity=0,
            pricing_result_status="CUSTOM_REQUIRED",
            pricing_policy_version=None,
            pricing_snapshot=snap,  # CUSTOM must not have snapshot
        )


def test_S30_custom_policy_version_present_rejected():
    with pytest.raises(ValidationError):
        _make_commercial_version(
            product_tier="CUSTOM",
            pricing_mode="CUSTOM",
            worker_capacity=0,
            pricing_result_status="CUSTOM_REQUIRED",
            pricing_policy_version="SOME_POLICY",  # CUSTOM must be None
            pricing_snapshot=None,
        )


def test_S31_custom_ready_rejected():
    with pytest.raises(ValidationError):
        _make_commercial_version(
            product_tier="CUSTOM",
            pricing_mode="CUSTOM",
            worker_capacity=0,
            pricing_result_status="READY",  # CUSTOM must be CUSTOM_REQUIRED
            pricing_policy_version=None,
            pricing_snapshot=None,
        )


# ── S32-S37: Site Scope entity/sector mapping ─────────────────────────────────

def test_S32_industry_factory_accepted():
    scope = SaasContractSiteScopeV2(
        entity_type="factory", entity_id=uuid4(),
        sector="INDUSTRY", base_band_code="INDUSTRY_STARTER_V3",
    )
    assert scope.entity_type == "factory"


def test_S33_building_factory_accepted():
    scope = SaasContractSiteScopeV2(
        entity_type="factory", entity_id=uuid4(),
        sector="BUILDING", base_band_code="BUILDING_BASIC_V3",
    )
    assert scope.entity_type == "factory"


def test_S34_construction_site_accepted():
    scope = SaasContractSiteScopeV2(
        entity_type="site", entity_id=uuid4(),
        sector="CONSTRUCTION", base_band_code="CONSTRUCTION_STANDARD_V3",
    )
    assert scope.entity_type == "site"


def test_S35_industry_site_rejected():
    with pytest.raises(ValidationError):
        SaasContractSiteScopeV2(
            entity_type="site", entity_id=uuid4(),
            sector="INDUSTRY",
        )


def test_S36_building_site_rejected():
    with pytest.raises(ValidationError):
        SaasContractSiteScopeV2(
            entity_type="site", entity_id=uuid4(),
            sector="BUILDING",
        )


def test_S37_construction_factory_rejected():
    with pytest.raises(ValidationError):
        SaasContractSiteScopeV2(
            entity_type="factory", entity_id=uuid4(),
            sector="CONSTRUCTION",
        )


# ── S38-S44: Bundle Integrity ─────────────────────────────────────────────────

def _site_scope(entity_id: UUID, sector: str = "INDUSTRY") -> SaasContractSiteScopeV2:
    etype = "site" if sector == "CONSTRUCTION" else "factory"
    bbc = {"INDUSTRY": "INDUSTRY_STARTER_V3", "BUILDING": "BUILDING_BASIC_V3", "CONSTRUCTION": "CONSTRUCTION_STANDARD_V3"}[sector]
    return SaasContractSiteScopeV2(entity_type=etype, entity_id=entity_id, sector=sector, base_band_code=bbc)


def test_S38_duplicate_site_rejected():
    cv = _valid_mgr_version()
    eid = uuid4()
    scope1 = _site_scope(eid)
    scope2 = _site_scope(eid)  # same entity_id
    with pytest.raises(ValidationError):
        SaasContractStorageBundleV2(
            commercial_version=cv,
            site_scopes=[scope1, scope2],
        )


def test_S39_standard_scope_missing_snapshot_site_rejected():
    eid = uuid4()
    site_input = _site(entity_id=eid)
    sel = _mgr_sel()
    result = _ready_result(sel, sites=[site_input])
    cv = _make_commercial_version(
        product_tier="MANAGER",
        pricing_snapshot=result.snapshot,
        pricing_policy_version=result.snapshot.policy_version,
    )
    # provide no site_scopes — snapshot has 1 site
    with pytest.raises(ValidationError):
        SaasContractStorageBundleV2(commercial_version=cv, site_scopes=[])


def test_S40_standard_extra_scope_rejected():
    eid = uuid4()
    site_input = _site(entity_id=eid)
    sel = _mgr_sel()
    result = _ready_result(sel, sites=[site_input])
    cv = _make_commercial_version(
        product_tier="MANAGER",
        pricing_snapshot=result.snapshot,
        pricing_policy_version=result.snapshot.policy_version,
    )
    # provide correct + one extra site scope
    correct_scope = _site_scope(eid)
    extra_scope = _site_scope(uuid4())  # not in snapshot
    with pytest.raises(ValidationError):
        SaasContractStorageBundleV2(
            commercial_version=cv,
            site_scopes=[correct_scope, extra_scope],
        )


def test_S41_sector_mismatch_rejected():
    eid = uuid4()
    # Snapshot built with INDUSTRY/factory
    site_input = SaasSitePricingInput(
        entity_type="factory", entity_id=eid,
        sector="INDUSTRY", base_band_code="INDUSTRY_STARTER_V3", base_amount=149000,
    )
    sel = _mgr_sel()
    result = _ready_result(sel, sites=[site_input])
    cv = _make_commercial_version(
        product_tier="MANAGER",
        pricing_snapshot=result.snapshot,
        pricing_policy_version=result.snapshot.policy_version,
    )
    # Site scope with wrong sector (BUILDING instead of INDUSTRY) for same entity_id
    wrong_scope = SaasContractSiteScopeV2(
        entity_type="factory", entity_id=eid,
        sector="BUILDING", base_band_code="INDUSTRY_STARTER_V3",
    )
    with pytest.raises(ValidationError):
        SaasContractStorageBundleV2(commercial_version=cv, site_scopes=[wrong_scope])


def test_S42_base_band_code_mismatch_rejected():
    eid = uuid4()
    site_input = SaasSitePricingInput(
        entity_type="factory", entity_id=eid,
        sector="INDUSTRY", base_band_code="INDUSTRY_STARTER_V3", base_amount=149000,
    )
    sel = _mgr_sel()
    result = _ready_result(sel, sites=[site_input])
    cv = _make_commercial_version(
        product_tier="MANAGER",
        pricing_snapshot=result.snapshot,
        pricing_policy_version=result.snapshot.policy_version,
    )
    # Scope with different base_band_code
    wrong_scope = SaasContractSiteScopeV2(
        entity_type="factory", entity_id=eid,
        sector="INDUSTRY", base_band_code="INDUSTRY_BUSINESS_V3",  # mismatch
    )
    with pytest.raises(ValidationError):
        SaasContractStorageBundleV2(commercial_version=cv, site_scopes=[wrong_scope])


def test_S43_custom_zero_site_scopes_accepted():
    cv = _valid_custom_version()
    bundle = SaasContractStorageBundleV2(commercial_version=cv, site_scopes=[])
    assert bundle.site_scopes == []


def test_S44_custom_optional_site_scopes_accepted():
    cv = _valid_custom_version()
    eid = uuid4()
    scope = SaasContractSiteScopeV2(
        entity_type="factory", entity_id=eid,
        sector="INDUSTRY", base_band_code=None,  # CUSTOM: None is allowed
    )
    bundle = SaasContractStorageBundleV2(commercial_version=cv, site_scopes=[scope])
    assert len(bundle.site_scopes) == 1


# ── M01-M08: Mapper Tests ─────────────────────────────────────────────────────

def test_M01_ready_result_to_storage_bundle():
    sel = _mgr_sel()
    result = _ready_result(sel)
    contract_id = uuid4()
    bundle = build_standard_contract_storage_bundle_v2(
        contract_id=contract_id,
        version_no=1,
        selection=sel,
        calculation_result=result,
        effective_from=_now(),
    )
    assert bundle.commercial_version.product_tier == "MANAGER"
    assert bundle.commercial_version.pricing_result_status == "READY"
    assert bundle.commercial_version.pricing_snapshot is not None
    assert bundle.commercial_version.contract_id == contract_id


def test_M02_unresolved_result_rejected():
    """TERM_DISCOUNT_UNRESOLVED 결과는 STANDARD mapper가 거부."""
    none_policy = SaasPricingPolicyV2(
        policy_version="TEST_NONE_DISCOUNT",
        effective_from=date(2026, 9, 28),
        field_base_amount=249000,
        primary_site_rate_bps=10000,
        additional_site_rate_bps=8000,
        worker_brackets=[SaasWorkerRateBracketPolicy(range_from=1, range_to=None, unit_rate=3000)],
        vat_rate_bps=1000,
        term_discounts=[
            SaasTermDiscountPolicy(payment_months=1,  discount_rate_bps=None),
            SaasTermDiscountPolicy(payment_months=3,  discount_rate_bps=None),
            SaasTermDiscountPolicy(payment_months=6,  discount_rate_bps=None),
            SaasTermDiscountPolicy(payment_months=9,  discount_rate_bps=None),
            SaasTermDiscountPolicy(payment_months=12, discount_rate_bps=None),
        ],
    )
    sel = _mgr_sel()
    result = calculate_saas_price_v2(sel, [_site()], none_policy)
    assert result.status == "TERM_DISCOUNT_UNRESOLVED"
    with pytest.raises(SaasContractStorageMapperError):
        build_standard_contract_storage_bundle_v2(
            contract_id=uuid4(),
            version_no=1,
            selection=sel,
            calculation_result=result,
            effective_from=_now(),
        )


def test_M03_custom_result_rejected_by_standard_mapper():
    """CUSTOM_REQUIRED 결과는 STANDARD mapper가 거부."""
    sel = _custom_sel()
    result = calculate_saas_price_v2(sel, [], _resolved_policy())
    assert result.status == "CUSTOM_REQUIRED"
    with pytest.raises(SaasContractStorageMapperError):
        build_standard_contract_storage_bundle_v2(
            contract_id=uuid4(),
            version_no=1,
            selection=sel,
            calculation_result=result,
            effective_from=_now(),
        )


def test_M04_sites_derived_from_snapshot():
    """Site Scopes는 snapshot.sites에서 derive되어야 한다."""
    eid = uuid4()
    site_input = _site(entity_id=eid)
    sel = _mgr_sel()
    result = _ready_result(sel, sites=[site_input])
    bundle = build_standard_contract_storage_bundle_v2(
        contract_id=uuid4(), version_no=1,
        selection=sel, calculation_result=result, effective_from=_now(),
    )
    assert len(bundle.site_scopes) == 1
    assert bundle.site_scopes[0].entity_id == eid
    assert bundle.site_scopes[0].sector == "INDUSTRY"
    assert bundle.site_scopes[0].base_band_code == "INDUSTRY_STARTER_V3"


def test_M05_input_objects_not_mutated():
    """입력 selection, calculation_result가 mapper 호출 후 변경되지 않아야 한다."""
    sel = _mgr_sel()
    site = _site()
    result = _ready_result(sel, sites=[site])

    sel_tier_before = sel.product_tier
    snap_total_before = result.snapshot.total_amount
    sites_before_count = len(result.snapshot.sites)

    build_standard_contract_storage_bundle_v2(
        contract_id=uuid4(), version_no=1,
        selection=sel, calculation_result=result, effective_from=_now(),
    )

    assert sel.product_tier == sel_tier_before
    assert result.snapshot.total_amount == snap_total_before
    assert len(result.snapshot.sites) == sites_before_count


def test_M06_custom_selection_to_custom_bundle():
    sel = _custom_sel(workers=10)
    bundle = build_custom_contract_storage_bundle_v2(
        contract_id=uuid4(), version_no=1,
        selection=sel, effective_from=_now(),
    )
    assert bundle.commercial_version.product_tier == "CUSTOM"
    assert bundle.commercial_version.pricing_result_status == "CUSTOM_REQUIRED"
    assert bundle.commercial_version.worker_capacity == 10


def test_M07_custom_snapshot_always_none():
    sel = _custom_sel()
    bundle = build_custom_contract_storage_bundle_v2(
        contract_id=uuid4(), version_no=1,
        selection=sel, effective_from=_now(),
    )
    assert bundle.commercial_version.pricing_snapshot is None


def test_M08_custom_policy_version_always_none():
    sel = _custom_sel()
    bundle = build_custom_contract_storage_bundle_v2(
        contract_id=uuid4(), version_no=1,
        selection=sel, effective_from=_now(),
    )
    assert bundle.commercial_version.pricing_policy_version is None


# ── D01-D09: DDL Proposal Source Tests ───────────────────────────────────────

DDL_PATH = Path(__file__).parent.parent / "docs" / "2026-09-27_TAI_SAFE_PRICING_V2_BE_OBJ04_DDL_PROPOSAL.sql"


def _ddl() -> str:
    return DDL_PATH.read_text(encoding="utf-8")


def test_D01_two_create_table_statements():
    ddl = _ddl()
    matches = re.findall(r"\bCREATE TABLE\b", ddl, re.IGNORECASE)
    assert len(matches) == 2, f"Expected 2 CREATE TABLE, found {len(matches)}"
    assert "saas_contract_commercial_versions" in ddl
    assert "saas_contract_site_scopes" in ddl


def test_D02_rls_enabled_on_both_tables():
    ddl = _ddl()
    assert "saas_contract_commercial_versions ENABLE ROW LEVEL SECURITY" in ddl
    assert "saas_contract_site_scopes ENABLE ROW LEVEL SECURITY" in ddl


def test_D03_version_unique_constraint_or_index():
    ddl = _ddl()
    assert "contract_id, version_no" in ddl or "(contract_id, version_no)" in ddl


def test_D04_current_version_partial_unique_index():
    ddl = _ddl()
    assert "superseded_at IS NULL" in ddl


def test_D05_duplicate_site_unique_constraint():
    ddl = _ddl()
    assert "commercial_version_id, entity_type, entity_id" in ddl


def test_D06_fk_contracts():
    ddl = _ddl()
    assert "REFERENCES public.contracts" in ddl


def test_D07_no_alter_table_contracts():
    ddl = _ddl()
    lines = [line.strip().upper() for line in ddl.splitlines()]
    for line in lines:
        if "ALTER TABLE" in line and "CONTRACTS" in line:
            # ALTER TABLE public.saas_... is OK; ALTER TABLE contracts/public.contracts is NOT
            assert "SAAS_CONTRACT" in line, (
                f"ALTER TABLE contracts 발견 (금지): {line}"
            )


def test_D08_no_update_delete_truncate_drop():
    """독립 DML/DDL 문장 금지. FK 액션 절(ON DELETE RESTRICT)은 허용."""
    ddl = _ddl().upper()
    # Statement-level keywords only — skip FK action "ON DELETE" / "ON UPDATE"
    lines = ddl.splitlines()
    for line in lines:
        stripped = line.strip()
        # skip FK action lines
        if stripped.startswith("ON DELETE") or stripped.startswith("ON UPDATE"):
            continue
        for kw in ("UPDATE ", "DELETE ", "TRUNCATE ", "DROP "):
            assert kw not in stripped, f"금지 키워드({kw.strip()}) 발견: {stripped}"


def test_D09_no_anon_auth_policy():
    ddl = _ddl().upper()
    # GRANT USAGE 등도 없어야 함
    assert "GRANT ANON" not in ddl
    assert "GRANT AUTHENTICATED" not in ddl
    assert "FOR ROLE ANON" not in ddl
    assert "FOR ROLE AUTHENTICATED" not in ddl
    assert "AS PERMISSIVE" not in ddl or "CREATE POLICY" not in ddl
    # CREATE POLICY 자체가 없어야 함
    assert "CREATE POLICY" not in ddl, "CREATE POLICY 발견 (금지)"
