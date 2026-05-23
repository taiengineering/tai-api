"""작업지시서 최종 확인: adapter → format_rule_result_db → _classify_rules_db."""

from services.legal_format import _classify_rules_db, format_rule_result_db
from services.rule_candidate_projection import project_metadata_to_v1
from services.rule_v2_adapter import adapt_v2_to_v1

FORMAT_DB_REQUIRED_INPUT_KEYS = frozenset(
    {
        "rule_id",
        "rule_type_code",
        "law_name",
        "law_article",
        "obligation_summary",
        "obligation_type",
        "appointment_required",
        "inspection_required",
        "action_required",
        "report_required",
        "notify_required",
        "sector",
        "diagnosis_stage",
    }
)


def test_v2_adapter_produces_classifiable_row():
    v2 = {
        "id": "11111111-1111-1111-1111-111111111111",
        "rule_kind": "OBLIGATION",
        "status": "ACTIVE",
        "sectors": ["BUILDING"],
        "why_law_citation": "산업안전보건법 제36조",
        "why_obligation_summary": "안전관리자를 선임하여야 한다",
        "obligation_category": "선임",
    }
    v1 = adapt_v2_to_v1(v2)
    assert v1 is not None
    assert FORMAT_DB_REQUIRED_INPUT_KEYS <= set(v1.keys())

    triggered = {"appointment": [], "inspection": [], "notify": [], "report": [], "action": []}
    _classify_rules_db([v1], triggered)
    assert len(triggered["appointment"]) == 1
    formatted = triggered["appointment"][0]
    assert formatted["law_name"] == "산업안전보건법"
    assert formatted["obligation_type"] == "APPOINT"


def test_runtime_projection_produces_classifiable_row():
    meta = {
        "id": "22222222-2222-2222-2222-222222222222",
        "runtime_name": "안전관리자 선임",
        "source_law_name": "산업안전보건법",
        "source_article_no": "17",
        "who_value": "사업주",
        "when_value": "14일이내",
        "how_value": "선임+신고",
        "sector": "ALL",
    }
    v1 = project_metadata_to_v1(meta, sector_hint="BUILDING")
    assert FORMAT_DB_REQUIRED_INPUT_KEYS <= set(v1.keys())

    triggered = {"appointment": [], "inspection": [], "notify": [], "report": [], "action": []}
    _classify_rules_db([v1], triggered)
    assert len(triggered["appointment"]) == 1
    row = format_rule_result_db(v1)
    assert row["law_name"] == "산업안전보건법"
    assert row.get("rule_id")
    assert row.get("schedule_type")
