"""WO-PRICING-V2-BE-OBJ01 — Commercial Domain Contract V2 테스트.

T01~T25 모두 DB / Runtime 없이 순수 Pydantic validation 검증.
"""
import uuid

import pytest
from pydantic import ValidationError

from schemas.saas_pricing_v2 import (
    SCHEMA_VERSION,
    SaasCommercialSelection,
    SaasPricingSnapshotV2,
    SaasSiteScope,
    SaasWorkerBracketLine,
    SaasWorkerPricingSnapshot,
)

_UUID = str(uuid.uuid4())

# ── helpers ───────────────────────────────────────────────────────────────────

def _site(sector="INDUSTRY", entity_type="factory", rate_bps=10000):
    return dict(
        entity_type=entity_type,
        entity_id=_UUID,
        sector=sector,
        base_band_code="INDUSTRY_STARTER",
        base_amount=149000,
        is_primary=True,
        applied_rate_bps=rate_bps,
        final_site_amount=149000,
    )

def _worker(capacity=0, amount=0, brackets=None):
    return dict(capacity=capacity, amount=amount, brackets=brackets or [])

def _snapshot(**overrides):
    base = dict(
        schema_version=SCHEMA_VERSION,
        policy_version="2026-09-27",
        product_tier="MANAGER",
        pricing_mode="STANDARD",
        sites=[_site()],
        worker=_worker(),
        term_months=1,
        term_discount_rate_bps=0,
        monthly_supply_amount=149000,
        prepaid_supply_amount=149000,
        vat_rate_bps=1000,
        vat_amount=14900,
        total_amount=163900,
    )
    base.update(overrides)
    return base


# ── T01 MANAGER valid ─────────────────────────────────────────────────────────

def test_T01_manager_valid():
    sel = SaasCommercialSelection(
        product_tier="MANAGER",
        pricing_mode="STANDARD",
        worker_capacity=0,
        term_months=1,
    )
    assert sel.product_tier == "MANAGER"


# ── T02 FIELD valid ───────────────────────────────────────────────────────────

def test_T02_field_valid():
    sel = SaasCommercialSelection(
        product_tier="FIELD",
        pricing_mode="STANDARD",
        worker_capacity=5,
        term_months=12,
    )
    assert sel.product_tier == "FIELD"


# ── T03 CUSTOM + STANDARD rejected (K06) — CUSTOM tier는 CUSTOM mode만 허용 ───

def test_T03_custom_standard_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="CUSTOM",
            pricing_mode="STANDARD",
            worker_capacity=0,
            term_months=1,
        )


# ── T04 STARTER product_tier rejected ────────────────────────────────────────

def test_T04_starter_product_tier_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="STARTER",
            pricing_mode="STANDARD",
            worker_capacity=0,
            term_months=1,
        )


# ── T05 MANAGER + worker_capacity > 0 rejected ───────────────────────────────

def test_T05_manager_with_workers_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="MANAGER",
            pricing_mode="STANDARD",
            worker_capacity=1,
            term_months=1,
        )


# ── T06 FIELD + worker_capacity 0 accepted ───────────────────────────────────

def test_T06_field_worker_capacity_zero_accepted():
    sel = SaasCommercialSelection(
        product_tier="FIELD",
        pricing_mode="STANDARD",
        worker_capacity=0,
        term_months=1,
    )
    assert sel.worker_capacity == 0


# ── T07~T11 term months accepted ─────────────────────────────────────────────

@pytest.mark.parametrize("months", [1, 3, 6, 9, 12])
def test_T07_to_T11_term_months_accepted(months):
    sel = SaasCommercialSelection(
        product_tier="MANAGER",
        pricing_mode="STANDARD",
        worker_capacity=0,
        term_months=months,
    )
    assert sel.term_months == months


# ── T12 term 2 rejected ───────────────────────────────────────────────────────

def test_T12_term_2_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="MANAGER",
            pricing_mode="STANDARD",
            worker_capacity=0,
            term_months=2,
        )


