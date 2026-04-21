from services.rule_gen_builders import _build_draft_row, _build_master_payload, _build_reparse_prompt, _pick_reparse_targets


def test_build_master_payload_core_mapping():
    row = {
        "sector": "BUILDING",
        "law_name": "산안법",
        "law_article": "제1조",
        "obligation_type": "INSPECT",
        "obligation_summary": "정기점검",
        "condition_value": "50",
        "submit_org_code": "KOSHA",
        "inspection_required": True,
        "inspection_cycle_value": "6",
        "inspection_cycle_unit_code": "month",
    }
    payload = _build_master_payload(row, "R-1")
    assert payload["rule_id"] == "R-1"
    assert payload["submit_org_code"] == "kosha"
    assert payload["condition_value"] == 50.0
    assert payload["inspection_cycle_value"] == 6


def test_build_draft_row_and_pick_targets():
    draft = _build_draft_row("산안법", "제2조", "a1", "본문", {"draft_rule_id": "D1", "obligation_type": "REPORT", "sector": "COMMON"})
    assert draft["draft_rule_id"] == "D1"
    assert draft["article_id"] == "a1"

    rows = [
        {"rule_id": "r1", "penalty_summary": None, "form_code": None, "remarks": None},
        {"rule_id": "r2", "penalty_summary": "x", "form_code": "f", "remarks": "ok"},
    ]
    picked = _pick_reparse_targets(rows, 1)
    assert picked[0]["rule_id"] == "r1"


def test_build_reparse_prompt_contains_context():
    prompt = _build_reparse_prompt({"rule_id": "R1"}, "컨텍스트", [{"rule_id": "E1"}])
    assert "기존 룰" in prompt
    assert "컨텍스트" in prompt
