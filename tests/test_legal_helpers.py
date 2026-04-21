from services.legal_helpers import (
    _normalize_target_code,
    _parse_survey_data,
    _to_float,
    _to_int,
    get_construction_amount_threshold,
    get_effective_worker_count,
    get_sector_groups,
)


def test_to_float_and_to_int_fallbacks():
    assert _to_float(None, "", "x", "3.5") == 3.5
    assert _to_float(None, "x") == 0.0
    assert _to_int(None, "", "12.9") == 12
    assert _to_int("abc") == 0


def test_parse_and_normalize_helpers():
    assert _parse_survey_data('{"a": 1}') == {"a": 1}
    assert _parse_survey_data("{bad json}") is None
    assert _normalize_target_code("소방안전관리자") == "fire_safety_manager"
    assert _normalize_target_code("custom") == "custom"


def test_sector_groups_and_construction_worker_threshold():
    assert "COMMON" in get_sector_groups("building")
    assert get_sector_groups("unknown") == ["UNKNOWN"]
    assert get_effective_worker_count({"sector": "CONSTRUCTION", "employee_count": 10, "subcontractor_worker_count": 7}) == 17
    assert get_construction_amount_threshold({"construction_type": "토목"}) == 12_000_000_000
