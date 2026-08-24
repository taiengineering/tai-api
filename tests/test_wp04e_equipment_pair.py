"""WP-DATA-ARCH-04E equipment_checkins pair fail-closed — mock supabase only, no real DB."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import routers.equipment_checkins as mod
from routers.equipment_checkins import EquipmentCheckinCreate

ASSET_ID = "asset-1"
SCHED_ID = "sched-1"
FACTORY_A = "factory-A"
FACTORY_B = "factory-B"


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
            if q._table == "equipment_checkins":
                return _Exec([{"id": "checkin-1", "checkin_at": "2026-08-24T00:00:00+00:00"}])
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
        equipment_asset_id=ASSET_ID,
        overall_result="OK",
        worker_name="작업자",
    )
    defaults.update(kw)
    return EquipmentCheckinCreate(**defaults)


def _run(monkeypatch, sb: FakeSB, body: EquipmentCheckinCreate, notify_calls=None):
    monkeypatch.setattr(mod, "get_supabase", lambda: sb)
    if notify_calls is not None:
        def _capture(*_a, **_k):
            notify_calls.append({"args": _a, "kwargs": _k})
        monkeypatch.setattr(mod, "_notify_abnormal_checkin", _capture)
    return asyncio.run(mod.submit_checkin(body))


def _ec_inserts(sb: FakeSB):
    return [c for c in sb.inserts if c["table"] == "equipment_checkins"]


def _ws_updates(sb: FakeSB):
    return [c for c in sb.updates if c["table"] == "work_schedules"]


def _notif_inserts(sb: FakeSB):
    return [c for c in sb.inserts if c["table"] == "notifications"]


def test_t1_standalone_insert_asset_factory(monkeypatch):
    sb = FakeSB({
        "equipment_assets": [{"id": ASSET_ID, "asset_name": "펌프", "factory_id": FACTORY_A}],
        "factories": [{"id": FACTORY_A, "company_id": "C1"}],
    })
    out = _run(monkeypatch, sb, _body())
    assert out["status"] == "success"
    ins = _ec_inserts(sb)
    assert len(ins) == 1
    assert ins[0]["payload"]["factory_id"] == FACTORY_A
    assert "schedule_id" not in ins[0]["payload"]


def test_t2_matching_pair_inserts_schedule_and_asset_factory(monkeypatch):
    sb = FakeSB({
        "equipment_assets": [{"id": ASSET_ID, "asset_name": "펌프", "factory_id": FACTORY_A}],
        "factories": [{"id": FACTORY_A, "company_id": "C1"}],
        "work_schedules": [{"id": SCHED_ID, "factory_id": FACTORY_A}],
    })
    out = _run(monkeypatch, sb, _body(schedule_id=SCHED_ID))
    assert out["status"] == "success"
    ins = _ec_inserts(sb)
    assert len(ins) == 1
    assert ins[0]["payload"]["factory_id"] == FACTORY_A
    assert ins[0]["payload"]["schedule_id"] == SCHED_ID


def test_t3_missing_schedule_409_no_insert(monkeypatch):
    sb = FakeSB({
        "equipment_assets": [{"id": ASSET_ID, "asset_name": "펌프", "factory_id": FACTORY_A}],
        "factories": [{"id": FACTORY_A, "company_id": "C1"}],
        "work_schedules": [],
    })
    with pytest.raises(HTTPException) as ei:
        _run(monkeypatch, sb, _body(schedule_id=SCHED_ID))
    assert ei.value.status_code == 409
    assert _ec_inserts(sb) == []


def test_t4_schedule_factory_null_409_no_insert(monkeypatch):
    sb = FakeSB({
        "equipment_assets": [{"id": ASSET_ID, "asset_name": "펌프", "factory_id": FACTORY_A}],
        "factories": [{"id": FACTORY_A, "company_id": "C1"}],
        "work_schedules": [{"id": SCHED_ID, "factory_id": None}],
    })
    with pytest.raises(HTTPException) as ei:
        _run(monkeypatch, sb, _body(schedule_id=SCHED_ID))
    assert ei.value.status_code == 409
    assert _ec_inserts(sb) == []


def test_t5_asset_factory_null_409_no_insert(monkeypatch):
    sb = FakeSB({
        "equipment_assets": [{"id": ASSET_ID, "asset_name": "펌프", "factory_id": None}],
        "work_schedules": [{"id": SCHED_ID, "factory_id": FACTORY_A}],
    })
    with pytest.raises(HTTPException) as ei:
        _run(monkeypatch, sb, _body(schedule_id=SCHED_ID))
    assert ei.value.status_code == 409
    assert _ec_inserts(sb) == []


def test_t6_cross_factory_409_no_side_effects(monkeypatch):
    notify_calls = []
    sb = FakeSB({
        "equipment_assets": [{"id": ASSET_ID, "asset_name": "펌프", "factory_id": FACTORY_A}],
        "factories": [{"id": FACTORY_A, "company_id": "C1"}],
        "work_schedules": [{"id": SCHED_ID, "factory_id": FACTORY_B}],
    })
    with pytest.raises(HTTPException) as ei:
        _run(monkeypatch, sb, _body(schedule_id=SCHED_ID, overall_result="NG"), notify_calls=notify_calls)
    assert ei.value.status_code == 409
    assert _ec_inserts(sb) == []
    assert _ws_updates(sb) == []
    assert _notif_inserts(sb) == []
    assert notify_calls == []


def test_t7_invalid_overall_result_422(monkeypatch):
    sb = FakeSB()
    with pytest.raises(HTTPException) as ei:
        _run(monkeypatch, sb, _body(overall_result="BAD"))
    assert ei.value.status_code == 422
    assert _ec_inserts(sb) == []


def test_t8_missing_worker_422(monkeypatch):
    sb = FakeSB()
    with pytest.raises(HTTPException) as ei:
        _run(monkeypatch, sb, _body(worker_id=None, worker_name=None))
    assert ei.value.status_code == 422
    assert _ec_inserts(sb) == []


def test_t9_ok_matching_pair_updates_schedule_done(monkeypatch):
    sb = FakeSB({
        "equipment_assets": [{"id": ASSET_ID, "asset_name": "펌프", "factory_id": FACTORY_A}],
        "factories": [{"id": FACTORY_A, "company_id": "C1"}],
        "work_schedules": [{"id": SCHED_ID, "factory_id": FACTORY_A}],
    })
    _run(monkeypatch, sb, _body(schedule_id=SCHED_ID, overall_result="OK"))
    assert len(_ec_inserts(sb)) == 1
    ups = _ws_updates(sb)
    assert len(ups) == 1
    assert ups[0]["payload"] == {"status_code": "DONE"}
    assert ups[0]["eq"] == {"id": SCHED_ID}


def test_t10_ng_with_factory_notifies(monkeypatch):
    notify_calls = []
    sb = FakeSB({
        "equipment_assets": [{"id": ASSET_ID, "asset_name": "펌프", "factory_id": FACTORY_A}],
        "factories": [{"id": FACTORY_A, "company_id": "C1"}],
        "work_schedules": [{"id": SCHED_ID, "factory_id": FACTORY_A}],
    })
    _run(
        monkeypatch,
        sb,
        _body(schedule_id=SCHED_ID, overall_result="NG"),
        notify_calls=notify_calls,
    )
    assert len(_ec_inserts(sb)) == 1
    assert len(notify_calls) == 1
    assert notify_calls[0]["kwargs"]["overall_result"] == "NG"
    assert notify_calls[0]["kwargs"]["factory_id"] == FACTORY_A
