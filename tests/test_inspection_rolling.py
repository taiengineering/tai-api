"""OBJ-04 ROLLING-02 — ensure_next_rolling_schedule R1~R18 (실 DB 0).

멱등 근거: 결정적 next_date + unique(inspection_set_id,planned_date,factory_id)
+ ON CONFLICT DO NOTHING(ignore_duplicates=True).
"""
from __future__ import annotations

import asyncio
import inspect
import os
import threading
from copy import deepcopy
from datetime import date

from services.inspection_rolling import (
    CONFLICT_KEY,
    _add_cycle as helper_add_cycle,
    ensure_next_rolling_schedule,
)
from services.status_vocab import ws_write_scheduled
import routers.inspection_checklist as ic
from routers.inspection_checklist import _add_cycle as router_add_cycle


ROW_KEYS = (
    "inspection_set_id", "company_id", "factory_id",
    "planned_date", "start_date", "end_date",
    "status_code", "source_type", "obligation_type",
    "summary", "active_yn", "assigned_user_id",
)


class _Resp:
    def __init__(self, data=None):
        self.data = data if data is not None else []


def _uq(row):
    return (row["inspection_set_id"], row["planned_date"], row["factory_id"])


class MemTable:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self._op = None
        self._payload = None
        self._filters = {}
        self._on_conflict = None
        self._ignore_dup = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def eq(self, k, v):
        self._filters[k] = v
        return self

    def limit(self, n):
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def delete(self, *a, **k):
        self._op = "delete"
        return self

    def upsert(self, row, on_conflict=None, ignore_duplicates=False):
        self._op = "upsert"
        self._payload = row
        self._on_conflict = on_conflict
        self._ignore_dup = ignore_duplicates
        return self

    def execute(self):
        rows = self.db.tables.setdefault(self.name, [])
        self.db.log.append((self.name, self._op, deepcopy(self._payload), dict(self._filters)))
        if self._op == "select":
            out = rows
            for k, v in self._filters.items():
                out = [r for r in out if r.get(k) == v]
            return _Resp(deepcopy(out))
        if self._op == "update":
            matched = []
            for r in rows:
                if all(r.get(k) == v for k, v in self._filters.items()):
                    r.update(self._payload)
                    matched.append(deepcopy(r))
            return _Resp(matched)
        if self._op == "insert":
            payload = self._payload
            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                rows.append(deepcopy(item))
            return _Resp(deepcopy(items))
        if self._op == "upsert":
            self.db.upsert_kwargs.append({
                "on_conflict": self._on_conflict,
                "ignore_duplicates": self._ignore_dup,
            })
            row = deepcopy(self._payload)
            key = _uq(row)
            with self.db.lock:
                existing = next((r for r in rows if _uq(r) == key), None)
                if existing is not None:
                    if self._ignore_dup:
                        return _Resp([])          # DO NOTHING
                    existing.update(row)
                    return _Resp([deepcopy(existing)])
                rows.append(row)
                return _Resp([deepcopy(row)])
        if self._op == "delete":
            raise AssertionError("delete 금지")
        return _Resp([])


class MemDB:
    def __init__(self):
        self.tables = {
            "work_schedules": [],
            "inspection_sets": [],
            "factories": [],
            "safety_inspections": [],
            "safety_inspection_results": [],
        }
        self.log = []
        self.upsert_kwargs = []
        self.lock = threading.Lock()

    def table(self, name):
        return MemTable(self, name)


def _seed(db: MemDB, *,
          ws_id="WS-1",
          set_id="SET-1",
          factory_id="F-1",
          company_id="C-1",
          planned="2026-01-15",
          completed_at=None,
          cycle_unit="year",
          cycle_value=1,
          source="LEGAL_ENGINE",
          end_date=None,
          next_planned=None,
          category="GENERAL",
          name="월간점검"):
    db.tables["work_schedules"].append({
        "id": ws_id,
        "factory_id": factory_id,
        "inspection_set_id": set_id,
        "planned_date": planned,
        "company_id": company_id,
        "completed_at": completed_at,
        "status_code": "in_progress",
        "assigned_user_id": "USER-OLD",
    })
    db.tables["inspection_sets"].append({
        "id": set_id,
        "factory_id": factory_id,
        "company_id": company_id,
        "cycle_unit": cycle_unit,
        "cycle_value": cycle_value,
        "inspection_set_name": name,
        "inspection_category": category,
        "source": source,
        "schedule_end_date": end_date,
        "next_planned_date": next_planned,
    })
    db.tables["factories"].append({"id": factory_id, "company_id": company_id})
    db.tables["safety_inspections"].append({"id": "INS", "assignment_id": ws_id})
    return db


