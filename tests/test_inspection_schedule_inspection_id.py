"""OBJ-05 CLOSEOUT-01 — GET /inspection/schedules/{factory_id} inspection_id additive."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import routers.inspection_checklist as R


class _Resp:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class _Q:
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self._in = {}
        self._eq = {}
        self._select = None
        self.action = "select"

    def select(self, *a, **k):
        self._select = a[0] if a else None
        self.action = "select"
        return self

    def insert(self, *a, **k):
        raise AssertionError("schedule list must not INSERT")

    def update(self, *a, **k):
        raise AssertionError("schedule list must not UPDATE")

    def delete(self, *a, **k):
        raise AssertionError("schedule list must not DELETE")

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def in_(self, col, vals):
        self._in[col] = list(vals)
        return self

    def gte(self, *a, **k):
        return self

    def lte(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def execute(self):
        self.client.calls.append({
            "name": self.name,
            "action": self.action,
            "select": self._select,
            "eq": dict(self._eq),
            "in_": dict(self._in),
        })
        if self.name == "work_schedules":
            return _Resp(data=self.client.ws_rows, count=len(self.client.ws_rows))
        if self.name == "safety_inspections":
            ids = set(self._in.get("assignment_id") or [])
            factory = self._eq.get("factory_id")
            rows = []
            for rec in self.client.insp_rows:
                if rec.get("assignment_id") not in ids:
                    continue
                if factory is not None and rec.get("factory_id") != factory:
                    continue
                rows.append({"id": rec["id"], "assignment_id": rec["assignment_id"]})
            return _Resp(data=rows)
        return _Resp(data=[])


class _SB:
    def __init__(self, ws_rows, insp_rows):
        self.ws_rows = ws_rows
        self.insp_rows = insp_rows
        self.calls = []

    def table(self, name):
        return _Q(self, name)


def test_zero_inspections_null():
    items = [{"id": "ws-1", "planned_date": "2026-08-01"}]
    sb = _SB([], [])
    R.attach_schedule_inspection_ids(sb, items, "f1")
    assert items[0]["inspection_id"] is None
    assert items[0]["planned_date"] == "2026-08-01"


def test_one_inspection_exact():
    items = [{"id": "ws-1"}, {"id": "ws-2"}]
    sb = _SB([], [
        {"id": "ins-A", "assignment_id": "ws-1", "factory_id": "f1"},
        {"id": "ins-B", "assignment_id": "ws-2", "factory_id": "f1"},
    ])
    R.attach_schedule_inspection_ids(sb, items, "f1")
    assert items[0]["inspection_id"] == "ins-A"
    assert items[1]["inspection_id"] == "ins-B"
    insp_calls = [c for c in sb.calls if c["name"] == "safety_inspections"]
    assert len(insp_calls) == 1
    assert set(insp_calls[0]["in_"]["assignment_id"]) == {"ws-1", "ws-2"}
    assert insp_calls[0]["eq"]["factory_id"] == "f1"
    assert insp_calls[0]["select"] == "id,assignment_id"


def test_dup_cardinality_409():
    items = [{"id": "ws-1"}]
    sb = _SB([], [
        {"id": "ins-A", "assignment_id": "ws-1", "factory_id": "f1"},
        {"id": "ins-B", "assignment_id": "ws-1", "factory_id": "f1"},
    ])
    with pytest.raises(HTTPException) as ei:
        R.attach_schedule_inspection_ids(sb, items, "f1")
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "INSPECTION_CARDINALITY_VIOLATION"


def test_n_plus_one_zero_many_rows():
    items = [{"id": f"ws-{i}"} for i in range(20)]
    insp = [{"id": f"ins-{i}", "assignment_id": f"ws-{i}", "factory_id": "f1"} for i in range(20)]
    sb = _SB([], insp)
    R.attach_schedule_inspection_ids(sb, items, "f1")
    insp_calls = [c for c in sb.calls if c["name"] == "safety_inspections"]
    assert len(insp_calls) == 1
    assert items[7]["inspection_id"] == "ins-7"


def test_empty_page_skips_query():
    items = []
    sb = _SB([], [{"id": "x", "assignment_id": "ws-1", "factory_id": "f1"}])
    R.attach_schedule_inspection_ids(sb, items, "f1")
    assert sb.calls == []


def test_other_factory_not_attached():
    items = [{"id": "ws-1"}]
    sb = _SB([], [
        {"id": "ins-other", "assignment_id": "ws-1", "factory_id": "f-OTHER"},
    ])
    R.attach_schedule_inspection_ids(sb, items, "f1")
    assert items[0]["inspection_id"] is None


def test_existing_fields_preserved():
    items = [{"id": "ws-1", "law_name": "산안법", "inspection_set_name": "월간"}]
    sb = _SB([], [{"id": "ins-A", "assignment_id": "ws-1", "factory_id": "f1"}])
    R.attach_schedule_inspection_ids(sb, items, "f1")
    assert items[0]["law_name"] == "산안법"
    assert items[0]["inspection_set_name"] == "월간"
    assert items[0]["inspection_id"] == "ins-A"


def test_list_schedules_handler_additive(monkeypatch):
    ws_rows = [{
        "id": "ws-1",
        "planned_date": "2026-08-01",
        "status_code": "completed",
        "inspection_sets": {
            "inspection_set_name": "월간점검",
            "law_name": "산안법",
            "law_article": "21",
            "cycle_unit": "month",
            "cycle_value": 1,
        },
    }]
    sb = _SB(ws_rows, [
        {"id": "ins-A", "assignment_id": "ws-1", "factory_id": "f1"},
    ])
    monkeypatch.setattr(R, "get_supabase", lambda: sb)
    monkeypatch.setattr(R, "_ensure_factory_own", lambda *a, **k: None)
    out = asyncio.run(R.list_schedules(
        "f1", month=None, status_code=None, page=1, page_size=20, current={"id": "u"}
    ))
    item = out["data"]["items"][0]
    assert item["inspection_id"] == "ins-A"
    assert item["inspection_set_name"] == "월간점검"
    assert item["law_name"] == "산안법"
    assert item["id"] == "ws-1"
    assert "inspection_sets" not in item
    insp_calls = [c for c in sb.calls if c["name"] == "safety_inspections"]
    assert len(insp_calls) == 1
    assert not any(c["action"] == "update" for c in sb.calls)


def test_list_schedules_dup_409(monkeypatch):
    ws_rows = [{"id": "ws-1", "inspection_sets": {}}]
    sb = _SB(ws_rows, [
        {"id": "ins-A", "assignment_id": "ws-1", "factory_id": "f1"},
        {"id": "ins-B", "assignment_id": "ws-1", "factory_id": "f1"},
    ])
    monkeypatch.setattr(R, "get_supabase", lambda: sb)
    monkeypatch.setattr(R, "_ensure_factory_own", lambda *a, **k: None)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(R.list_schedules(
            "f1", month=None, status_code=None, page=1, page_size=20, current={"id": "u"}
        ))
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "INSPECTION_CARDINALITY_VIOLATION"
    assert not any(c.get("action") == "update" for c in sb.calls)
