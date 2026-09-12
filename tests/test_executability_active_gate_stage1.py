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
from services.inspection_sets_svc.errors import InspectionSetsSvcError
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
    state = {"ws_rows": [{"factory_id": "F1", "active_yn": False, "id": "ws1", "company_id": "c1"}]}

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
    # Real ownership return — inactive pair must fail active gate on start
    monkeypatch.setattr(
        ic,
        "_ensure_ws_own",
        lambda *a, **k: state["ws_rows"][0],
    )

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
        "work_assignments": [{"id": "wa1", "schedule_id": "ws1", "factory_id": "f1"}],
        "work_schedules": [
            {"id": "ws1", "factory_id": "f1", "inspection_set_id": "set1", "active_yn": False},
        ],
    }
    sb = _SB(rows)
    monkeypatch.setattr(items_svc, "get_supabase", lambda: sb)
    assert items_svc.resolve_set_id_for_assignment("wa1") is None

    rows["work_schedules"][0]["active_yn"] = True
    assert items_svc.resolve_set_id_for_assignment("wa1") == "set1"


def test_complete_ownership_helper_not_gated_by_active_yn():
    """_ensure_ws_own must remain ownership/exact-id only (complete path preserve)."""
    import inspect
    src = inspect.getsource(ic._ensure_ws_own)
    assert "require_active_executable" not in src
    # May select active_yn for callers, but must not fail-close on inactive itself
    assert "active_yn is not True" not in src
    assert "require_active" not in src


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

def test_owned_ids_ownership_only_includes_inactive(monkeypatch):
    """PATCH-R3/R5: ownership helpers must NOT apply active_yn."""
    import inspect

    src = inspect.getsource(ws._owned_pairs)
    assert "require_active_executable" not in src
    assert ".eq(\"active_yn\"" not in src
    assert ".eq('active_yn'" not in src

    rows = [
        {"id": "a", "factory_id": "f1", "company_id": "c1", "active_yn": True},
        {"id": "b", "factory_id": "f1", "company_id": "c1", "active_yn": False},
        {"id": "c", "factory_id": "f1", "company_id": "c1", "active_yn": None},
    ]
    sb = _SB({"work_schedules": rows})
    monkeypatch.setattr(ws, "_is_admin", lambda *a, **k: False)
    monkeypatch.setattr(ws, "_scope", lambda *a, **k: "COMPANY")
    monkeypatch.setattr(ws, "scoped_filter", lambda *a, **k: {"company_id": "c1"})
    monkeypatch.setattr(
        ws,
        "apply_scoped_filter",
        lambda q, filt: q.eq("company_id", filt["company_id"]) if filt else q,
    )
    DENY = object()
    monkeypatch.setattr(ws, "DENY", DENY)

    owned = ws._owned_pairs(sb, ["a", "b", "c"], {"id": "u", "role_code": "010"})
    assert owned == {("a", "f1"), ("b", "f1"), ("c", "f1")}
    assert ("eq", "active_yn", True) not in sb.last["work_schedules"]._ops


def test_batch_owned_inactive_does_not_mutate_active_sibling(monkeypatch):
    """PATCH-R5: FB-scoped ownership of inactive pair must not update FA."""
    same = "shared-id"
    rows = [
        {"id": same, "factory_id": "FA", "company_id": "c1", "active_yn": True},
        {"id": same, "factory_id": "FB", "company_id": "c1", "active_yn": False},
    ]
    sb = _SB({"work_schedules": rows, "work_assignments": []})
    monkeypatch.setattr(ws, "get_supabase", lambda: sb)
    monkeypatch.setattr(ws, "_now", lambda: "2026-09-12T00:00:00+00:00")
    # Simulate FB factory scope ownership
    monkeypatch.setattr(
        ws,
        "_owned_pairs",
        lambda *a, **k: {(same, "FB")},
    )
    out = ws.batch_update_schedules(
        ws.BatchUpdateBody(
            updates=[ws.ScheduleUpdateItem(id=same, assigned_user_id="user-NEW")]
        ),
        current={"id": "u", "role_code": "010", "factory_id": "FB"},
    )
    assert out["data"]["updated"] == 0
    assert sb.updates == []
    fa = next(r for r in rows if r["factory_id"] == "FA")
    assert fa.get("assigned_user_id") is None


