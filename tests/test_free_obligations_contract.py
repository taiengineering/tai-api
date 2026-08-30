"""
tests/test_free_obligations_contract.py — FREE-DIAGNOSIS-RESULT-UX-01 WP-B

free_obligations additive contract 검증(순수 함수 단위).
계약: free_obligations[] row 키는 정확히 {obligation_type, obligation_summary, law_name}.
유료 상세필드·rule_id·내부 메타 누출 0. free_obligation_count == len(free_obligations).
엔진/DB 무관 — 표시행 투영 로직만 검증.
"""
from routers.diagnosis_result_web import (
    _build_free_obligations,
    _project_free_obligation,
    _dedupe_rules_table,
)

FREE_KEYS = {"obligation_type", "obligation_summary", "law_name"}
FORBIDDEN = [
    "rule_id", "atom_id", "law_article", "evidence", "penalty_summary",
    "inspection_cycle", "executor_type_label", "submit_org_label", "condition",
    "triggered_by", "mapped_field", "category", "content_type", "description", "source",
]


def _rich_rows(n):
    # 유료 상세필드가 섞인 표시행 — 무료 투영에서 반드시 제거되어야 한다.
    return [{
        "obligation_type": "INSPECT",
        "obligation_summary": f"의무 {i}",
        "law_name": f"법 {i % 3}",
        "law_article": "제1조", "evidence": "근거원문", "penalty_summary": "과태료",
        "inspection_cycle": "1년", "condition": "조건", "triggered_by": ["employee_count"],
        "mapped_field": "emp", "rule_id": f"tmp-{i}", "atom_id": f"a{i}",
        "description": "desc", "category": "점검", "source": "LEG",
    } for i in range(n)]


import pytest


@pytest.mark.parametrize("n", [0, 1, 5, 6, 20, 50])
def test_count_matches_input(n):
    rows = _rich_rows(n)
    fo = _build_free_obligations(rows)
    assert len(fo) == n  # 절단 없음(전건)


@pytest.mark.parametrize("n", [1, 5, 6, 20, 50])
def test_strict_keys_only(n):
    for r in _build_free_obligations(_rich_rows(n)):
        assert set(r.keys()) == FREE_KEYS


@pytest.mark.parametrize("n", [1, 6, 50])
def test_no_paid_or_internal_field_leak(n):
    for r in _build_free_obligations(_rich_rows(n)):
        for f in FORBIDDEN:
            assert f not in r


def test_count_consistency_scalar():
    fo = _build_free_obligations(_rich_rows(21))
    assert len(fo) == 21  # free_obligation_count == len(free_obligations)


def test_summary_falls_back_to_description():
    rows = [{"obligation_type": "ACTION", "obligation_summary": "", "description": "설명폴백", "law_name": "법"}]
    fo = _build_free_obligations(rows)
    assert fo[0]["obligation_summary"] == "설명폴백"
    assert fo[0]["obligation_type"] == "ACTION"
    assert fo[0]["law_name"] == "법"


def test_dedupe_reduces_then_projects():
    # dedupe 전 3건(동일 law|article+rule_kind 1쌍) → dedupe 후 2건 → 무료 투영 2건.
    raw = [
        {"law_name": "산안법", "law_article": "제17조", "obligation_type": "APPOINT", "obligation_summary": "선임", "rule_kind": "APPOINT"},
        {"law_name": "산안법", "law_article": "제17조", "obligation_type": "APPOINT", "obligation_summary": "선임(중복)", "rule_kind": "APPOINT"},
        {"law_name": "소방법", "law_article": "제22조", "obligation_type": "INSPECT", "obligation_summary": "점검", "rule_kind": "INSPECT"},
    ]
    deduped = _dedupe_rules_table(raw)
    assert len(deduped) == 2
    fo = _build_free_obligations(deduped)
    assert len(fo) == 2


def test_empty_returns_empty_list():
    assert _build_free_obligations([]) == []


def test_project_single_row_shape():
    r = {"obligation_type": "REPORT", "obligation_summary": "보고", "law_name": "법", "evidence": "x"}
    p = _project_free_obligation(r)
    assert p == {"obligation_type": "REPORT", "obligation_summary": "보고", "law_name": "법"}
