"""Tests for WO-PRICING-V2-BE-OBJ07 — Change Order Domain V2.

Coverage: C01–C75 (75 tests)
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import List
from uuid import UUID, uuid4

import pytest

from pydantic import ValidationError

from schemas.saas_change_order_v2 import (
    CHANGE_TYPE_ORDER,
    SaasChangeOrderProposalV2,
    SaasCommercialChangeLineV2,
)
from schemas.saas_commercial_fit_v2 import SaasComplianceBandCatalogEntryV2
from schemas.saas_contract_commercial_v2 import SaasContractStorageBundleV2
from schemas.saas_pricing_policy_v2 import (
    SaasPricingPolicyV2,
    SaasTermDiscountPolicy,
    SaasWorkerRateBracketPolicy,
)
from schemas.saas_pricing_v2 import SaasCommercialSelection
from services.saas_change_order_v2 import (
    SaasChangeOrderError,
    evaluate_saas_change_order_v2,
)
from services.saas_contract_storage_mapper_v2 import (
    build_custom_contract_storage_bundle_v2,
    build_standard_contract_storage_bundle_v2,
)
from services.saas_pricing_composer_v2 import (
    SaasPricingCalculationResult,
    SaasSitePricingInput,
    calculate_saas_price_v2,
)

_SVC_SRC = Path(__file__).parent.parent / "services" / "saas_change_order_v2.py"

_CONTRACT = uuid4()
_SITE_A = uuid4()
_SITE_B = uuid4()
_SITE_C = uuid4()


# ── Policy / time ─────────────────────────────────────────────────────────────

def _policy(version: str = "TEST_CO_V1") -> SaasPricingPolicyV2:
    return SaasPricingPolicyV2(
        policy_version=version,
        effective_from=date(2026, 9, 28),
        field_uplift_amount=100_000,
        primary_site_rate_bps=10_000,
        additional_site_rate_bps=8_000,
        worker_brackets=[
            SaasWorkerRateBracketPolicy(range_from=1, range_to=20, unit_rate=3_000),
            SaasWorkerRateBracketPolicy(range_from=21, range_to=50, unit_rate=2_500),
            SaasWorkerRateBracketPolicy(range_from=51, range_to=100, unit_rate=2_000),
            SaasWorkerRateBracketPolicy(range_from=101, range_to=300, unit_rate=1_500),
            SaasWorkerRateBracketPolicy(range_from=301, range_to=None, unit_rate=1_200),
        ],
        vat_rate_bps=1_000,
        term_discounts=[
            SaasTermDiscountPolicy(term_months=1, discount_rate_bps=0),
            SaasTermDiscountPolicy(term_months=3, discount_rate_bps=300),
            SaasTermDiscountPolicy(term_months=6, discount_rate_bps=500),
            SaasTermDiscountPolicy(term_months=9, discount_rate_bps=700),
            SaasTermDiscountPolicy(term_months=12, discount_rate_bps=1_000),
        ],
    )


def _now() -> datetime:
    return datetime(2026, 9, 28, 9, 0, 0, tzinfo=timezone.utc)


def _after() -> datetime:
    return datetime(2026, 9, 28, 10, 0, 0, tzinfo=timezone.utc)


def _before() -> datetime:
    return datetime(2026, 9, 27, 9, 0, 0, tzinfo=timezone.utc)


# ── Catalog ───────────────────────────────────────────────────────────────────

def _catalog() -> List[SaasComplianceBandCatalogEntryV2]:
    return [
        SaasComplianceBandCatalogEntryV2(sector="INDUSTRY", base_band_code="STARTER", sort_order=1),
        SaasComplianceBandCatalogEntryV2(sector="INDUSTRY", base_band_code="BUSINESS", sort_order=2),
        SaasComplianceBandCatalogEntryV2(sector="INDUSTRY", base_band_code="PRO", sort_order=3),
    ]


# ── Site / Calc helpers ───────────────────────────────────────────────────────

def _site(eid: UUID, bbc: str = "STARTER", amount: int = 149_000, sector: str = "INDUSTRY") -> SaasSitePricingInput:
    etype = "site" if sector == "CONSTRUCTION" else "factory"
    return SaasSitePricingInput(entity_type=etype, entity_id=eid, sector=sector,
                                base_band_code=bbc, base_amount=amount)


def _calc(tier, sites, workers=0, term=1, policy=None):
    p = policy or _policy()
    sel = SaasCommercialSelection(
        product_tier=tier,
        pricing_mode="STANDARD" if tier != "CUSTOM" else "CUSTOM",
        worker_capacity=workers, term_months=term,
    )
    return sel, calculate_saas_price_v2(sel, sites, p)


def _ready(tier, sites, workers=0, term=1, policy=None):
    sel, r = _calc(tier, sites, workers, term, policy)
    assert r.status == "READY"
    return sel, r


# ── Bundle builders ───────────────────────────────────────────────────────────

def _cur_mgr(sites, term=1, contract_id=None, effective_from=None, superseded_at=None, policy=None):
    sel, result = _ready("MANAGER", sites, 0, term, policy)
    bundle = build_standard_contract_storage_bundle_v2(
        contract_id=contract_id or _CONTRACT,
        version_no=1, selection=sel, calculation_result=result,
        effective_from=effective_from or _now(),
    )
    if superseded_at is not None:
        new_cv = bundle.commercial_version.model_copy(update={"superseded_at": superseded_at})
        bundle = SaasContractStorageBundleV2.model_construct(
            commercial_version=new_cv, site_scopes=bundle.site_scopes,
        )
    return bundle


def _cur_field(sites, workers=10, term=1, contract_id=None, effective_from=None, policy=None):
    sel, result = _ready("FIELD", sites, workers, term, policy)
    return build_standard_contract_storage_bundle_v2(
        contract_id=contract_id or _CONTRACT,
        version_no=1, selection=sel, calculation_result=result,
        effective_from=effective_from or _now(),
    )


def _cur_custom(contract_id=None):
    sel = SaasCommercialSelection(product_tier="CUSTOM", pricing_mode="CUSTOM", worker_capacity=0, term_months=1)
    return build_custom_contract_storage_bundle_v2(
        contract_id=contract_id or _CONTRACT, version_no=1, selection=sel,
        effective_from=_now(),
    )


def _eval(bundle, sel, result, catalog=None, at=None):
    return evaluate_saas_change_order_v2(
        bundle, sel, result, catalog or _catalog(), at or _after(),
    )


def _code_lines(path: Path) -> str:
    lines = path.read_text().splitlines()
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith(("#", '"""', "- ")))


