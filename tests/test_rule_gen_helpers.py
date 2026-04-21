from services.rule_gen_helpers import (
    _extract_json_payload,
    _is_blank,
    _normalize_submit_org_code,
    _safe_float,
    _safe_int,
    _to_bool,
    _validate_rule_row,
)


def test_safe_number_and_bool_helpers():
    assert _safe_float("3.14") == 3.14
    assert _safe_float("abc") is None
    assert _safe_int("12.9") == 12
    assert _safe_int(None) is None
    assert _to_bool("true") is True
    assert _to_bool("0") is False


def test_extract_json_payload_and_blank_and_org_code():
    assert _extract_json_payload('{"a":1}') == {"a": 1}
    assert _extract_json_payload("```json\n[1,2]\n```") == [1, 2]
    assert _is_blank(None) is True
    assert _is_blank("  ") is True
    assert _normalize_submit_org_code("KOSHA") == "kosha"
    assert _normalize_submit_org_code("unknown") is None


def test_validate_rule_row_errors():
    row = {
        "condition_code": "worker_count",
        "condition_operator_code": "gte",
        "condition_value": 50,
        "inspection_required": True,
        "inspection_cycle_value": None,
        "inspection_cycle_unit_code": None,
        "report_required": True,
        "report_method_code": None,
        "appointment_required": True,
        "appointment_qualification_code": None,
        "penalty_summary": "벌칙",
        "penalty_value": None,
        "obligation_summary": "",
    }
    errs = _validate_rule_row(row)
    assert "missing_inspection_cycle" in errs
    assert "missing_report_method" in errs
    assert "missing_qualification" in errs
    assert "missing_penalty_value" in errs
    assert "missing_obligation_summary" in errs
