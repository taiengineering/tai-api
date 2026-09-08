"""Obligation Result Contract v1 + presentation mappers 단위테스트.

WO-OBLIGATION-RESULT-CONTRACT-001 / T1~T10 + PATCH-1(absent≠null / mapped_field / known types).
DB/network 불필요. contract 모델 테스트는 pydantic 필요(레포 pytest).
"""
import copy

from schemas.obligation_result_v1 import (
    ObligationResultV1, ObligationDetailV1, ObligationEnrichmentV1,
)
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
        "mapped_field": "has_alarm_device",
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
            "completeness": "PARTIAL",
            "needs_numeric_condition": True,
            "missing_fields": ["floor_area"],
        },
        "evidence": "산업안전보건기준에 관한 규칙 제19조",
        "triggered_by": ["floor_area>=400"],
        "check_result": "VERIFIED",
        "applicability": "APPLICABLE",
    }


def _thin_ob():
    # where/how/recipient/mapped_field/triggered_by/evidence/check_result 부재
    return {
        "atom_id": "b-1",
        "law_name": "건축물의 설비기준 등에 관한 규칙",
        "law_article": "20",
        "obligation_detail": {"what": "설치", "who": "사업주", "condition": "해당시"},
        "enrichment": {"obligation_type": "INSPECT"},
    }


def _dump(m):
    # pydantic v2(model_dump) / v1(dict) 양립
    return m.model_dump(exclude_unset=True) if hasattr(m, "model_dump") else m.dict(exclude_unset=True)


# ── T1 core ──
def test_t1_core_fields_mapped():
    d = map_diagnosis_presentation(_full_ob())
    assert d["action"] == "경보용 설비 또는 기구를 설치하여야 한다"
    assert d["actor"] == "사업주" and d["timing"] == "즉시"
    assert d["condition"] == "연면적 400㎡ 이상" and d["cycle"] == "ANNUAL"


# ── T2 present preserved ──
def test_t2_present_preserved():
    d = map_diagnosis_presentation(_full_ob())
    assert d["where"] == "옥내작업장" and d["how"] == "설치" and d["recipient"] == "고용노동부장관"
    op = map_operation_presentation(_full_ob())
    assert op["location"] == "옥내작업장" and op["method"] == "설치" and op["recipient"] == "고용노동부장관"


# ── T3 absent → key 미생성 (PATCH-1 P2) ──
def test_t3_absent_no_key():
    d = map_diagnosis_presentation(_thin_ob())
    for k in ("where", "how", "recipient", "timing", "cycle", "reason", "evidence", "status"):
        assert k not in d
    op = map_operation_presentation(_thin_ob())
    for k in ("method", "location", "recipient", "timing", "cycle", "reason"):
        assert k not in op
    # identity 는 atom_id 있으므로 존재하되 source_atom_ids 는 미포함
    assert op["identity"] == {"atom_id": "b-1"}


# ── PATCH-1: explicit None 보존 ──
def test_explicit_none_preserved_in_mapper():
    ob = {"obligation_detail": {"what": "x", "recipient": None, "where": None}, "law_name": "L"}
    d = map_diagnosis_presentation(ob)
    assert "recipient" in d and d["recipient"] is None    # 명시 None 유지
    assert "where" in d and d["where"] is None
    op = map_operation_presentation(ob)
    assert "recipient" in op and op["recipient"] is None
    assert "location" in op and op["location"] is None


def test_empty_identity_not_created():
    op = map_operation_presentation({"obligation_detail": {"what": "x"}})
    assert "identity" not in op                            # atom_id/source_atom_ids 둘 다 없음 → 미생성


# ── T4 legal_basis ──
def test_t4_legal_basis():
    assert map_diagnosis_presentation(_full_ob())["legal_basis"] == {"law_name": "산업안전보건기준에 관한 규칙", "law_article": "19"}


def test_legal_basis_partial_only_present():
    d = map_diagnosis_presentation({"law_name": "L", "obligation_detail": {"what": "x"}})
    assert d["legal_basis"] == {"law_name": "L"}           # law_article 부재 → 미포함
    assert "legal_basis" not in map_diagnosis_presentation({"obligation_detail": {"what": "x"}})


# ── T5 identity ──
def test_t5_identity():
    assert map_operation_presentation(_full_ob())["identity"] == {"atom_id": "a-1", "source_atom_ids": ["a-1", "a-2"]}


# ── T6 reason/evidence ──
def test_t6_reason_evidence():
    d = map_diagnosis_presentation(_full_ob())
    assert d["reason"] == ["floor_area>=400"] and d["evidence"] == "산업안전보건기준에 관한 규칙 제19조"


# ── T7 법적 의미 불변 ──
def test_t7_no_legal_meaning_change():
    ob = _full_ob()
    d = map_diagnosis_presentation(ob)
    assert d["action"] == ob["obligation_detail"]["what"] and d["actor"] == ob["obligation_detail"]["who"]


# ── T8 operation SaaS-only 0 ──
def test_t8_operation_no_saas_only():
    op = map_operation_presentation(_full_ob())
    for k in ("assignee_user_id", "next_due_date", "status", "completed_at", "execution_record", "attachment"):
        assert k not in op


# ── T9 no mutation ──
def test_t9_no_input_mutation():
    ob = _full_ob()
    snap = copy.deepcopy(ob)
    map_diagnosis_presentation(ob)
    map_operation_presentation(ob)
    assert ob == snap


# ── T10 deterministic ──
def test_t10_deterministic():
    ob = _full_ob()
    assert map_diagnosis_presentation(ob) == map_diagnosis_presentation(copy.deepcopy(ob))
    assert map_operation_presentation(ob) == map_operation_presentation(copy.deepcopy(ob))


def test_malformed_input_no_crash():
    for bad in (None, [], "x", 123, {}):
        assert isinstance(map_diagnosis_presentation(bad), dict)
        assert isinstance(map_operation_presentation(bad), dict)


# ── PATCH-1: contract 모델 (pydantic) ──
def test_contract_absent_vs_explicit_none():
    # absent: thin 에 없는 mapped_field/evidence/triggered_by → exclude_unset dump 에 key 없음
    dumped = _dump(ObligationResultV1.from_raw(_thin_ob()))
    for k in ("mapped_field", "evidence", "triggered_by", "check_result", "applicability", "source_atom_ids"):
        assert k not in dumped
    # explicit None: source 에 명시된 None → key 유지 + None
    dumped2 = _dump(ObligationResultV1.from_raw({"atom_id": "z", "evidence": None}))
    assert "evidence" in dumped2 and dumped2["evidence"] is None
    # nested detail: 없는 where/how/recipient → detail dump 에 key 없음
    d_detail = _dump(ObligationResultV1.from_raw(_thin_ob()).obligation_detail)
    for k in ("where", "how", "recipient", "when"):
        assert k not in d_detail
    assert d_detail["what"] == "설치"


def test_contract_mapped_field_and_types():
    m = ObligationResultV1.from_raw(_full_ob())
    assert m.mapped_field == "has_alarm_device"           # P3 계약 반영
    assert m.source_atom_ids == ["a-1", "a-2"]
    assert m.triggered_by == ["floor_area>=400"]
    assert m.enrichment.missing_fields == ["floor_area"]
    assert m.enrichment.completeness == "PARTIAL"          # P4 문자열
    assert isinstance(m.obligation_detail, ObligationDetailV1)
    assert isinstance(m.enrichment, ObligationEnrichmentV1)