# ═══════════════════════════════════════════════════════════════════════════════
# C01–C04: NO_CHANGE
# ═══════════════════════════════════════════════════════════════════════════════

def test_C01_identical_manager_no_change():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s), *_ready("MANAGER", s))
    assert r.status == "NO_CHANGE"


def test_C02_identical_field_no_change():
    s = [_site(_SITE_A)]
    r = _eval(_cur_field(s, workers=10), *_ready("FIELD", s, 10))
    assert r.status == "NO_CHANGE"


def test_C03_no_change_delta_zero():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s), *_ready("MANAGER", s))
    assert r.monthly_supply_delta == 0


def test_C04_no_change_prepaid_false():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s), *_ready("MANAGER", s))
    assert r.requires_remaining_term_prepaid is False


# ═══════════════════════════════════════════════════════════════════════════════
# C05–C10: Tier
# ═══════════════════════════════════════════════════════════════════════════════

def test_C05_manager_to_field_change_ready():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s), *_ready("FIELD", s, workers=0))
    assert r.status == "CHANGE_READY"


def test_C06_tier_upgrade_in_change_types():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s), *_ready("FIELD", s, workers=0))
    assert "PRODUCT_TIER_UPGRADE" in r.change_types


def test_C07_field_to_manager_renewal_only():
    s = [_site(_SITE_A)]
    r = _eval(_cur_field(s, workers=10), *_ready("MANAGER", s))
    assert r.status == "RENEWAL_ONLY"
    assert "PRODUCT_TIER_DECREASE" in r.renewal_only_types


def test_C08_manager_to_custom_quote_required():
    s = [_site(_SITE_A)]
    custom_sel, custom_result = _calc("CUSTOM", [])
    r = _eval(_cur_mgr(s), custom_sel, custom_result)
    assert r.status == "CUSTOM_QUOTE_REQUIRED"


