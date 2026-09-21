"""pricing_resolver_svc.resolve_plan SAAS 경계값 회귀 테스트.

pricing_resolver_svc 변경이 SAAS 경로에 회귀를 일으키지 않는지 확인.
WORKER_COUNT / FLOOR_AREA: upper bound 포함(≤)
CONTRACT_AMOUNT: upper bound 제외(<)
"""
from unittest.mock import patch, MagicMock
from services.pricing_resolver_svc import resolve_plan

_SAAS_INDUSTRY = [
    {"id": "i1", "tier_code": "INDUSTRY_STARTER",  "criteria_type": "WORKER_COUNT", "criteria_min": 0,   "criteria_max": 49,  "amount": 149000, "is_recommended": False, "sort_order": 1},
    {"id": "i2", "tier_code": "INDUSTRY_BUSINESS",  "criteria_type": "WORKER_COUNT", "criteria_min": 50,  "criteria_max": 299, "amount": 299000, "is_recommended": False, "sort_order": 2},
    {"id": "i3", "tier_code": "INDUSTRY_PRO",       "criteria_type": "WORKER_COUNT", "criteria_min": 300, "criteria_max": 499, "amount": 499000, "is_recommended": False, "sort_order": 3},
    {"id": "i4", "tier_code": "INDUSTRY_CUSTOM",    "criteria_type": "WORKER_COUNT", "criteria_min": 500, "criteria_max": None,"amount": 0,      "is_recommended": False, "sort_order": 4},
]

_SAAS_BUILDING = [
    {"id": "b1", "tier_code": "BUILDING_BASIC",    "criteria_type": "FLOOR_AREA", "criteria_min": 0,    "criteria_max": 5000, "amount": 149000, "is_recommended": False, "sort_order": 1},
    {"id": "b2", "tier_code": "BUILDING_STANDARD", "criteria_type": "FLOOR_AREA", "criteria_min": 5000, "criteria_max": None, "amount": 349000, "is_recommended": False, "sort_order": 2},
    {"id": "b3", "tier_code": "BUILDING_CUSTOM",   "criteria_type": "FLAT",       "criteria_min": None, "criteria_max": None, "amount": 0,      "is_recommended": False, "sort_order": 3},
]

_SAAS_CONSTRUCTION = [
    {"id": "c1", "tier_code": "CONSTRUCTION_STANDARD", "criteria_type": "CONTRACT_AMOUNT", "criteria_min": 0,          "criteria_max": 5000000000, "amount": 249000, "is_recommended": False, "sort_order": 1},
    {"id": "c2", "tier_code": "CONSTRUCTION_PREMIUM",  "criteria_type": "CONTRACT_AMOUNT", "criteria_min": 5000000000, "criteria_max": None,       "amount": 499000, "is_recommended": False, "sort_order": 2},
    {"id": "c3", "tier_code": "CONSTRUCTION_CUSTOM",   "criteria_type": "FLAT",            "criteria_min": None,       "criteria_max": None,       "amount": 0,      "is_recommended": False, "sort_order": 3},
]


def _resolve(rows, value):
    with patch("services.pricing_resolver_svc.load_prices", return_value=rows):
        return resolve_plan(MagicMock(), "SAAS", "ANY", value)


# ── SAAS INDUSTRY ─────────────────────────────────────────────────────────────

def test_saas_industry_49_starter():
    assert _resolve(_SAAS_INDUSTRY, 49)["data"]["tier_code"] == "INDUSTRY_STARTER"

def test_saas_industry_50_business():
    assert _resolve(_SAAS_INDUSTRY, 50)["data"]["tier_code"] == "INDUSTRY_BUSINESS"

def test_saas_industry_299_business():
    assert _resolve(_SAAS_INDUSTRY, 299)["data"]["tier_code"] == "INDUSTRY_BUSINESS"

def test_saas_industry_300_pro():
    assert _resolve(_SAAS_INDUSTRY, 300)["data"]["tier_code"] == "INDUSTRY_PRO"

def test_saas_industry_499_pro():
    assert _resolve(_SAAS_INDUSTRY, 499)["data"]["tier_code"] == "INDUSTRY_PRO"

def test_saas_industry_500_custom():
    assert _resolve(_SAAS_INDUSTRY, 500)["data"]["tier_code"] == "INDUSTRY_CUSTOM"


# ── SAAS BUILDING ─────────────────────────────────────────────────────────────

def test_saas_building_5000_basic():
    assert _resolve(_SAAS_BUILDING, 5000)["data"]["tier_code"] == "BUILDING_BASIC"

def test_saas_building_5000_1_standard():
    assert _resolve(_SAAS_BUILDING, 5000.1)["data"]["tier_code"] == "BUILDING_STANDARD"


# ── SAAS CONSTRUCTION ─────────────────────────────────────────────────────────

def test_saas_construction_4999999999_standard():
    assert _resolve(_SAAS_CONSTRUCTION, 4999999999)["data"]["tier_code"] == "CONSTRUCTION_STANDARD"

def test_saas_construction_5000000000_premium():
    assert _resolve(_SAAS_CONSTRUCTION, 5000000000)["data"]["tier_code"] == "CONSTRUCTION_PREMIUM"
