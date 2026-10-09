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
# DEV-IN-004 / 004V: (B) 구조적 what_text/where_text 확장 + 매칭근거.
# (A) 누락 스펙은 emitter 미declared(dead) 확인되어 철회 → 기존 정식 코드로만 테스트.
# =====================================================================

def _clause(**kw):
    base = {
        "id": "c", "source_article_id": "a", "content_type": "OBLIGATION",
        "executor_text": "사업주", "condition_text": None, "action_text": "",
        "what_text": None, "where_text": None, "source_text": None,
    }
    base.update(kw)
    return base


# ---- (B) Positive: 설비명이 구조적 what_text/where_text 에만 있어도 검출 (기존 정식 코드) ----

def test_devin004_subject_in_what_text_detected():
    # 압력용기(EQUIPMENT:PRESSURE_VESSEL, 정식 코드)가 구조적 목적어(what_text)에만 존재
    c = _clause(
        condition_text="다음 각 호의 경우",
        action_text="사업주는 안전밸브를 설치해야 한다.",
        what_text="압력용기",
    )
    assert len(match_clauses_for_trigger([c], "EQUIPMENT:PRESSURE_VESSEL")) == 1


def test_devin004_subject_in_where_text_detected():
    # 밀폐공간(WORK:CONFINED_SPACE)이 구조적 장소(where_text)에만 존재
    c = _clause(
        action_text="사업주는 산소농도를 측정해야 한다.",
        where_text="밀폐공간",
    )
    assert len(match_clauses_for_trigger([c], "WORK:CONFINED_SPACE")) == 1


def test_devin004_matched_field_recorded_condition_action():
    clauses = [_clause(action_text="사업주는 밀폐공간의 산소농도를 측정해야 한다.")]
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.eq.return_value.range.return_value.execute.return_value.data = clauses
    out = generate_obligation_candidates(["WORK:CONFINED_SPACE"], sb)
    assert len(out) == 1
    assert out[0]["matched_field"] == "condition_action"
    assert out[0]["matched_text"] == "밀폐공간"


def test_devin004_matched_field_recorded_what_text():
    clauses = [_clause(action_text="사업주는 안전밸브를 설치한다.", what_text="압력용기")]
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.eq.return_value.range.return_value.execute.return_value.data = clauses
    out = generate_obligation_candidates(["EQUIPMENT:PRESSURE_VESSEL"], sb)
    assert len(out) == 1
    assert out[0]["matched_field"] == "what_text"


# ---- Negative: 과탐 방지 (수정과 동일 비중) ----

def test_devin004_neg_hazmat_only_in_source_text_not_matched():
    # (B) 핵심 가드: 위험물이 raw source_text 에만 있고
    # 구조적 필드(condition/action/what/where)엔 없으면 매칭하지 않는다.
    c = _clause(
        condition_text="다음의 경우",
        action_text="사업주는 게시판을 설치해야 한다.",
        what_text="게시판",
        where_text="출입구",
        source_text="위험물 저장소 인근의 사업장에서 사업주는 게시판을 설치해야 한다.",
    )
    assert match_clauses_for_trigger([c], "WORK:HAZARDOUS_MATERIAL") == []


def test_devin004_neg_absent_keyword_not_matched_even_with_structural():
    # 트리거 키워드가 어느 필드에도 없으면, 구조적 필드가 있어도 매칭되지 않는다.
    c = _clause(
        action_text="사업주는 근로자에게 안전보건교육을 실시해야 한다.",
        what_text="교육자료",
        where_text="회의실",
    )
    for code in ("WORK:CONFINED_SPACE", "EQUIPMENT:PRESSURE_VESSEL", "EQUIPMENT:CRANE"):
        assert match_clauses_for_trigger([c], code) == []


def test_devin004_neg_existing_behavior_condition_action_preserved():
    # 기존 동작 보존: condition+action 에 키워드 있으면 그대로 매칭
    c = _clause(condition_text="밀폐공간에서 작업하는 경우", action_text="환기한다")
    assert len(match_clauses_for_trigger([c], "WORK:CONFINED_SPACE")) == 1
