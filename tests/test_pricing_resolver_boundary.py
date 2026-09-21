"""pricing_resolver_svc.resolve_plan 경계값 단위 테스트.

price_master mock rows를 직접 주입 → DB 의존 없음.
경계 기준:
  BUILDING  FLOOR_AREA:    ≤5000 → BASIC(149k), >5000 → STANDARD(349k)
  INDUSTRY  WORKER_COUNT:  ≤49  → STARTER(149k), 50~299 → BUSINESS(299k), ≥300 → PRO(499k)
  CONSTRUCTION CONTRACT_AMOUNT: <5000000000 → STANDARD(249k), ≥5000000000 → PREMIUM(499k)
"""
from unittest.mock import patch, MagicMock
from services.pricing_resolver_svc import resolve_plan

# ── mock price_master rows ────────────────────────────────────────────────────

_BUILDING = [
    {
        "id": "b1", "tier_code": "BUILDING_V2", "criteria_type": "FLOOR_AREA",
        "criteria_min": 0, "criteria_max": 5000, "amount": 149000,
        "is_recommended": False, "sort_order": 1,
    },
    {
        "id": "b2", "tier_code": "BUILDING_LARGE_V2", "criteria_type": "FLOOR_AREA",
        "criteria_min": 0, "criteria_max": None, "amount": 349000,
        "is_recommended": False, "sort_order": 2,
    },
]

_INDUSTRY = [
    {
        "id": "i1", "tier_code": "INDUSTRY_V2", "criteria_type": "WORKER_COUNT",
        "criteria_min": 0, "criteria_max": 49, "amount": 149000,
        "is_recommended": False, "sort_order": 1,
    },
    {
        "id": "i2", "tier_code": "INDUSTRY_STANDARD", "criteria_type": "WORKER_COUNT",
        "criteria_min": 50, "criteria_max": 299, "amount": 299000,
        "is_recommended": False, "sort_order": 2,
    },
    {
        "id": "i3", "tier_code": "INDUSTRY_PREMIUM", "criteria_type": "WORKER_COUNT",
        "criteria_min": 300, "criteria_max": None, "amount": 499000,
        "is_recommended": False, "sort_order": 3,
    },
]

_CONSTRUCTION = [
    {
        "id": "c1", "tier_code": "CONSTRUCTION", "criteria_type": "CONTRACT_AMOUNT",
        "criteria_min": 0, "criteria_max": 5000000000, "amount": 249000,
        "is_recommended": False, "sort_order": 1,
    },
    {
        "id": "c2", "tier_code": "CONSTRUCTION_PREMIUM", "criteria_type": "CONTRACT_AMOUNT",
        "criteria_min": 0, "criteria_max": None, "amount": 499000,
        "is_recommended": False, "sort_order": 2,
    },
]


def _mock_sb(rows):
    sb = MagicMock()
    with patch("services.pricing_resolver_svc.load_prices", return_value=rows):
        yield sb


def _resolve(rows, value):
    with patch("services.pricing_resolver_svc.load_prices", return_value=rows):
        return resolve_plan(MagicMock(), "DIAGNOSIS", "ANY", value)


# ── BUILDING ─────────────────────────────────────────────────────────────────

def test_building_4999_basic():
    r = _resolve(_BUILDING, 4999)
    assert r["data"]["tier_code"] == "BUILDING_V2"
    assert r["data"]["amount"] == 149000


def test_building_5000_basic_inclusive():
    # 5000㎡ 이하 → BASIC. 상한 포함(≤)
    r = _resolve(_BUILDING, 5000)
    assert r["data"]["tier_code"] == "BUILDING_V2"
    assert r["data"]["amount"] == 149000


def test_building_5000_1_standard():
    r = _resolve(_BUILDING, 5000.1)
    assert r["data"]["tier_code"] == "BUILDING_LARGE_V2"
    assert r["data"]["amount"] == 349000


def test_building_9999_standard():
    r = _resolve(_BUILDING, 9999)
    assert r["data"]["tier_code"] == "BUILDING_LARGE_V2"


# ── INDUSTRY ─────────────────────────────────────────────────────────────────

def test_industry_48_starter():
    r = _resolve(_INDUSTRY, 48)
    assert r["data"]["tier_code"] == "INDUSTRY_V2"
    assert r["data"]["amount"] == 149000


def test_industry_49_starter_inclusive():
    # 49인 이하 → STARTER. 상한 포함(≤)
    r = _resolve(_INDUSTRY, 49)
    assert r["data"]["tier_code"] == "INDUSTRY_V2"
    assert r["data"]["amount"] == 149000


def test_industry_50_business():
    # 50인 → BUSINESS
    r = _resolve(_INDUSTRY, 50)
    assert r["data"]["tier_code"] == "INDUSTRY_STANDARD"
    assert r["data"]["amount"] == 299000


def test_industry_299_business_inclusive():
    # 299인 이하 → BUSINESS. 상한 포함(≤)
    r = _resolve(_INDUSTRY, 299)
    assert r["data"]["tier_code"] == "INDUSTRY_STANDARD"
    assert r["data"]["amount"] == 299000


def test_industry_300_pro():
    # 300인 이상 → PRO
    r = _resolve(_INDUSTRY, 300)
    assert r["data"]["tier_code"] == "INDUSTRY_PREMIUM"
    assert r["data"]["amount"] == 499000


def test_industry_500_pro():
    r = _resolve(_INDUSTRY, 500)
    assert r["data"]["tier_code"] == "INDUSTRY_PREMIUM"


def test_industry_1000_pro():
    r = _resolve(_INDUSTRY, 1000)
    assert r["data"]["tier_code"] == "INDUSTRY_PREMIUM"


# ── CONSTRUCTION ─────────────────────────────────────────────────────────────

def test_construction_4999999999_standard():
    # 49억9999만 → STANDARD
    r = _resolve(_CONSTRUCTION, 4999999999)
    assert r["data"]["tier_code"] == "CONSTRUCTION"
    assert r["data"]["amount"] == 249000


def test_construction_5000000000_premium_exclusive():
    # 50억 → PREMIUM. CONTRACT_AMOUNT 상한 제외(<)
    r = _resolve(_CONSTRUCTION, 5000000000)
    assert r["data"]["tier_code"] == "CONSTRUCTION_PREMIUM"
    assert r["data"]["amount"] == 499000


def test_construction_9999999999_premium():
    r = _resolve(_CONSTRUCTION, 9999999999)
    assert r["data"]["tier_code"] == "CONSTRUCTION_PREMIUM"