def test_C09_field_to_custom_quote_required():
    s = [_site(_SITE_A)]
    custom_sel, custom_result = _calc("CUSTOM", [])
    r = _eval(_cur_field(s, workers=10), custom_sel, custom_result)
    assert r.status == "CUSTOM_QUOTE_REQUIRED"


def test_C10_custom_current_quote_required():
    s = [_site(_SITE_A)]
    r = _eval(_cur_custom(), *_ready("MANAGER", s))
    assert r.status == "CUSTOM_QUOTE_REQUIRED"


# ═══════════════════════════════════════════════════════════════════════════════
# C11–C14: Worker
# ═══════════════════════════════════════════════════════════════════════════════

def test_C11_field_worker_increase_change_ready():
    s = [_site(_SITE_A)]
    r = _eval(_cur_field(s, workers=20), *_ready("FIELD", s, workers=100))
    assert r.status == "CHANGE_READY"
    assert "WORKER_CAPACITY_INCREASE" in r.change_types


def test_C12_field_worker_same_no_change():
    s = [_site(_SITE_A)]
    r = _eval(_cur_field(s, workers=100), *_ready("FIELD", s, workers=100))
    assert r.status == "NO_CHANGE"


def test_C13_field_worker_decrease_renewal_only():
    s = [_site(_SITE_A)]
    r = _eval(_cur_field(s, workers=100), *_ready("FIELD", s, workers=20))
    assert r.status == "RENEWAL_ONLY"
    assert "WORKER_CAPACITY_DECREASE" in r.renewal_only_types


def test_C14_manager_worker_remains_zero():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s), *_ready("MANAGER", s))
    assert r.current_worker_capacity == 0
    assert r.target_worker_capacity == 0


# ═══════════════════════════════════════════════════════════════════════════════
# C15–C20: Site
# ═══════════════════════════════════════════════════════════════════════════════

def test_C15_add_one_site():
    r = _eval(_cur_mgr([_site(_SITE_A)]), *_ready("MANAGER", [_site(_SITE_A), _site(_SITE_B)]))
    assert r.status == "CHANGE_READY"
    assert "SITE_ADDED" in r.change_types


def test_C16_add_multiple_sites_deterministic():
    r = _eval(_cur_mgr([_site(_SITE_A)]),
              *_ready("MANAGER", [_site(_SITE_A), _site(_SITE_B), _site(_SITE_C)]))
    added = [l for l in r.change_lines if l.change_type == "SITE_ADDED"]
    assert len(added) == 2
    ids = [str(l.entity_id) for l in added]
    assert ids == sorted(ids)


def test_C17_remove_site_renewal_only():
    r = _eval(_cur_mgr([_site(_SITE_A), _site(_SITE_B)]), *_ready("MANAGER", [_site(_SITE_A)]))
    assert r.status == "RENEWAL_ONLY"
    assert "SITE_REMOVED" in r.renewal_only_types


def test_C18_current_subset_target_expansion():
    r = _eval(_cur_mgr([_site(_SITE_A)]),
              *_ready("MANAGER", [_site(_SITE_A), _site(_SITE_B)]))
    assert r.status == "CHANGE_READY"


def test_C19_target_subset_current_renewal_only():
    r = _eval(_cur_mgr([_site(_SITE_A), _site(_SITE_B)]), *_ready("MANAGER", [_site(_SITE_A)]))
    assert r.status == "RENEWAL_ONLY"


def test_C20_same_identity_sector_mismatch_rejected():
    bundle = _cur_mgr([_site(_SITE_A, "STARTER", 149_000, "INDUSTRY")])
    sel, result = _ready("MANAGER", [_site(_SITE_A, "STARTER", 149_000, "BUILDING")])
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, result)
    assert exc.value.code == "SITE_CONTEXT_MISMATCH"


# ═══════════════════════════════════════════════════════════════════════════════
# C21–C27: Band
# ═══════════════════════════════════════════════════════════════════════════════

def test_C21_same_band_no_scale_change():
    s = [_site(_SITE_A, "STARTER")]
    r = _eval(_cur_mgr(s), *_ready("MANAGER", s))
    assert "SCALE_BAND_INCREASE" not in r.change_types
    assert "SCALE_BAND_DECREASE" not in r.renewal_only_types


