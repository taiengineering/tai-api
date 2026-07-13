"""Tests for trigger_generator + trigger_obligation_generator (CURSOR-TASK-001)."""

from unittest.mock import MagicMock

from services.trigger_generator import (
    generate_trigger_codes_from_row,
)
from services.trigger_obligation_generator import (
    generate_obligation_candidates,
    match_clauses_for_trigger,
)


def test_generate_trigger_codes_example_factory():
    row = {
        "employee_count": 80,
        "has_confined_space": True,
    }
    equipment = [{"equipment_type_code": "CRANE", "is_operating": True}]
    codes = generate_trigger_codes_from_row(row, equipment)
    assert codes == [
        "BUSINESS:REGISTERED",
        "THRESHOLD:EMPLOYEE_50_PLUS",
        "WORK:CONFINED_SPACE",
        "EQUIPMENT:CRANE",
        "EQUIPMENT_ACT:CRANE_USE",
    ]


def test_generate_trigger_codes_has_star_only_when_true():
    row = {
        "employee_count": 10,
        "has_confined_space": False,
        "has_blasting": True,
    }
    codes = generate_trigger_codes_from_row(row, [])
    assert "WORK:CONFINED_SPACE" not in codes
    assert "WORK:BLASTING" in codes
    assert "THRESHOLD:EMPLOYEE_50_PLUS" not in codes


def test_obligation_candidates_business_registered_null_condition():
    clauses = [
        {
            "id": "c1",
            "source_article_id": "a1",
            "condition_text": None,
            "action_text": "사업주는 안전조치를 해야 한다.",
            "content_type": "OBLIGATION",
            "executor_text": "사업주",
        },
        {
            "id": "c2",
            "source_article_id": "a2",
            "condition_text": "밀폐공간에서 작업하는 경우",
            "action_text": "사업주는 환기를 해야 한다.",
            "content_type": "OBLIGATION",
            "executor_text": "사업주",
        },
    ]
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.eq.return_value.range.return_value.execute.return_value.data = clauses

    out = generate_obligation_candidates(["BUSINESS:REGISTERED"], sb)
    assert len(out) == 1
    assert out[0]["source_article_id"] == "a1"
    assert out[0]["confidence"] == "MEDIUM"


def test_obligation_candidates_confined_space_high_confidence():
    clauses = [
        {
            "id": "c1",
            "source_article_id": "a1",
            "condition_text": "밀폐공간에서 작업하는 경우",
            "action_text": "사업주는 산소농도를 측정해야 한다.",
            "content_type": "OBLIGATION",
            "executor_text": "사업주",
        }
    ]
    matched = match_clauses_for_trigger(clauses, "WORK:CONFINED_SPACE")
    assert len(matched) == 1


def test_obligation_candidates_dedupe_by_article():
    clauses = [
        {
            "id": "c1",
            "source_article_id": "a1",
            "condition_text": None,
            "action_text": "사업주는 해야 한다.",
            "content_type": "OBLIGATION",
            "executor_text": "사업주",
        },
        {
            "id": "c2",
            "source_article_id": "a1",
            "condition_text": "밀폐공간",
            "action_text": "사업주는 환기를 해야 한다.",
            "content_type": "OBLIGATION",
            "executor_text": "사업주",
        },
    ]
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.eq.return_value.range.return_value.execute.return_value.data = clauses

    out = generate_obligation_candidates(
        ["BUSINESS:REGISTERED", "WORK:CONFINED_SPACE"], sb
    )
    assert len(out) == 1
    assert out[0]["trigger_code"] == "WORK:CONFINED_SPACE"
    assert out[0]["confidence"] == "HIGH"


# =====================================================================
# DEV-IN-004: (A) 누락 스펙 추가 + (B) 구조적 what_text/where_text 확장
# =====================================================================

def _clause(**kw):
    base = {
        "id": "c", "source_article_id": "a", "content_type": "OBLIGATION",
        "executor_text": "사업주", "condition_text": None, "action_text": "",
        "what_text": None, "where_text": None, "source_text": None,
    }
    base.update(kw)
    return base


# ---- (A) Positive: 누락됐던 트리거가 검출된다 ----

def test_devin004_grinding_detected():
    c = _clause(action_text="사업주는 연삭기의 덮개를 설치해야 한다.")
    assert len(match_clauses_for_trigger([c], "WORK:GRINDING")) == 1


