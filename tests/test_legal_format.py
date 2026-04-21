from services.legal_format import _calc_due_date, _classify_rules_db, format_rule_result, format_rule_result_db


def test_format_rule_result_core_fields():
    rule = {
        "rule_id": "R-1",
        "rule_type_code": "001",
        "law_name": "산업안전보건법",
        "law_article": "제1조",
        "remarks": "안전관리자 선임",
        "appointment_target_code": "safety_manager",
        "appointment_required": True,
        "condition_code": "worker_count",
        "condition_value": "50",
    }
    out = format_rule_result(rule)
    assert out["rule_id"] == "R-1"
    assert out["appointment_target"] == "안전관리자"
    assert out["obligation_type"] == "APPOINT"


def test_calc_due_date_and_penalty_fallback():
    d = _calc_due_date(3)
    assert d["due_days"] == 3
    assert d["urgency"] == "IMMEDIATE"

    db = format_rule_result_db({"rule_id": "R-2", "obligation_type": "REPORT", "report_required": True})
    assert db["penalty_summary"] == "미신고 시 과태료 부과 가능"


def test_classify_rules_db_deduplicates_appointment_target():
    rules = [
        {"rule_id": "A1", "obligation_type": "APPOINT", "appointment_target_code": "safety_manager"},
        {"rule_id": "A2", "obligation_type": "APPOINT", "appointment_target_code": "안전관리자"},
        {"rule_id": "I1", "obligation_type": "INSPECT", "inspection_required": True},
    ]
    triggered = {"appointment": [], "inspection": [], "notify": [], "report": [], "action": [], "not_applicable": []}
    _classify_rules_db(rules, triggered)
    assert len(triggered["appointment"]) == 1
    assert len(triggered["inspection"]) == 1
