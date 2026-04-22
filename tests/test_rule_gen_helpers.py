from services.rule_gen_helpers import (
    _extract_json_payload,
    _is_blank,
    _normalize_submit_org_code,
    _safe_float,
    _safe_int,
    _to_bool,
    _validate_rule_row,
    sanitize_master_patch,
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


def test_sanitize_master_patch_uuid_removal():
    """updated_by/created_by 컬럼에서 UUID 아닌 값은 제거된다."""
    for bad_value in ["system", "SYSTEM", "system_import", "", "admin", "SYSTEM_USER"]:
        patch = {"updated_by": bad_value, "law_name": "X"}
        sanitize_master_patch(patch)
        assert "updated_by" not in patch, f"sanitize가 '{bad_value}' 제거 실패"

    valid_uuid = "12345678-1234-1234-1234-123456789012"
    patch = {"updated_by": valid_uuid, "created_by": valid_uuid}
    sanitize_master_patch(patch)
    assert patch["updated_by"] == valid_uuid
    assert patch["created_by"] == valid_uuid


def test_sanitize_master_patch_numeric_coercion():
    """condition_value, penalty_value 등 numeric 컬럼은 변환 or 제거."""
    patch = {"condition_value": "50"}
    sanitize_master_patch(patch)
    assert patch["condition_value"] == 50.0

    for bad_value in ["과태료 최대 500만원", "true", "charging_business,group_supply_business"]:
        patch = {"penalty_value": bad_value}
        sanitize_master_patch(patch)
        if "penalty_value" in patch:
            assert isinstance(patch["penalty_value"], (int, float)), (
                f"'{bad_value}' 처리 후 잘못된 타입: {type(patch['penalty_value'])}"
            )


def test_sanitize_master_patch_varchar_truncate():
    long_value = "A" * 50
    patch = {"condition_code": long_value}
    sanitize_master_patch(patch)
    assert len(patch["condition_code"]) == 30


def test_sanitize_master_patch_preserves_valid_fields():
    patch = {
        "law_name": "건축법",
        "law_article": "제12조",
        "obligation_summary": "2년마다 안전점검 실시",
        "condition_code": "floor_count",
    }
    original = dict(patch)
    sanitize_master_patch(patch)
    assert patch == original
