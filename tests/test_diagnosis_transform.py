"""Tests for diagnosis_transform (BE-08) — Layer 4→5 obligations standardization."""

from routers.diagnosis_transform import _extract_obligations


def _sample_rule_row(**overrides):
    base = {
        "rule_id": "r1",
        "rule_type": "APPOINTMENT_TASK_CANDIDATE",
        "law_name": "산업안전보건법",
        "law_article": "제17조",
        "obligation_summary": "안전관리자 선임",
        "description": "안전관리자 선임",
        "category": "선임",
    }
    base.update(overrides)
    return base


def test_extract_obligations_expands_wrapper_items():
    rd = {
        "obligations": [
            {
                "category": "appointment",
                "label": "선임",
                "items": [
                    _sample_rule_row(rule_id="r1"),
                    _sample_rule_row(
                        rule_id="r2",
                        obligation_summary="보건관리자 선임",
                        law_name="화재의 예방 및 안전관리에 관한 법률",
                    ),
                ],
            },
            {
                "category": "inspection",
                "label": "점검",
                "items": [_sample_rule_row(rule_id="r3", rule_type="INSPECTION_TASK_CANDIDATE", obligation_summary="정기점검")],
            },
        ],
        "applicable_count": 3,
    }
    out = _extract_obligations(rd)
    assert len(out) == 3
    assert all("items" not in o for o in out)
    assert out[0]["title"] == "안전관리자 선임"
    assert out[0]["law_name"] == "산업안전보건법"
    assert out[0]["rule_type"] == "APPOINTMENT_TASK_CANDIDATE"
    assert out[0]["category"] == "선임"
    assert out[0]["evidence"] == ["산업안전보건법 제17조"]
    assert out[2]["title"] == "정기점검"
    assert out[2]["category"] == "점검"


def test_extract_obligations_wrapper_item_count_preserved():
    items = [_sample_rule_row(rule_id=f"r{i}") for i in range(5)]
    rd = {"obligations": [{"category": "action", "label": "조치", "items": items}]}
    out = _extract_obligations(rd)
    assert len(out) == len(items)


def test_extract_obligations_flat_dict_backward_compat():
    rd = {
        "obligations": [
            {
                "id": "flat-1",
                "category": "report",
                "title": "신고 의무",
                "description": "상세",
                "evidence": ["법령 근거"],
                "risk_level": "HIGH",
            }
        ]
    }
    out = _extract_obligations(rd)
    assert len(out) == 1
    assert out[0]["title"] == "신고 의무"
    assert out[0]["evidence"] == ["법령 근거"]
    assert out[0]["category"] == "신고"


def test_extract_obligations_key_obligations_strings_when_no_wrapper():
    rd = {"key_obligations": ["교육 실시", "점검 실시"]}
    out = _extract_obligations(rd)
    assert len(out) == 2
    assert out[0]["title"] == "교육 실시"
    assert out[0]["evidence"] == []


def test_extract_obligations_no_generic_title_for_wrapper_items():
    rd = {
        "obligations": [
            {
                "category": "appointment",
                "label": "선임",
                "items": [_sample_rule_row()],
            }
        ]
    }
    out = _extract_obligations(rd)
    assert out[0]["title"] != "의무사항"
    assert out[0]["title"] == "안전관리자 선임"
