from services.rule_v2_adapter import (
    adapt_v2_batch,
    adapt_v2_to_v1,
    build_relation_map,
    build_scope_map,
    filter_v2_rules_for_sector,
    merge_scope_with_thresholds,
)


def _sample_obligation() -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "rule_kind": "OBLIGATION",
        "status": "ACTIVE",
        "sectors": ["BUILDING"],
        "why_law_citation": "산업안전보건법 제36조",
        "why_obligation_summary": "안전관리자를 선임하여야 한다",
        "what_action_text_raw": "안전관리자를 선임하여야 한다",
        "what_action": "선임",
        "obligation_category": "선임",
        "when_cycle_type": "YEARLY",
        "when_cycle_value": 1,
        "when_cycle_unit": "YEAR",
        "scope_min_employees": 50,
    }


def test_adapt_obligation_maps_core_fields():
    v1 = adapt_v2_to_v1(_sample_obligation())
    assert v1 is not None
    assert v1["rule_id"] == "11111111-1111-1111-1111-111111111111"
    assert v1["law_name"] == "산업안전보건법"
    assert v1["law_article"] == "제36조"
    assert v1["obligation_type"] == "APPOINT"
    assert v1["appointment_required"] is True
    assert v1["rule_type_code"] == "001"
    assert v1["sector"] == "BUILDING"
    assert v1["condition_code"] == "employee_count"
    assert v1["condition_value"] == 50
    assert v1["cycle_unit_std"] == "year"
    assert v1["inspection_cycle_unit_code"] == "006"


def test_penalty_rule_kind_returns_none():
    assert adapt_v2_to_v1({"id": "p1", "rule_kind": "PENALTY"}) is None
    assert adapt_v2_to_v1({"id": "d1", "rule_kind": "DEFINITION"}) is None


def test_relation_penalty_merge():
    obl = _sample_obligation()
    rel = {
        "source_rule_id": obl["id"],
        "target_rule_id": "pen-1",
        "relation_type": "has_penalty",
        "penalty_summary": "500만원 이하 과태료",
    }
    v1 = adapt_v2_to_v1(obl, relation=rel)
    assert v1["penalty_summary"] == "500만원 이하 과태료"


def test_scope_threshold_maps_condition():
    obl = {
        "id": "22222222-2222-2222-2222-222222222222",
        "rule_kind": "OBLIGATION",
        "status": "ACTIVE",
        "sectors": ["MANUFACTURING"],
        "why_law_citation": "근로기준법 제24조",
        "why_obligation_summary": "근로자 대표와 협의하여야 한다",
        "what_action_text_raw": "협의하여야 한다",
        "obligation_category": "조치",
    }
    scope = merge_scope_with_thresholds(
        {"layer": "LABOR", "scope_code": "SCOPE_x"},
        [{"criterion_code": "employee", "numeric_value": 100, "operator": "GTE"}],
    )
    v1 = adapt_v2_to_v1(obl, scope=scope)
    assert v1["condition_code"] == "employee_count"
    assert v1["condition_value"] == 100
    assert v1["condition_operator_code"] == "gte"
    assert v1["law_category_code"] == "LABOR"


def test_adapt_v2_batch_and_sector_filter():
    rows = [
        _sample_obligation(),
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "rule_kind": "OBLIGATION",
            "status": "ACTIVE",
            "sectors": ["CONSTRUCTION"],
            "why_law_citation": "건설기술진흥법 제10조",
            "why_obligation_summary": "안전점검을 실시하여야 한다",
            "obligation_category": "점검",
        },
        {"id": "x", "rule_kind": "PENALTY", "why_obligation_summary": "벌칙"},
    ]
    out = adapt_v2_batch(rows, sector_hint="BUILDING")
    assert len(out) == 2
    assert all(r["sector"] == "BUILDING" for r in out if r["rule_id"].startswith("1111"))

    filtered = filter_v2_rules_for_sector(rows, "CONSTRUCTION")
    assert len(filtered) == 1
    assert filtered[0]["id"].startswith("3333")


def test_draft_status_counts_as_active():
    v1 = adapt_v2_to_v1(
        {
            "id": "draft-1",
            "rule_kind": "OBLIGATION",
            "status": "DRAFT",
            "sectors": ["BUILDING"],
            "why_law_citation": "테스트법 제1조",
            "why_obligation_summary": "조치하여야 한다",
            "action_category_code": "action",
        }
    )
    assert v1 is not None
    assert v1["is_active"] is True


def test_build_relation_and_scope_maps():
    rel_map = build_relation_map(
        [{"source_rule_id": "a", "target_rule_id": "b", "relation_type": "has_penalty"}]
    )
    assert "a" in rel_map

    scope_map = build_scope_map(
        [{"rule_id": "r1", "scope_id": "s1"}],
        {"s1": {"layer": "SAFETY", "scope_code": "SCOPE_1"}},
        {"s1": [{"criterion_code": "area_floor", "numeric_value": 5000, "operator": "GTE"}]},
    )
    assert scope_map["r1"]["layer"] == "SAFETY"
    assert len(scope_map["r1"]["thresholds"]) == 1
