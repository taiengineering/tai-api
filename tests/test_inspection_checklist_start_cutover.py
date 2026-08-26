"""OBJ-01 KNOT-3C1 — SAFE start router cutover tests (T15-T22).

start_inspection() 이 직접 work_schedules UPDATE / safety_inspections INSERT 대신
원자적 서비스(start_safe_inspection)를 1회 호출하고, 응답 계약과 auth/ownership 이
보존됨을 검증한다. get_supabase 는 직접 write 를 트랩하는 FakeSupabase 로,
start_safe_inspection 은 호출 인자를 포착하는 스텁으로 monkeypatch 한다.
"""
from __future__ import annotations

import asyncio

import pytest

from fastapi import HTTPException

from routers import inspection_checklist as ic
from services.inspection_record_start import SafeStartError


class _Q:
    def __init__(self, tbl, forbidden):
        self.tbl = tbl
        self.forbidden = forbidden
        self._f = {}

    def select(self, *a, **k):
        return self

    def eq(self, k, v):
        self._f[k] = v
        return self

    def limit(self, n):
        return self

    def update(self, payload):
        self.forbidden.append((self.tbl, "update", payload))
        return self

    def insert(self, payload):
        self.forbidden.append((self.tbl, "insert", payload))
        return self

    def execute(self):
        class R:
            pass
        r = R()
        # start_inspection 의 parent factory PRE-READ 만 데이터가 필요하다.
        if self.tbl == "work_schedules":
            r.data = [{"factory_id": "FCT-1"}]
        else:
            r.data = []
        return r


class FakeSupabase:
    def __init__(self, forbidden):
        self.forbidden = forbidden

    def table(self, name):
        return _Q(name, self.forbidden)


@pytest.fixture
def wired(monkeypatch):
    state = {"forbidden": [], "calls": [], "next": None, "raise": None}

    monkeypatch.setattr(ic, "get_supabase", lambda: FakeSupabase(state["forbidden"]))
    # ownership 가드는 호출 여부만 확인(부작용 없음)
    state["own_called"] = []
    monkeypatch.setattr(ic, "_ensure_ws_own",
                        lambda sb, wsid, cur: state["own_called"].append(wsid))

    def fake_start(sb, **kw):
        state["calls"].append(kw)
        if state["raise"] is not None:
            raise state["raise"]
        return state["next"]

    monkeypatch.setattr(ic, "start_safe_inspection", fake_start)
    return state


def _snap(iid="INS-1", replayed=False, status="IN_PROGRESS"):
    return {"data": {"inspection_id": iid, "work_schedule_id": "WS-1", "factory_id": "FCT-1",
                     "inspection_status": status, "started_at": "2026-08-27", "inspector_name": "홍길동"},
            "replayed": replayed}


def _run(coro):
    return asyncio.run(coro)


def _start(body=None):
    return _run(ic.start_inspection("WS-1", body=body or {"inspector_name": "홍길동"}, current={"id": "U-1"}))


# T15/T16 — no direct safety_inspections INSERT, no direct work_schedule status UPDATE
def test_no_direct_base_insert_no_schedule_update(wired):
    wired["next"] = _snap()
    _start()
    inserts = [f for f in wired["forbidden"] if f[1] == "insert"]
    updates = [f for f in wired["forbidden"] if f[1] == "update"]
    assert inserts == []      # safety_inspections 직접 INSERT 0
    assert updates == []      # work_schedules 직접 status UPDATE 0


# T17 — service call exactly once, with trusted parent factory + started_at
def test_service_called_once_with_parent_factory(wired):
    wired["next"] = _snap()
    _start({"inspector_name": "김점검", "started_at": "2026-08-27"})
    assert len(wired["calls"]) == 1
    c = wired["calls"][0]
    assert c["schedule_id"] == "WS-1"
    assert c["factory_id"] == "FCT-1"          # parent companion(신뢰), body 아님
    assert c["started_at"] == "2026-08-27"
    assert c["inspector_name"] == "김점검"


# T18 — existing inspection replay → response carries existing id, no second create
def test_replay_returns_existing_id_no_second_create(wired):
    wired["next"] = _snap(iid="INS-EXIST", replayed=True)
    r = _start()
    assert r["data"]["inspection_id"] == "INS-EXIST"
    assert [f for f in wired["forbidden"] if f[1] == "insert"] == []
    assert len(wired["calls"]) == 1            # 서비스 1회, 두 번째 생성 경로 없음


# T19 — WORK_SCHEDULE_NOT_FOUND → 404
def test_not_found_maps_to_404(wired):
    wired["raise"] = SafeStartError("WORK_SCHEDULE_NOT_FOUND")
    with pytest.raises(HTTPException) as ei:
        _start()
    assert ei.value.status_code == 404


# T20 — INSPECTION_CARDINALITY_VIOLATION → 409
def test_cardinality_maps_to_409(wired):
    wired["raise"] = SafeStartError("INSPECTION_CARDINALITY_VIOLATION")
    with pytest.raises(HTTPException) as ei:
        _start()
    assert ei.value.status_code == 409


# T21 — auth/ownership guard still invoked before writer
def test_ownership_guard_invoked(wired):
    wired["next"] = _snap()
    _start()
    assert wired["own_called"] == ["WS-1"]


# T22 — existing response contract preserved
def test_response_contract_preserved(wired):
    wired["next"] = _snap(iid="INS-9")
    r = _start({"inspector_name": "홍길동", "started_at": "2026-08-27"})
    d = r["data"]
    assert r["status"] == "success"
    assert d["work_schedule_id"] == "WS-1"
    assert d["inspection_id"] == "INS-9"
    assert d["inspector_name"] == "홍길동"
    assert d["started_at"] == "2026-08-27"
