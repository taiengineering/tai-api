from services.legal_rules import (
    _check_rule_conditions,
    _resolve_obligation_type,
    evaluate_facility_conditions_db,
    normalize_sector_db,
    risk_level,
)


def test_check_rule_conditions_numeric_and_boolean():
    rule = {"condition_code": "worker_count", "condition_operator_code": "gte", "condition_value": "50"}
    assert _check_rule_conditions(rule, {"worker_count": 60}) is True
    assert _check_rule_conditions(rule, {"worker_count": 49}) is False

    bool_rule = {"condition_code": "is_hazardous_material", "condition_value": None}
    assert _check_rule_conditions(bool_rule, {"is_hazardous_material": 1}) is True
    assert _check_rule_conditions(bool_rule, {"is_hazardous_material": 0}) is False


def test_resolve_obligation_and_risk_level():
    assert _resolve_obligation_type({"notify_required": True}) == "NOTIFY"
    assert _resolve_obligation_type({"action_required": True}) == "ACTION"
    assert _resolve_obligation_type({}) == "OTHER"
    assert risk_level(12, 0) == "HIGH"
    assert risk_level(6, 0) == "MEDIUM"
    assert risk_level(2, 0) == "LOW"
    assert normalize_sector_db(" building ") == "BUILDING"


def test_evaluate_facility_conditions_db_filters():
    facility_ctx = {"worker_count": 55}
    rules = [
        {"rule_id": "r1", "sector": "COMMON", "condition_code": None, "condition_value": None},
        {"rule_id": "r2", "sector": "CONSTRUCTION", "condition_code": "worker_count", "condition_operator_code": "gte", "condition_value": "50"},
        {"rule_id": "r3", "sector": "CONSTRUCTION", "condition_code": "worker_count", "condition_operator_code": "gte", "condition_value": "100"},
    ]
    applicable, not_applicable = evaluate_facility_conditions_db(facility_ctx, rules, "CONSTRUCTION")
    ids_app = {r["rule_id"] for r in applicable}
    ids_not = {r["rule_id"] for r in not_applicable}
    assert ids_app == {"r1", "r2"}
    assert ids_not == {"r3"}
