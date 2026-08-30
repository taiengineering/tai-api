"""§98 STEP 2 — inspection completion trace continuity (routers/inspection_checklist.py)."""
import ast
import pathlib
import asyncio
import pytest
SRC = (pathlib.Path(__file__).resolve().parents[1] / "routers" / "inspection_checklist.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)
def _fn(name):
    return next(n for n in ast.walk(TREE)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
def _create_trace_calls(fnname):
    return [n for n in ast.walk(_fn(fnname))
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "create_trace"]
def _emit_calls(fnname):
    return [n for n in ast.walk(_fn(fnname))
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "emit_event"]
def _kw(c):
    return {k.arg: (k.value.value if isinstance(k.value, ast.Constant) else "?") for k in c.keywords}
def _clear_in_finally(fnname):
    for n in ast.walk(_fn(fnname)):
        if isinstance(n, ast.Try):
            for fb in n.finalbody:
                for x in ast.walk(fb):
                    if isinstance(x, ast.Call) and getattr(x.func, "id", None) == "clear_trace":
                        return True
    return False
def test_t1_result_submit_trace():
    calls = _create_trace_calls("record_inspection_results")
    assert len(calls) == 1
    assert _kw(calls[0])["flow_key"] == "inspection_result_submit"
def test_t2_complete_trace():
    calls = _create_trace_calls("complete_inspection")
    assert len(calls) == 1
    assert _kw(calls[0])["flow_key"] == "inspection_complete"
def test_t3_namespace_and_actor():
    for fnname in ("record_inspection_results", "complete_inspection"):
        kw = _kw(_create_trace_calls(fnname)[0])
        assert kw["tenant_id"] == "tai"
        assert kw["actor_type"] == "user"
def test_t4_clear_in_finally():
    assert _clear_in_finally("record_inspection_results")
    assert _clear_in_finally("complete_inspection")
def test_t5_target_funcs_no_emit():
    assert _emit_calls("record_inspection_results") == []
    assert _emit_calls("complete_inspection") == []
@pytest.fixture
def mod(monkeypatch):
    import routers.inspection_checklist as m
    calls = {"create": [], "clear": 0}
    monkeypatch.setattr(m, "create_trace", lambda **kw: calls["create"].append(kw))
    monkeypatch.setattr(m, "clear_trace", lambda: calls.__setitem__("clear", calls["clear"] + 1))
    monkeypatch.setattr(m, "get_supabase", lambda: object())
    monkeypatch.setattr(m, "_ensure_inspection_own", lambda *a, **k: None)
    monkeypatch.setattr(m, "_ensure_ws_own", lambda *a, **k: None)
    return m, calls, monkeypatch
def test_result_empty_body_clears(mod):
    m, calls, _ = mod
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        asyncio.run(m.record_inspection_results("insp-1", {"results": []}, current={"id": "u1"}))
    assert ei.value.status_code == 400
    assert len(calls["create"]) == 1
    assert calls["create"][0]["flow_key"] == "inspection_result_submit"
    assert calls["clear"] == 1
def test_result_ownership_failure_no_trace(mod):
    m, calls, monkeypatch = mod
    from fastapi import HTTPException
    def _deny(*a, **k): raise HTTPException(status_code=404, detail="x")
    monkeypatch.setattr(m, "_ensure_inspection_own", _deny)
    with pytest.raises(HTTPException):
        asyncio.run(m.record_inspection_results("insp-1", {"results": [{"result": "NORMAL"}]}, current={"id": "u1"}))
    assert calls["create"] == [] and calls["clear"] == 0
def test_complete_ownership_failure_no_trace(mod):
    m, calls, monkeypatch = mod
    from fastapi import HTTPException
    def _deny(*a, **k): raise HTTPException(status_code=404, detail="x")
    monkeypatch.setattr(m, "_ensure_ws_own", _deny)
    with pytest.raises(HTTPException):
        asyncio.run(m.complete_inspection("ws-1", {}, current={"id": "u1"}))
    assert calls["create"] == [] and calls["clear"] == 0
