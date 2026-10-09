from routers import diagnosis_integrated


def test_auto_tier_building_boundary():
    # 5,000㎡ 이하 → BASIC (이하: ≤ 5000)
    assert diagnosis_integrated._auto_tier("BUILDING", floor_area=4999) == "BUILDING_V2"
    assert diagnosis_integrated._auto_tier("BUILDING", floor_area=5000) == "BUILDING_V2"
    # 5,000㎡ 초과 → STANDARD
    assert diagnosis_integrated._auto_tier("BUILDING", floor_area=5000.1) == "BUILDING_LARGE_V2"
    assert diagnosis_integrated._auto_tier("BUILDING", floor_area=9999) == "BUILDING_LARGE_V2"


def test_auto_tier_construction_boundary():
    # 50억 미만 → STANDARD
    assert diagnosis_integrated._auto_tier("CONSTRUCTION", contract_amount_eok=49.9) == "CONSTRUCTION"
    # 50억 이상 → PREMIUM (이상: ≥ 50)
    assert diagnosis_integrated._auto_tier("CONSTRUCTION", contract_amount_eok=50) == "CONSTRUCTION_PREMIUM"
    assert diagnosis_integrated._auto_tier("CONSTRUCTION", contract_amount_eok=100) == "CONSTRUCTION_PREMIUM"


def test_auto_tier_industry_worker_count_boundary():
    # 49인 이하 → STARTER (INDUSTRY_V2)
    assert diagnosis_integrated._auto_tier("INDUSTRIAL", worker_count=48) == "INDUSTRY_V2"
    assert diagnosis_integrated._auto_tier("INDUSTRIAL", worker_count=49) == "INDUSTRY_V2"
    # 50인 이상 → BUSINESS (INDUSTRY_STANDARD)
    assert diagnosis_integrated._auto_tier("INDUSTRIAL", worker_count=50) == "INDUSTRY_STANDARD"
    assert diagnosis_integrated._auto_tier("INDUSTRIAL", worker_count=299) == "INDUSTRY_STANDARD"
    # 300인 이상 → PRO (INDUSTRY_PREMIUM)
    assert diagnosis_integrated._auto_tier("INDUSTRIAL", worker_count=300) == "INDUSTRY_PREMIUM"
    assert diagnosis_integrated._auto_tier("INDUSTRIAL", worker_count=500) == "INDUSTRY_PREMIUM"


def test_auto_tier_industry_user_tier_override():
    # user_tier 명시 시 worker_count 무관 override
    assert diagnosis_integrated._auto_tier("INDUSTRIAL", user_tier="INDUSTRY_STANDARD") == "INDUSTRY_STANDARD"
    assert diagnosis_integrated._auto_tier("INDUSTRIAL", user_tier="INDUSTRY_STANDARD", worker_count=10) == "INDUSTRY_STANDARD"
    # user_tier 없고 worker_count 없으면 STARTER fallback
    assert diagnosis_integrated._auto_tier("INDUSTRIAL", user_tier=None) == "INDUSTRY_V2"


def test_build_partial_includes_core_fields_and_truncation():
    from services.diagnosis_helpers import SOURCE_DIAGNOSIS, _build_partial

    full = {
        "risk_level": "HIGH",
        "summary": {"total": 10},
        "applicable_count": 10,
        "sector": "BUILDING",
        "evaluated_at": "2026-06-08T00:00:00+00:00",
        "engine_version": "v3.0-compiler-core-anonymous",
        "key_obligations": list(range(10)),
        "law_badges": list(range(30)),
        "rules_table": [{"rule_id": "r1", "law_name": "법A"}],
    }
    partial = _build_partial(full)
    assert partial["risk_level"] == "HIGH"
    assert partial["summary"]["total"] == 10
    assert partial["applicable_count"] == 10
    assert partial["evaluated_at"] == "2026-06-08T00:00:00+00:00"
    assert partial["rules_preview"]
    assert len(partial["key_obligations"]) == 6
    assert len(partial["law_badges"]) == 18
    assert partial["key_obligations"][0]["source"] == SOURCE_DIAGNOSIS
    assert partial["rules_table"][0]["source"] == SOURCE_DIAGNOSIS


def test_price_table_contains_expected_core_tiers():
    prices = diagnosis_integrated.PAID_TIER_PRICES
    # 건물
    assert prices["BUILDING_V2"] == 149000
    assert prices["BUILDING_LARGE_V2"] == 349000
    # 산업
    assert prices["INDUSTRY_V2"] == 149000
    assert prices["INDUSTRY_STANDARD"] == 299000
    assert prices["INDUSTRY_PREMIUM"] == 499000
    # 건설
    assert prices["CONSTRUCTION"] == 249000
    assert prices["CONSTRUCTION_PREMIUM"] == 499000


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


