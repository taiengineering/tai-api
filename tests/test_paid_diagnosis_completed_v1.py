"""§97-A STEP A — paid /diagnosis/run DIAGNOSIS_COMPLETED Common Event v1."""
import ast
import pathlib
import asyncio
import pytest
SRC = (pathlib.Path(__file__).resolve().parents[1] / "routers" / "diagnosis_integrated.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)
def _fn(name):
    return next(n for n in ast.walk(TREE)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
def _emits(fnname):
    fn = _fn(fnname)
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "emit_event"]
def _kw(c):
    out = {}
    for k in c.keywords:
        if isinstance(k.value, ast.Constant):
            out[k.arg] = k.value.value
        elif isinstance(k.value, ast.JoinedStr):
            out[k.arg] = "fstr"
        else:
            out[k.arg] = "?"
    return out
def test_p1_run_exactly_one_emit():
    assert len(_emits("_run_diagnosis_impl")) == 1
def test_p2_p9_run_emit_contract():
    kw = _kw(_emits("_run_diagnosis_impl")[0])
    assert kw["event_name"] == "DIAGNOSIS_COMPLETED"
    assert kw["step_key"] == "result_save"
    assert kw["step_order"] == 1
    assert kw["event_type"] == "save"
    assert kw["result"] == "success"
    assert kw["connector_type"] == "database"
    assert kw["actor_kind"] == "USER"
    assert kw["actor_ref"] == "fstr"
def test_static_no_overrides():
    kw = {k.arg for k in _emits("_run_diagnosis_impl")[0].keywords}
    for f in ("event_version", "occurred_at", "outcome", "trace", "trace_id",
              "tenant_id", "service_key", "environment"):
        assert f not in kw
def test_static_is_false_guard_exact():
    assert 'result.get("is_free") is False' in SRC
def test_static_safe_actor_extraction():
    assert '(current_user or {}).get("id")' in SRC
def test_static_upgrade_no_emit():
    assert _emits("_upgrade_diagnosis_impl") == []
def test_static_binding_trace_untouched():
    assert 'f"diagnosis-{diagnosis_id}"' in SRC
def test_static_only_one_canonical_event_name():
    assert "DIAGNOSIS_UPGRADED" not in SRC
    assert "DIAGNOSIS_FAILED" not in SRC
@pytest.fixture
def mod(monkeypatch):
    import routers.diagnosis_integrated as m
    calls = {"emit": [], "clear": 0}
    monkeypatch.setattr(m, "create_trace", lambda **kw: None)
    monkeypatch.setattr(m, "clear_trace", lambda: calls.__setitem__("clear", calls["clear"] + 1))
    monkeypatch.setattr(m, "emit_event", lambda **kw: calls["emit"].append(kw) or True)
    monkeypatch.setattr(m, "get_supabase", lambda: object())
    monkeypatch.setattr(m, "nexas_run_body_from_request", lambda d: type("B", (), d)())
    monkeypatch.setattr(m, "build_nexas_run_response", lambda r: {"ok": True})
    return m, calls
def _runbody(**kw):
    from schemas.diagnosis_integrated import DiagnosisRunBody
    base = dict(auth_token="t", sector="INDUSTRY")
    base.update(kw)
    return DiagnosisRunBody(**base)
def _run(m, result, current_user, payment_ref="pay-1"):
    m.diagnosis_integrated_svc.run_diagnosis = lambda **kw: result
    return asyncio.run(
        m._run_diagnosis_impl(_runbody(payment_ref=payment_ref, factory_id=None), current_user=current_user))
def test_paid_emits_completed(mod):
    m, calls = mod
    _run(m, {"is_free": False, "diagnosis_id": "d1", "public_token": "p1", "result": {}}, {"id": "u1"})
    assert len(calls["emit"]) == 1
    e = calls["emit"][0]
    assert e["event_name"] == "DIAGNOSIS_COMPLETED"
    assert e["actor_kind"] == "USER"
    assert e["actor_ref"] == "user:u1"
    assert calls["clear"] == 1
def test_free_result_no_emit(mod):
    m, calls = mod
    _run(m, {"is_free": True, "result": {}}, {"id": "u1"})
    assert calls["emit"] == []
def test_missing_is_free_no_emit(mod):
    m, calls = mod
    _run(m, {"result": {}}, {"id": "u1"})
    assert calls["emit"] == []
def test_missing_actor_no_emit_no_exception(mod):
    m, calls = mod
    _run(m, {"is_free": False, "result": {}}, {})
    assert calls["emit"] == []
