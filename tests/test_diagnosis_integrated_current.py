from routers import diagnosis_integrated


def test_auto_tier_building_threshold_snapshot():
    assert diagnosis_integrated._auto_tier("BUILDING", floor_area=4999) == "BUILDING_V2"
    assert diagnosis_integrated._auto_tier("BUILDING", floor_area=5000) == "BUILDING_LARGE_V2"


def test_auto_tier_construction_threshold_snapshot():
    assert diagnosis_integrated._auto_tier("CONSTRUCTION", contract_amount_eok=49.9) == "CONSTRUCTION"
    assert diagnosis_integrated._auto_tier("CONSTRUCTION", contract_amount_eok=50) == "CONSTRUCTION_PREMIUM"


def test_auto_tier_industry_uses_user_tier_or_default():
    assert diagnosis_integrated._auto_tier("INDUSTRY", user_tier="INDUSTRY_STANDARD") == "INDUSTRY_STANDARD"
    assert diagnosis_integrated._auto_tier("INDUSTRY", user_tier=None) == "INDUSTRY_V2"


def test_build_partial_includes_core_fields_and_truncation():
    full = {
        "risk_level": "HIGH",
        "summary": {"total": 10},
        "applicable_count": 10,
        "sector": "BUILDING",
        "key_obligations": list(range(10)),
        "law_badges": list(range(30)),
    }
    partial = diagnosis_integrated._build_partial(full)
    assert partial["risk_level"] == "HIGH"
    assert partial["summary"]["total"] == 10
    assert partial["applicable_count"] == 10
    assert len(partial["key_obligations"]) == 6
    assert len(partial["law_badges"]) == 18


def test_price_table_contains_expected_core_tiers():
    prices = diagnosis_integrated.PAID_TIER_PRICES
    assert prices["BUILDING_V2"] == 99000
    assert prices["CONSTRUCTION_PREMIUM"] == 299000
    assert prices["INDUSTRY_PREMIUM"] == 249000


def test_diagnosis_run_body_schema_snapshot():
    body = diagnosis_integrated.DiagnosisRunBody(
        auth_token="tok",
        disclaimer_log_id="disc",
        sector="BUILDING",
    )
    dumped = body.model_dump()
    assert dumped["auth_token"] == "tok"
    assert dumped["disclaimer_log_id"] == "disc"
    assert dumped["sector"] == "BUILDING"