# ── WO-LFR-DUAL-CONSUMER-FINAL-CORRECTION-004-REPAIR-001 R2 ──────────────────
# form_data numeric + parent-child validator tests

import pytest
from pydantic import ValidationError
from schemas.diagnosis_integrated import DiagnosisRunBody

def _body(form_data):
    return DiagnosisRunBody(sector="INDUSTRY", form_data=form_data)


def test_FD_R2_01_negative_numeric_rejected():
    with pytest.raises(ValidationError):
        _body({"work_height_m": -1.0})


def test_FD_R2_02_nan_rejected():
    import math
    with pytest.raises(ValidationError):
        _body({"work_height_m": float("nan")})


def test_FD_R2_03_infinity_rejected():
    with pytest.raises(ValidationError):
        _body({"work_height_m": float("inf")})


def test_FD_R2_04_zero_allowed():
    b = _body({"work_height_m": 0.0})
    assert b.form_data["work_height_m"] == 0.0


def test_FD_R2_05_positive_allowed():
    b = _body({"work_height_m": 5.0})
    assert b.form_data["work_height_m"] == 5.0


def test_FD_R2_06_truck_child_no_parent_rejected():
    with pytest.raises(ValidationError) as exc:
        _body({"truck_loading_height_m": 1.5})
    assert "truck_loading_height_m" in str(exc.value)


def test_FD_R2_07_truck_child_parent_false_rejected():
    with pytest.raises(ValidationError) as exc:
        _body({"has_truck_loading_unloading": False, "truck_loading_height_m": 2.0})
    assert "truck_loading_height_m" in str(exc.value)


def test_FD_R2_08_truck_child_parent_true_allowed():
    b = _body({"has_truck_loading_unloading": True, "truck_loading_height_m": 2.0})
    assert b.form_data["truck_loading_height_m"] == 2.0


def test_FD_R2_09_manual_child_no_parent_rejected():
    with pytest.raises(ValidationError) as exc:
        _body({"manual_handling_weight_kg": 25.0})
    assert "manual_handling_weight_kg" in str(exc.value)


def test_FD_R2_10_manual_child_parent_false_rejected():
    with pytest.raises(ValidationError) as exc:
        _body({"has_manual_heavy_handling": False, "manual_handling_weight_kg": 5.0})
    assert "manual_handling_weight_kg" in str(exc.value)


def test_FD_R2_11_manual_child_parent_true_allowed():
    b = _body({"has_manual_heavy_handling": True, "manual_handling_weight_kg": 5.0})
    assert b.form_data["manual_handling_weight_kg"] == 5.0


def test_FD_R2_12_child_none_parent_false_allowed():
    """Absent child is always OK regardless of parent."""
    b = _body({"has_truck_loading_unloading": False, "truck_loading_height_m": None})
    assert b.form_data["truck_loading_height_m"] is None


# ── FD-R3: string type bypass prevention ────────────────────────────────────
# work_height_m / truck_loading_height_m / manual_handling_weight_kg must be
# numeric (int/float) or None — strings are rejected, not coerced.

def test_FD_R3_01_work_height_string_rejected():
    with pytest.raises(ValidationError) as exc:
        _body({"work_height_m": "-1"})
    assert "work_height_m" in str(exc.value)


def test_FD_R3_02_work_height_string_positive_rejected():
    """Even a valid-looking positive string must be rejected — no coercion."""
    with pytest.raises(ValidationError) as exc:
        _body({"work_height_m": "5.0"})
    assert "work_height_m" in str(exc.value)


def test_FD_R3_03_truck_loading_height_string_rejected():
    with pytest.raises(ValidationError) as exc:
        _body({"has_truck_loading_unloading": True, "truck_loading_height_m": "1.5"})
    assert "truck_loading_height_m" in str(exc.value)


def test_FD_R3_04_manual_handling_weight_string_rejected():
    with pytest.raises(ValidationError) as exc:
        _body({"has_manual_heavy_handling": True, "manual_handling_weight_kg": "25"})
    assert "manual_handling_weight_kg" in str(exc.value)


def test_FD_R3_05_work_height_list_rejected():
    with pytest.raises(ValidationError) as exc:
        _body({"work_height_m": [2.0]})
    assert "work_height_m" in str(exc.value)


def test_FD_R3_06_work_height_none_allowed():
    """None is always allowed — not a type violation."""
    b = _body({"work_height_m": None})
    assert b.form_data["work_height_m"] is None


def test_FD_R3_07_unrelated_string_not_blocked():
    """Non-strict fields accept any value — only the 3 targeted keys are guarded."""
    b = _body({"some_flag": "yes"})
    assert b.form_data["some_flag"] == "yes"
