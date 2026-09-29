"""WO-PRICING-V2-BE-OBJ03 — Pricing Composer V2 테스트.

C01~C14  Site 계산
W00~W1000 Worker 누진 계산
T01/T03/T06/T09/T12 Term Unresolved
R01~R06  READY 계산
Floor    절삭 규칙
Tier     Product Tier 분기
Custom   CUSTOM 처리
Integrity 불변성·순서 독립성
"""
from datetime import date
from typing import Optional
from uuid import UUID

import pytest
from pydantic import ValidationError

from schemas.saas_pricing_policy_v2 import (
    SaasPricingPolicyV2,
    SaasTermDiscountPolicy,
    SaasWorkerRateBracketPolicy,
    get_canonical_pricing_policy_v2,
)
from schemas.saas_pricing_v2 import SaasCommercialSelection
from services.saas_pricing_composer_v2 import (
    SaasPricingCalculationResult,
    SaasPricingComposerError,
    SaasSitePricingInput,
    calculate_saas_price_v2,
)

# ── Fixed UUIDs ────────────────────────────────────────────────────────────────

_UUID_A = UUID("00000000-0000-0000-0000-000000000001")
_UUID_B = UUID("00000000-0000-0000-0000-000000000002")
_UUID_C = UUID("00000000-0000-0000-0000-000000000003")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sel(
    product_tier: str = "MANAGER",
    pricing_mode: str = "STANDARD",
    worker_capacity: int = 0,
    payment_months: int = 1,
) -> SaasCommercialSelection:
    return SaasCommercialSelection(
        product_tier=product_tier,
        pricing_mode=pricing_mode,
        worker_capacity=worker_capacity,
        payment_months=payment_months,
    )


def _site(
    entity_id: UUID = _UUID_A,
    sector: str = "INDUSTRY",
    entity_type: str = "factory",
    base_band_code: str = "INDUSTRY_STARTER",
    base_amount: int = 149000,
) -> SaasSitePricingInput:
    return SaasSitePricingInput(
        entity_type=entity_type,
        entity_id=entity_id,
        sector=sector,
        base_band_code=base_band_code,
        base_amount=base_amount,
    )


def _resolved_policy(
    term1_bps: Optional[int] = 0,
    term3_bps: Optional[int] = None,
    term6_bps: Optional[int] = None,
    term9_bps: Optional[int] = None,
    term12_bps: Optional[int] = 1000,
) -> SaasPricingPolicyV2:
    """테스트 전용 Policy. canonical term discounts 일부를 resolved로 설정."""
    return SaasPricingPolicyV2(
        policy_version="TEST_RESOLVED_POLICY",
        effective_from=date(2026, 9, 28),
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
            SaasTermDiscountPolicy(payment_months=1,  discount_rate_bps=term1_bps),
            SaasTermDiscountPolicy(payment_months=3,  discount_rate_bps=term3_bps),
            SaasTermDiscountPolicy(payment_months=6,  discount_rate_bps=term6_bps),
            SaasTermDiscountPolicy(payment_months=9,  discount_rate_bps=term9_bps),
            SaasTermDiscountPolicy(payment_months=12, discount_rate_bps=term12_bps),
        ],
    )


# ── C01 STANDARD zero sites rejected ──────────────────────────────────────────

def test_C01_standard_zero_sites_rejected():
    with pytest.raises(SaasPricingComposerError, match="최소 1개"):
        calculate_saas_price_v2(_sel(), [], _resolved_policy())


# ── C02 duplicate site rejected ───────────────────────────────────────────────

def test_C02_duplicate_site_rejected():
    site_a = _site(entity_id=_UUID_A, base_amount=149000)
    site_dup = _site(entity_id=_UUID_A, base_amount=299000)  # same UUID = duplicate
    with pytest.raises(SaasPricingComposerError, match="중복"):
        calculate_saas_price_v2(_sel(), [site_a, site_dup], _resolved_policy())


