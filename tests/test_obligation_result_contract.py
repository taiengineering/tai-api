"""Obligation Result Contract v1 + presentation mappers 단위테스트.

WO-OBLIGATION-RESULT-CONTRACT-001 / T1~T10. DB/network 불필요.
"""
import copy

from schemas.obligation_result_v1 import ObligationResultV1, ObligationDetailV1, ObligationEnrichmentV1
from services.obligation_presentation_mapper import (
    map_diagnosis_presentation,
    map_operation_presentation,
)


def _full_ob():
    return {
        "atom_id": "a-1",
        "source_atom_ids": ["a-1", "a-2"],
        "law_name": "산업안전보건기준에 관한 규칙",
        "law_article": "19",
        "obligation_detail": {
            "what": "경보용 설비 또는 기구를 설치하여야 한다",
            "who": "사업주",
            "when": "즉시",
            "where": "옥내작업장",
            "how": "설치",
            "condition": "연면적 400㎡ 이상",
            "recipient": "고용노동부장관",
        },
        "enrichment": {
            "obligation_type": "ACTION",
            "content_type": "OBLIGATION",
            "inspection_cycle": "ANNUAL",
            "consumer_status": "applicable",
            "usable_for_evaluation": True,
            "completeness": 0.9,
            "needs_numeric_condition": True,
            "missing_fields": [],
        },
        "evidence": "산업안전보건기준에 관한 규칙 제19조",
        "triggered_by": ["floor_area>=400"],
        "check_result": "VERIFIED",
        "applicability": "APPLICABLE",
    }


def _thin_ob():
    return {
        "atom_id": "b-1",
        "law_name": "건축물의 설비기준 등에 관한 규칙",
        "law_article": "20",
        "obligation_detail": {"what": "설치", "who": "사업주", "condition": "해당시"},
        "enrichment": {"obligation_type": "INSPECT"},
    }


# ── T1 ──
def test_t1_core_fields_mapped():
    d = map_diagnosis_presentation(_full_ob())
    assert d["action"] == "경보용 설비 또는 기구를 설치하여야 한다"
    assert d["actor"] == "사업주"
    assert d["timing"] == "즉시"
    assert d["condition"] == "연면적 400㎡ 이상"
    assert d["cycle"] == "ANNUAL"


# ── T2 ──
def test_t2_where_how_recipient_preserved_when_present():
    d = map_diagnosis_presentation(_full_ob())
    assert d["where"] == "옥내작업장"
    assert d["how"] == "설치"
    assert d["recipient"] == "고용노동부장관"
    op = map_operation_presentation(_full_ob())
    assert op["location"] == "옥내작업장"
    assert op["method"] == "설치"
    assert op["recipient"] == "고용노동부장관"


# ── T3 ──
def test_t3_absent_where_how_recipient_no_default():
    d = map_diagnosis_presentation(_thin_ob())
    assert "where" not in d          # diagnosis: 없으면 키 자체 미생성
    assert "how" not in d
    assert d["recipient"] is None    # 없으면 None (임의 문자열 default 아님)
    op = map_operation_presentation(_thin_ob())
    assert op["method"] is None      # 없으면 None (생성 안 함)
    assert op["location"] is None
    assert op["recipient"] is None


# ── T4 ──
def test_t4_legal_basis_preserved():
    d = map_diagnosis_presentation(_full_ob())
    assert d["legal_basis"] == {"law_name": "산업안전보건기준에 관한 규칙", "law_article": "19"}
    op = map_operation_presentation(_full_ob())
    assert op["legal_basis"] == {"law_name": "산업안전보건기준에 관한 규칙", "law_article": "19"}


# ── T5 ──
def test_t5_identity_preserved():
    op = map_operation_presentation(_full_ob())
    assert op["identity"] == {"atom_id": "a-1", "source_atom_ids": ["a-1", "a-2"]}


# ── T6 ──
def test_t6_triggered_by_evidence_preserved():
    d = map_diagnosis_presentation(_full_ob())
    assert d["reason"] == ["floor_area>=400"]
    assert d["evidence"] == "산업안전보건기준에 관한 규칙 제19조"


# ── T7 ──
def test_t7_diagnosis_no_legal_meaning_change():
    ob = _full_ob()
    d = map_diagnosis_presentation(ob)
    # action == 입력 what 그대로 (요약/재작성 없음)
    assert d["action"] == ob["obligation_detail"]["what"]
    assert d["actor"] == ob["obligation_detail"]["who"]


# ── T8 ──
def test_t8_operation_no_saas_only_fields():
    op = map_operation_presentation(_full_ob())
    for k in ("assignee_user_id", "next_due_date", "status", "completed_at", "execution_record", "attachment"):
        assert k not in op


# ── T9 ──
def test_t9_no_input_mutation():
    ob = _full_ob()
    snapshot = copy.deepcopy(ob)
    map_diagnosis_presentation(ob)
    map_operation_presentation(ob)
    assert ob == snapshot


# ── T10 ──
def test_t10_deterministic():
    ob = _full_ob()
    assert map_diagnosis_presentation(ob) == map_diagnosis_presentation(copy.deepcopy(ob))
    assert map_operation_presentation(ob) == map_operation_presentation(copy.deepcopy(ob))


# ── 방어/계약 ──
def test_malformed_input_no_crash():
    for bad in (None, [], "x", 123, {}):
        assert isinstance(map_diagnosis_presentation(bad), dict)
        assert isinstance(map_operation_presentation(bad), dict)


def test_contract_model_from_raw_preserves_absent():
    m = ObligationResultV1.from_raw(_thin_ob())
    assert m.atom_id == "b-1"
    assert m.obligation_detail.what == "설치"
    assert m.obligation_detail.where is None      # 없는 값 None 보존
    assert m.obligation_detail.how is None
    assert m.enrichment.obligation_type == "INSPECT"
    assert m.enrichment.inspection_cycle is None


def test_contract_model_types():
    m = ObligationResultV1.from_raw(_full_ob())
    assert isinstance(m.obligation_detail, ObligationDetailV1)
    assert isinstance(m.enrichment, ObligationEnrichmentV1)
    assert m.enrichment.usable_for_evaluation is True
    assert m.check_result == "VERIFIED"
