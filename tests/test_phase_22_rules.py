"""Phase 2.2 룰 매칭 단위 테스트 — 코드 시안 룰 + subtype_rule_match 보강."""

from __future__ import annotations

import pytest

from engine.phase_22_apply import PHASE22_RULE_INSERTS
from engine.subtype_rule_match import match_subtype_rule, pick_first_matching_subtype_rule


def _rule_from_tuple(t: tuple) -> dict:
    rule_name, sub_type, mstrat, pat, pos, pri, _desc = t
    return {
        "id": f"test-{rule_name}",
        "rule_name": rule_name,
        "sub_type": sub_type,
        "match_strategy": mstrat,
        "pattern": pat,
        "pattern_position": pos,
        "priority": pri,
    }


@pytest.fixture
def phase22_rules() -> list[dict]:
    return [_rule_from_tuple(t) for t in PHASE22_RULE_INSERTS]


@pytest.mark.parametrize(
    ("text", "expect_rule"),
    [
        ("법 제5조는 다음 각 호와 같다.", "ENUMERATION_LIST_INTRO_DAUM"),
        ("별표 3에 따른다.", "REFERENCE_TO_ATTACHMENT_BYULPYO"),
        ("별지 2 서식을 제출한다.", "REFERENCE_TO_ATTACHMENT_BYULJI"),
        ("안전관리자는 이를 이행하여야 한다.", "OBLIGATION_HEADER_YA_COMPOSITE"),
        ("사업주는 의무가 있다.", "OBLIGATION_HAS_DUTY_COMPOSITE"),
        ("이러한 행위는 안 된다.", "PROHIBITION_HEADER_AN_DOEN_COMP"),
        ("임의로 조작하면 못한다.", "PROHIBITION_HEADER_MOTHAN_COMP"),
    ],
)
def test_composite_rules_positive(text: str, expect_rule: str, phase22_rules: list[dict]) -> None:
    tok: list[dict] = [{"form": "x", "tag": "NNG"}]
    rules = [r for r in phase22_rules if r["rule_name"] == expect_rule]
    assert len(rules) == 1
    assert match_subtype_rule(rules[0], tok, text) is True


def test_composite_tail_window_not_match_head_only() -> None:
    """COMPOSITE + pattern_position=TAIL — 앞부분만 일치하고 꼬리에는 없으면 미매칭."""
    rule = {
        "rule_name": "tail_test",
        "sub_type": "X",
        "match_strategy": "COMPOSITE",
        "pattern": r"꼬리마커",
        "pattern_position": "TAIL",
        "priority": 1,
    }
    long_head = "앞내용" * 80 + "다른끝"
    tok: list[dict] = [{"form": "x", "tag": "NNG"}]
    assert match_subtype_rule(rule, tok, long_head) is False
    tail_ok = "시작" * 40 + "여기꼬리마커"
    assert match_subtype_rule(rule, tok, tail_ok) is True


def test_tail_regex_strategy() -> None:
    rule = {
        "rule_name": "tr",
        "sub_type": "Y",
        "match_strategy": "TAIL_REGEX",
        "pattern": r"[가-힣]{2,}마커",
        "pattern_position": "ANY",
        "priority": 1,
    }
    tok: list[dict] = []
    assert match_subtype_rule(rule, tok, "xxx 테스트마커") is True


def test_tail_pos_wildcard_form() -> None:
    rule = {
        "rule_name": "wild",
        "sub_type": "Z",
        "match_strategy": "TAIL_POS",
        "pattern": "시험/NNG + */NNG",
        "pattern_position": "ANY",
        "priority": 1,
    }
    tok = [
        {"form": "앞", "tag": "NNG"},
        {"form": "시험", "tag": "NNG"},
        {"form": "무엇이든", "tag": "NNG"},
    ]
    assert match_subtype_rule(rule, tok, "") is True


def test_last_meaningful_tag_rule(phase22_rules: list[dict]) -> None:
    r = next(x for x in phase22_rules if x["rule_name"] == "ENUMERATION_ITEM_NOMINAL_LAST")
    tok = [{"form": "항목", "tag": "NNG"}]
    assert match_subtype_rule(r, tok, "") is True


def test_pick_first_priority_order(phase22_rules: list[dict]) -> None:
    rules = sorted(phase22_rules, key=lambda x: x["priority"])
    tok = [{"form": "호", "tag": "NNG"}]
    text = "다음과 같다 별표 1"
    picked = pick_first_matching_subtype_rule(rules, tok, text)
    assert picked is not None
    assert picked["rule_name"]


def test_all_phase22_rules_have_positive_case(phase22_rules: list[dict]) -> None:
    """각 INSERT 룰 최소 1건 긍정 샘플 (통합 커버리지)."""
    samples = {
        "ENUMERATION_LIST_INTRO_DAUM": ("다음 각 호와 같다 설명", []),
        "REFERENCE_TO_ATTACHMENT_BYULPYO": ("별표 10 참조", []),
        "REFERENCE_TO_ATTACHMENT_BYULJI": ("별지 5", []),
        "OBLIGATION_HEADER_YA_COMPOSITE": ("해야 한다", []),
        "OBLIGATION_HAS_DUTY_COMPOSITE": ("의무가 있다", []),
        "PROHIBITION_HEADER_AN_DOEN_COMP": ("안 된다", []),
        "PROHIBITION_HEADER_MOTHAN_COMP": ("못한다", []),
        "ENUMERATION_ITEM_NOMINAL_LAST": ("명사", [{"form": "명사", "tag": "NNG"}]),
    }
    by_name = {r["rule_name"]: r for r in phase22_rules}
    for name, r in by_name.items():
        text, tok = samples.get(name, ("다음 각 호와 같다", [{"form": "x", "tag": "NNG"}]))
        assert match_subtype_rule(r, tok, text), name