# ── C03 MANAGER one site ───────────────────────────────────────────────────────

def test_C03_manager_one_site():
    result = calculate_saas_price_v2(_sel(), [_site(base_amount=149000)], _resolved_policy())
    assert result.status == "READY"
    assert len(result.site_breakdown) == 1
    assert result.site_breakdown[0].is_primary is True
    assert result.site_breakdown[0].normal_site_amount == 149000
    assert result.site_breakdown[0].final_site_amount == 149000


# ── C04 FIELD one site ────────────────────────────────────────────────────────

def test_C04_field_one_site():
    result = calculate_saas_price_v2(
        _sel(product_tier="FIELD", worker_capacity=0),
        [_site(base_amount=149000)],
        _resolved_policy(),
    )
    assert result.status == "READY"
    assert result.site_breakdown[0].normal_site_amount == 249000  # policy.field_base_amount
    assert result.site_breakdown[0].final_site_amount == 249000   # 249000 × 10000 // 10000


# ── C05 two equal-price sites deterministic primary ───────────────────────────

def test_C05_two_equal_price_sites_deterministic_primary():
    # 동일 normal → tie-break: sector ASC → BUILDING < INDUSTRY → BUILDING이 primary
    site_industry = _site(entity_id=_UUID_A, sector="INDUSTRY", base_amount=149000)
    site_building = SaasSitePricingInput(
        entity_type="factory", entity_id=_UUID_B, sector="BUILDING",
        base_band_code="BUILDING_BASIC", base_amount=149000,
    )
    result1 = calculate_saas_price_v2(_sel(), [site_industry, site_building], _resolved_policy())
    result2 = calculate_saas_price_v2(_sel(), [site_building, site_industry], _resolved_policy())

    primary1 = next(bd for bd in result1.site_breakdown if bd.is_primary)
    primary2 = next(bd for bd in result2.site_breakdown if bd.is_primary)
    assert primary1.sector == primary2.sector == "BUILDING"


# ── C06 two unequal-price sites highest primary ───────────────────────────────

def test_C06_two_unequal_price_highest_primary():
    site_low  = _site(entity_id=_UUID_A, base_amount=149000)
    site_high = _site(entity_id=_UUID_B, base_amount=499000)
    result = calculate_saas_price_v2(_sel(), [site_low, site_high], _resolved_policy())
    primary = next(bd for bd in result.site_breakdown if bd.is_primary)
    assert primary.base_amount == 499000


# ── C07 three-site MANAGER ────────────────────────────────────────────────────

def test_C07_three_site_manager():
    # 499000×100% + 299000×80% + 149000×80% = 499000+239200+119200 = 857400
    sites = [
        _site(entity_id=_UUID_A, base_amount=149000),
        _site(entity_id=_UUID_B, base_amount=299000),
        _site(entity_id=_UUID_C, base_amount=499000),
    ]
    result = calculate_saas_price_v2(_sel(), sites, _resolved_policy())
    assert result.monthly_supply_amount == 857400


# ── C08 three-site FIELD ──────────────────────────────────────────────────────

def test_C08_three_site_field():
    # V3: all normals = 249000 (fixed)
    # 249000×100% + 249000×80% + 249000×80% = 249000+199200+199200 = 647400
    sites = [
        _site(entity_id=_UUID_A, base_amount=149000),
        _site(entity_id=_UUID_B, base_amount=299000),
        _site(entity_id=_UUID_C, base_amount=499000),
    ]
    result = calculate_saas_price_v2(
        _sel(product_tier="FIELD", worker_capacity=0),
        sites,
        _resolved_policy(),
    )
    assert result.monthly_supply_amount == 647400


# ── C09 input reorder produces same result ────────────────────────────────────

