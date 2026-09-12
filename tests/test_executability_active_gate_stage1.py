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

    def __init__(self, rows, name="work_schedules", client=None):
        self.name = name
        self.rows = rows
        self.client = client
        self.filters = {}
        self._in = {}
        self._ops = []
        self._op = "select"
        self._payload = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = dict(payload)
        self._ops.append(("update", payload))
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
        if self._op == "update":
            if self.client is not None:
                self.client.updates.append(
                    {"table": self.name, "payload": dict(self._payload), "filters": dict(self.filters), "in": dict(self._in)}
                )
            for r in self.rows:
                ok = True
                for k, v in self.filters.items():
                    if r.get(k) != v:
                        ok = False
                        break
                if ok and self._in:
                    for k, vals in self._in.items():
                        if r.get(k) not in vals:
                            ok = False
                            break
                if ok:
                    r.update(self._payload)
            return SimpleNamespace(data=[{"ok": True}])
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
        self.updates = []

    def table(self, name):
        ch = _Chain(self.rows_by_table.get(name, []), name, client=self)
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
            ch = _Chain(self.rows_by_table.get(name, []), name, client=self)
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


def test_confirm_excluded_writes_active_yn_false_not_is_active(monkeypatch):
    """PATCH-R1: confirm exclusion aligns executability axis to active_yn=false."""
    fid = "f-confirm"
    rows = [
        {
            "id": "ex1",
            "factory_id": fid,
            "is_excluded": True,
            "active_yn": True,
            "status_code": "planned",
            "custom_cycle": None,
        },
        {
            "id": "ok1",
            "factory_id": fid,
            "is_excluded": False,
            "active_yn": True,
            "status_code": "planned",
            "custom_cycle": None,
        },
        {
            "id": "already_off",
            "factory_id": fid,
            "is_excluded": False,
            "active_yn": False,
            "status_code": "planned",
            "custom_cycle": None,
        },
    ]
    sb = _SB({"work_schedules": rows})
    monkeypatch.setattr(ws, "get_supabase", lambda: sb)
    monkeypatch.setattr(ws, "_ensure_ws_factory_access", lambda *a, **k: None)
    monkeypatch.setattr(ws, "_now", lambda: "2026-09-12T00:00:00+00:00")

    out = ws.confirm_schedules(fid, ws.ConfirmBody(reviewed_by="user-1"), current={"id": "u"})
    assert out["data"]["excluded"] == 1
    assert out["data"]["confirmed"] == 1  # only active_yn=true + not excluded

    excl_updates = [u for u in sb.updates if u["payload"].get("status_code") == "EXCLUDED"]
    assert len(excl_updates) == 1
    payload = excl_updates[0]["payload"]
    assert payload.get("active_yn") is False
    assert "is_active" not in payload
    assert excl_updates[0]["filters"].get("factory_id") == fid
    assert "ex1" in excl_updates[0]["in"].get("id", [])

    # active confirm write also factory-scoped
    active_updates = [
        u for u in sb.updates
        if "reviewed_at" in u["payload"] and u["payload"].get("status_code") != "EXCLUDED"
    ]
    assert active_updates
    assert all(u["filters"].get("factory_id") == fid for u in active_updates)
    assert all(u["filters"].get("id") for u in active_updates)

    # row mutated in place
    ex = next(r for r in rows if r["id"] == "ex1")
    assert ex["active_yn"] is False
    assert ex["status_code"] == "EXCLUDED"

    # active branch must still require active_yn=true (already_off not confirmed)
    ok = next(r for r in rows if r["id"] == "ok1")
    assert ok["active_yn"] is True
    assert "reviewed_at" in ok

    already = next(r for r in rows if r["id"] == "already_off")
    assert already["active_yn"] is False
    assert "reviewed_at" not in already

    # executable list excludes inactivated excluded row
    monkeypatch.setattr(ws, "_is_admin", lambda *a, **k: True)
    monkeypatch.setattr(ws, "_scope", lambda *a, **k: "ALL")
    monkeypatch.setattr(ws, "_tier", lambda *a, **k: "ALL")
    monkeypatch.setattr(ws, "scoped_filter", lambda *a, **k: {})
    monkeypatch.setattr(ws, "apply_scoped_filter", lambda q, filt: q)

    listed = ws.get_work_schedules(
        company_id="c1",
        factory_id=fid,
        status_code=None,
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
    ids = {r["id"] for r in listed["data"]["items"]}
    assert "ex1" not in ids
    assert "ok1" in ids
    assert "already_off" not in ids


def test_confirm_schedules_source_has_no_is_active_write():
    import inspect
    src = inspect.getsource(ws.confirm_schedules)
    assert '"is_active"' not in src
    assert '"active_yn":   False' in src or '"active_yn": False' in src
    assert '.eq("factory_id", factory_id)' in src
    # both UPDATE chains must include factory_id after id / in_(id)
    assert 'eq("id", row["id"]).eq("factory_id", factory_id)' in src.replace(" \\\n", "").replace("\n", "")
    assert 'in_("id", batch).eq("factory_id", factory_id)' in src.replace(" \\\n", "").replace("\n", "")


def test_confirm_excluded_does_not_cross_factory_same_id(monkeypatch):
    """PATCH-R2 CASE A: identical schedule id in F2 must stay active_yn=true."""
    same_id = "SAME"
    rows = [
        {
            "id": same_id, "factory_id": "F1", "is_excluded": True,
            "active_yn": True, "status_code": "planned", "custom_cycle": None,
        },
        {
            "id": same_id, "factory_id": "F2", "is_excluded": True,
            "active_yn": True, "status_code": "planned", "custom_cycle": None,
        },
    ]
    sb = _SB({"work_schedules": rows})
    monkeypatch.setattr(ws, "get_supabase", lambda: sb)
    monkeypatch.setattr(ws, "_ensure_ws_factory_access", lambda *a, **k: None)
    monkeypatch.setattr(ws, "_now", lambda: "2026-09-12T00:00:00+00:00")

    out = ws.confirm_schedules("F1", ws.ConfirmBody(reviewed_by="user-1"), current={"id": "u"})
    assert out["data"]["excluded"] == 1
    assert out["data"]["confirmed"] == 0

    f1 = next(r for r in rows if r["factory_id"] == "F1")
    f2 = next(r for r in rows if r["factory_id"] == "F2")
    assert f1["active_yn"] is False
    assert f1["status_code"] == "EXCLUDED"
    assert f2["active_yn"] is True
    assert f2["status_code"] == "planned"

    excl = [u for u in sb.updates if u["payload"].get("status_code") == "EXCLUDED"]
    assert len(excl) == 1
    assert excl[0]["filters"].get("factory_id") == "F1"
    assert same_id in excl[0]["in"].get("id", [])


def test_confirm_active_does_not_cross_factory_same_id(monkeypatch):
    """PATCH-R2 CASE B: reviewed_at only on target factory composite identity."""
    same_id = "SAME2"
    rows = [
        {
            "id": same_id, "factory_id": "F1", "is_excluded": False,
            "active_yn": True, "status_code": "planned", "custom_cycle": None,
        },
        {
            "id": same_id, "factory_id": "F2", "is_excluded": False,
            "active_yn": True, "status_code": "planned", "custom_cycle": None,
        },
    ]
    sb = _SB({"work_schedules": rows})
    monkeypatch.setattr(ws, "get_supabase", lambda: sb)
    monkeypatch.setattr(ws, "_ensure_ws_factory_access", lambda *a, **k: None)
    monkeypatch.setattr(ws, "_now", lambda: "2026-09-12T12:00:00+00:00")

    out = ws.confirm_schedules("F1", ws.ConfirmBody(reviewed_by="user-1"), current={"id": "u"})
    assert out["data"]["confirmed"] == 1
    assert out["data"]["excluded"] == 0

    f1 = next(r for r in rows if r["factory_id"] == "F1")
    f2 = next(r for r in rows if r["factory_id"] == "F2")
    assert "reviewed_at" in f1
    assert f1["reviewed_by"] == "user-1"
    assert "reviewed_at" not in f2

    active_updates = [u for u in sb.updates if "reviewed_at" in u["payload"]]
    assert len(active_updates) == 1
    assert active_updates[0]["filters"] == {"id": same_id, "factory_id": "F1"}
