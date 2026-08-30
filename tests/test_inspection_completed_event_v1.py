"""INSPECTION_COMPLETED STEP A — 2 producer (routers/inspection_checklist.py)."""
import ast
import pathlib
import asyncio
import pytest

SRC = (pathlib.Path(__file__).resolve().parents[1] / "routers" / "inspection_checklist.py").read_text(encoding="utf-8")
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


_CONTRACT = dict(
    event_name="INSPECTION_COMPLETED",
    step_key="inspection_complete",
    step_order=1,
    event_type="update",
    result="success",
    connector_type="database",
    actor_kind="USER",
    actor_ref="fstr",
)
_OVERRIDES = ("event_version", "occurred_at", "outcome", "trace", "trace_id",
              "tenant_id", "service_key", "environment")


def test_static_auto_emit_contract():
    calls = _emits("record_inspection_results")
    assert len(calls) == 1
    kw = _kw(calls[0])
    for k, v in _CONTRACT.items():
        assert kw[k] == v
    assert set(kw).isdisjoint(_OVERRIDES)


def test_static_explicit_emit_contract():
    calls = _emits("complete_inspection")
    assert len(calls) == 1
    kw = _kw(calls[0])
    for k, v in _CONTRACT.items():
        assert kw[k] == v
    assert set(kw).isdisjoint(_OVERRIDES)


def test_static_changed_oracle_and_safe_actor():
    assert '_completion.get("changed") is True' in SRC
    assert '(current or {}).get("id")' in SRC


class _Resp:
    def __init__(self, data=None):
        self.data = data


