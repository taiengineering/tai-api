"""
WO-MKT-GA4-SOURCE-IV-R1 — scheduler handler failure propagation tests.

Coverage:
  H01  HTTP 200 ok=True     → returns result dict (SUCCESS recorded by scheduler)
  H02  HTTP 503 GA4_NOT_CONFIGURED → raises RuntimeError (FAILED recorded by scheduler)
  H03  HTTP 401 UNAUTHORIZED       → raises RuntimeError (FAILED recorded by scheduler)
  H04  HTTP 200 partial=True       → returns result dict (WARNING via errors key absent → SUCCESS)
  H05  MKT_API_URL not set         → raises RuntimeError
  H06  timeout propagated from payload
"""
from __future__ import annotations

import pytest
import services.scheduler.handlers as handlers_mod


# ---------------------------------------------------------------------------
# Fake _mkt_http responses
# ---------------------------------------------------------------------------

def _ok_body():
    return {
        "ok": True, "partial": False,
        "source_latest_date": "2026-11-01",
        "collected_at": "2026-11-01T00:00:00+00:00",
        "periods": [1, 7, 30],
        "results": {f"{ds}_p{p}": {"status": "OK", "inserted": True, "deduplicated": False}
                    for ds in ("ACQUISITION", "BEHAVIOR", "FUNNEL") for p in (1, 7, 30)},
    }


def _partial_body():
    body = _ok_body()
    body["ok"] = False
    body["partial"] = True
    body["results"]["ACQUISITION_p1"] = {"status": "COLLECTION_FAILED", "inserted": True}
    return body


def _err_body(code, message):
    return {"error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# H01: HTTP 200 ok → result returned (scheduler → SUCCESS)
# ---------------------------------------------------------------------------

def test_H01_200_ok_returns_result(monkeypatch):
    monkeypatch.setattr(
        handlers_mod, "_mkt_http",
        lambda path, timeout=120: {"http_status": 200, "body": _ok_body(), "url": "http://x/api/mkt/ga4/collect"},
    )
    result = handlers_mod._run_mkt_ga4_collect({})
    assert result["http_status"] == 200
    assert result["body"]["ok"] is True


# ---------------------------------------------------------------------------
# H02: HTTP 503 → raises RuntimeError (scheduler → FAILED)
# ---------------------------------------------------------------------------

def test_H02_503_raises(monkeypatch):
    monkeypatch.setattr(
        handlers_mod, "_mkt_http",
        lambda path, timeout=120: {"http_status": 503, "body": _err_body("GA4_NOT_CONFIGURED", "..."), "url": "http://x/api/mkt/ga4/collect"},
    )
    with pytest.raises(RuntimeError, match="503"):
        handlers_mod._run_mkt_ga4_collect({})


# ---------------------------------------------------------------------------
# H03: HTTP 401 → raises RuntimeError (scheduler → FAILED)
# ---------------------------------------------------------------------------

def test_H03_401_raises(monkeypatch):
    monkeypatch.setattr(
        handlers_mod, "_mkt_http",
        lambda path, timeout=120: {"http_status": 401, "body": _err_body("UNAUTHORIZED", "invalid token"), "url": "http://x/api/mkt/ga4/collect"},
    )
    with pytest.raises(RuntimeError, match="401"):
        handlers_mod._run_mkt_ga4_collect({})


# ---------------------------------------------------------------------------
# H04: HTTP 200 partial=True → raises RuntimeError (scheduler → FAILED)
#      DB inserts for succeeded rows already committed; raise is signal only.
# ---------------------------------------------------------------------------

def test_H04_200_partial_raises(monkeypatch):
    monkeypatch.setattr(
        handlers_mod, "_mkt_http",
        lambda path, timeout=120: {"http_status": 200, "body": _partial_body(), "url": "http://x/api/mkt/ga4/collect"},
    )
    with pytest.raises(RuntimeError, match="partial"):
        handlers_mod._run_mkt_ga4_collect({})


# ---------------------------------------------------------------------------
# H04b: HTTP 200 ok=False, partial=False (all failed) → raises RuntimeError
# ---------------------------------------------------------------------------

def test_H04b_200_all_failed_raises(monkeypatch):
    all_failed_body = {
        "ok": False, "partial": False,
        "source_latest_date": "2026-11-01",
        "collected_at": "2026-11-01T00:00:00+00:00",
        "periods": [1, 7, 30],
        "results": {f"{ds}_p{p}": {"status": "COLLECTION_FAILED", "inserted": True}
                    for ds in ("ACQUISITION", "BEHAVIOR", "FUNNEL") for p in (1, 7, 30)},
    }
    monkeypatch.setattr(
        handlers_mod, "_mkt_http",
        lambda path, timeout=120: {"http_status": 200, "body": all_failed_body, "url": "http://x/api/mkt/ga4/collect"},
    )
    with pytest.raises(RuntimeError, match="partial/incomplete"):
        handlers_mod._run_mkt_ga4_collect({})


# ---------------------------------------------------------------------------
# H05: MKT_API_URL not set → _mkt_http raises RuntimeError
# ---------------------------------------------------------------------------

def test_H05_no_mkt_api_url_raises(monkeypatch):
    monkeypatch.delenv("MKT_API_URL", raising=False)
    with pytest.raises(RuntimeError, match="MKT_API_URL"):
        handlers_mod._mkt_http("/api/mkt/ga4/collect")


# ---------------------------------------------------------------------------
# H06: timeout from payload is forwarded
# ---------------------------------------------------------------------------

def test_H06_timeout_forwarded(monkeypatch):
    captured = {}

    def fake_mkt_http(path, timeout=120):
        captured["timeout"] = timeout
        return {"http_status": 200, "body": _ok_body(), "url": "http://x" + path}

    monkeypatch.setattr(handlers_mod, "_mkt_http", fake_mkt_http)
    handlers_mod._run_mkt_ga4_collect({"timeout_seconds": 60})
    assert captured["timeout"] == 60