def test_C22_higher_sort_order_scale_band_increase():
    r = _eval(_cur_mgr([_site(_SITE_A, "STARTER")]),
              *_ready("MANAGER", [_site(_SITE_A, "BUSINESS", 200_000)]))
    assert r.status == "CHANGE_READY"
    assert "SCALE_BAND_INCREASE" in r.change_types


def test_C23_lower_sort_order_scale_band_decrease():
    r = _eval(_cur_mgr([_site(_SITE_A, "BUSINESS")]),
              *_ready("MANAGER", [_site(_SITE_A, "STARTER")]))
    assert r.status == "RENEWAL_ONLY"
    assert "SCALE_BAND_DECREASE" in r.renewal_only_types


def test_C24_missing_current_band_rejected():
    partial = [
        SaasComplianceBandCatalogEntryV2(sector="INDUSTRY", base_band_code="STARTER", sort_order=1),
    ]
    bundle = _cur_mgr([_site(_SITE_A, "PRO")])
    sel, result = _ready("MANAGER", [_site(_SITE_A, "STARTER")])
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, result, catalog=partial)
    assert exc.value.code == "BAND_CATALOG_ENTRY_NOT_FOUND"


def test_C25_missing_target_band_rejected():
    partial = [
        SaasComplianceBandCatalogEntryV2(sector="INDUSTRY", base_band_code="STARTER", sort_order=1),
    ]
    bundle = _cur_mgr([_site(_SITE_A, "STARTER")])
    sel, result = _ready("MANAGER", [_site(_SITE_A, "PRO")])
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, result, catalog=partial)
    assert exc.value.code == "BAND_CATALOG_ENTRY_NOT_FOUND"


def test_C26_duplicate_catalog_key_rejected():
    dup = [
        SaasComplianceBandCatalogEntryV2(sector="INDUSTRY", base_band_code="STARTER", sort_order=1),
        SaasComplianceBandCatalogEntryV2(sector="INDUSTRY", base_band_code="STARTER", sort_order=2),
    ]
    s = [_site(_SITE_A)]
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(_cur_mgr(s), *_ready("MANAGER", s), catalog=dup)
    assert exc.value.code == "DUPLICATE_BAND_CATALOG_ENTRY"


def test_C27_ambiguous_sector_sort_order_rejected():
    amb = [
        SaasComplianceBandCatalogEntryV2(sector="INDUSTRY", base_band_code="STARTER", sort_order=1),
        SaasComplianceBandCatalogEntryV2(sector="INDUSTRY", base_band_code="BUSINESS", sort_order=1),
    ]
    s = [_site(_SITE_A)]
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(_cur_mgr(s), *_ready("MANAGER", s), catalog=amb)
    assert exc.value.code == "AMBIGUOUS_BAND_ORDER"


# ═══════════════════════════════════════════════════════════════════════════════
# C28–C31: Term
# ═══════════════════════════════════════════════════════════════════════════════

def test_C28_same_term_allowed():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s, term=1), *_ready("MANAGER", s, term=1))
    assert r.status == "NO_CHANGE"


def test_C29_12_to_6_renewal_only():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s, term=12), *_ready("MANAGER", s, term=6))
    assert r.status == "RENEWAL_ONLY"
    assert "TERM_CHANGE" in r.renewal_only_types


def test_C30_6_to_12_renewal_only():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s, term=6), *_ready("MANAGER", s, term=12))
    assert r.status == "RENEWAL_ONLY"
    assert "TERM_CHANGE" in r.renewal_only_types


def test_C31_term_change_never_change_ready():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s, term=1), *_ready("MANAGER", s, term=12))
    assert r.status != "CHANGE_READY"


# ═══════════════════════════════════════════════════════════════════════════════
# C32–C33: Policy Version
# ═══════════════════════════════════════════════════════════════════════════════

def test_C32_same_policy_version_allowed():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s, policy=_policy("V1")), *_ready("MANAGER", s, policy=_policy("V1")))
    assert r.current_policy_version == "V1"
    assert r.target_policy_version == "V1"


def test_C33_policy_version_mismatch_rejected():
    s = [_site(_SITE_A)]
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(_cur_mgr(s, policy=_policy("V1")), *_ready("MANAGER", s, policy=_policy("V2")))
    assert exc.value.code == "POLICY_VERSION_MISMATCH"