def test_r1_missing_work_schedule_skipped():
    db = MemDB()
    out = ensure_next_rolling_schedule(db, "NOPE", date(2026, 1, 20))
    assert out == {"created": False, "next_planned_date": None, "skipped": True}


def test_r2_no_inspection_set_id_skipped():
    db = _seed(MemDB())
    db.tables["work_schedules"][0]["inspection_set_id"] = None
    out = ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    assert out["skipped"] is True and out["created"] is False
    assert [r for r in db.tables["work_schedules"] if r.get("planned_date") != "2026-01-15"] == []


def test_r3_missing_inspection_set_skipped():
    db = _seed(MemDB())
    db.tables["inspection_sets"] = []
    out = ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    assert out["skipped"] is True


def test_r4_first_create_and_complete_response_shape():
    db = _seed(MemDB(), next_planned=None)
    anchor = date(2026, 1, 20)
    out = ensure_next_rolling_schedule(db, "WS-1", anchor)
    assert out["skipped"] is False
    assert out["created"] is True
    assert out["next_planned_date"] == "2027-01-20"
    assert len([r for r in db.tables["work_schedules"] if r.get("planned_date") == "2027-01-20"]) == 1

    calls = {"roll": None}

    def _roll(sb, wid, a):
        calls["roll"] = (wid, a)
        return {"created": True, "next_planned_date": "2027-01-20", "skipped": False}

    class _Chain:
        def __init__(self, name):
            self.name = name

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def update(self, p):
            return self

        def limit(self, n):
            return self

        def execute(self):
            if self.name == "safety_inspections":
                return _Resp([{"id": "insp-9"}])
            if self.name == "work_schedules":
                return _Resp([{"id": "ws-1", "inspection_set_id": "SET-1", "factory_id": "F-1",
                               "completed_at": None, "status_code": "in_progress"}])
            return _Resp([])

    class _SB:
        def table(self, name):
            return _Chain(name)

    orig_g, orig_own, orig_roll, orig_c = (
        ic.get_supabase, ic._ensure_ws_own, ic.ensure_next_rolling_schedule, ic.complete_inspection_status,
    )
    ic.get_supabase = lambda: _SB()
    ic._ensure_ws_own = lambda *a, **k: None
    ic.ensure_next_rolling_schedule = _roll
    ic.complete_inspection_status = lambda *a, **k: None
    try:
        resp = asyncio.run(ic.complete_inspection(
            "ws-1", body={"completed_at": "2026-01-20", "summary": "ok"}, current={"id": "U"},
        ))
    finally:
        ic.get_supabase = orig_g
        ic._ensure_ws_own = orig_own
        ic.ensure_next_rolling_schedule = orig_roll
        ic.complete_inspection_status = orig_c
    assert resp["status"] == "success"
    assert set(resp["data"].keys()) == {
        "work_schedule_id", "completed_at", "summary", "next_schedule_created", "next_planned_date",
    }
    assert resp["data"]["next_schedule_created"] is True
    assert resp["data"]["next_planned_date"] == "2027-01-20"
    assert calls["roll"][0] == "ws-1"
    assert calls["roll"][1] == date(2026, 1, 20)


