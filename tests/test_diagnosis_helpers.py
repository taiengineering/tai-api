from services import diagnosis_helpers as h


def test_now_iso_has_utc_offset():
    now = h._now()
    assert "T" in now
    assert now.endswith("+00:00")


def test_sha256_snapshot():
    assert h._sha256("tai") == "f4ddd195cab04430d4595e18bd75fd48df4a0dfb3a7a28c6b2fcf3582762d49d"


def test_auto_tier_snapshot():
    assert h._auto_tier("BUILDING", floor_area=4999) == "BUILDING_V2"
    assert h._auto_tier("BUILDING", floor_area=5000) == "BUILDING_LARGE_V2"
    assert h._auto_tier("CONSTRUCTION", contract_amount_eok=49) == "CONSTRUCTION"
    assert h._auto_tier("CONSTRUCTION", contract_amount_eok=50) == "CONSTRUCTION_PREMIUM"
    assert h._auto_tier("INDUSTRY", user_tier="INDUSTRY_STANDARD") == "INDUSTRY_STANDARD"


def test_build_partial_truncates_lists():
    full = {
        "risk_level": "HIGH",
        "summary": {"total": 10},
        "applicable_count": 10,
        "sector": "BUILDING",
        "key_obligations": [f"k{i}" for i in range(10)],
        "law_badges": [f"l{i}" for i in range(30)],
    }
    part = h._build_partial(full)
    assert len(part["key_obligations"]) == 6
    assert len(part["law_badges"]) == 18