def test_devin004_dust_detected():
    c = _clause(condition_text="분진이 발생하는 작업을 하는 경우",
                action_text="사업주는 국소배기장치를 설치해야 한다.")
    assert len(match_clauses_for_trigger([c], "WORK:DUST")) == 1


def test_devin004_radiation_detected():
    c = _clause(action_text="사업주는 방사선 발생장치에 차폐물을 설치해야 한다.")
    assert len(match_clauses_for_trigger([c], "WORK:RADIATION")) == 1


def test_devin004_roller_detected():
    c = _clause(action_text="사업주는 압연롤러에 방호장치를 설치해야 한다.")
    assert len(match_clauses_for_trigger([c], "EQUIPMENT:ROLLER")) == 1


# ---- (B) Positive: 설비명이 구조적 what_text(목적어)에만 있어도 검출 ----

def test_devin004_subject_in_what_text_detected():
    # 압력용기가 condition/action 이 아닌 구조적 목적어(what_text)에만 존재
    c = _clause(
        condition_text="다음 각 호의 경우",
        action_text="사업주는 안전밸브를 설치해야 한다.",
        what_text="압력용기",
    )
    matched = match_clauses_for_trigger([c], "EQUIPMENT:PRESSURE_VESSEL")
    assert len(matched) == 1


def test_devin004_matched_field_recorded():
    clauses = [_clause(action_text="사업주는 연삭기 덮개를 설치해야 한다.")]
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.eq.return_value.range.return_value.execute.return_value.data = clauses
    out = generate_obligation_candidates(["WORK:GRINDING"], sb)
    assert len(out) == 1
    assert out[0]["matched_field"] == "condition_action"
    assert out[0]["matched_text"] == "연삭"


# ---- Negative: 과탐 방지 (수정과 동일 비중) ----

def test_devin004_neg_education_training_not_facility():
    # "교육"(훈련)이 시설/설비 트리거로 오매칭되지 않는다
    c = _clause(action_text="사업주는 근로자에게 안전보건교육을 실시해야 한다.")
    for code in ("WORK:GRINDING", "WORK:DUST", "WORK:RADIATION", "EQUIPMENT:ROLLER"):
        assert match_clauses_for_trigger([c], code) == []


def test_devin004_neg_office_work_not_facility():
    # "사무직"이 업무시설/설비 트리거로 오매칭되지 않는다
    c = _clause(action_text="사무직에 종사하는 근로자에 대하여 사업주는 휴게시설을 갖추어야 한다.")
    for code in ("WORK:GRINDING", "WORK:DUST", "EQUIPMENT:ROLLER", "EQUIPMENT:PRESS"):
        assert match_clauses_for_trigger([c], code) == []


def test_devin004_neg_cargo_vehicle_not_excavator():
    # "화물자동차"가 건설기계(굴착기) 트리거로 오매칭되지 않는다
    c = _clause(action_text="사업주는 화물자동차에 화물을 실을 때 낙하를 방지해야 한다.")
    assert match_clauses_for_trigger([c], "EQUIPMENT:EXCAVATOR") == []


def test_devin004_neg_factory_contrast_not_facility():
    # "공장"이 단순 대조어로 등장해도 facility 트리거로 오매칭되지 않는다
    c = _clause(
        action_text="사무직 근로자(공장 또는 공사현장과 같은 구역에 있지 않은 사람)에 대하여 사업주는 조치한다."
    )
    for code in ("WORK:GRINDING", "WORK:DUST", "WORK:RADIATION", "EQUIPMENT:ROLLER"):
        assert match_clauses_for_trigger([c], code) == []


def test_devin004_neg_hazmat_only_in_source_text_not_matched():
    # (B) 가드: 위험물이 raw source_text/source_part_text 에만 있고
    # 구조적 필드(condition/action/what/where)엔 없으면 매칭하지 않는다.
    c = _clause(
        condition_text="다음의 경우",
        action_text="사업주는 게시판을 설치해야 한다.",
        what_text="게시판",
        where_text="출입구",
        source_text="위험물 저장소 인근의 사업장에서 사업주는 게시판을 설치해야 한다.",
    )
    assert match_clauses_for_trigger([c], "WORK:HAZARDOUS_MATERIAL") == []
