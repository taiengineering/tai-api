"""tests/test_leg_runtime_evidence_rows.py — WO-DQ-WHAT-05D-A0 CLIENT C01–C10

대상: clients.leg_runtime_client.fetch_evidence_rows
실 HTTP / 실 LEG Runtime 은 호출하지 않는다.
"""
from __future__ import annotations

import inspect

import pytest

import clients.leg_runtime_client as leg
from clients.leg_runtime_client import LegRuntimeError, fetch_evidence_rows


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


VALID = {
    "version": 1,
    "source_mode": "LIVE_LEG_EVIDENCE",
    "laws": [{"id": "law-1", "law_name": "산업안전보건법"}],
    "articles": [],
}


def install_post(monkeypatch, resp=None, exc=None, url_is="http://leg.test"):
    calls = {"n": 0, "url": None, "json": None, "timeout": None}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        calls["url"] = url
        calls["json"] = json
        calls["timeout"] = timeout
        if exc is not None:
            raise exc
        return resp

    monkeypatch.setattr(leg, "LEG_RUNTIME_URL", url_is)
    monkeypatch.setattr(leg.httpx, "post", fake_post)
    return calls


def test_C01_endpoint_exact(monkeypatch):
    calls = install_post(monkeypatch, FakeResp(200, VALID))
    fetch_evidence_rows(["산업안전보건법"], [221])
    assert calls["url"] == "http://leg.test/rtm/evidence-rows"


def test_C02_payload_exact(monkeypatch):
    calls = install_post(monkeypatch, FakeResp(200, VALID))
    fetch_evidence_rows(["산업안전보건법"], [221])
    assert calls["json"] == {"law_names": ["산업안전보건법"], "article_nos": [221]}


def test_C03_valid_200(monkeypatch):
    install_post(monkeypatch, FakeResp(200, VALID))
    assert fetch_evidence_rows(["산업안전보건법"], [221]) == VALID


def test_C04_missing_leg_runtime_url(monkeypatch):
    monkeypatch.setattr(leg, "LEG_RUNTIME_URL", "")
    with pytest.raises(LegRuntimeError) as ei:
        fetch_evidence_rows(["법"], [1])
    assert "LEG_RUNTIME_URL" in str(ei.value)


def test_C05_network_error(monkeypatch):
    install_post(monkeypatch, exc=RuntimeError("conn reset"))
    with pytest.raises(LegRuntimeError) as ei:
        fetch_evidence_rows(["법"], [1])
    assert str(ei.value).startswith("request failed:")


def test_C06_non200_raises_without_body_leak(monkeypatch):
    install_post(monkeypatch, FakeResp(500, text="SECRET-REPO-DETAIL-leak"))
    with pytest.raises(LegRuntimeError) as ei:
        fetch_evidence_rows(["법"], [1])
    assert "SECRET-REPO-DETAIL-leak" not in str(ei.value)
    assert str(ei.value) == "HTTP 500"


def test_C07_invalid_json(monkeypatch):
    install_post(monkeypatch, FakeResp(200, raise_json=True))
    with pytest.raises(LegRuntimeError) as ei:
        fetch_evidence_rows(["법"], [1])
    assert str(ei.value).startswith("invalid json:")


@pytest.mark.parametrize("payload", [
    None,
    [],
    {"version": 2, "source_mode": "LIVE_LEG_EVIDENCE", "laws": [], "articles": []},
    {"version": 1, "source_mode": "LIVE_LEG_SOURCE", "laws": [], "articles": []},
    {"version": 1, "source_mode": "LIVE_LEG_EVIDENCE", "laws": None, "articles": []},
    {"version": 1, "source_mode": "LIVE_LEG_EVIDENCE", "laws": [], "articles": None},
    {"version": 1, "source_mode": "LIVE_LEG_EVIDENCE"},
])
def test_C08_malformed_contract(monkeypatch, payload):
    install_post(monkeypatch, FakeResp(200, payload))
    with pytest.raises(LegRuntimeError) as ei:
        fetch_evidence_rows(["법"], [1])
    assert "malformed evidence-rows contract" in str(ei.value)


def test_C09_retry_zero(monkeypatch):
    calls = install_post(monkeypatch, FakeResp(500))
    with pytest.raises(LegRuntimeError):
        fetch_evidence_rows(["법"], [1])
    assert calls["n"] == 1


def test_C10_direct_db_zero():
    src = inspect.getsource(fetch_evidence_rows)
    for banned in (
        "get_supabase",
        "db.supabase_client",
        "DATABASE_URL",
        "psycopg",
        "SUPABASE_DB_URL",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        ".table(",
    ):
        assert banned not in src, "fetch_evidence_rows must not touch DB: %s" % banned
