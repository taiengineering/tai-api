"""§97-B STEP A — paid /diagnosis/upgrade DIAGNOSIS_UPGRADED Common Event v1."""
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


def test_b1_upgrade_exactly_one_emit():
    assert len(_emits("_upgrade_diagnosis_impl")) == 1

def test_b2_b10_upgrade_emit_contract():
    kw = _kw(_emits("_upgrade_diagnosis_impl")[0])
    assert kw["event_name"] == "DIAGNOSIS_UPGRADED"
    assert kw["step_key"] == "result_upgrade"
    assert kw["step_order"] == 1
    assert kw["event_type"] == "update"
    assert kw["result"] == "success"
    assert kw["connector_type"] == "database"
    assert kw["actor_kind"] == "USER"
    assert kw["actor_ref"] == "fstr"

def test_b10_no_overrides():
    kw = {k.arg for k in _emits("_upgrade_diagnosis_impl")[0].keywords}
    for f in ("event_version", "occurred_at", "outcome", "trace", "trace_id",
              "tenant_id", "service_key", "environment"):
        assert f not in kw

def test_safe_actor_extraction():
    assert '(current_user or {}).get("id")' in SRC


@pytest.fixture
def mod(monkeypatch):
    import routers.diagnosis_integrated as m
    calls = {"emit": [], "clear": 0}
    monkeypatch.setattr(m, "create_trace", lambda **kw: None)
    monkeypatch.setattr(m, "clear_trace", lambda: calls.__setitem__("clear", calls["clear"] + 1))
    monkeypatch.setattr(m, "emit_event", lambda **kw: calls["emit"].append(kw) or True)
    monkeypatch.setattr(m, "get_supabase", lambda: object())
    return m, calls


def _body():
    from schemas.diagnosis_integrated import UpgradeBody
    return UpgradeBody(auth_token="t", public_token="p", target_tier_code="X", payment_ref="pay-1")


def _upg(m, result, current_user):
    m.diagnosis_integrated_svc.upgrade_diagnosis = lambda **kw: result
    return asyncio.run(m._upgrade_diagnosis_impl(_body(), current_user=current_user))


def test_upgrade_emits(mod):
    m, calls = mod
    r = _upg(m, {"status": "success", "public_token": "p1", "prev_tier": "T1", "new_tier": "T2", "result": {}}, {"id": "u1"})
    assert len(calls["emit"]) == 1
    e = calls["emit"][0]
    assert e["event_name"] == "DIAGNOSIS_UPGRADED"
    assert e["actor_kind"] == "USER"
    assert e["actor_ref"] == "user:u1"
    assert calls["clear"] == 1
    assert r["new_tier"] == "T2"


def test_missing_actor_no_emit(mod):
    m, calls = mod
    _upg(m, {"status": "success", "result": {}}, {})
    assert calls["emit"] == [] and calls["clear"] == 1


def test_service_exception_clears_trace(mod):
    m, calls = mod
    def _boom(**kw): raise RuntimeError("upgrade down")
    m.diagnosis_integrated_svc.upgrade_diagnosis = _boom
    with pytest.raises(RuntimeError):
        asyncio.run(m._upgrade_diagnosis_impl(_body(), current_user={"id": "u1"}))
    assert calls["emit"] == [] and calls["clear"] == 1
