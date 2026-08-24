"""WP-DATA-ARCH-04C W2/W3 writer targeted tests — mock supabase only, no real DB."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import routers.legal_engine_patch as w2
from routers.work_schedules import _apply_one_update
from services.status_vocab import wa_write_ready


FID = "factory-parent-1"
SID = "schedule-1"
UID = "user-manager-1"
AID = "assignment-1"
NOW = "2026-08-24T00:00:00+00:00"


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
        self._in = {}

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

    def is_(self, _col, _val):
        return self

    def in_(self, col, vals):
        self._in[col] = list(vals)
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
            return _Exec([])
        if q._op == "update":
            self.updates.append({"table": q._table, "payload": q._payload, "eq": dict(q._eq)})
            return _Exec([{"ok": True}])
        rows = list(self.rows.get(q._table, []))
        for col, val in q._eq.items():
            rows = [r for r in rows if r.get(col) == val]
        for col, vals in q._in.items():
            rows = [r for r in rows if r.get(col) in vals]
        return _Exec(rows)


def _sched(**kw):
    row = {
        "id": SID,
        "factory_id": FID,
        "company_id": "company-1",
        "planned_date": "2026-08-24",
        "rule_code": "R1",
        "description": "d",
        "obligation_type": "INSPECT",
        "status_code": "PENDING",
        "active_yn": True,
        "assigned_user_id": None,
    }
    row.update(kw)
    return row


def _user():
    return {"id": UID, "factory_id": FID, "role_code": "003", "is_active": True}


def _run_w2(monkeypatch, sb: FakeSB):
    monkeypatch.setattr(w2, "get_supabase", lambda: sb)
    return w2.auto_assign_schedules(factory_id=None)


# ── W2 auto_assign_schedules ──────────────────────────────────────

def test_t1_empty_schedules_success(monkeypatch):
    sb = FakeSB({"work_schedules": []})
    out = _run_w2(monkeypatch, sb)
    assert out["status"] == "success"
    assert out["data"]["assigned"] == 0
    assert sb.inserts == []
    assert sb.updates == []


def test_t2_null_factory_id_http_409(monkeypatch):
    sb = FakeSB({"work_schedules": [_sched(factory_id=None)]})
    with pytest.raises(HTTPException) as ei:
        _run_w2(monkeypatch, sb)
    assert ei.value.status_code == 409
    assert "factory_id" in ei.value.detail


def test_t3_null_factory_id_no_assignment_insert(monkeypatch):
    sb = FakeSB({"work_schedules": [_sched(factory_id=None)]})
    with pytest.raises(HTTPException):
        _run_w2(monkeypatch, sb)
    assert [c for c in sb.inserts if c["table"] == "work_assignments"] == []


def test_t4_null_factory_id_no_schedule_update(monkeypatch):
    sb = FakeSB({"work_schedules": [_sched(factory_id=None)]})
    with pytest.raises(HTTPException):
        _run_w2(monkeypatch, sb)
    assert [c for c in sb.updates if c["table"] == "work_schedules"] == []


def test_t5_happy_insert_factory_id_equals_parent(monkeypatch):
    sb = FakeSB({
        "work_schedules": [_sched()],
        "users": [_user()],
    })
    out = _run_w2(monkeypatch, sb)
    assert out["status"] == "success"
    assert out["data"]["assigned"] == 1
    wa_inserts = [c for c in sb.inserts if c["table"] == "work_assignments"]
    assert len(wa_inserts) == 1
    payload = wa_inserts[0]["payload"]
    assert isinstance(payload, list) and len(payload) == 1
    assert payload[0]["factory_id"] == FID
    assert payload[0]["schedule_id"] == SID


# ── W3 _apply_one_update ──────────────────────────────────────────

def test_t6_parent_factory_null_http_409():
    sb = FakeSB({"work_schedules": [{"id": SID, "factory_id": None}]})
    with pytest.raises(HTTPException) as ei:
        _apply_one_update(sb, SID, {"assigned_user_id": UID}, NOW)
    assert ei.value.status_code == 409
    assert "factory_id" in ei.value.detail


def test_t7_parent_factory_null_no_schedule_update():
    sb = FakeSB({"work_schedules": [{"id": SID, "factory_id": None}]})
    with pytest.raises(HTTPException):
        _apply_one_update(sb, SID, {"assigned_user_id": UID}, NOW)
    assert [c for c in sb.updates if c["table"] == "work_schedules"] == []


def test_t8_parent_factory_null_no_assignment_write():
    sb = FakeSB({"work_schedules": [{"id": SID, "factory_id": None}]})
    with pytest.raises(HTTPException):
        _apply_one_update(sb, SID, {"assigned_user_id": UID}, NOW)
    assert [c for c in sb.inserts if c["table"] == "work_assignments"] == []
    assert [c for c in sb.updates if c["table"] == "work_assignments"] == []


def test_t9_new_assignment_factory_id_equals_parent():
    sb = FakeSB({
        "work_schedules": [{"id": SID, "factory_id": FID}],
        "work_assignments": [],
    })
    updated = _apply_one_update(sb, SID, {"assigned_user_id": UID}, NOW)
    assert updated is True
    wa_inserts = [c for c in sb.inserts if c["table"] == "work_assignments"]
    assert len(wa_inserts) == 1
    assert wa_inserts[0]["payload"]["factory_id"] == FID
    assert wa_inserts[0]["payload"]["status_code"] == wa_write_ready()


def test_t10_existing_assignment_update_path_no_factory_change():
    sb = FakeSB({
        "work_schedules": [{"id": SID, "factory_id": FID}],
        "work_assignments": [{"id": AID, "schedule_id": SID, "status_code": "READY"}],
    })
    updated = _apply_one_update(sb, SID, {"assigned_user_id": UID}, NOW)
    assert updated is True
    assert sb.inserts == []
    wa_updates = [c for c in sb.updates if c["table"] == "work_assignments"]
    assert len(wa_updates) == 1
    assert wa_updates[0]["payload"] == {"assigned_user_id": UID, "updated_at": NOW}
    assert "factory_id" not in wa_updates[0]["payload"]
    assert wa_updates[0]["eq"] == {"id": AID}


def test_t11_unassign_cancelled_path_no_regression():
    sb = FakeSB({
        "work_schedules": [{"id": SID, "factory_id": FID}],
        "work_assignments": [{"id": AID, "schedule_id": SID, "status_code": "READY"}],
    })
    updated = _apply_one_update(sb, SID, {"assigned_user_id": None}, NOW)
    assert updated is True
    assert sb.inserts == []
    wa_updates = [c for c in sb.updates if c["table"] == "work_assignments"]
    assert len(wa_updates) == 1
    assert wa_updates[0]["payload"] == {"status_code": "CANCELLED", "updated_at": NOW}
    assert "factory_id" not in wa_updates[0]["payload"]
    ws_updates = [c for c in sb.updates if c["table"] == "work_schedules"]
    assert len(ws_updates) == 1
    assert ws_updates[0]["payload"]["assigned_user_id"] is None
