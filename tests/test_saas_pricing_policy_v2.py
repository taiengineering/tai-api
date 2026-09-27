"""WO-PRICING-V2-BE-OBJ02 — Canonical Pricing Policy Model 테스트.

P01~P37. DB / Runtime 없이 순수 Pydantic validation 검증.
"""
import inspect
from datetime import date

import pytest
from pydantic import ValidationError

import schemas.saas_pricing_policy_v2 as policy_module
from schemas.saas_pricing_policy_v2 import (
    PRICING_POLICY_VERSION,
    SaasPricingPolicyV2,
    SaasTermDiscountPolicy,
    SaasWorkerRateBracketPolicy,
    get_canonical_pricing_policy_v2,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _canonical_brackets():
    return [
        SaasWorkerRateBracketPolicy(range_from=1,   range_to=20,   unit_rate=3000),
        SaasWorkerRateBracketPolicy(range_from=21,  range_to=50,   unit_rate=2500),
        SaasWorkerRateBracketPolicy(range_from=51,  range_to=100,  unit_rate=2000),
        SaasWorkerRateBracketPolicy(range_from=101, range_to=300,  unit_rate=1500),
        SaasWorkerRateBracketPolicy(range_from=301, range_to=None, unit_rate=1200),
    ]


def _canonical_term_discounts():
    return [
        SaasTermDiscountPolicy(term_months=m, discount_rate_bps=None)
        for m in [1, 3, 6, 9, 12]
    ]


def _policy_data(**overrides):
    data = dict(
        policy_version=PRICING_POLICY_VERSION,
        effective_from=date(2026, 9, 27),
        field_uplift_amount=100000,
        primary_site_rate_bps=10000,
        additional_site_rate_bps=8000,
        worker_brackets=_canonical_brackets(),
        vat_rate_bps=1000,
        term_discounts=_canonical_term_discounts(),
    )
    data.update(overrides)
    return data


# ── P01~P02 Policy Identity ───────────────────────────────────────────────────

def test_P01_policy_version_exact():
    policy = get_canonical_pricing_policy_v2()
    assert policy.policy_version == "TAI_SAFE_PRICING_POLICY_2026_09_27"


def test_P02_effective_from():
    policy = get_canonical_pricing_policy_v2()
    assert policy.effective_from == date(2026, 9, 27)


# ── P03~P05 FIELD Uplift ──────────────────────────────────────────────────────

def test_P03_field_uplift_amount():
    policy = get_canonical_pricing_policy_v2()
    assert policy.field_uplift_amount == 100000


def test_P04_field_uplift_float_rejected():
    with pytest.raises(ValidationError):
        SaasPricingPolicyV2(**_policy_data(field_uplift_amount=100000.0))


def test_P05_field_uplift_bool_rejected():
    with pytest.raises(ValidationError):
        SaasPricingPolicyV2(**_policy_data(field_uplift_amount=True))


# ── P06~P10 Site Rate ─────────────────────────────────────────────────────────

def test_P06_primary_site_rate():
    policy = get_canonical_pricing_policy_v2()
    assert policy.primary_site_rate_bps == 10000


def test_P07_additional_site_rate():
    policy = get_canonical_pricing_policy_v2()
    assert policy.additional_site_rate_bps == 8000


def test_P08_rate_over_max_rejected():
    with pytest.raises(ValidationError):
        SaasPricingPolicyV2(**_policy_data(primary_site_rate_bps=10001))


def test_P09_rate_float_rejected():
    with pytest.raises(ValidationError):
        SaasPricingPolicyV2(**_policy_data(additional_site_rate_bps=8000.0))


def test_P10_rate_bool_rejected():
    with pytest.raises(ValidationError):
        SaasPricingPolicyV2(**_policy_data(primary_site_rate_bps=True))


# ── P11~P16 Worker Brackets (canonical values) ───────────────────────────────

def test_P11_bracket_count():
    policy = get_canonical_pricing_policy_v2()
    assert len(policy.worker_brackets) == 5


def test_P12_bracket_1_20_3000():
    b = get_canonical_pricing_policy_v2().worker_brackets[0]
    assert b.range_from == 1 and b.range_to == 20 and b.unit_rate == 3000


def test_P13_bracket_21_50_2500():
    b = get_canonical_pricing_policy_v2().worker_brackets[1]
    assert b.range_from == 21 and b.range_to == 50 and b.unit_rate == 2500


def test_P14_bracket_51_100_2000():
    b = get_canonical_pricing_policy_v2().worker_brackets[2]
    assert b.range_from == 51 and b.range_to == 100 and b.unit_rate == 2000


def test_P15_bracket_101_300_1500():
    b = get_canonical_pricing_policy_v2().worker_brackets[3]
    assert b.range_from == 101 and b.range_to == 300 and b.unit_rate == 1500


def test_P16_bracket_301_open_1200():
    b = get_canonical_pricing_policy_v2().worker_brackets[4]
    assert b.range_from == 301 and b.range_to is None and b.unit_rate == 1200


# ── P17~P24 Worker Bracket Validation ────────────────────────────────────────

def test_P17_gap_rejected():
    brackets = [
        SaasWorkerRateBracketPolicy(range_from=1,   range_to=20,   unit_rate=3000),
        SaasWorkerRateBracketPolicy(range_from=22,  range_to=50,   unit_rate=2500),  # gap: 21 없음
        SaasWorkerRateBracketPolicy(range_from=51,  range_to=100,  unit_rate=2000),
        SaasWorkerRateBracketPolicy(range_from=101, range_to=300,  unit_rate=1500),
        SaasWorkerRateBracketPolicy(range_from=301, range_to=None, unit_rate=1200),
    ]
    with pytest.raises(ValidationError):
        SaasPricingPolicyV2(**_policy_data(worker_brackets=brackets))


def test_P18_overlap_rejected():
    brackets = [
        SaasWorkerRateBracketPolicy(range_from=1,   range_to=20,   unit_rate=3000),
        SaasWorkerRateBracketPolicy(range_from=20,  range_to=50,   unit_rate=2500),  # overlap: 20 중복
        SaasWorkerRateBracketPolicy(range_from=51,  range_to=100,  unit_rate=2000),
        SaasWorkerRateBracketPolicy(range_from=101, range_to=300,  unit_rate=1500),
        SaasWorkerRateBracketPolicy(range_from=301, range_to=None, unit_rate=1200),
    ]
    with pytest.raises(ValidationError):
        SaasPricingPolicyV2(**_policy_data(worker_brackets=brackets))


def test_P19_first_range_not_1_rejected():
    brackets = [
        SaasWorkerRateBracketPolicy(range_from=2,   range_to=20,   unit_rate=3000),  # 1이 아님
        SaasWorkerRateBracketPolicy(range_from=21,  range_to=50,   unit_rate=2500),
        SaasWorkerRateBracketPolicy(range_from=51,  range_to=100,  unit_rate=2000),
        SaasWorkerRateBracketPolicy(range_from=101, range_to=300,  unit_rate=1500),
        SaasWorkerRateBracketPolicy(range_from=301, range_to=None, unit_rate=1200),
    ]
    with pytest.raises(ValidationError):
        SaasPricingPolicyV2(**_policy_data(worker_brackets=brackets))


def test_P20_middle_null_rejected():
    # 중간 bracket의 range_to=None → 거부
    brackets = [
        SaasWorkerRateBracketPolicy(range_from=1,   range_to=None, unit_rate=3000),  # 첫 bracket에 null
        SaasWorkerRateBracketPolicy(range_from=21,  range_to=None, unit_rate=1200),
    ]
    with pytest.raises(ValidationError):
        SaasPricingPolicyV2(**_policy_data(worker_brackets=brackets))


def test_P21_last_non_null_rejected():
    # 마지막 bracket의 range_to가 None이 아님 → 거부
    brackets = [
        SaasWorkerRateBracketPolicy(range_from=1,   range_to=20,   unit_rate=3000),
        SaasWorkerRateBracketPolicy(range_from=21,  range_to=50,   unit_rate=2500),
        SaasWorkerRateBracketPolicy(range_from=51,  range_to=100,  unit_rate=2000),
        SaasWorkerRateBracketPolicy(range_from=101, range_to=300,  unit_rate=1500),
        SaasWorkerRateBracketPolicy(range_from=301, range_to=500,  unit_rate=1200),  # 마지막에 range_to 있음
    ]
    with pytest.raises(ValidationError):
        SaasPricingPolicyV2(**_policy_data(worker_brackets=brackets))


def test_P22_range_to_less_than_range_from_rejected():
    with pytest.raises(ValidationError):
        SaasWorkerRateBracketPolicy(range_from=50, range_to=20, unit_rate=2000)


def test_P23_float_unit_rate_rejected():
    with pytest.raises(ValidationError):
        SaasWorkerRateBracketPolicy(range_from=1, range_to=20, unit_rate=3000.0)


def test_P24_bool_unit_rate_rejected():
    with pytest.raises(ValidationError):
        SaasWorkerRateBracketPolicy(range_from=1, range_to=20, unit_rate=True)


# ── P25~P26 VAT ───────────────────────────────────────────────────────────────

def test_P25_vat_rate_bps():
    policy = get_canonical_pricing_policy_v2()
    assert policy.vat_rate_bps == 1000


def test_P26_vat_float_rejected():
    with pytest.raises(ValidationError):
        SaasPricingPolicyV2(**_policy_data(vat_rate_bps=1000.0))


# ── P27~P33 Term Discount ────────────────────────────────────────────────────

def test_P27_term_months_exactly_1_3_6_9_12():
    policy = get_canonical_pricing_policy_v2()
    months = {td.term_months for td in policy.term_discounts}
    assert months == {1, 3, 6, 9, 12}


def test_P28_term_2_rejected():
    with pytest.raises(ValidationError):
        SaasTermDiscountPolicy(term_months=2, discount_rate_bps=None)


def test_P29_float_term_rejected():
    with pytest.raises(ValidationError):
        SaasTermDiscountPolicy(term_months=12.0, discount_rate_bps=None)


def test_P30_all_canonical_discount_none():
    policy = get_canonical_pricing_policy_v2()
    for td in policy.term_discounts:
        assert td.discount_rate_bps is None, f"term={td.term_months} has discount {td.discount_rate_bps}"


def test_P31_discount_none_accepted():
    td = SaasTermDiscountPolicy(term_months=12, discount_rate_bps=None)
    assert td.discount_rate_bps is None


def test_P32_explicit_discount_structurally_accepted():
    # 구조적으로 값을 담을 수 있음 (Canonical Policy에는 없음)
    td = SaasTermDiscountPolicy(term_months=12, discount_rate_bps=500)
    assert td.discount_rate_bps == 500


def test_P33_discount_over_max_rejected():
    with pytest.raises(ValidationError):
        SaasTermDiscountPolicy(term_months=12, discount_rate_bps=10001)


# ── P34~P36 No Base Price Duplication ────────────────────────────────────────

def test_P34_no_industry_starter_in_source():
    source = inspect.getsource(policy_module)
    assert "INDUSTRY_STARTER" not in source


def test_P35_no_building_basic_in_source():
    source = inspect.getsource(policy_module)
    assert "BUILDING_BASIC" not in source


def test_P36_no_construction_standard_in_source():
    source = inspect.getsource(policy_module)
    assert "CONSTRUCTION_STANDARD" not in source


# ── P37 Immutability / Isolation ─────────────────────────────────────────────

def test_P37_canonical_policy_immutable_and_isolated():
    policy1 = get_canonical_pricing_policy_v2()
    policy2 = get_canonical_pricing_policy_v2()

    # frozen model은 변경 시 ValidationError 발생
    with pytest.raises(ValidationError):
        policy1.field_uplift_amount = 99999

    # 두 번째 호출은 별도 instance이며 올바른 값을 유지
    assert policy1 is not policy2
    assert policy2.field_uplift_amount == 100000
