"""tests/test_paid_result_evidence_leg_runtime_v1.py — WO-DQ-WHAT-05D-A0 EVIDENCE R01–R11

resolver 불변 + production default 가 LEG Runtime HTTP 인지 검증.
실 HTTP / 실 LEG Runtime / 실 Supabase 는 호출하지 않는다.
"""
from __future__ import annotations

import copy

import pytest

import clients.leg_runtime_client as leg
import services.paid_result_evidence_svc as svc
from clients.leg_runtime_client import LegRuntimeError
from services.paid_result_evidence_svc import (
    MATCH_RULE,
    RESOLUTION_RULE,
    build_paid_result_evidence_v1,
    resolve_articles,
)
from tests.test_paid_result_evidence_v1 import (
    ARTICLES_221,
    ARTICLES_338,
    LAW,
    LAWS,
    RecordingLoader,
    obligation,
    only,
)


class FakeResp:
    def __init__(self, status_code=200, payload=None, text="", raise_json=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("no json")
        return self._payload


def _leg_payload(laws=None, articles=None):
    return {
        "version": 1,
        "source_mode": "LIVE_LEG_EVIDENCE",
        "laws": list(laws if laws is not None else LAWS),
        "articles": list(articles if articles is not None else ARTICLES_221),
    }


def install_http(monkeypatch, payload=None, status_code=200, exc=None, raise_json=False):
    calls = {"n": 0, "url": None, "json": None}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        calls["url"] = url
        calls["json"] = json
        if exc is not None:
            raise exc
        return FakeResp(status_code, payload if payload is not None else _leg_payload(), raise_json=raise_json)

    monkeypatch.setattr(leg, "LEG_RUNTIME_URL", "http://leg.test")
    monkeypatch.setattr(leg.httpx, "post", fake_post)
    return calls


def test_R01_existing_golden_exact():
    evidence = (
        "사업주는 다음 각 호의 사항을 모두 갖춘 굴착기의 경우에는 "
        "굴착기를 사용하여 화물 인양작업을 할 수 있다."
    )
    result = resolve_articles([obligation(0, "221", evidence)], LAWS, ARTICLES_221)
    row = only(result)
    assert result["resolution"]["rule"] == RESOLUTION_RULE
    assert row["article_no"] == 221
    assert row["article_sub_no"] == 5
    assert row["article_no_sort"] == "0221-005"
    assert row["article_title"] == "인양작업 시 조치"
    assert row["related_obligation_refs"] == [0]
    assert row["provenance"]["law_article_id"] == "a-221-005"
    assert row["provenance"]["match_rule"] == MATCH_RULE
    assert result["unresolved"] == []


def test_R02_existing_unresolved_exact():
    result = resolve_articles(
        [obligation(0, "221", "이 문장은 어느 조문 원문에도 들어 있지 않다.")],
        LAWS,
        ARTICLES_221,
    )
    assert result["articles"] == []
    assert result["unresolved"] == [{
        "obligation_ref": 0,
        "law_name": LAW,
        "law_article": "221",
        "reason": "NO_EXACT_EVIDENCE_MATCH",
    }]


def test_R03_injected_loader_unchanged():
    evidence = "사업주는 굴착기를 운전하는 사람이 좌석안전띠를 착용하도록 해야 한다."
    loader = RecordingLoader(LAWS, ARTICLES_221)
    via_loader = build_paid_result_evidence_v1(
        {"normalized_obligations": [obligation(0, "221", evidence)]},
        loader=loader,
    )
    via_resolver = resolve_articles([obligation(0, "221", evidence)], LAWS, ARTICLES_221)
    assert via_loader == via_resolver
    assert len(loader.law_calls) == 1
    assert len(loader.article_calls) == 1


def test_R04_loader_none_http_exactly_1(monkeypatch):
    evidence = "사업주는 굴착기를 운전하는 사람이 좌석안전띠를 착용하도록 해야 한다."
    calls = install_http(monkeypatch, _leg_payload(LAWS, ARTICLES_221))
    result = build_paid_result_evidence_v1(
        {"normalized_obligations": [obligation(0, "221", evidence)]},
    )
    assert calls["n"] == 1
    assert calls["url"] == "http://leg.test/rtm/evidence-rows"
    assert calls["json"] == {"law_names": [LAW], "article_nos": [221]}
    assert only(result)["article_sub_no"] == 3


def test_R05_loader_none_supabase_zero(monkeypatch):
    evidence = "사업주는 굴착기를 운전하는 사람이 좌석안전띠를 착용하도록 해야 한다."
    install_http(monkeypatch, _leg_payload(LAWS, ARTICLES_221))

    def boom_loader(*_a, **_k):
        raise AssertionError("SupabaseArticleLoader constructed on default path")

    def boom_supabase(*_a, **_k):
        raise AssertionError("get_supabase called on default path")

    monkeypatch.setattr(svc, "SupabaseArticleLoader", boom_loader)
    monkeypatch.setattr("db.supabase_client.get_supabase", boom_supabase)
    result = build_paid_result_evidence_v1(
        {"normalized_obligations": [obligation(0, "221", evidence)]},
    )
    assert only(result)["article_sub_no"] == 3


def test_R06_resolution_rule_exact_unchanged():
    assert RESOLUTION_RULE == "EXACT_EVIDENCE_SUBSTRING_V1"
    assert svc.RESOLUTION_RULE == RESOLUTION_RULE


def test_R07_match_rule_exact_unchanged():
    assert MATCH_RULE == "WHITESPACE_NORMALIZED_EXACT_SUBSTRING_V1"
    assert svc.MATCH_RULE == MATCH_RULE


def test_R08_materials_mutation_zero(monkeypatch):
    materials = {
        "normalized_obligations": [
            obligation(0, "221", "굴착기를 사용하여 화물 인양작업을 할 수 있다."),
        ]
    }
    before = copy.deepcopy(materials)
    install_http(monkeypatch, _leg_payload(LAWS, ARTICLES_221))
    build_paid_result_evidence_v1(materials)
    assert materials == before


def test_R09_normalized_obligations_mutation_zero(monkeypatch):
    row = obligation(0, "221", "굴착기를 사용하여 화물 인양작업을 할 수 있다.")
    before = copy.deepcopy(row)
    install_http(monkeypatch, _leg_payload(LAWS, ARTICLES_221))
    build_paid_result_evidence_v1({"normalized_obligations": [row]})
    assert row == before


def test_R10_empty_obligations_http_zero(monkeypatch):
    calls = install_http(monkeypatch, _leg_payload([], []))
    result = build_paid_result_evidence_v1({"normalized_obligations": []})
    assert calls["n"] == 0
    assert result["articles"] == []
    assert result["unresolved"] == []
    assert result["resolution"]["source_obligation_count"] == 0


def test_R11_malformed_leg_response_fail_closed(monkeypatch):
    install_http(
        monkeypatch,
        {"version": 2, "source_mode": "LIVE_LEG_EVIDENCE", "laws": [], "articles": []},
    )
    with pytest.raises(LegRuntimeError):
        build_paid_result_evidence_v1(
            {"normalized_obligations": [obligation(0, "338", "굴착작업을 할 때에")]},
        )