# ═══════════════════════════════════════════════════════════════════════════════
# C34–C37: Target Readiness
# ═══════════════════════════════════════════════════════════════════════════════

def test_C34_ready_target_accepted():
    s = [_site(_SITE_A, "BUSINESS", 200_000)]
    bundle = _cur_mgr([_site(_SITE_A, "STARTER")])
    sel, result = _ready("MANAGER", s)
    r = _eval(bundle, sel, result)
    assert r.status in ("NO_CHANGE", "CHANGE_READY", "RENEWAL_ONLY")


def test_C35_term_discount_unresolved_rejected():
    s = [_site(_SITE_A)]
    bundle = _cur_mgr(s)
    sel, result = _ready("MANAGER", s)
    bad = result.model_copy(update={"status": "TERM_DISCOUNT_UNRESOLVED"})
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, bad)
    assert exc.value.code == "TARGET_PRICING_NOT_READY"


def test_C36_custom_required_target_quote_required():
    s = [_site(_SITE_A)]
    custom_sel, custom_result = _calc("CUSTOM", [])
    assert custom_result.status == "CUSTOM_REQUIRED"
    r = _eval(_cur_mgr(s), custom_sel, custom_result)
    assert r.status == "CUSTOM_QUOTE_REQUIRED"


def test_C37_ready_snapshot_none_rejected():
    s = [_site(_SITE_A)]
    bundle = _cur_mgr(s)
    sel, result = _ready("MANAGER", s)
    bad = result.model_copy(update={"snapshot": None})
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, bad)
    assert exc.value.code == "TARGET_PRICING_NOT_READY"


# ═══════════════════════════════════════════════════════════════════════════════
# C38–C41: Snapshot Integrity
# ═══════════════════════════════════════════════════════════════════════════════

def test_C38_selection_tier_mismatch_rejected():
    s = [_site(_SITE_A)]
    bundle = _cur_mgr(s)
    sel, result = _ready("FIELD", s, workers=0)
    bad_snap = result.snapshot.model_copy(update={"product_tier": "MANAGER"})
    bad = result.model_copy(update={"snapshot": bad_snap})
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, bad)
    assert exc.value.code == "TARGET_SNAPSHOT_MISMATCH"


def test_C39_selection_worker_mismatch_rejected():
    s = [_site(_SITE_A)]
    bundle = _cur_mgr(s)
    sel, result = _ready("FIELD", s, workers=10)
    bad_worker = result.snapshot.worker.model_copy(update={"capacity": 999})
    bad_snap = result.snapshot.model_copy(update={"worker": bad_worker})
    bad = result.model_copy(update={"snapshot": bad_snap})
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, bad)
    assert exc.value.code == "TARGET_SNAPSHOT_MISMATCH"


def test_C40_selection_term_mismatch_rejected():
    s = [_site(_SITE_A)]
    bundle = _cur_mgr(s, term=1)
    sel, result = _ready("MANAGER", s, term=1)
    bad_snap = result.snapshot.model_copy(update={"term_months": 3})
    bad = result.model_copy(update={"snapshot": bad_snap})
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, bad)
    assert exc.value.code == "TARGET_SNAPSHOT_MISMATCH"


def test_C41_result_monthly_vs_snapshot_mismatch_rejected():
    s = [_site(_SITE_A)]
    bundle = _cur_mgr(s)
    sel, result = _ready("MANAGER", s)
    bad = result.model_copy(update={"monthly_supply_amount": result.monthly_supply_amount + 1})
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, bad)
    assert exc.value.code == "TARGET_SNAPSHOT_MISMATCH"


# ═══════════════════════════════════════════════════════════════════════════════
# C42–C45: Delta
# ═══════════════════════════════════════════════════════════════════════════════

def test_C42_monthly_delta_is_target_minus_current():
    bundle = _cur_mgr([_site(_SITE_A, "STARTER")])
    sel, result = _ready("MANAGER", [_site(_SITE_A, "BUSINESS", 200_000)])
    r = _eval(bundle, sel, result)
    assert r.status == "CHANGE_READY"
    assert r.monthly_supply_delta == r.target_monthly_supply_amount - r.current_monthly_supply_amount


