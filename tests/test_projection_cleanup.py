"""tests/test_projection_cleanup.py"""

from services.projection_cleanup import (
    cleanup_projection,
    cleanup_runtime_labels,
    collapse_duplicates,
    stable_sort,
    stabilize_summary,
)


def test_cleanup_runtime_labels():
    assert cleanup_runtime_labels("SAFETY_INSPECTION_TASK_CANDIDATE 점검") == "점검"
    assert cleanup_runtime_labels("일반 텍스트") == "일반 텍스트"
    assert cleanup_runtime_labels("") == ""
    assert "_TASK_CANDIDATE" not in cleanup_runtime_labels(
        "APPOINTMENT_TASK_CANDIDATE: APPOINT_FAMILY 선임"
    )


def test_stabilize_summary_fallback():
    row = {"remarks": "상세한 설명입니다", "obligation_summary": "짧은요약"}
    assert stabilize_summary(row) == "상세한 설명입니다"

    row = {"remarks": "", "obligation_summary": "점검 의무 (제75조)"}
    assert stabilize_summary(row) == "점검 의무 (제75조)"

    row = {
        "remarks": "",
        "obligation_summary": "",
        "law_name": "산업안전보건법",
        "law_article": "제36조",
    }
    assert stabilize_summary(row) == "산업안전보건법 제36조 관련 의무"


def test_collapse_duplicates():
    rules = [
        {"rule_id": "R1", "law_name": "산안법", "law_article": "제36조", "obligation_summary": "점검"},
        {"rule_id": "R1", "law_name": "산안법", "law_article": "제36조", "obligation_summary": "점검"},
        {"rule_id": "R2", "law_name": "소방법", "law_article": "제10조", "obligation_summary": "신고"},
    ]
    result = collapse_duplicates(rules)
    assert len(result) == 2


def test_stable_sort_deterministic():
    rules = [
        {"category": "점검", "law_name": "소방법", "law_article": "제5조", "rule_id": "R2"},
        {"category": "선임", "law_name": "산안법", "law_article": "제15조", "rule_id": "R1"},
    ]
    sorted1 = stable_sort(rules)
    sorted2 = stable_sort(rules)
    assert sorted1 == sorted2
    assert sorted1[0]["category"] == "선임"


def test_pipeline_end_to_end():
    rules = [
        {
            "rule_id": "R1",
            "category": "점검",
            "law_name": "산안법",
            "law_article": "제36조",
            "obligation_summary": "SAFETY_INSPECTION_TASK_CANDIDATE",
            "remarks": "정기점검 실시",
            "description": "",
        },
        {
            "rule_id": "R1",
            "category": "점검",
            "law_name": "산안법",
            "law_article": "제36조",
            "obligation_summary": "SAFETY_INSPECTION_TASK_CANDIDATE",
            "remarks": "정기점검 실시",
            "description": "",
        },
    ]
    result = cleanup_projection(rules)
    assert result["stats"]["duplicates_removed"] == 1
    assert "_TASK_CANDIDATE" not in result["rules_table"][0].get("obligation_summary", "")
    assert result["rules_table"][0]["obligation_summary"] == "정기점검 실시"