def test_C09_input_reorder_same_result():
    sites_abc = [
        _site(entity_id=_UUID_A, base_amount=149000),
        _site(entity_id=_UUID_B, base_amount=299000),
        _site(entity_id=_UUID_C, base_amount=499000),
    ]
    sites_cab = [sites_abc[2], sites_abc[0], sites_abc[1]]
    policy = _resolved_policy()
    result1 = calculate_saas_price_v2(_sel(), sites_abc, policy)
    result2 = calculate_saas_price_v2(_sel(), sites_cab, policy)
    assert result1.monthly_supply_amount == result2.monthly_supply_amount
    assert result1.snapshot.model_dump() == result2.snapshot.model_dump()


# ── C10 mixed sectors accepted ────────────────────────────────────────────────

def test_C10_mixed_sectors_accepted():
    site_industry = _site(entity_id=_UUID_A, sector="INDUSTRY", entity_type="factory")
    site_building = SaasSitePricingInput(
        entity_type="factory", entity_id=_UUID_B, sector="BUILDING",
        base_band_code="BUILDING_BASIC", base_amount=349000,
    )
    site_construction = SaasSitePricingInput(
        entity_type="site", entity_id=_UUID_C, sector="CONSTRUCTION",
        base_band_code="CONSTRUCTION_STANDARD", base_amount=249000,
    )
    result = calculate_saas_price_v2(
        _sel(),
        [site_industry, site_building, site_construction],
        _resolved_policy(),
    )
    assert result.status == "READY"
    assert len(result.site_breakdown) == 3


# ── C11 base_amount=0 rejected ────────────────────────────────────────────────

def test_C11_base_amount_zero_rejected():
    with pytest.raises(ValidationError):
        SaasSitePricingInput(
            entity_type="factory", entity_id=_UUID_A, sector="INDUSTRY",
            base_band_code="INDUSTRY_STARTER", base_amount=0,
        )


# ── C12 negative base rejected ────────────────────────────────────────────────

def test_C12_negative_base_rejected():
    with pytest.raises(ValidationError):
        SaasSitePricingInput(
            entity_type="factory", entity_id=_UUID_A, sector="INDUSTRY",
            base_band_code="INDUSTRY_STARTER", base_amount=-1,
        )


# ── C13 float base rejected ───────────────────────────────────────────────────

def test_C13_float_base_rejected():
    with pytest.raises(ValidationError):
        SaasSitePricingInput(
            entity_type="factory", entity_id=_UUID_A, sector="INDUSTRY",
            base_band_code="INDUSTRY_STARTER", base_amount=149000.0,
        )


# ── C14 FIELD additional-site uplift discounted together ──────────────────────

def test_C14_field_additional_site_uplift_discounted_together():
    # additional: base=149000, normal=249000 (uplift 포함)
    # final = 249000 × 8000 // 10000 = 199200 (NOT 149000×80%+uplift = 219200)
    site_primary    = _site(entity_id=_UUID_A, base_amount=499000)
    site_additional = _site(entity_id=_UUID_B, base_amount=149000)
    result = calculate_saas_price_v2(
        _sel(product_tier="FIELD", worker_capacity=0),
        [site_primary, site_additional],
        _resolved_policy(),
    )
    additional = next(bd for bd in result.site_breakdown if not bd.is_primary)
    assert additional.normal_site_amount == 249000
    assert additional.final_site_amount == 199200


# ── W00~W1000 Worker 누진 계산 ─────────────────────────────────────────────────

@pytest.mark.parametrize("capacity,expected_amount", [
    (0,    0),
    (1,    3_000),
    (20,   60_000),
    (21,   62_500),
    (50,   135_000),
    (51,   137_000),
    (100,  235_000),
    (101,  236_500),
    (150,  310_000),
    (300,  535_000),
    (301,  536_200),
    (305,  541_000),
    (500,  775_000),
    (1000, 1_375_000),
])
def test_worker_progressive(capacity: int, expected_amount: int):
    result = calculate_saas_price_v2(
        _sel(product_tier="FIELD", worker_capacity=capacity),
        [_site()],
        _resolved_policy(),
    )
    assert result.worker_breakdown.amount == expected_amount