def test_r5_next_day_replay_same_anchor_insert_0():
    db = _seed(MemDB(), completed_at="2026-01-20")
    first = ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    assert first["created"] is True
    second = ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    assert second["created"] is False
    assert second["next_planned_date"] == first["next_planned_date"] == "2027-01-20"
    assert len([r for r in db.tables["work_schedules"] if r.get("planned_date") == "2027-01-20"]) == 1

    payloads = []

    class FreezeTbl:
        def __init__(self, name):
            self.name = name

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, n):
            return self

        def update(self, p):
            if self.name == "work_schedules":
                payloads.append(p)
            return self

        def execute(self):
            if self.name == "safety_inspections":
                return _Resp([{"assignment_id": "WS-1"}])
            if self.name == "work_schedules":
                return _Resp([{"completed_at": "2026-01-20"}])
            return _Resp([])

    class FreezeSB:
        def table(self, name):
            return FreezeTbl(name)

    helper_args = []
    orig = (ic.get_supabase, ic._ensure_inspection_own, ic.record_safe_result_batch,
            ic.complete_inspection_status, ic.ensure_next_rolling_schedule)
    ic.get_supabase = lambda: FreezeSB()
    ic._ensure_inspection_own = lambda *a, **k: None
    ic.record_safe_result_batch = lambda *a, **k: {"mode": "REPLAY", "count": 1}
    ic.complete_inspection_status = lambda *a, **k: None

    def _roll(sb, wid, a):
        helper_args.append((wid, a))
        return {"created": False, "next_planned_date": "2027-01-20", "skipped": False}

    ic.ensure_next_rolling_schedule = _roll
    try:
        asyncio.run(ic.record_inspection_results("INS", {"results": [{"result": "NORMAL"}]}, {"id": "U"}))
    finally:
        (ic.get_supabase, ic._ensure_inspection_own, ic.record_safe_result_batch,
         ic.complete_inspection_status, ic.ensure_next_rolling_schedule) = orig
    assert payloads[0]["completed_at"] == "2026-01-20"
    assert helper_args[0][1] == date(2026, 1, 20)


def test_r6_schedule_end_date_skip():
    db = _seed(MemDB(), end_date="2026-06-01")
    out = ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    assert out["skipped"] is True and out["created"] is False
    assert db.upsert_kwargs == []


def test_r7_next_planned_backward_regression_0():
    db = _seed(MemDB(), planned="2026-01-15", next_planned="2027-06-01")
    ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    iset_updates = [p for (t, op, p, _) in db.log if t == "inspection_sets" and op == "update"]
    assert iset_updates == []
    assert db.tables["inspection_sets"][0]["next_planned_date"] == "2027-06-01"


def test_r8_next_planned_forward_when_cur_le_src():
    db = _seed(MemDB(), planned="2026-01-15", next_planned="2026-01-15")
    ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    assert db.tables["inspection_sets"][0]["next_planned_date"] == "2027-01-20"