class _Tbl:
    def __init__(self, name, resp):
        self.name = name
        self.resp = resp
        self.action = None

    def select(self, *a, **k):
        self.action = "select"; return self

    def update(self, payload, *a, **k):
        self.action = "update"; return self

    def eq(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def execute(self):
        data = self.resp.get((self.name, self.action))
        return _Resp(data=data if data is not None else [])


class _FakeSB:
    def __init__(self, resp):
        self.resp = resp

    def table(self, name):
        return _Tbl(name, self.resp)


@pytest.fixture
def mod(monkeypatch):
    import routers.inspection_checklist as m
    from services.inspection_record_writer_bridge import InspectionStatusWriteError
    calls = {"emit": [], "bridge": [], "roll": 0}
    monkeypatch.setattr(m, "create_trace", lambda **kw: None)
    monkeypatch.setattr(m, "clear_trace", lambda: None)
    monkeypatch.setattr(m, "emit_event", lambda **kw: calls["emit"].append(kw) or True)
    monkeypatch.setattr(m, "_ensure_inspection_own", lambda *a, **k: None)
    monkeypatch.setattr(m, "_ensure_ws_own", lambda *a, **k: None)
    monkeypatch.setattr(m, "record_safe_result_batch",
                        lambda sb, *, inspection_id, results: {"count": len(results)})
    monkeypatch.setattr(m, "ensure_next_rolling_schedule",
                        lambda *a, **k: calls.__setitem__("roll", calls["roll"] + 1) or {"created": False})
    return m, calls, monkeypatch, InspectionStatusWriteError


def _auto_sb():
    return _FakeSB({
        ("safety_inspections", "select"): [{"assignment_id": "ws-1"}],
        ("work_schedules", "select"): [{"completed_at": None}],
        ("work_schedules", "update"): [{"id": "ws-1"}],
    })


def _explicit_sb(*, completed_at=None, inspection_id="insp-1"):
    return _FakeSB({
        ("safety_inspections", "select"): [{"id": inspection_id}],
        ("work_schedules", "select"): [{
            "completed_at": completed_at,
            "status_code": "completed" if completed_at else "in_progress",
            "inspection_set_id": None,
            "summary": None,
        }],
        ("work_schedules", "update"): [{"id": "ws-1", "inspection_set_id": None}],
    })


def test_t1_auto_transition(mod):
    m, calls, monkeypatch, _ = mod
    monkeypatch.setattr(m, "get_supabase", lambda: _auto_sb())
    monkeypatch.setattr(m, "complete_inspection_status",
                        lambda *a, **k: calls["bridge"].append(k) or {"changed": True, "status": "COMPLETED"})
    asyncio.run(m.record_inspection_results("insp-1", {"results": [{"result": "NORMAL"}]}, current={"id": "u1"}))
    assert len(calls["emit"]) == 1
    e = calls["emit"][0]
    assert e["event_name"] == "INSPECTION_COMPLETED"
    assert e["step_key"] == "inspection_complete"
    assert e["actor_kind"] == "USER"
    assert e["actor_ref"] == "user:u1"
    assert calls["roll"] == 1


def test_t2_auto_noop(mod):
    m, calls, monkeypatch, _ = mod
    monkeypatch.setattr(m, "get_supabase", lambda: _auto_sb())
    monkeypatch.setattr(m, "complete_inspection_status", lambda *a, **k: {"changed": False, "noop": True})
    asyncio.run(m.record_inspection_results("insp-1", {"results": [{"result": "NORMAL"}]}, current={"id": "u1"}))
    assert calls["emit"] == []
    assert calls["roll"] == 1


def test_t3_auto_abnormal(mod):
    m, calls, monkeypatch, _ = mod
    monkeypatch.setattr(m, "get_supabase", lambda: _auto_sb())
    monkeypatch.setattr(m, "complete_inspection_status",
                        lambda *a, **k: calls["bridge"].append(1) or {"changed": True})
    asyncio.run(m.record_inspection_results(
        "insp-1", {"results": [{"result": "ABNORMAL"}]}, current={"id": "u1"}))
    assert calls["bridge"] == []
    assert calls["emit"] == []
    assert calls["roll"] == 0


def test_t4_auto_bridge_error(mod):
    m, calls, monkeypatch, InspectionStatusWriteError = mod
    from fastapi import HTTPException
    monkeypatch.setattr(m, "get_supabase", lambda: _auto_sb())
    def _boom(*a, **k):
        raise InspectionStatusWriteError("INVALID_STATUS_TRANSITION", "x")
    monkeypatch.setattr(m, "complete_inspection_status", _boom)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(m.record_inspection_results(
            "insp-1", {"results": [{"result": "NORMAL"}]}, current={"id": "u1"}))
    assert ei.value.status_code == 409
    assert calls["emit"] == []
    assert calls["roll"] == 0


def test_t5_explicit_transition(mod):
    m, calls, monkeypatch, _ = mod
    monkeypatch.setattr(m, "get_supabase", lambda: _explicit_sb(completed_at=None))
    monkeypatch.setattr(m, "complete_inspection_status", lambda *a, **k: {"changed": True, "status": "COMPLETED"})
    asyncio.run(m.complete_inspection("ws-1", {}, current={"id": "u1"}))
    assert len(calls["emit"]) == 1
    e = calls["emit"][0]
    assert e["event_name"] == "INSPECTION_COMPLETED"
    assert e["actor_kind"] == "USER"
    assert e["actor_ref"] == "user:u1"


def test_t6_explicit_already_completed(mod):
    m, calls, monkeypatch, _ = mod
    monkeypatch.setattr(m, "get_supabase", lambda: _explicit_sb(completed_at="2026-01-01"))
    monkeypatch.setattr(m, "complete_inspection_status", lambda *a, **k: {"changed": False, "noop": True})
    out = asyncio.run(m.complete_inspection("ws-1", {}, current={"id": "u1"}))
    assert out["data"]["mode"] == "REPLAY"
    assert calls["emit"] == []


def test_t8_explicit_repair_replay_but_changed(mod):
    m, calls, monkeypatch, _ = mod
    monkeypatch.setattr(m, "get_supabase", lambda: _explicit_sb(completed_at="2026-01-01"))
    monkeypatch.setattr(m, "complete_inspection_status", lambda *a, **k: {"changed": True, "status": "COMPLETED"})
    out = asyncio.run(m.complete_inspection("ws-1", {}, current={"id": "u1"}))
    assert out["data"]["mode"] == "REPLAY"
    assert len(calls["emit"]) == 1
    assert calls["emit"][0]["event_name"] == "INSPECTION_COMPLETED"