# ── T13 INDUSTRY + factory accepted ──────────────────────────────────────────

def test_T13_industry_factory_accepted():
    scope = SaasSiteScope(**_site(sector="INDUSTRY", entity_type="factory"))
    assert scope.entity_type == "factory"


# ── T14 BUILDING + factory accepted ──────────────────────────────────────────

def test_T14_building_factory_accepted():
    scope = SaasSiteScope(**_site(sector="BUILDING", entity_type="factory"))
    assert scope.entity_type == "factory"


# ── T15 CONSTRUCTION + site accepted ─────────────────────────────────────────

def test_T15_construction_site_accepted():
    scope = SaasSiteScope(**_site(sector="CONSTRUCTION", entity_type="site"))
    assert scope.entity_type == "site"


# ── T16 INDUSTRY + site rejected ─────────────────────────────────────────────

def test_T16_industry_site_rejected():
    with pytest.raises(ValidationError):
        SaasSiteScope(**_site(sector="INDUSTRY", entity_type="site"))


# ── T17 CONSTRUCTION + factory rejected ──────────────────────────────────────

def test_T17_construction_factory_rejected():
    with pytest.raises(ValidationError):
        SaasSiteScope(**_site(sector="CONSTRUCTION", entity_type="factory"))


# ── T18 negative money rejected ──────────────────────────────────────────────

def test_T18_negative_money_rejected():
    with pytest.raises(ValidationError):
        data = _site()
        data["base_amount"] = -1
        SaasSiteScope(**data)


# ── T19 float money prohibition verified ─────────────────────────────────────

def test_T19_float_money_rejected():
    with pytest.raises(ValidationError):
        SaasSiteScope(
            entity_type="factory",
            entity_id=_UUID,
            sector="INDUSTRY",
            base_band_code="INDUSTRY_STARTER",
            base_amount=149000.5,  # float
            is_primary=True,
            applied_rate_bps=10000,
            final_site_amount=149000,
        )


# ── T20 applied_rate_bps > 10000 rejected ────────────────────────────────────

def test_T20_rate_bps_over_max_rejected():
    with pytest.raises(ValidationError):
        SaasSiteScope(**_site(rate_bps=10001))


# ── T21 schema_version canonical value verified ──────────────────────────────

def test_T21_schema_version_canonical():
    snap = SaasPricingSnapshotV2(**_snapshot())
    assert snap.schema_version == SCHEMA_VERSION
    assert snap.schema_version == "SAAS_PRICING_V2"


# ── T22 policy_version independent from schema_version ───────────────────────

def test_T22_policy_version_independent():
    snap = SaasPricingSnapshotV2(**_snapshot(policy_version="2027-01-01"))
    assert snap.policy_version == "2027-01-01"
    assert snap.schema_version == SCHEMA_VERSION
    assert snap.policy_version != snap.schema_version


# ── T23 worker bracket open-ended range_to=null accepted ─────────────────────

def test_T23_worker_bracket_open_range_accepted():
    bracket = SaasWorkerBracketLine(
        range_from=51,
        range_to=None,
        unit_rate=1200,
        units=10,
        amount=12000,
    )
    assert bracket.range_to is None


# ── T24 pricing_mode STANDARD accepted ───────────────────────────────────────

def test_T24_pricing_mode_standard_accepted():
    sel = SaasCommercialSelection(
        product_tier="MANAGER",
        pricing_mode="STANDARD",
        worker_capacity=0,
        term_months=1,
    )
    assert sel.pricing_mode == "STANDARD"


# ── T25 MANAGER + CUSTOM rejected (K04) ──────────────────────────────────────

def test_T25_manager_custom_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="MANAGER",
            pricing_mode="CUSTOM",
            worker_capacity=0,
            term_months=1,
        )


# ── Additional guards ─────────────────────────────────────────────────────────

def test_wrong_schema_version_rejected():
    with pytest.raises(ValidationError):
        SaasPricingSnapshotV2(**_snapshot(schema_version="SAAS_PRICING_V1"))