def test_r9_concurrent_same_anchor_one_insert():
    db = _seed(MemDB())
    results = []

    def _run():
        results.append(ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20)))

    t1 = threading.Thread(target=_run)
    t2 = threading.Thread(target=_run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    created = [r["created"] for r in results]
    assert created.count(True) == 1
    assert created.count(False) == 1
    assert len([r for r in db.tables["work_schedules"] if r.get("planned_date") == "2027-01-20"]) == 1


def test_r10_add_cycle_byte_and_behavior_parity():
    assert inspect.getsource(helper_add_cycle) == inspect.getsource(router_add_cycle)
    base = date(2026, 1, 31)
    for unit, val in (("day", 10), ("week", 2), ("month", 1), ("quarter", 1), ("half_year", 1), ("year", 1)):
        assert helper_add_cycle(base, unit, val) == router_add_cycle(base, unit, val)


def test_r11_upsert_do_nothing_kwargs():
    db = _seed(MemDB())
    ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    assert db.upsert_kwargs[-1]["on_conflict"] == CONFLICT_KEY
    assert db.upsert_kwargs[-1]["ignore_duplicates"] is True
    assert CONFLICT_KEY == "inspection_set_id,planned_date,factory_id"
    assert ws_write_scheduled() == "scheduled"


def test_r12_assigned_user_id_null():
    db = _seed(MemDB())
    ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    nxt = next(r for r in db.tables["work_schedules"] if r.get("planned_date") == "2027-01-20")
    assert nxt["assigned_user_id"] is None
    assert nxt["status_code"] == "scheduled"


def test_r13_source_type_legal_and_manual():
    db = _seed(MemDB(), source="LEGAL_ENGINE")
    ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    nxt = next(r for r in db.tables["work_schedules"] if r.get("planned_date") == "2027-01-20")
    assert nxt["source_type"] == "LEGAL"
    db2 = _seed(MemDB(), source="MANUAL")
    ensure_next_rolling_schedule(db2, "WS-1", date(2026, 1, 20))
    nxt2 = next(r for r in db2.tables["work_schedules"] if r.get("planned_date") == "2027-01-20")
    assert nxt2["source_type"] == "MANUAL"


def test_r14_row_shape_exact():
    db = _seed(MemDB(), category="FIRE", name="소화기")
    ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    nxt = next(r for r in db.tables["work_schedules"] if r.get("planned_date") == "2027-01-20")
    assert set(nxt.keys()) == set(ROW_KEYS)
    expected = {
        "inspection_set_id": "SET-1",
        "company_id": "C-1",
        "factory_id": "F-1",
        "planned_date": "2027-01-20",
        "start_date": "2027-01-20",
        "end_date": "2027-01-20",
        "status_code": "scheduled",
        "source_type": "LEGAL",
        "obligation_type": "FIRE",
        "summary": "소화기",
        "active_yn": True,
        "assigned_user_id": None,
    }
    assert nxt == expected


def _w3_call(results, mode="CREATED"):
    helper_spy = []
    db = _seed(MemDB())

    def _rb(*a, **k):
        return {"mode": mode, "count": len(results)}

    def _roll(sb, wid, a):
        helper_spy.append((wid, a))
        return {"created": True, "next_planned_date": "2027-01-01", "skipped": False}

    orig = (ic.get_supabase, ic._ensure_inspection_own, ic.record_safe_result_batch,
            ic.complete_inspection_status, ic.ensure_next_rolling_schedule)
    ic.get_supabase = lambda: db
    ic._ensure_inspection_own = lambda *a, **k: None
    ic.record_safe_result_batch = _rb
    ic.complete_inspection_status = lambda *a, **k: None
    ic.ensure_next_rolling_schedule = _roll
    try:
        asyncio.run(ic.record_inspection_results("INS", {"results": results}, {"id": "U"}))
    finally:
        (ic.get_supabase, ic._ensure_inspection_own, ic.record_safe_result_batch,
         ic.complete_inspection_status, ic.ensure_next_rolling_schedule) = orig
    return helper_spy, db


def test_r15_abnormal_helper_not_called():
    spy, db = _w3_call([{"result": "ABNORMAL"}])
    assert spy == []
    ws_updates = [p for (t, op, p, _) in db.log if t == "work_schedules" and op == "update"]
    assert ws_updates == []


def test_r16_hold_helper_not_called():
    spy, _db = _w3_call([{"result": "HOLD"}])
    assert spy == []


def test_r17_replay_normal_helper_called():
    spy, db = _w3_call([{"result": "NORMAL"}, {"result": "ok"}], mode="REPLAY")
    assert len(spy) == 1
    assert spy[0][0] == "WS-1"
    ws_updates = [p for (t, op, p, _) in db.log if t == "work_schedules" and op == "update"]
    assert ws_updates and ws_updates[0]["completed_at"] == date.today().isoformat()


def test_r18_obj01_base_update_delete_0():
    rolling_src = open(
        os.path.join(os.path.dirname(__file__), "..", "services", "inspection_rolling.py"),
        encoding="utf-8",
    ).read()
    assert "safety_inspections" not in rolling_src
    assert "safety_inspection_results" not in rolling_src
    assert "inspection_record_journal" not in rolling_src
    assert ".delete(" not in rolling_src

    db = _seed(MemDB())
    ensure_next_rolling_schedule(db, "WS-1", date(2026, 1, 20))
    base_ops = [(t, op) for (t, op, _p, _f) in db.log if t in ("safety_inspections", "safety_inspection_results")]
    assert base_ops == []
    deletes = [op for (_t, op, _p, _f) in db.log if op == "delete"]
    assert deletes == []

    chk = open(
        os.path.join(os.path.dirname(__file__), "..", "routers", "inspection_checklist.py"),
        encoding="utf-8",
    ).read()
    assert "record_safe_result_batch" in chk
    assert "CREATE TABLE" not in chk and "ALTER TABLE" not in rolling_src