def test_C43_valid_expansion_delta_positive():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s), *_ready("FIELD", s, workers=0))
    assert r.monthly_supply_delta is not None
    assert r.monthly_supply_delta > 0


def test_C44_expansion_with_zero_delta_rejected():
    s1 = [_site(_SITE_A)]
    s2 = [_site(_SITE_A), _site(_SITE_B)]
    bundle = _cur_mgr(s1)
    sel, result = _ready("MANAGER", s2)
    cur_monthly = bundle.commercial_version.pricing_snapshot.monthly_supply_amount
    bad_snap = result.snapshot.model_copy(update={"monthly_supply_amount": cur_monthly})
    bad = result.model_copy(update={"monthly_supply_amount": cur_monthly, "snapshot": bad_snap})
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, bad)
    assert exc.value.code == "INVALID_CHANGE_DELTA"


def test_C45_expansion_with_negative_delta_rejected():
    s1 = [_site(_SITE_A)]
    s2 = [_site(_SITE_A), _site(_SITE_B)]
    bundle = _cur_mgr(s1)
    sel, result = _ready("MANAGER", s2)
    cur_monthly = bundle.commercial_version.pricing_snapshot.monthly_supply_amount
    low = max(1, cur_monthly - 50_000)
    bad_snap = result.snapshot.model_copy(update={"monthly_supply_amount": low})
    bad = result.model_copy(update={"monthly_supply_amount": low, "snapshot": bad_snap})
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, bad)
    assert exc.value.code == "INVALID_CHANGE_DELTA"


# ═══════════════════════════════════════════════════════════════════════════════
# C46–C50: Composite Changes
# ═══════════════════════════════════════════════════════════════════════════════

def test_C46_tier_plus_site():
    r = _eval(_cur_mgr([_site(_SITE_A)]),
              *_ready("FIELD", [_site(_SITE_A), _site(_SITE_B)], workers=0))
    assert r.status == "CHANGE_READY"
    assert "PRODUCT_TIER_UPGRADE" in r.change_types
    assert "SITE_ADDED" in r.change_types


def test_C47_site_plus_scale():
    r = _eval(_cur_mgr([_site(_SITE_A, "STARTER")]),
              *_ready("MANAGER", [_site(_SITE_A, "BUSINESS"), _site(_SITE_B, "STARTER")]))
    assert r.status == "CHANGE_READY"
    assert "SITE_ADDED" in r.change_types
    assert "SCALE_BAND_INCREASE" in r.change_types


def test_C48_scale_plus_worker():
    r = _eval(_cur_field([_site(_SITE_A, "STARTER")], workers=10),
              *_ready("FIELD", [_site(_SITE_A, "BUSINESS")], workers=50))
    assert r.status == "CHANGE_READY"
    assert "SCALE_BAND_INCREASE" in r.change_types
    assert "WORKER_CAPACITY_INCREASE" in r.change_types


def test_C49_all_four_expansion_types():
    r = _eval(_cur_mgr([_site(_SITE_A, "STARTER")]),
              *_ready("FIELD", [_site(_SITE_A, "BUSINESS"), _site(_SITE_B, "STARTER")], workers=20))
    assert r.status == "CHANGE_READY"
    assert set(r.change_types) == {
        "PRODUCT_TIER_UPGRADE", "SITE_ADDED", "SCALE_BAND_INCREASE", "WORKER_CAPACITY_INCREASE"
    }


def test_C50_canonical_change_type_order():
    r = _eval(_cur_mgr([_site(_SITE_A, "STARTER")]),
              *_ready("FIELD", [_site(_SITE_A, "BUSINESS"), _site(_SITE_B, "STARTER")], workers=20))
    order_index = {t: i for i, t in enumerate(CHANGE_TYPE_ORDER)}
    positions = [order_index[t] for t in r.change_types]
    assert positions == sorted(positions)


# ═══════════════════════════════════════════════════════════════════════════════
# C51–C54: Mixed Increase + Decrease → RENEWAL_ONLY
# ═══════════════════════════════════════════════════════════════════════════════

