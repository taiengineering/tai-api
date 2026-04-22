from routers import legal_engine_v510 as v510


def test_condition_code_map_includes_contract_amount_alias():
    assert v510.CONDITION_CODE_TO_CONTEXT_KEY_V510["contract_amount"] == "construction_amount"
    assert v510.CONDITION_CODE_TO_CONTEXT_KEY_V510["construction_amount"] == "construction_amount"


def test_input_context_construction_maps_amount_and_workers_snapshot():
    ctx = v510._input_to_facility_context_v510(
        "CONSTRUCTION",
        {
            "contract_amount_eok": 60,
            "construction_type": "CIVIL",
            "direct_workers": 20,
            "subcon_workers": 31,
        },
    )

    assert ctx["construction_amount"] == 6_000_000_000.0
    assert ctx["contract_amount"] == 6_000_000_000.0
    assert ctx["worker_count"] == 51
    assert ctx["direct_workers"] == 20
    assert ctx["subcon_workers"] == 31
    assert ctx["safety_manager_threshold"] == 12_000_000_000


def test_db_rule_matches_facility_uses_contract_amount_alias():
    context = {"construction_amount": 6_000_000_000.0}
    rule = {
        "condition_code": "contract_amount",
        "condition_value": 5_000_000_000,
        "condition_operator_code": "gte",
    }
    assert v510._db_rule_matches_facility_v510(rule, context) is True


def test_evaluate_facility_conditions_filters_non_construction_laws():
    facility_ctx = {"worker_count": 10}
    rules = [
        {"law_name": "산업안전보건법", "condition_code": None, "condition_value": None},
        {"law_name": "정보통신망법", "condition_code": None, "condition_value": None},
    ]
    applicable, not_applicable = v510._evaluate_facility_conditions_db_v510(
        facility_ctx,
        rules,
        "CONSTRUCTION",
    )

    assert len(applicable) == 1
    assert applicable[0]["law_name"] == "산업안전보건법"
    assert len(not_applicable) == 1
    assert not_applicable[0]["law_name"] == "정보통신망법"


def test_get_construction_summary_worker_threshold_snapshot():
    summary = v510._get_construction_summary(
        {
            "construction_amount": 1_000_000_000,
            "worker_count": 60,
            "construction_type": "BUILDING",
            "direct_workers": 40,
            "subcon_workers": 20,
        }
    )

    assert summary["site_type"] == "BUILDING"
    assert summary["safety_manager_required"] is True
    assert "근로자 50명 이상" in summary["safety_manager_basis"]
    assert summary["contract_amount_eok"] == 10.0


def test_get_construction_summary_civil_amount_threshold_snapshot():
    summary = v510._get_construction_summary(
        {
            "construction_amount": 12_000_000_000,
            "worker_count": 20,
            "construction_type": "CIVIL",
        }
    )

    assert summary["safety_manager_required"] is True
    assert summary["key_thresholds_met"]["120억_안전관리자선임_토목"] is True
    assert summary["key_thresholds_met"]["150억_안전관리자선임_건축"] is False
