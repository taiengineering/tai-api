"""tests/test_leg_obligation_enrichment.py"""

from services.leg_obligation_enrichment import (
    _check_missing_fields,
    _extract_who,
    _extract_when,
    _extract_what,
    _extract_condition,
    enrich,
)


def _make_ob(**overrides):
    base = {
        "obligation_id": "R1",
        "obligation_type": "INSPECT",
        "law_name": "산업안전보건법",
        "law_article": "제36조",
        "title": "위험성평가 실시",
        "description": "위험성평가를 실시해야 한다",
        "executor": {"type_code": "employer", "type_label": "사업주",
                      "appointment_target": "", "qualification": ""},
        "schedule_info": {"schedule_type": "PERIODIC", "cycle_label": "연 1회",
                          "cycle_unit": "year", "cycle_int": 1, "due_days": 0},
        "penalty_summary": "500만원 이하 과태료",
        "submission": {"org_code": "", "org_label": "", "method": "",
                       "method_label": "", "form_name": "", "form_url": "",
                       "system_name": "", "system_url": ""},
        "evidence": {"rule_id": "R1", "rule_type": "", "condition_code": "",
                      "condition_value": None, "source_bucket": "action_required"},
    }
    base.update(overrides)
    return base


def test_extract_who():
    ob = _make_ob(executor={"type_label": "사업주", "appointment_target": "",
                             "type_code": "", "qualification": ""})
    assert _extract_who(ob) == "사업주"


def test_extract_who_appointment():
    ob = _make_ob(executor={"type_label": "", "appointment_target": "안전관리자",
                             "type_code": "", "qualification": ""})
    assert _extract_who(ob) == "안전관리자"


def test_extract_when():
    ob = _make_ob(schedule_info={"cycle_label": "연 1회", "cycle_unit": "year",
                                  "cycle_int": 1, "due_days": 0,
                                  "schedule_type": "PERIODIC"})
    assert _extract_when(ob) == "연 1회"


def test_extract_what():
    ob = _make_ob(title="위험성평가 실시")
    assert _extract_what(ob) == "위험성평가 실시"


def test_extract_condition_present():
    ob = _make_ob(evidence={"condition_code": "employee_count",
                             "condition_value": 50, "rule_id": "R1",
                             "rule_type": "", "source_bucket": ""})
    assert _extract_condition(ob) == "employee_count"


def test_extract_condition_absent():
    ob = _make_ob(evidence={"condition_code": "", "condition_value": None,
                             "rule_id": "R1", "rule_type": "",
                             "source_bucket": ""})
    assert _extract_condition(ob) == ""


def test_missing_fields_complete():
    ob = _make_ob(
        executor={"type_label": "사업주", "appointment_target": "",
                   "type_code": "", "qualification": ""},
        schedule_info={"cycle_label": "연 1회", "cycle_unit": "",
                       "cycle_int": 0, "due_days": 0, "schedule_type": ""},
        evidence={"condition_code": "employee_count", "condition_value": 50,
                   "rule_id": "R1", "rule_type": "", "source_bucket": ""},
    )
    assert _check_missing_fields(ob) == []


def test_missing_fields_no_condition():
    ob = _make_ob(
        executor={"type_label": "사업주", "appointment_target": "",
                   "type_code": "", "qualification": ""},
        schedule_info={"cycle_label": "연 1회", "cycle_unit": "",
                       "cycle_int": 0, "due_days": 0, "schedule_type": ""},
        evidence={"condition_code": "", "condition_value": None,
                   "rule_id": "R1", "rule_type": "", "source_bucket": ""},
    )
    missing = _check_missing_fields(ob)
    assert "condition_code" in missing
    assert "who" not in missing


def test_missing_fields_multiple():
    ob = _make_ob(
        executor={"type_label": "", "appointment_target": "",
                   "type_code": "", "qualification": ""},
        schedule_info={"cycle_label": "", "cycle_unit": "",
                       "cycle_int": 0, "due_days": 0, "schedule_type": ""},
        title="",
        description="",
        evidence={"condition_code": "", "condition_value": None,
                   "rule_id": "R1", "rule_type": "", "source_bucket": ""},
    )
    missing = _check_missing_fields(ob)
    assert "who" in missing
    assert "when" in missing
    assert "what" in missing
    assert "condition_code" in missing


class MockSupabase:
    """enrich() 테스트용 mock — batch_resolve_numeric_flags를 bypass."""
    pass


def test_enrich_with_mock(monkeypatch):
    """needs_numeric=False → usable=True (조건 불필요)."""
    import services.leg_obligation_enrichment as mod

    def mock_resolve(sb, pairs):
        return {p: False for p in pairs}

    monkeypatch.setattr(mod, "batch_resolve_numeric_flags", mock_resolve)

    obs = [_make_ob()]
    result = enrich(obs, MockSupabase())
    assert len(result["applicable"]) == 1
    assert len(result["review_required"]) == 0
    assert result["applicable"][0]["enrichment"]["usable_for_evaluation"] is True


def test_enrich_needs_condition(monkeypatch):
    """needs_numeric=True + condition 없음 → review_required."""
    import services.leg_obligation_enrichment as mod

    def mock_resolve(sb, pairs):
        return {p: True for p in pairs}

    monkeypatch.setattr(mod, "batch_resolve_numeric_flags", mock_resolve)

    obs = [_make_ob()]
    result = enrich(obs, MockSupabase())
    assert len(result["applicable"]) == 0
    assert len(result["review_required"]) == 1
    assert result["review_required"][0]["enrichment"]["usable_for_evaluation"] is False
    assert "condition_code" in result["review_required"][0]["enrichment"]["missing_fields"]


def test_enrich_has_condition(monkeypatch):
    """condition 있음 → 무조건 applicable."""
    import services.leg_obligation_enrichment as mod

    def mock_resolve(sb, pairs):
        return {p: True for p in pairs}

    monkeypatch.setattr(mod, "batch_resolve_numeric_flags", mock_resolve)

    obs = [_make_ob(evidence={"condition_code": "employee_count",
                               "condition_value": 50, "rule_id": "R1",
                               "rule_type": "", "source_bucket": ""})]
    result = enrich(obs, MockSupabase())
    assert len(result["applicable"]) == 1
    assert result["applicable"][0]["enrichment"]["usable_for_evaluation"] is True


def test_enrich_empty():
    result = enrich([], MockSupabase())
    assert result["applicable"] == []
    assert result["review_required"] == []
    assert result["enrichment_stats"]["total"] == 0