def test_C51_site_add_plus_worker_decrease_renewal_only():
    r = _eval(_cur_field([_site(_SITE_A)], workers=100),
              *_ready("FIELD", [_site(_SITE_A), _site(_SITE_B)], workers=20))
    assert r.status == "RENEWAL_ONLY"
    assert "SITE_ADDED" in r.change_types
    assert "WORKER_CAPACITY_DECREASE" in r.renewal_only_types


def test_C52_scale_increase_plus_site_removal_renewal_only():
    r = _eval(_cur_mgr([_site(_SITE_A, "STARTER"), _site(_SITE_B, "STARTER")]),
              *_ready("MANAGER", [_site(_SITE_A, "BUSINESS")]))
    assert r.status == "RENEWAL_ONLY"
    assert "SCALE_BAND_INCREASE" in r.change_types
    assert "SITE_REMOVED" in r.renewal_only_types


def test_C53_renewal_types_retained_in_result():
    r = _eval(_cur_mgr([_site(_SITE_A, "BUSINESS")]),
              *_ready("MANAGER", [_site(_SITE_A, "STARTER")]))
    assert r.status == "RENEWAL_ONLY"
    assert len(r.renewal_only_types) > 0


def test_C54_no_payable_delta_for_renewal_only():
    r = _eval(_cur_mgr([_site(_SITE_A, "BUSINESS")]),
              *_ready("MANAGER", [_site(_SITE_A, "STARTER")]))
    assert r.status == "RENEWAL_ONLY"
    assert r.monthly_supply_delta is None


# ═══════════════════════════════════════════════════════════════════════════════
# C55–C56: Version Validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_C55_superseded_current_version_rejected():
    s = [_site(_SITE_A)]
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(_cur_mgr(s, superseded_at=_now()), *_ready("MANAGER", s))
    assert exc.value.code == "NON_CURRENT_COMMERCIAL_VERSION"


def test_C56_requested_effective_before_current_rejected():
    s = [_site(_SITE_A)]
    bundle = _cur_mgr(s, effective_from=_now())
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, *_ready("FIELD", s, workers=0), at=_before())
    assert exc.value.code == "CHANGE_EFFECTIVE_BEFORE_CURRENT_VERSION"


# ═══════════════════════════════════════════════════════════════════════════════
# C57–C60: Determinism
# ═══════════════════════════════════════════════════════════════════════════════

def test_C57_site_input_reorder_same_structural_result():
    bundle = _cur_mgr([_site(_SITE_A, "STARTER")])
    sel1, r1 = _ready("MANAGER", [_site(_SITE_A, "BUSINESS"), _site(_SITE_B, "STARTER")])
    sel2, r2 = _ready("MANAGER", [_site(_SITE_B, "STARTER"), _site(_SITE_A, "BUSINESS")])
    p1 = _eval(bundle, sel1, r1)
    p2 = _eval(bundle, sel2, r2)
    assert p1.status == p2.status
    assert set(p1.change_types) == set(p2.change_types)


def test_C58_catalog_reorder_same_result():
    bundle = _cur_mgr([_site(_SITE_A, "STARTER")])
    sel, result = _ready("MANAGER", [_site(_SITE_A, "BUSINESS", 200_000)])
    r1 = _eval(bundle, sel, result, catalog=_catalog())
    r2 = _eval(bundle, sel, result, catalog=list(reversed(_catalog())))
    assert r1.status == r2.status
    assert r1.monthly_supply_delta == r2.monthly_supply_delta


def test_C59_same_input_twice_exact_output():
    bundle = _cur_mgr([_site(_SITE_A, "STARTER")])
    sel, result = _ready("MANAGER", [_site(_SITE_A, "BUSINESS", 200_000)])
    r1 = _eval(bundle, sel, result)
    r2 = _eval(bundle, sel, result)
    assert r1.model_dump() == r2.model_dump()


def test_C60_input_objects_unchanged():
    bundle = _cur_mgr([_site(_SITE_A, "STARTER")])
    sel, result = _ready("MANAGER", [_site(_SITE_A, "BUSINESS", 200_000)])
    scopes_before = list(bundle.site_scopes)
    snap_before = result.snapshot.monthly_supply_amount
    _eval(bundle, sel, result)
    assert list(bundle.site_scopes) == scopes_before
    assert result.snapshot.monthly_supply_amount == snap_before