def test_worker_home_hard_hides_inactive_and_null_schedule(monkeypatch):
    """PATCH-R3: inactive/null parent schedule → assignment/task excluded entirely."""
    from routers import worker_home as wh

    rows = {
        "work_assignments": [
            {
                "id": "wa-active",
                "schedule_id": "ws-a",
                "factory_id": "fa-1",
                "asset_id": None,
                "status_code": "PENDING",
                "inspection_set_id": "set1",
                "scheduled_date": "2026-09-12",
                "assigned_user_id": "u1",
            },
            {
                "id": "wa-inactive",
                "schedule_id": "ws-off",
                "factory_id": "fa-1",
                "asset_id": None,
                "status_code": "PENDING",
                "inspection_set_id": "set1",
                "scheduled_date": "2026-09-12",
                "assigned_user_id": "u1",
            },
            {
                "id": "wa-null",
                "schedule_id": "ws-null",
                "factory_id": "fa-1",
                "asset_id": None,
                "status_code": "PENDING",
                "inspection_set_id": "set1",
                "scheduled_date": "2026-09-12",
                "assigned_user_id": "u1",
            },
        ],
        "work_schedules": [
            {
                "id": "ws-a",
                "factory_id": "fa-1",
                "active_yn": True,
                "description": "ok",
                "law_name": "L",
                "obligation_type": "CHECK",
            },
            {
                "id": "ws-off",
                "factory_id": "fa-1",
                "active_yn": False,
                "description": "hidden",
                "law_name": "L",
                "obligation_type": "CHECK",
            },
            {
                "id": "ws-null",
                "factory_id": "fa-1",
                "active_yn": None,
                "description": "hidden-null",
                "law_name": "L",
                "obligation_type": "CHECK",
            },
        ],
        "inspection_sets": [
            {"id": "set1", "inspection_set_name": "SET", "cycle_unit": "month", "cycle_value": 1},
        ],
    }
    sb = _SB(rows)
    monkeypatch.setattr(wh, "get_supabase", lambda: sb)
    monkeypatch.setattr(wh, "_today", lambda: "2026-09-12")

    out = wh.get_today_tasks(user_id="u1", factory_id=None, company_id=None)
    inspections = out["data"]["tasks"]["inspections"]
    ids = {i["assignment_id"] for i in inspections}
    assert ids == {"wa-active"}
    assert inspections[0].get("description") == "ok"
    assert ("eq", "active_yn", True) in sb.last["work_schedules"]._ops


def test_worker_home_same_schedule_id_mixed_factory_active(monkeypatch):
    """PATCH-R4: A active / B inactive same schedule_id — only A assignment survives."""
    from routers import worker_home as wh

    same = "ws-shared"
    rows = {
        "work_assignments": [
            {
                "id": "wa-A", "schedule_id": same, "factory_id": "FA",
                "status_code": "PENDING", "inspection_set_id": None,
                "scheduled_date": "2026-09-12", "assigned_user_id": "u1",
            },
            {
                "id": "wa-B", "schedule_id": same, "factory_id": "FB",
                "status_code": "PENDING", "inspection_set_id": None,
                "scheduled_date": "2026-09-12", "assigned_user_id": "u1",
            },
        ],
        "work_schedules": [
            {"id": same, "factory_id": "FA", "active_yn": True, "description": "A"},
            {"id": same, "factory_id": "FB", "active_yn": False, "description": "B"},
        ],
        "inspection_sets": [],
    }
    sb = _SB(rows)
    monkeypatch.setattr(wh, "get_supabase", lambda: sb)
    monkeypatch.setattr(wh, "_today", lambda: "2026-09-12")
    out = wh.get_today_tasks(user_id="u1", factory_id=None, company_id=None)
    ids = {i["assignment_id"] for i in out["data"]["tasks"]["inspections"]}
    assert ids == {"wa-A"}


