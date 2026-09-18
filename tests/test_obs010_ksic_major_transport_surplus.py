"""WO-E2E-OBS010-KSIC-MAJOR-CONTEXT-FINALIZE-001.

ksic_major is SaaS classification, not LEG applicability or engine context.
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
    assert "industry" not in _LEG_INPUT_FIELDS
    assert "industry_name" not in _LEG_INPUT_FIELDS
    assert "ksic_name" not in _LEG_INPUT_FIELDS
    assert "business_type" not in _LEG_INPUT_FIELDS
    assert "process_type" not in _LEG_INPUT_FIELDS
    assert len(_LEG_INPUT_FIELDS) == 212
    assert len(set(_LEG_INPUT_FIELDS)) == 212
    assert _CONTEXT_FIELDS == ("sector",)


def test_build_facility_omits_ksic_major_keeps_worker_count():
    body = _body(
        sector="MANUFACTURING",
        ksic_major="29",
        input={"ksic_major": "29", "worker_count": 100},
    )
    fac = build_facility(body)
    assert fac.get("worker_count") == 100
    assert "ksic_major" not in fac


def test_build_engine_context_carries_sector_omits_ksic():
    body = _body(
        sector="MANUFACTURING",
        ksic_major="29",
        input={"ksic_major": "29", "worker_count": 100},
    )
    ctx = build_engine_context(body)
    assert ctx == {"sector": "MANUFACTURING"}
    assert "ksic_major" not in ctx


def test_build_engine_context_drops_industry_name():
    body = _body(
        sector="MANUFACTURING",
        ksic_major="29",
        industry_name="기타 기계 및 장비 제조업",
        input={"industry_name": "기타 기계 및 장비 제조업", "ksic_major": "29"},
    )
    ctx = build_engine_context(body)
    assert ctx == {"sector": "MANUFACTURING"}
    assert "industry_name" not in ctx
    assert "ksic_major" not in ctx


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
        "context": {"sector": "MANUFACTURING"},
    }
    assert "ksic_major" not in captured["json"]["facility"]
    assert "ksic_major" not in captured["json"]["context"]


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
