"""WP-DATA-ARCH-04D W1/W2 writer targeted tests — mock supabase only, no real DB."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import routers.inspection_checklist as w2
import routers.worker_check as w1
from routers.worker_check import CheckItem, CheckSubmitBody

FID = "factory-parent-1"
SID = "schedule-1"
AID = "assignment-1"
PHONE = "01012345678"
INSPECTOR = "user-inspector-1"
OTHER_FID = "factory-spoof-99"


class _Exec:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table):
        self._c = client
        self._table = table
        self._op = "select"
        self._payload = None
        self._eq = {}

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def limit(self, _n):
        return self

    def execute(self):
        return self._c._execute(self)


class FakeSB:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.inserts = []
        self.updates = []

    def table(self, name):
        return _Query(self, name)

    def _execute(self, q: _Query):
        if q._op == "insert":
            self.inserts.append({"table": q._table, "payload": q._payload})
            if q._table == "safety_inspections":
                return _Exec([{"id": "insp-1"}])
            return _Exec([])
        if q._op == "update":
            self.updates.append({"table": q._table, "payload": q._payload, "eq": dict(q._eq)})
            return _Exec([{"ok": True}])
        rows = list(self.rows.get(q._table, []))
        for col, val in q._eq.items():
            rows = [r for r in rows if r.get(col) == val]
        return _Exec(rows)


def _body(**kw):
    defaults = dict(
        phone=PHONE,
        items=[CheckItem(name="외관", result="ok")],
    )
    defaults.update(kw)
    return CheckSubmitBody(**defaults)


def _run_w1(monkeypatch, sb: FakeSB, body: CheckSubmitBody):
    monkeypatch.setattr(w1, "get_supabase", lambda: sb)
    monkeypatch.setattr(w1._iss, "resolve_set_id_for_assignment", lambda *_a, **_k: None)
    return w1.submit_check(body)


def _si_inserts(sb: FakeSB):
    return [c for c in sb.inserts if c["table"] == "safety_inspections"]


def _ws_updates(sb: FakeSB):
    return [c for c in sb.updates if c["table"] == "work_schedules"]


# ── W1 submit_check ───────────────────────────────────────────────

def test_t1_schedule_id_insert_factory_id_equals_parent(monkeypatch):
    sb = FakeSB({
        "users": [{"id": INSPECTOR, "name": "Kim", "phone": PHONE}],
        "work_schedules": [{"id": SID, "factory_id": FID}],
    })
    _run_w1(monkeypatch, sb, _body(schedule_id=SID))
    ins = _si_inserts(sb)
    assert len(ins) == 1
    assert ins[0]["payload"]["factory_id"] == FID
    assert ins[0]["payload"]["assignment_id"] == SID


def test_t2_assignment_id_resolves_to_parent_factory(monkeypatch):
    sb = FakeSB({
        "users": [{"id": INSPECTOR, "name": "Kim", "phone": PHONE}],
        "work_assignments": [{"id": AID, "schedule_id": SID}],
        "work_schedules": [{"id": SID, "factory_id": FID}],
    })
    _run_w1(monkeypatch, sb, _body(assignment_id=AID))
    ins = _si_inserts(sb)
    assert len(ins) == 1
    assert ins[0]["payload"]["factory_id"] == FID
    assert ins[0]["payload"]["assignment_id"] == SID


def test_t3_missing_parent_schedule_409_no_insert(monkeypatch):
    sb = FakeSB({
        "users": [{"id": INSPECTOR, "name": "Kim", "phone": PHONE}],
        "work_schedules": [],
    })
    with pytest.raises(HTTPException) as ei:
        _run_w1(monkeypatch, sb, _body(schedule_id=SID))
    assert ei.value.status_code == 409
    assert _si_inserts(sb) == []


def test_t4_parent_factory_null_409_no_insert(monkeypatch):
    sb = FakeSB({
        "users": [{"id": INSPECTOR, "name": "Kim", "phone": PHONE}],
        "work_schedules": [{"id": SID, "factory_id": None}],
    })
    with pytest.raises(HTTPException) as ei:
        _run_w1(monkeypatch, sb, _body(schedule_id=SID))
    assert ei.value.status_code == 409
    assert _si_inserts(sb) == []


def test_t5_body_factory_id_ignored_parent_used(monkeypatch):
    sb = FakeSB({
        "users": [{"id": INSPECTOR, "name": "Kim", "phone": PHONE}],
        "work_schedules": [{"id": SID, "factory_id": FID}],
    })
    _run_w1(monkeypatch, sb, _body(schedule_id=SID, factory_id=OTHER_FID))
    ins = _si_inserts(sb)
    assert len(ins) == 1
    assert ins[0]["payload"]["factory_id"] == FID
    assert ins[0]["payload"]["factory_id"] != OTHER_FID


def test_t6_no_schedule_or_assignment_409_no_standalone(monkeypatch):
    sb = FakeSB({
        "users": [{"id": INSPECTOR, "name": "Kim", "phone": PHONE}],
    })
    with pytest.raises(HTTPException) as ei:
        _run_w1(monkeypatch, sb, _body())
    assert ei.value.status_code == 409
    assert _si_inserts(sb) == []


# ── W2 start_inspection ───────────────────────────────────────────

def _current_all():
    return {"id": "u-admin", "role_code": "001", "company_id": "C1"}


def _current_company():
    return {"id": "u-co", "role_code": "012", "company_id": "C1"}


def _run_w2(monkeypatch, sb: FakeSB, ws_id=SID, body=None, current=None):
    monkeypatch.setattr(w2, "get_supabase", lambda: sb)
    return asyncio.run(w2.start_inspection(ws_id, body or {}, current or _current_all()))


def test_t7_start_insert_assignment_and_parent_factory(monkeypatch):
    sb = FakeSB({
        "role_data_scope": [{"role_code": "001", "scope_type": "ALL"}],
        "work_schedules": [{"id": SID, "company_id": "C1", "factory_id": FID}],
    })
    out = _run_w2(monkeypatch, sb)
    assert out["status"] == "success"
    ins = _si_inserts(sb)
    assert len(ins) == 1
    assert ins[0]["payload"]["assignment_id"] == SID
    assert ins[0]["payload"]["factory_id"] == FID


def test_t8_parent_factory_null_409_no_side_effects(monkeypatch):
    sb = FakeSB({
        "role_data_scope": [{"role_code": "001", "scope_type": "ALL"}],
        "work_schedules": [{"id": SID, "company_id": "C1", "factory_id": None}],
    })
    with pytest.raises(HTTPException) as ei:
        _run_w2(monkeypatch, sb)
    assert ei.value.status_code == 409
    assert _ws_updates(sb) == []
    assert _si_inserts(sb) == []


def test_t9_foreign_company_ws_404_no_regression(monkeypatch):
    sb = FakeSB({
        "role_data_scope": [{"role_code": "012", "scope_type": "COMPANY"}],
        "work_schedules": [{"id": SID, "company_id": "C2", "factory_id": FID}],
    })
    with pytest.raises(HTTPException) as ei:
        _run_w2(monkeypatch, sb, current=_current_company())
    assert ei.value.status_code == 404
    assert _ws_updates(sb) == []
    assert _si_inserts(sb) == []


def test_t10_start_status_in_progress_no_regression(monkeypatch):
    sb = FakeSB({
        "role_data_scope": [{"role_code": "001", "scope_type": "ALL"}],
        "work_schedules": [{"id": SID, "company_id": "C1", "factory_id": FID}],
    })
    out = _run_w2(monkeypatch, sb, body={"inspector_name": "Park"})
    assert out["status"] == "success"
    ups = _ws_updates(sb)
    assert len(ups) == 1
    assert ups[0]["payload"]["status_code"] == "in_progress"
    assert ups[0]["payload"]["inspector_name"] == "Park"
    assert ups[0]["eq"] == {"id": SID}