# ── T01/T03/T06/T09/T12 Canonical policy (V3) → READY ────────────────────────

@pytest.mark.parametrize("term,expected_bps", [(1, 0), (3, 500), (6, 1000), (9, 1500), (12, 2000)])
def test_canonical_term_ready(term: int, expected_bps: int):
    canonical = get_canonical_pricing_policy_v2()
    result = calculate_saas_price_v2(_sel(payment_months=term), [_site()], canonical)
    assert result.status == "READY"
    assert result.snapshot is not None
    assert result.term_discount_rate_bps == expected_bps


# ── TERM_DISCOUNT_UNRESOLVED branch — explicit None policy ────────────────────

@pytest.mark.parametrize("term", [1, 3, 6, 9, 12])
def test_unresolved_discount_branch_explicit_none(term: int):
    none_policy = _resolved_policy(term1_bps=None, term3_bps=None, term6_bps=None, term9_bps=None, term12_bps=None)
    result = calculate_saas_price_v2(_sel(payment_months=term), [_site()], none_policy)
    assert result.status == "TERM_DISCOUNT_UNRESOLVED"
    assert result.snapshot is None
    assert result.term_discount_rate_bps is None


# ── R01 term1 / 0bps → READY ─────────────────────────────────────────────────

def test_R01_term1_0bps_ready():
    result = calculate_saas_price_v2(
        _sel(payment_months=1), [_site(base_amount=149000)], _resolved_policy(term1_bps=0),
    )
    assert result.status == "READY"
    assert result.snapshot is not None


# ── R02 term12 / 1000bps → READY ─────────────────────────────────────────────

def test_R02_term12_1000bps_ready():
    result = calculate_saas_price_v2(
        _sel(payment_months=12), [_site(base_amount=149000)], _resolved_policy(term12_bps=1000),
    )
    assert result.status == "READY"
    assert result.snapshot is not None


# ── R03 Snapshot only on READY ───────────────────────────────────────────────

def test_R03_snapshot_only_on_ready():
    none_policy = _resolved_policy(term1_bps=None, term3_bps=None, term6_bps=None, term9_bps=None, term12_bps=None)
    result_unresolved = calculate_saas_price_v2(_sel(payment_months=1), [_site()], none_policy)
    assert result_unresolved.snapshot is None

    result_ready = calculate_saas_price_v2(_sel(payment_months=1), [_site()], _resolved_policy(term1_bps=0))
    assert result_ready.snapshot is not None


# ── R04 discount arithmetic ───────────────────────────────────────────────────

def test_R04_discount_arithmetic():
    # monthly=149000, term=1, discount=1000bps(10%)
    # discount_amount = 149000*1000//10000 = 14900
    # prepaid = 149000 - 14900 = 134100
    result = calculate_saas_price_v2(
        _sel(payment_months=1),
        [_site(base_amount=149000)],
        _resolved_policy(term1_bps=1000),
    )
    assert result.snapshot.prepaid_supply_amount == 134100


# ── R05 VAT arithmetic ────────────────────────────────────────────────────────

def test_R05_vat_arithmetic():
    # prepaid=149000, vat_bps=1000 → vat = 149000*1000//10000 = 14900
    result = calculate_saas_price_v2(
        _sel(payment_months=1),
        [_site(base_amount=149000)],
        _resolved_policy(term1_bps=0),
    )
    assert result.snapshot.vat_amount == 14900


# ── R06 total arithmetic ──────────────────────────────────────────────────────

def test_R06_total_arithmetic():
    # prepaid=149000, vat=14900 → total=163900
    result = calculate_saas_price_v2(
        _sel(payment_months=1),
        [_site(base_amount=149000)],
        _resolved_policy(term1_bps=0),
    )
    assert result.snapshot.total_amount == 163900