# ═══════════════════════════════════════════════════════════════════════════════
# C61–C70: Source Guards
# ═══════════════════════════════════════════════════════════════════════════════

def test_C61_no_db_io():
    src = _SVC_SRC.read_text()
    for kw in ["supabase", "get_supabase", "execute_sql", "psycopg"]:
        assert kw not in src, f"DB I/O: {kw}"


def test_C62_no_payment_prepare():
    code = _code_lines(_SVC_SRC)
    for kw in ["run_inicis_prepare", "PrepareBody", "payment_helpers", "paid_amount"]:
        assert kw not in code, f"Payment: {kw}"


def test_C63_no_payment_service():
    src = _SVC_SRC.read_text()
    assert "payment_svc" not in src
    assert "payment_post_process" not in src


def test_C64_no_vat_calculation():
    code = _code_lines(_SVC_SRC)
    for kw in ["vat_rate_bps", "vat_amount"]:
        assert kw not in code, f"VAT: {kw}"


def test_C65_no_proration():
    code = _code_lines(_SVC_SRC)
    for kw in ["days_remaining", "months_remaining", "daily_rate", "prorated_amount"]:
        assert kw not in code, f"Proration: {kw}"


def test_C66_no_tier_upgrade_svc():
    code = _code_lines(_SVC_SRC)
    assert "tier_upgrade_svc" not in code


def test_C67_no_commercial_fit_gate_call():
    src = _SVC_SRC.read_text()
    assert "saas_commercial_fit_gate_v2" not in src
    assert "evaluate_saas_commercial_fit" not in src


def test_C68_no_entitlement_call():
    src = _SVC_SRC.read_text()
    assert "saas_entitlement_gate_v2" not in src
    assert "evaluate_saas_entitlement" not in src


def test_C69_no_router():
    src = _SVC_SRC.read_text()
    for kw in ["APIRouter", "from routers", "import routers"]:
        assert kw not in src, f"Router: {kw}"


def test_C70_no_contracts_mutation():
    code = _code_lines(_SVC_SRC)
    for kw in [".insert(", ".update(", ".delete(", ".upsert("]:
        assert kw not in code, f"Mutation: {kw}"


# ═══════════════════════════════════════════════════════════════════════════════
# C71–C75: PATCH1 — pricing_mode + type hardening
# ═══════════════════════════════════════════════════════════════════════════════

def test_C71_pricing_mode_mismatch_rejected():
    s = [_site(_SITE_A)]
    bundle = _cur_mgr(s)
    sel, result = _ready("MANAGER", s)
    bad_snap = result.snapshot.model_copy(update={"pricing_mode": "CUSTOM"})
    bad = result.model_copy(update={"snapshot": bad_snap})
    with pytest.raises(SaasChangeOrderError) as exc:
        _eval(bundle, sel, bad)
    assert exc.value.code == "TARGET_SNAPSHOT_MISMATCH"


def test_C72_matching_pricing_mode_accepted():
    s = [_site(_SITE_A)]
    r = _eval(_cur_mgr(s), *_ready("MANAGER", s))
    assert r.status == "NO_CHANGE"


def test_C73_invalid_change_type_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialChangeLineV2(change_type="UPGRADE")


def test_C74_proposal_invalid_product_tier_rejected():
    with pytest.raises(ValidationError):
        SaasChangeOrderProposalV2(
            status="NO_CHANGE",
            contract_id=_CONTRACT,
            current_version_no=1,
            proposed_next_version_no=2,
            current_product_tier="STANDARD",
            target_product_tier="MANAGER",
            current_worker_capacity=0,
            target_worker_capacity=0,
            current_site_count=1,
            target_site_count=1,
            change_types=[],
            renewal_only_types=[],
            change_lines=[],
            current_monthly_supply_amount=None,
            target_monthly_supply_amount=None,
            monthly_supply_delta=0,
            requires_remaining_term_prepaid=False,
            current_policy_version="V1",
            target_policy_version="V1",
            current_term_months=1,
            target_term_months=1,
            requested_effective_at=_now(),
        )


def test_C75_change_line_invalid_product_tier_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialChangeLineV2(
            change_type="PRODUCT_TIER_UPGRADE",
            from_product_tier="STARTER",
            to_product_tier="FIELD",
        )
