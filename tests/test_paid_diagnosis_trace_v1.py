"""§94 STEP A — paid diagnosis trace lifecycle (routers/diagnosis_integrated.py).

§94 owns trace lifecycle only. Later explicitly-approved Common Event producers
may coexist in this router.
"""
import ast
import pathlib
import pytest
SRC = (pathlib.Path(__file__).resolve().parents[1] / "routers" / "diagnosis_integrated.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)
def _calls(callee):
    return [n for n in ast.walk(TREE)
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == callee]
def _kw(call):
    return {k.arg: (k.value.value if isinstance(k.value, ast.Constant) else "?") for k in call.keywords}
def test_static_two_create_trace_paid_flow_keys():
    fks = sorted(_kw(c).get("flow_key") for c in _calls("create_trace"))
    assert fks == ["paid_diagnosis_run", "paid_diagnosis_upgrade"]
def test_static_trace_namespace_and_actor():
    for c in _calls("create_trace"):
        kw = _kw(c)
        assert kw.get("tenant_id") == "tai"
        assert kw.get("actor_type") == "user"
def test_static_binding_trace_string_untouched():
    assert 'f"diagnosis-{diagnosis_id}"' in SRC
@pytest.fixture
def mod(monkeypatch):
    import routers.diagnosis_integrated as m
    calls = {"create": [], "clear": 0}
    monkeypatch.setattr(m, "create_trace", lambda **kw: calls["create"].append(kw))
    monkeypatch.setattr(m, "clear_trace", lambda: calls.__setitem__("clear", calls["clear"] + 1))
    monkeypatch.setattr(m, "get_supabase", lambda: object())
    monkeypatch.setattr(m, "nexas_run_body_from_request", lambda d: type("B", (), d)())
    monkeypatch.setattr(m, "build_nexas_run_response", lambda r: {"ok": True})
    return m, calls
def _runbody(**kw):
    from schemas.diagnosis_integrated import DiagnosisRunBody
    base = dict(auth_token="t", sector="INDUSTRY")
    base.update(kw)
    return DiagnosisRunBody(**base)
import asyncio
def test_r1_r5_paid_run_trace_lifecycle(mod):
    m, calls = mod
    m.diagnosis_integrated_svc.run_diagnosis = lambda **kw: {}
    asyncio.get_event_loop().run_until_complete(
        m._run_diagnosis_impl(_runbody(payment_ref="pay-1", factory_id=None), current_user={"id": "u-1"}))
    assert len(calls["create"]) == 1
    assert calls["create"][0]["flow_key"] == "paid_diagnosis_run"
    assert calls["create"][0]["tenant_id"] == "tai"
    assert calls["create"][0]["actor_type"] == "user"
    assert calls["clear"] == 1
def test_r6_paid_run_clear_on_exception(mod):
    m, calls = mod
    def _boom(**kw): raise RuntimeError("svc down")
    m.diagnosis_integrated_svc.run_diagnosis = _boom
    with pytest.raises(RuntimeError):
        asyncio.get_event_loop().run_until_complete(
            m._run_diagnosis_impl(_runbody(payment_ref="pay-1"), current_user={"id": "u-1"}))
    assert calls["clear"] == 1
def test_free1_guest_no_trace(mod):
    m, calls = mod
    m.diagnosis_integrated_svc.run_diagnosis = lambda **kw: {}
    asyncio.get_event_loop().run_until_complete(
        m._run_diagnosis_impl(_runbody(payment_ref=None), current_user=None))
    assert calls["create"] == [] and calls["clear"] == 0
def test_free2_authed_no_payment_no_trace(mod):
    m, calls = mod
    m.diagnosis_integrated_svc.run_diagnosis = lambda **kw: {}
    asyncio.get_event_loop().run_until_complete(
        m._run_diagnosis_impl(_runbody(payment_ref=None), current_user={"id": "u-1"}))
    assert calls["create"] == [] and calls["clear"] == 0
def test_u1_u5_upgrade_trace_lifecycle(mod):
    m, calls = mod
    m.diagnosis_integrated_svc.upgrade_diagnosis = lambda **kw: {}
    from schemas.diagnosis_integrated import UpgradeBody
    body = UpgradeBody(auth_token="t", public_token="p", target_tier_code="X", payment_ref="pay-1")
    asyncio.get_event_loop().run_until_complete(
        m._upgrade_diagnosis_impl(body, current_user={"id": "u-1"}))
    assert len(calls["create"]) == 1
    assert calls["create"][0]["flow_key"] == "paid_diagnosis_upgrade"
    assert calls["create"][0]["tenant_id"] == "tai"
    assert calls["create"][0]["actor_type"] == "user"
    assert calls["clear"] == 1
def test_u6_upgrade_clear_on_exception(mod):
    m, calls = mod
    def _boom(**kw): raise RuntimeError("upgrade down")
    m.diagnosis_integrated_svc.upgrade_diagnosis = _boom
    from schemas.diagnosis_integrated import UpgradeBody
    body = UpgradeBody(auth_token="t", public_token="p", target_tier_code="X", payment_ref="pay-1")
    with pytest.raises(RuntimeError):
        asyncio.get_event_loop().run_until_complete(
            m._upgrade_diagnosis_impl(body, current_user={"id": "u-1"}))
    assert calls["clear"] == 1