# ── Floor: site additional rate ───────────────────────────────────────────────

def test_floor_site_additional_rate():
    # additional: normal=101, rate=8000 → 101*8000//10000 = 80 (not 81)
    site_primary    = _site(entity_id=_UUID_A, base_amount=999999)
    site_additional = _site(entity_id=_UUID_B, base_amount=101)
    result = calculate_saas_price_v2(
        _sel(),
        [site_primary, site_additional],
        _resolved_policy(term1_bps=0),
    )
    additional_bd = next(bd for bd in result.site_breakdown if not bd.is_primary)
    assert additional_bd.final_site_amount == 80


# ── Floor: VAT ────────────────────────────────────────────────────────────────

def test_floor_vat():
    # prepaid=101, vat_bps=1000 → 101*1000//10000 = 10 (not 10.1 → 11)
    # base=101, primary, MANAGER → monthly=101, raw_prepaid=101, prepaid=101 (0% discount)
    result = calculate_saas_price_v2(
        _sel(payment_months=1),
        [_site(base_amount=101)],
        _resolved_policy(term1_bps=0),
    )
    assert result.snapshot.vat_amount == 10
    assert result.snapshot.total_amount == 111


# ── Floor: term discount ──────────────────────────────────────────────────────

def test_floor_term_discount():
    # raw_prepaid=11, discount_bps=1000 → 11*1000//10000 = 1 (floor of 1.1)
    # prepaid = 10
    result = calculate_saas_price_v2(
        _sel(payment_months=1),
        [_site(base_amount=11)],
        _resolved_policy(term1_bps=1000),
    )
    assert result.snapshot.prepaid_supply_amount == 10


# ── Tier: MANAGER no uplift, no worker ───────────────────────────────────────

def test_manager_no_uplift_no_worker():
    result = calculate_saas_price_v2(
        _sel(product_tier="MANAGER"),
        [_site(base_amount=149000)],
        _resolved_policy(term1_bps=0),
    )
    assert result.site_breakdown[0].normal_site_amount == 149000
    assert result.worker_breakdown.amount == 0
    assert result.worker_breakdown.capacity == 0


# ── Tier: FIELD per-site uplift + worker charge ───────────────────────────────

def test_field_per_site_uplift_and_worker():
    result = calculate_saas_price_v2(
        _sel(product_tier="FIELD", worker_capacity=20),
        [_site(base_amount=149000)],
        _resolved_policy(term1_bps=0),
    )
    assert result.site_breakdown[0].normal_site_amount == 249000
    assert result.worker_breakdown.amount == 60000  # 20명 × 3000


# ── CUSTOM: zero sites → CUSTOM_REQUIRED (product_tier 기준) ─────────────────

def test_custom_zero_sites_custom_required():
    result = calculate_saas_price_v2(
        _sel(product_tier="CUSTOM", pricing_mode="CUSTOM"),
        [],
        _resolved_policy(),
    )
    assert result.status == "CUSTOM_REQUIRED"
    assert result.snapshot is None


# ── CUSTOM: snapshot=None (product_tier 기준) ─────────────────────────────────

def test_custom_snapshot_none():
    result = calculate_saas_price_v2(
        _sel(product_tier="CUSTOM", pricing_mode="CUSTOM"),
        [_site()],
        _resolved_policy(),
    )
    assert result.status == "CUSTOM_REQUIRED"
    assert result.snapshot is None
    assert result.site_breakdown is None


# ── Canonical policy immutable after compose ──────────────────────────────────

def test_canonical_policy_immutable_after_compose():
    canonical = get_canonical_pricing_policy_v2()
    before = canonical.model_dump()
    calculate_saas_price_v2(_sel(), [_site()], canonical)
    after = canonical.model_dump()
    assert before == after


