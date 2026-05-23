from services.rule_candidate_projection import (
    filter_runtime_for_sector,
    project_metadata_batch,
    project_metadata_to_v1,
)


def _sample_metadata() -> dict:
    return {
        "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "runtime_name": "안전관리자 선임",
        "source_law_name": "산업안전보건법",
        "source_article_no": "17",
        "who_value": "사업주",
        "when_value": "14일이내",
        "how_value": "선임+신고",
        "schedule_json": {"unit": "일", "value": 14, "anchor": "선임사유", "operator": "이내"},
        "sector": "ALL",
        "condition_value": "50명",
    }


def test_project_metadata_maps_core_fields():
    v1 = project_metadata_to_v1(_sample_metadata(), sector_hint="BUILDING")
    assert v1["rule_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert v1["law_name"] == "산업안전보건법"
    assert v1["law_article"] == "제17조"
    assert v1["obligation_type"] == "APPOINT"
    assert v1["appointment_required"] is True
    assert v1["rule_type_code"] == "001"
    assert v1["sector"] == "BUILDING"
    assert v1["due_days"] == 14
    assert v1["condition_code"] == "employee_count"
    assert v1["condition_value"] == 50.0


def test_risk_assessment_maps_inspect():
    row = {
        "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "runtime_name": "위험성평가",
        "source_law_name": "산업안전보건법",
        "source_article_no": "36",
        "who_value": "사업주",
        "when_value": "정기",
        "how_value": "유해위험요인 파악",
        "schedule_json": {"정기": {"value": 1, "period": "년"}},
        "sector": "ALL",
    }
    v1 = project_metadata_to_v1(row, sector_hint="MANUFACTURING")
    assert v1["obligation_type"] == "INSPECT"
    assert v1["inspection_required"] is True
    assert v1["cycle_unit_std"] == "year"


def test_technical_runtime_falls_back_to_law_and_task_label():
    row = {
        "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
        "runtime_name": "INSTALL_TASK_CANDIDATE: INSTALL_FAMILY",
        "source_law_name": "산업안전보건기준에 관한 규칙",
        "source_article_no": "19",
        "who_value": "사업주",
        "when_value": None,
        "how_value": "INSTALL_FAMILY",
        "sector": "ALL",
    }
    v1 = project_metadata_to_v1(row, sector_hint="BUILDING")
    assert "산업안전보건기준" in v1["obligation_summary"]
    assert "INSTALL" in v1["obligation_summary"].upper()


def test_technical_runtime_name_uses_who_when_how():
    row = {
        "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "runtime_name": "APPOINTMENT_TASK_CANDIDATE: APPOINT_FAMILY",
        "source_law_name": "산업안전보건법",
        "source_article_no": "17",
        "who_value": "사업주",
        "when_value": "14일이내",
        "how_value": "안전관리자 선임",
        "sector": "ALL",
    }
    v1 = project_metadata_to_v1(row, sector_hint="BUILDING")
    assert "안전관리자 선임" in v1["obligation_summary"]
    assert v1["obligation_type"] == "APPOINT"


def test_filter_runtime_for_sector():
    rules = project_metadata_batch([_sample_metadata()], sector_hint="BUILDING")
    out = filter_runtime_for_sector(rules, "BUILDING")
    assert len(out) == 1
    assert filter_runtime_for_sector(rules, "CONSTRUCTION") == []
