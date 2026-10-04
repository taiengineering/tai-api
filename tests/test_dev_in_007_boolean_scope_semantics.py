"""DEV-IN-007: boolean scope applicability semantics.

우선 3개 건설작업 trigger(has_excavation_work/has_welding_work/has_demolition_work)에서
boolean 3-state 계약을 검증한다.
  true  -> MATCH_CANDIDATE
  false -> NOT_MATCHED
  null  -> POSSIBLE_CANDIDATE
회귀: numeric / business / 비대상 boolean scope 기존 동작 유지.
"""
from services.trigger_applicability_adapter import evaluate_candidate

_TARGETS = {
    "WORK:EXCAVATION": "has_excavation_work",
    "WORK:WELDING": "has_welding_work",
    "WORK:DEMOLITION": "has_demolition_work",
}


def _cand(code):
    return {"clause_id": "c", "source_article_id": "a", "trigger_code": code, "confidence": "HIGH"}


def _status(code, value):
    facility = {"id": "f"}
    if value is not None:
        facility[_TARGETS[code]] = value
    return evaluate_candidate(_cand(code), facility, [code])["applicability_status"]


def test_boolean_true_is_match():
    for code in _TARGETS:
        assert _status(code, True) == "MATCH_CANDIDATE"


def test_boolean_false_is_not_matched():
    for code in _TARGETS:
        assert _status(code, False) == "NOT_MATCHED"


def test_boolean_null_is_possible():
    for code in _TARGETS:
        assert _status(code, None) == "POSSIBLE_CANDIDATE"


def test_null_not_treated_as_false():
    # null은 NOT_MATCHED가 아니라 POSSIBLE (판단 유보)
    for code in _TARGETS:
        assert _status(code, None) != "NOT_MATCHED"


# ---- 회귀: 비대상 동작 유지 ----

def test_regression_numeric_threshold_unchanged():
    cand = {"clause_id": "t", "source_article_id": "a", "trigger_code": "THRESHOLD:EMPLOYEE_50_PLUS", "confidence": "HIGH"}
    assert evaluate_candidate(cand, {"employee_count": 80}, ["THRESHOLD:EMPLOYEE_50_PLUS"])["applicability_status"] == "MATCH_CANDIDATE"
    assert evaluate_candidate(cand, {"employee_count": 10}, ["THRESHOLD:EMPLOYEE_50_PLUS"])["applicability_status"] == "NOT_MATCHED"


def test_regression_business_registered_unchanged():
    cand = {"clause_id": "b", "source_article_id": "a", "trigger_code": "BUSINESS:REGISTERED", "confidence": "MEDIUM"}
    assert evaluate_candidate(cand, {}, ["BUSINESS:REGISTERED"])["applicability_status"] == "MATCH_CANDIDATE"


def test_regression_nontarget_boolean_scope_unchanged():
    # WORK:CONFINED_SPACE는 대상 아님 → 기존 존재기반 POSSIBLE 유지
    cand = {"clause_id": "c", "source_article_id": "a", "trigger_code": "WORK:CONFINED_SPACE", "confidence": "HIGH"}
    assert evaluate_candidate(cand, {"has_confined_space": True}, ["WORK:CONFINED_SPACE"])["applicability_status"] == "POSSIBLE_CANDIDATE"