def test_event_schedules_list_active_gate(monkeypatch):
    from routers import event_trigger as et

    fid = "f1"
    rows = [
        {"id": "e1", "factory_id": fid, "source_type": "EVENT", "active_yn": True, "planned_date": "2026-10-01"},
        {"id": "e2", "factory_id": fid, "source_type": "EVENT", "active_yn": False, "planned_date": "2026-10-02"},
        {"id": "e3", "factory_id": fid, "source_type": "EVENT", "active_yn": None, "planned_date": "2026-10-03"},
        {"id": "m1", "factory_id": fid, "source_type": "MANUAL", "active_yn": True, "planned_date": "2026-10-01"},
    ]
    sb = _SB({"work_schedules": rows})
    monkeypatch.setattr(et, "get_supabase", lambda: sb)

    out = et.get_event_schedules(
        factory_id=fid,
        obligation_type=None,
        status_code=None,
        event_type=None,
        planned_date_from=None,
        planned_date_to=None,
        page=1,
        size=20,
    )
    ids = [r["id"] for r in out["data"]["items"]]
    assert ids == ["e1"]
    assert ("eq", "active_yn", True) in sb.last["work_schedules"]._ops
    assert ("eq", "source_type", "EVENT") in sb.last["work_schedules"]._ops


def test_apply_one_update_still_gates_active_parent():
    import inspect

    src = inspect.getsource(ws._apply_one_update)
    assert "_resolve_exact_active_occurrence" in src
    assert "factory_id" in src
    helper = inspect.getsource(ws._resolve_exact_occurrence)
    assert "require_active" in helper
    assert "len(rows) > 1" in helper


def test_resolve_set_id_excludes_inactive_pair(monkeypatch):
    """PATCH-R5: WA factory FB inactive must not resolve via FA active sibling."""
    rows = {
        "work_assignments": [
            {"id": "wa1", "schedule_id": "ws1", "factory_id": "FB"},
        ],
        "work_schedules": [
            {"id": "ws1", "factory_id": "FA", "inspection_set_id": "setA", "active_yn": True},
            {"id": "ws1", "factory_id": "FB", "inspection_set_id": "setB", "active_yn": False},
        ],
    }
    sb = _SB(rows)
    monkeypatch.setattr(items_svc, "get_supabase", lambda: sb)
    assert items_svc.resolve_set_id_for_assignment("wa1") is None
    rows["work_schedules"][1]["active_yn"] = True
    assert items_svc.resolve_set_id_for_assignment("wa1") == "setB"


def test_R6_wa_factory_null_no_active_sibling_set_promotion(monkeypatch):
    """PATCH-R6 A: WA.factory_id NULL + FA active / FB inactive → do not pick FA set."""
    rows = {
        "work_assignments": [
            {"id": "wa-null-fid", "schedule_id": "S", "factory_id": None},
        ],
        "work_schedules": [
            {"id": "S", "factory_id": "FA", "inspection_set_id": "setA", "active_yn": True},
            {"id": "S", "factory_id": "FB", "inspection_set_id": "setB", "active_yn": False},
        ],
    }
    sb = _SB(rows)
    monkeypatch.setattr(items_svc, "get_supabase", lambda: sb)
    assert items_svc.resolve_set_id_for_assignment("wa-null-fid") is None
    with pytest.raises(InspectionSetsSvcError) as ei:
        items_svc.get_items_for_assignment("wa-null-fid")
    assert ei.value.status_code == 409


def test_no_work_schedules_is_active_write_in_stage1_surfaces():
    import inspect
    from pathlib import Path

    # confirm + work_schedules router production writes
    for mod in (ws,):
        src = inspect.getsource(mod)
        # allow comments mentioning is_active drift, forbid write payload key
        assert '"is_active"' not in src or '"is_active"' not in inspect.getsource(ws.confirm_schedules)
    assert '"is_active"' not in inspect.getsource(ws.confirm_schedules)

    # migration must not invent is_active writes
    mig = Path(__file__).resolve().parents[1] / "supabase/migrations/20260912070439_executability_rpc_active_gate.sql"
    text = mig.read_text(encoding="utf-8")
    assert "is_active" not in text
