from services import legal_v510_helpers as h


def test_contract_amount_alias_map_snapshot():
    assert h.CONDITION_CODE_TO_CONTEXT_KEY_V510["contract_amount"] == "construction_amount"


def test_context_builder_construction_threshold_building():
    ctx = h._input_to_facility_context_v510(
        "CONSTRUCTION",
        {
            "construction_type": "BUILDING",
            "contract_amount_eok": 160,
            "direct_workers": 10,
            "subcon_workers": 0,
        },
    )
    assert ctx["safety_manager_threshold"] == 15_000_000_000
    assert ctx["construction_amount"] == 16_000_000_000.0


def test_rule_match_numeric_gte():
    matched = h._db_rule_matches_facility_v510(
        {
            "condition_code": "worker_count",
            "condition_value": 50,
            "condition_operator_code": "gte",
        },
        {"worker_count": 50},
    )
    assert matched is True


def test_construction_summary_amount_only_snapshot():
    summary = h._get_construction_summary(
        {
            "construction_type": "CIVIL",
            "construction_amount": 12_000_000_000,
            "worker_count": 10,
        }
    )
    assert summary["safety_manager_required"] is True
    assert summary["key_thresholds_met"]["120억_안전관리자선임_토목"] is True