# ── Input sites not mutated ───────────────────────────────────────────────────

def test_input_sites_not_mutated():
    sites = [
        _site(entity_id=_UUID_A, base_amount=149000),
        _site(entity_id=_UUID_B, base_amount=499000),
    ]
    original_ids = [s.entity_id for s in sites]
    original_amounts = [s.base_amount for s in sites]
    calculate_saas_price_v2(_sel(), sites, _resolved_policy())
    assert [s.entity_id for s in sites] == original_ids
    assert [s.base_amount for s in sites] == original_amounts


# ── Result determinism ────────────────────────────────────────────────────────

def test_result_determinism():
    sites = [
        _site(entity_id=_UUID_A, base_amount=149000),
        _site(entity_id=_UUID_B, base_amount=299000),
    ]
    policy = _resolved_policy(term1_bps=0)
    result1 = calculate_saas_price_v2(_sel(), sites, policy)
    result2 = calculate_saas_price_v2(_sel(), sites, policy)
    assert result1.model_dump() == result2.model_dump()


# ── CANONICAL TIER CORRECTION: K16~K24 ────────────────────────────────────────

# K16 CUSTOM + zero sites → CUSTOM_REQUIRED
def test_K16_custom_zero_sites_custom_required():
    result = calculate_saas_price_v2(
        _sel(product_tier="CUSTOM", pricing_mode="CUSTOM"),
        [],
        _resolved_policy(),
    )
    assert result.status == "CUSTOM_REQUIRED"


# K17 CUSTOM + sites present → CUSTOM_REQUIRED
def test_K17_custom_with_sites_custom_required():
    result = calculate_saas_price_v2(
        _sel(product_tier="CUSTOM", pricing_mode="CUSTOM"),
        [_site()],
        _resolved_policy(),
    )
    assert result.status == "CUSTOM_REQUIRED"


# K18 CUSTOM + worker_capacity > 0 → CUSTOM_REQUIRED, worker_breakdown=None
def test_K18_custom_with_workers_custom_required():
    result = calculate_saas_price_v2(
        _sel(product_tier="CUSTOM", pricing_mode="CUSTOM", worker_capacity=100),
        [_site()],
        _resolved_policy(),
    )
    assert result.status == "CUSTOM_REQUIRED"
    assert result.worker_breakdown is None


# K19 CUSTOM snapshot=None
def test_K19_custom_snapshot_none():
    result = calculate_saas_price_v2(
        _sel(product_tier="CUSTOM", pricing_mode="CUSTOM"),
        [_site()],
        _resolved_policy(),
    )
    assert result.snapshot is None


# K20 CUSTOM monthly_supply_amount=None
def test_K20_custom_monthly_none():
    result = calculate_saas_price_v2(
        _sel(product_tier="CUSTOM", pricing_mode="CUSTOM"),
        [_site()],
        _resolved_policy(),
    )
    assert result.monthly_supply_amount is None


# K21 CUSTOM raw_prepaid_supply_amount=None
def test_K21_custom_raw_prepaid_none():
    result = calculate_saas_price_v2(
        _sel(product_tier="CUSTOM", pricing_mode="CUSTOM"),
        [_site()],
        _resolved_policy(),
    )
    assert result.raw_prepaid_supply_amount is None


# K22 MANAGER 3-site calculation regression
def test_K22_manager_calculation_regression():
    sites = [
        _site(entity_id=_UUID_A, base_amount=149000),
        _site(entity_id=_UUID_B, base_amount=299000),
        _site(entity_id=_UUID_C, base_amount=499000),
    ]
    result = calculate_saas_price_v2(_sel(), sites, _resolved_policy())
    assert result.monthly_supply_amount == 857400


