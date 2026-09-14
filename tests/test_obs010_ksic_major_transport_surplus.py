"""WO-E2E-OBS010-KSIC-MAJOR-ENGINE-CONTEXT-REV1-001.

ksic_major is Engine Context, not a LEG applicability input.
"""
from types import SimpleNamespace

from clients.leg_runtime_client import (
    _CONTEXT_FIELDS,
    _LEG_INPUT_FIELDS,
    build_engine_context,
    build_facility,
    evaluate_rtm,
)
from schemas.diagnosis_integrated import DiagnosisRunBody
from schemas.legal_engine import DiagnoseStep1Body


def _body(**kwargs):
    inp = kwargs.pop("input", None) or {}
    ns = SimpleNamespace(input=inp, **kwargs)
    return ns


def test_ksic_major_removed_from_leg_transport_allowlist():
    assert "ksic_major" not in _LEG_INPUT_FIELDS
    assert len(_LEG_INPUT_FIELDS) == 186
    assert len(set(_LEG_INPUT_FIELDS)) == 186
    assert _CONTEXT_FIELDS == ("sector", "ksic_major")


def test_build_facility_omits_ksic_major_keeps_worker_count():
    body = _body(
        sector="MANUFACTURING",
        ksic_major="29",
        input={"ksic_major": "29", "worker_count": 100},
    )
    fac = build_facility(body)
    assert fac.get("worker_count") == 100
    assert "ksic_major" not in fac


def test_build_engine_context_carries_sector_and_ksic_verbatim():
    body = _body(
        sector="MANUFACTURING",
        ksic_major="29",
        input={"ksic_major": "29", "worker_count": 100},
    )
    ctx = build_engine_context(body)
    assert ctx == {"sector": "MANUFACTURING", "ksic_major": "29"}


def test_build_engine_context_omits_blank_ksic():
    body = _body(sector="BUILDING", ksic_major="", input={"ksic_major": ""})
    ctx = build_engine_context(body)
    assert ctx.get("sector") == "BUILDING"
    assert "ksic_major" not in ctx


def test_consumer_schema_still_accepts_ksic_major():
    assert "ksic_major" in DiagnosisRunBody.model_fields
    assert "ksic_major" in DiagnoseStep1Body.model_fields
    run = DiagnosisRunBody(sector="MANUFACTURING", ksic_major="30")
    assert run.ksic_major == "30"
    step1 = DiagnoseStep1Body(sector="MANUFACTURING", ksic_major="30")
    assert step1.ksic_major == "30"


def test_evaluate_rtm_payload_separates_context(monkeypatch):
    captured = {}

    class _Resp:
        def json(self):
            return {"status": "OK"}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    import clients.leg_runtime_client as client

    monkeypatch.setattr(client, "LEG_RUNTIME_URL", "http://leg.test")
    monkeypatch.setattr(client.httpx, "post", fake_post)
    body = _body(
        sector="MANUFACTURING",
        ksic_major="29",
        input={"ksic_major": "29", "worker_count": 100},
    )
    fac = build_facility(body)
    ctx = build_engine_context(body)
    evaluate_rtm(fac, context=ctx)
    assert captured["json"] == {
        "facility": {"worker_count": 100},
        "context": {"sector": "MANUFACTURING", "ksic_major": "29"},
    }
    assert "ksic_major" not in captured["json"]["facility"]


def test_evaluate_rtm_omits_empty_context_key(monkeypatch):
    captured = {}

    class _Resp:
        def json(self):
            return {"status": "OK"}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _Resp()

    import clients.leg_runtime_client as client

    monkeypatch.setattr(client, "LEG_RUNTIME_URL", "http://leg.test")
    monkeypatch.setattr(client.httpx, "post", fake_post)
    evaluate_rtm({"worker_count": 100}, context={})
    assert captured["json"] == {"facility": {"worker_count": 100}}
    assert "context" not in captured["json"]
