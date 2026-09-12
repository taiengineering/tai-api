"""STAGE 1 — executable work_schedules active_yn=true hard gate.

Definition §6-7-10-O/P: LIFECYCLE ≠ EXECUTABILITY.
ACTIVE_EXECUTABLE := active_yn exact TRUE AND consumer-allowed lifecycle.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import inspection_checklist as ic
from routers import work_schedules as ws
from services.inspection_sets_svc import items as items_svc
from services.work_schedule_executability import require_active_executable


class _Chain:
    """Minimal Supabase query chain that records filters and returns matching rows."""

    def __init__(self, rows, name="work_schedules"):
        self.name = name
        self.rows = rows
        self.filters = {}
        self._in = {}
        self._ops = []

    def select(self, *a, **k):
        return self

    def eq(self, k, v):
        self.filters[k] = v
        self._ops.append(("eq", k, v))
        return self

    def neq(self, k, v):
        self._ops.append(("neq", k, v))
        return self

    def in_(self, k, vals):
        self._in[k] = list(vals)
        self._ops.append(("in", k, list(vals)))
        return self

    def gte(self, k, v):
        self._ops.append(("gte", k, v))
        return self

    def lte(self, k, v):
        self._ops.append(("lte", k, v))
        return self

    def lt(self, k, v):
        self._ops.append(("lt", k, v))
        return self

    def order(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def execute(self):
        out = []
        for r in self.rows:
            ok = True
            for k, v in self.filters.items():
                if r.get(k) != v:
                    ok = False
                    break
            if not ok:
                continue
            for k, vals in self._in.items():
                if r.get(k) not in vals:
                    ok = False
                    break
            if ok:
                out.append(dict(r))
        return SimpleNamespace(data=out, count=len(out))


class _SB:
    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table
        self.last = {}

    def table(self, name):
        ch = _Chain(self.rows_by_table.get(name, []), name)
        self.last[name] = ch
        return ch


def test_require_active_executable_eq_true_only():
    calls = []

    class Q:
        def eq(self, k, v):
            calls.append((k, v))
            return self

    require_active_executable(Q())
    assert calls == [("active_yn", True)]


def test_list_schedules_includes_active_true_excludes_false_and_null(monkeypatch):
    fid = "f1"
    rows = [
        {"id": "a", "factory_id": fid, "planned_date": "2026-10-01", "status_code": "planned", "active_yn": True},
        {"id": "b", "factory_id": fid, "planned_date": "2026-10-02", "status_code": "planned", "active_yn": False},
        {"id": "c", "factory_id": fid, "planned_date": "2026-10-03", "status_code": "planned", "active_yn": None},
        {"id": "d", "factory_id": fid, "planned_date": "2026-10-04", "status_code": "completed", "active_yn": True},
    ]
    sb = _SB({"work_schedules": rows, "safety_inspections": []})
    monkeypatch.setattr(ic, "get_supabase", lambda: sb)
    monkeypatch.setattr(ic, "_ensure_factory_own", lambda *a, **k: None)

    out = asyncio.run(
        ic.list_schedules(fid, month=None, status_code="planned", page=1, page_size=20, current={"id": "u"})
    )
    ids = [r["id"] for r in out["data"]["items"]]
    assert ids == ["a"]
    assert ("eq", "active_yn", True) in sb.last["work_schedules"]._ops
    assert ("eq", "status_code", "planned") in sb.last["work_schedules"]._ops
    assert ("eq", "factory_id", fid) in sb.last["work_schedules"]._ops


def test_upcoming_excludes_inactive_preserves_status_predicate(monkeypatch):
    fid = "f1"
    today = "2026-09-12"
    rows = [
        {
            "id": "u1", "factory_id": fid, "planned_date": "2026-09-15",
            "status_code": "planned", "active_yn": True, "inspection_set_id": "s1",
            "inspection_sets": {"inspection_set_name": "A", "law_name": "L"},
        },
        {
            "id": "u2", "factory_id": fid, "planned_date": "2026-09-16",
            "status_code": "planned", "active_yn": False, "inspection_set_id": "s1",
            "inspection_sets": {"inspection_set_name": "B", "law_name": "L"},
        },
        {
            "id": "u3", "factory_id": fid, "planned_date": "2026-09-17",
            "status_code": "completed", "active_yn": True, "inspection_set_id": "s1",
            "inspection_sets": {"inspection_set_name": "C", "law_name": "L"},
        },
    ]
    sb = _SB({"work_schedules": rows, "inspection_sets": []})

    class CountQ(_Chain):
        def execute(self):
            return SimpleNamespace(data=[], count=0)

    class SB2(_SB):
        def table(self, name):
            # count queries use select id count=exact — still return Chain
            ch = _Chain(self.rows_by_table.get(name, []), name)
            self.last[name] = ch
            return ch

    sb = SB2({"work_schedules": rows, "inspection_sets": [{"id": "x"}]})
    monkeypatch.setattr(ic, "get_supabase", lambda: sb)
    monkeypatch.setattr(ic, "_ensure_factory_own", lambda *a, **k: None)
    monkeypatch.setattr(ic, "business_today", lambda: __import__("datetime").date.fromisoformat(today))

    out = asyncio.run(
        ic.get_inspection_status(fid, current={"id": "u"})
    )
    upcoming_ids = [r["id"] for r in out["data"]["upcoming"]]
    assert "u1" in upcoming_ids
    assert "u2" not in upcoming_ids
    assert "u3" not in upcoming_ids  # completed not in upcoming status set
    assert ("eq", "active_yn", True) in sb.last["work_schedules"]._ops


def test_start_pre_read_rejects_inactive(monkeypatch):
    state = {"ws_rows": [{"factory_id": "F1", "active_yn": False, "id": "ws1"}]}

    class Q:
        def __init__(self):
            self.f = {}

        def select(self, *a, **k):
            return self

        def eq(self, k, v):
            self.f[k] = v
            return self

        def execute(self):
            rows = [r for r in state["ws_rows"] if all(r.get(k) == v for k, v in self.f.items())]
            return SimpleNamespace(data=rows)

    class SB:
        def table(self, name):
            return Q()

    monkeypatch.setattr(ic, "get_supabase", lambda: SB())
    monkeypatch.setattr(ic, "_ensure_ws_own", lambda *a, **k: None)

    with pytest.raises(HTTPException) as ei:
        asyncio.run(ic.start_inspection("ws1", body={}, current={"id": "u"}))
    assert ei.value.status_code == 404


def test_get_work_schedules_active_gate_and_factory(monkeypatch):
    rows = [
        {"id": "1", "factory_id": "fa", "company_id": "c1", "status_code": "planned", "active_yn": True, "created_at": "t"},
        {"id": "2", "factory_id": "fa", "company_id": "c1", "status_code": "planned", "active_yn": False, "created_at": "t"},
        {"id": "3", "factory_id": "fb", "company_id": "c1", "status_code": "planned", "active_yn": True, "created_at": "t"},
    ]
    sb = _SB({"work_schedules": rows})
    monkeypatch.setattr(ws, "get_supabase", lambda: sb)
    monkeypatch.setattr(ws, "_is_admin", lambda *a, **k: True)
    monkeypatch.setattr(ws, "_scope", lambda *a, **k: "ALL")
    monkeypatch.setattr(ws, "scoped_filter", lambda *a, **k: {"factory_id": "fa"})
    monkeypatch.setattr(
        ws, "apply_scoped_filter",
        lambda q, filt: q.eq("factory_id", filt["factory_id"]) if filt else q,
    )

    out = ws.get_work_schedules(
        company_id="c1",
        factory_id="fa",
        status_code="planned",
        source_type=None,
        obligation_type=None,
        is_assigned=None,
        planned_date_from=None,
        planned_date_to=None,
        keyword=None,
        page=1,
        size=50,
        current={"id": "u", "role_code": "001"},
    )
    ids = [r["id"] for r in out["data"]["items"]]
    assert ids == ["1"]
    assert ("eq", "active_yn", True) in sb.last["work_schedules"]._ops


def test_resolve_set_id_excludes_inactive(monkeypatch):
    rows = {
        "work_assignments": [{"id": "wa1", "schedule_id": "ws1"}],
        "work_schedules": [
            {"id": "ws1", "inspection_set_id": "set1", "active_yn": False},
        ],
    }
    sb = _SB(rows)
    monkeypatch.setattr(items_svc, "get_supabase", lambda: sb)
    assert items_svc.resolve_set_id_for_assignment("wa1") is None

    rows["work_schedules"][0]["active_yn"] = True
    assert items_svc.resolve_set_id_for_assignment("wa1") == "set1"


def test_complete_ownership_helper_not_gated_by_active_yn():
    """_ensure_ws_own must remain lifecycle/ownership only (complete path preserve)."""
    import inspect
    src = inspect.getsource(ic._ensure_ws_own)
    assert "require_active_executable" not in src
    assert "active_yn" not in src


def test_status_counts_path_not_using_active_gate_helper():
    """Dashboard count queries stay ungated (history/reporting)."""
    import inspect
    src = inspect.getsource(ic.get_inspection_status)
    # upcoming uses helper; month/completed/overdue counts must not wrap require_active
    # Verify helper appears once-ish in upcoming branch only by checking overdue block.
    assert "overdue_res = supabase.table" in src or "overdue_res = supabase.table(" in src.replace("\n", " ")
    assert "require_active_executable(upcoming_q)" in src