# K23 FIELD 3-site calculation regression (V3: all normals = 249000)
def test_K23_field_calculation_regression():
    sites = [
        _site(entity_id=_UUID_A, base_amount=149000),
        _site(entity_id=_UUID_B, base_amount=299000),
        _site(entity_id=_UUID_C, base_amount=499000),
    ]
    result = calculate_saas_price_v2(
        _sel(product_tier="FIELD", worker_capacity=0),
        sites,
        _resolved_policy(),
    )
    # V3: 249000 + 199200 + 199200 = 647400 (all normals fixed at 249000)
    assert result.monthly_supply_amount == 647400


# K24 Composer CUSTOM 분기가 product_tier를 기준으로 동작함
def test_K24_custom_branch_uses_product_tier():
    import inspect
    from services import saas_pricing_composer_v2
    source = inspect.getsource(saas_pricing_composer_v2.calculate_saas_price_v2)
    assert 'selection.product_tier == "CUSTOM"' in source


# ── V3 FIELD: Base Independence ───────────────────────────────────────────────

@pytest.mark.parametrize("base_amount", [149000, 249000, 299000, 499000])
def test_V3_field_base_independence(base_amount: int):
    """FIELD normal은 resolver base_amount에 무관하게 249000 고정."""
    result = calculate_saas_price_v2(
        _sel(product_tier="FIELD", worker_capacity=0),
        [_site(base_amount=base_amount)],
        _resolved_policy(term1_bps=0),
    )
    assert result.site_breakdown[0].normal_site_amount == 249000


# ── V3 FIELD: Multi-site ──────────────────────────────────────────────────────

def test_V3_field_1_site():
    result = calculate_saas_price_v2(
        _sel(product_tier="FIELD", worker_capacity=0),
        [_site(entity_id=_UUID_A, base_amount=149000)],
        _resolved_policy(term1_bps=0),
    )
    assert result.monthly_supply_amount == 249000


def test_V3_field_2_sites():
    result = calculate_saas_price_v2(
        _sel(product_tier="FIELD", worker_capacity=0),
        [_site(entity_id=_UUID_A, base_amount=149000), _site(entity_id=_UUID_B, base_amount=299000)],
        _resolved_policy(term1_bps=0),
    )
    # Primary 249000 + Additional 199200
    assert result.monthly_supply_amount == 448200


def test_V3_field_3_sites():
    result = calculate_saas_price_v2(
        _sel(product_tier="FIELD", worker_capacity=0),
        [
            _site(entity_id=_UUID_A, base_amount=149000),
            _site(entity_id=_UUID_B, base_amount=299000),
            _site(entity_id=_UUID_C, base_amount=499000),
        ],
        _resolved_policy(term1_bps=0),
    )
    # Primary 249000 + Additional × 2 (199200 each)
    assert result.monthly_supply_amount == 647400


# ── V3 FIELD: Golden Example ──────────────────────────────────────────────────

def test_V3_golden_field_2_sites_100_workers_6_months():
    """FIELD 2사업장 / 작업자 100명 / 6개월 10% 할인 golden example."""
    result = calculate_saas_price_v2(
        _sel(product_tier="FIELD", worker_capacity=100, payment_months=6),
        [_site(entity_id=_UUID_A, base_amount=149000), _site(entity_id=_UUID_B, base_amount=299000)],
        _resolved_policy(term6_bps=1000),
    )
    # monthly: 249000 + 199200 + (20×3000 + 30×2500 + 50×2000) = 448200 + 235000 = 683200
    assert result.monthly_supply_amount == 683200
    # raw prepaid: 683200 × 6 = 4099200
    assert result.raw_prepaid_supply_amount == 4099200
    # discount 10%: 4099200 × 1000 // 10000 = 409920
    # discounted supply: 4099200 - 409920 = 3689280
    assert result.snapshot.prepaid_supply_amount == 3689280
    # VAT: 3689280 × 1000 // 10000 = 368928
    # total: 3689280 + 368928 = 4058208
    assert result.snapshot.total_amount == 4058208
    assert result.term_discount_rate_bps == 1000