def test_snapshot_negative_total_rejected():
    with pytest.raises(ValidationError):
        SaasPricingSnapshotV2(**_snapshot(total_amount=-1))


def test_worker_snapshot_manager_capacity_zero():
    snap = SaasWorkerPricingSnapshot(capacity=0, amount=0, brackets=[])
    assert snap.capacity == 0


# ── PATCH-1: Strict Integer Contract ─────────────────────────────────────────

# P01~P03 base_amount strict

def test_P01_base_amount_integral_float_rejected():
    with pytest.raises(ValidationError):
        data = _site()
        data["base_amount"] = 149000.0
        SaasSiteScope(**data)


def test_P02_base_amount_string_rejected():
    with pytest.raises(ValidationError):
        data = _site()
        data["base_amount"] = "149000"
        SaasSiteScope(**data)


def test_P03_base_amount_bool_rejected():
    with pytest.raises(ValidationError):
        data = _site()
        data["base_amount"] = True
        SaasSiteScope(**data)


# P04 final_site_amount strict

def test_P04_final_site_amount_float_rejected():
    with pytest.raises(ValidationError):
        data = _site()
        data["final_site_amount"] = 149000.0
        SaasSiteScope(**data)


# P05~P06 applied_rate_bps strict

def test_P05_applied_rate_bps_float_rejected():
    with pytest.raises(ValidationError):
        SaasSiteScope(**_site(rate_bps=8000.0))


def test_P06_applied_rate_bps_bool_rejected():
    with pytest.raises(ValidationError):
        SaasSiteScope(**_site(rate_bps=True))


# P07~P08 worker_capacity strict

def test_P07_worker_capacity_float_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="FIELD",
            pricing_mode="STANDARD",
            worker_capacity=100.0,
            term_months=1,
        )


def test_P08_worker_capacity_bool_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="FIELD",
            pricing_mode="STANDARD",
            worker_capacity=True,
            term_months=1,
        )


# P09~P10 term_months strict

def test_P09_term_months_float_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="MANAGER",
            pricing_mode="STANDARD",
            worker_capacity=0,
            term_months=12.0,
        )


def test_P10_term_months_bool_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="MANAGER",
            pricing_mode="STANDARD",
            worker_capacity=0,
            term_months=True,
        )


# P11~P13 worker bracket strict

def test_P11_unit_rate_float_rejected():
    with pytest.raises(ValidationError):
        SaasWorkerBracketLine(range_from=1, range_to=20, unit_rate=3000.0, units=10, amount=30000)


def test_P12_units_float_rejected():
    with pytest.raises(ValidationError):
        SaasWorkerBracketLine(range_from=1, range_to=20, unit_rate=3000, units=20.0, amount=60000)


def test_P13_bracket_amount_float_rejected():
    with pytest.raises(ValidationError):
        SaasWorkerBracketLine(range_from=1, range_to=20, unit_rate=3000, units=20, amount=60000.0)


# P14~P15 range_to strict

def test_P14_range_to_float_rejected():
    with pytest.raises(ValidationError):
        SaasWorkerBracketLine(range_from=1, range_to=20.0, unit_rate=3000, units=20, amount=60000)


def test_P15_range_to_none_accepted():
    bracket = SaasWorkerBracketLine(range_from=301, range_to=None, unit_rate=1200, units=10, amount=12000)
    assert bracket.range_to is None


# P16~P20 snapshot integer fields strict

def test_P16_monthly_supply_float_rejected():
    with pytest.raises(ValidationError):
        SaasPricingSnapshotV2(**_snapshot(monthly_supply_amount=149000.0))


def test_P17_prepaid_supply_float_rejected():
    with pytest.raises(ValidationError):
        SaasPricingSnapshotV2(**_snapshot(prepaid_supply_amount=149000.0))


def test_P18_vat_rate_bps_float_rejected():
    with pytest.raises(ValidationError):
        SaasPricingSnapshotV2(**_snapshot(vat_rate_bps=1000.0))


def test_P19_vat_amount_float_rejected():
    with pytest.raises(ValidationError):
        SaasPricingSnapshotV2(**_snapshot(vat_amount=14900.0))


def test_P20_total_amount_float_rejected():
    with pytest.raises(ValidationError):
        SaasPricingSnapshotV2(**_snapshot(total_amount=163900.0))


# ── CANONICAL TIER CORRECTION: K01~K14 ────────────────────────────────────────

# K01 MANAGER + STANDARD accepted
def test_K01_manager_standard_accepted():
    sel = SaasCommercialSelection(
        product_tier="MANAGER", pricing_mode="STANDARD", worker_capacity=0, term_months=1
    )
    assert sel.product_tier == "MANAGER"
    assert sel.pricing_mode == "STANDARD"


# K02 FIELD + STANDARD accepted
def test_K02_field_standard_accepted():
    sel = SaasCommercialSelection(
        product_tier="FIELD", pricing_mode="STANDARD", worker_capacity=5, term_months=1
    )
    assert sel.product_tier == "FIELD"
    assert sel.pricing_mode == "STANDARD"


# K03 CUSTOM + CUSTOM accepted
def test_K03_custom_custom_accepted():
    sel = SaasCommercialSelection(
        product_tier="CUSTOM", pricing_mode="CUSTOM", worker_capacity=0, term_months=1
    )
    assert sel.product_tier == "CUSTOM"
    assert sel.pricing_mode == "CUSTOM"


# K04 MANAGER + CUSTOM rejected
def test_K04_manager_custom_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="MANAGER", pricing_mode="CUSTOM", worker_capacity=0, term_months=1
        )


# K05 FIELD + CUSTOM rejected
def test_K05_field_custom_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="FIELD", pricing_mode="CUSTOM", worker_capacity=5, term_months=1
        )


# K06 CUSTOM + STANDARD rejected
def test_K06_custom_standard_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="CUSTOM", pricing_mode="STANDARD", worker_capacity=0, term_months=1
        )


# K07 CUSTOM worker_capacity=0 accepted
def test_K07_custom_worker_capacity_zero_accepted():
    sel = SaasCommercialSelection(
        product_tier="CUSTOM", pricing_mode="CUSTOM", worker_capacity=0, term_months=1
    )
    assert sel.worker_capacity == 0


# K08 CUSTOM worker_capacity>0 accepted
def test_K08_custom_worker_capacity_positive_accepted():
    sel = SaasCommercialSelection(
        product_tier="CUSTOM", pricing_mode="CUSTOM", worker_capacity=300, term_months=1
    )
    assert sel.worker_capacity == 300


# K09 STARTER still rejected
def test_K09_starter_still_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="STARTER", pricing_mode="STANDARD", worker_capacity=0, term_months=1
        )


# K10 BUSINESS rejected
def test_K10_business_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="BUSINESS", pricing_mode="STANDARD", worker_capacity=0, term_months=1
        )


# K11 PRO rejected
def test_K11_pro_rejected():
    with pytest.raises(ValidationError):
        SaasCommercialSelection(
            product_tier="PRO", pricing_mode="STANDARD", worker_capacity=0, term_months=1
        )


# K12 CUSTOM snapshot rejected
def test_K12_custom_snapshot_rejected():
    with pytest.raises(ValidationError):
        SaasPricingSnapshotV2(**_snapshot(product_tier="CUSTOM"))


# K13 MANAGER + STANDARD snapshot accepted
def test_K13_manager_standard_snapshot_accepted():
    snap = SaasPricingSnapshotV2(**_snapshot(product_tier="MANAGER", pricing_mode="STANDARD"))
    assert snap.product_tier == "MANAGER"


# K14 FIELD + STANDARD snapshot accepted
def test_K14_field_standard_snapshot_accepted():
    snap = SaasPricingSnapshotV2(**_snapshot(product_tier="FIELD", pricing_mode="STANDARD"))
    assert snap.product_tier == "FIELD"
