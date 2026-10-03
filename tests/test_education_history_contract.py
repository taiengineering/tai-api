"""PATCH-001 contract tests — education_history DB column alignment.

T1: summary endpoint fetches status_code (not status)
T2: list endpoint nested select uses education_group + required_hours
T3: status filter converts API "pending" → DB "PENDING"
T4: create endpoint writes status_code=COMPLETED and completed_at (not status/completed_date)
T5: pending create writes status_code=PENDING and completed_at=None
T6: _map_history_row converts DB fields → API fields
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import routers.education as edu_mod
from routers.auth import get_current_user

FAC = "fac-t1"
USER_ID = "11111111-0000-4000-8000-000000000001"
CALLER = {"id": USER_ID, "company_id": "co-own", "factory_id": FAC, "role_code": "011", "team_id": None}
TODAY = date.today().isoformat()


# ── FakeSB ────────────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else len(data)


class _Q:
    def __init__(self, sb, name):
        self.sb = sb
        self.name = name
        self._eq = []
        self._in = []
        self._select = "*"
        self._op = "select"
        self._row = None
        self._range_args = None
        self._limit_n = None
        self._order_args = None
        self._count = None
        self._single = False

    def select(self, cols="*", count=None, **kw):
        self._op = "select"
        self._select = cols
        self._count = count
        return self

    def eq(self, col, val):
        self._eq.append((col, val))
        return self

    def in_(self, col, vals):
        self._in.append((col, list(vals)))
        return self

    def order(self, col, desc=False):
        self._order_args = (col, desc)
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def range(self, start, end):
        self._range_args = (start, end)
        return self

    def insert(self, row):
        self._op = "insert"
        self._row = row
        return self

    def update(self, payload):
        self._op = "update"
        self._row = payload
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    def _match(self, row):
        for col, val in self._eq:
            if row.get(col) != val:
                return False
        for col, vals in self._in:
            if row.get(col) not in vals:
                return False
        return True

    def execute(self):
        table = self.sb.tables.setdefault(self.name, [])
        if self._op == "insert":
            items = self._row if isinstance(self._row, list) else [self._row]
            out = []
            for row in items:
                r = dict(row)
                r.setdefault("id", str(uuid.uuid4()))
                table.append(r)
                self.sb.inserts.append({"table": self.name, "row": dict(r)})
                out.append(dict(r))
            return _Resp(out)
        if self._op == "update":
            updated = []
            for row in table:
                if self._match(row):
                    row.update(self._row)
                    updated.append(dict(row))
            return _Resp(updated)
        rows = [dict(r) for r in table if self._match(r)]
        if self._order_args:
            col, desc = self._order_args
            rows.sort(key=lambda r: r.get(col) or "", reverse=desc)
        total = len(rows)
        if self._range_args:
            s, e = self._range_args
            rows = rows[s : e + 1]
        elif self._limit_n:
            rows = rows[: self._limit_n]
        if self._single:
            return _Resp(rows[0] if rows else None, count=min(total, 1))
        return _Resp(rows, count=total)


class FakeSB:
    def __init__(self):
        self.tables: dict = {}
        self.inserts: list = []

    def table(self, name):
        return _Q(self, name)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_app(fake_sb: FakeSB) -> TestClient:
    app = FastAPI()
    app.include_router(edu_mod.router)
    app.dependency_overrides[get_current_user] = lambda: CALLER
    app.dependency_overrides[edu_mod.get_supabase] = lambda: fake_sb
    return TestClient(app, raise_server_exceptions=True)


def _seed_factory(fake_sb: FakeSB):
    """Seed factory row so _ensure_factory_own passes."""
    fake_sb.tables.setdefault("factories", []).append({"id": FAC, "company_id": "co-own"})


# ── T1: summary uses status_code ──────────────────────────────────────────────

def test_t1_summary_uses_status_code():
    """Summary endpoint must query status_code and count correctly."""
    fake_sb = FakeSB()
    _seed_factory(fake_sb)
    fake_sb.tables["education_history"] = [
        {"id": "h1", "factory_id": FAC, "status_code": "COMPLETED"},
        {"id": "h2", "factory_id": FAC, "status_code": "PENDING"},
        {"id": "h3", "factory_id": FAC, "status_code": "OVERDUE"},
    ]
    client = _make_app(fake_sb)
    r = client.get(f"/education-history/summary?factory_id={FAC}", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["total"] == 3
    assert d["completed"] == 1
    assert d["pending"] == 1
    assert d["overdue"] == 1


# ── T2: list nested select uses education_group + required_hours ───────────────

def test_t2_list_nested_select_columns():
    """List endpoint select string must reference education_group and required_hours."""
    import inspect
    src = inspect.getsource(edu_mod.get_education_history)
    assert "education_group" in src, "education_group missing from list nested select"
    assert "required_hours" in src, "required_hours missing from list nested select"
    assert "category," not in src.split("education_master(")[1].split(")")[0], \
        "stale 'category' still in education_master nested select"
    assert "min_hours," not in src.split("education_master(")[1].split(")")[0], \
        "stale 'min_hours' still in education_master nested select"


# ── T3: status filter converts API → DB ───────────────────────────────────────

def test_t3_status_filter_converts_to_uppercase():
    """?status=pending must filter on status_code=PENDING (uppercase)."""
    fake_sb = FakeSB()
    _seed_factory(fake_sb)
    fake_sb.tables["education_history"] = [
        {"id": "h1", "factory_id": FAC, "status_code": "PENDING", "due_date": TODAY},
        {"id": "h2", "factory_id": FAC, "status_code": "COMPLETED", "due_date": TODAY},
    ]
    client = _make_app(fake_sb)
    r = client.get(f"/education-history?factory_id={FAC}&status=pending", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["status"] == "pending"   # mapped back by _map_history_row


# ── T4: create writes status_code=COMPLETED and completed_at ─────────────────

def test_t4_create_writes_status_code_and_completed_at():
    """POST /education-history must insert status_code=COMPLETED and completed_at."""
    fake_sb = FakeSB()
    _seed_factory(fake_sb)
    fake_sb.tables["education_master"] = [
        {"id": "m1", "education_code": "SAFETY-001", "education_name": "안전교육", "required_hours": 2}
    ]
    client = _make_app(fake_sb)
    body = {
        "factory_id": FAC,
        "user_id": USER_ID,
        "education_code": "SAFETY-001",
        "completed_date": TODAY,
        "completed_hours": 4,
        "due_date": TODAY,
    }
    r = client.post("/education-history", json=body, headers={"Authorization": "Bearer x"})
    assert r.status_code == 200, r.text
    inserted = fake_sb.inserts[-1]["row"]
    assert "status" not in inserted, "stale 'status' column must not be written to DB"
    assert inserted.get("status_code") == "COMPLETED"
    assert "completed_date" not in inserted, "stale 'completed_date' column must not be written to DB"
    assert inserted.get("completed_at") == TODAY


# ── T5: pending create writes status_code=PENDING and completed_at=None ──────

def test_t5_pending_create_writes_status_code_pending():
    """POST /education-history/pending must insert status_code=PENDING and completed_at=None."""
    fake_sb = FakeSB()
    _seed_factory(fake_sb)
    fake_sb.tables["education_master"] = [
        {"id": "m1", "education_code": "SAFETY-001", "education_name": "안전교육"}
    ]
    client = _make_app(fake_sb)
    body = {
        "factory_id": FAC,
        "user_id": USER_ID,
        "education_code": "SAFETY-001",
        "due_date": TODAY,
    }
    r = client.post("/education-history/pending", json=body, headers={"Authorization": "Bearer x"})
    assert r.status_code == 200, r.text
    inserted = fake_sb.inserts[-1]["row"]
    assert "status" not in inserted, "stale 'status' column must not be written to DB"
    assert inserted.get("status_code") == "PENDING"
    assert "completed_date" not in inserted, "stale 'completed_date' column must not be written to DB"
    assert inserted.get("completed_at") is None


# ── T6: _map_history_row converts DB → API ────────────────────────────────────

def test_t6_map_history_row_conversion():
    """_map_history_row must rename DB columns to legacy API field names."""
    db_row = {
        "id": "h1",
        "status_code": "COMPLETED",
        "completed_at": TODAY,
        "institution": "한국산업안전보건공단",
        "method": "집합교육",
        "location": "서울",
        "education_master": {
            "required_hours": 8,
            "education_group": "근로자 안전보건교육",
        },
    }
    out = edu_mod._map_history_row(db_row)
    assert "status_code" not in out
    assert out["status"] == "completed"
    assert "completed_at" not in out
    assert out["completed_date"] == TODAY
    assert "institution" not in out
    assert out["institution_name"] == "한국산업안전보건공단"
    assert "method" not in out
    assert out["education_method"] == "집합교육"
    assert "location" not in out
    assert out["education_place"] == "서울"
    m = out["education_master"]
    assert "required_hours" not in m
    assert m["min_hours"] == 8
    assert "education_group" not in m
    assert m["category"] == "worker_safety"

# ── C1-C5: education_group (Korean) ↔ API category canonical mapping ──────────

def test_c1_근로자안전보건교육_maps_to_worker_safety():
    assert edu_mod._education_group_db_to_api("근로자 안전보건교육") == "worker_safety"


def test_c2_직무교육_maps_to_duty():
    assert edu_mod._education_group_db_to_api("직무교육") == "duty"


def test_c3_양성교육_maps_to_duty():
    assert edu_mod._education_group_db_to_api("양성교육") == "duty"


def test_c4_category_worker_safety_filters_correct_group():
    """GET ?category=worker_safety must only return '근로자 안전보건교육' rows."""
    fake_sb = FakeSB()
    _seed_factory(fake_sb)
    fake_sb.tables["education_master"] = [
        {"id": "m1", "education_code": "WS-001", "education_group": "근로자 안전보건교육", "is_active": True, "education_name": "안전보건교육"},
        {"id": "m2", "education_code": "DU-001", "education_group": "직무교육", "is_active": True, "education_name": "직무교육"},
    ]
    fake_sb.tables["education_history"] = [
        {"id": "h1", "factory_id": FAC, "education_code": "WS-001", "status_code": "PENDING", "due_date": TODAY},
        {"id": "h2", "factory_id": FAC, "education_code": "DU-001", "status_code": "PENDING", "due_date": TODAY},
    ]
    client = _make_app(fake_sb)
    r = client.get(f"/education-history?factory_id={FAC}&category=worker_safety", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    codes = [i["education_code"] for i in items]
    assert "WS-001" in codes
    assert "DU-001" not in codes


def test_c5_category_duty_filters_두가지_group():
    """GET ?category=duty must return '직무교육' and '양성교육' rows but not '근로자 안전보건교육'."""
    fake_sb = FakeSB()
    _seed_factory(fake_sb)
    fake_sb.tables["education_master"] = [
        {"id": "m1", "education_code": "WS-001", "education_group": "근로자 안전보건교육", "is_active": True, "education_name": "안전보건교육"},
        {"id": "m2", "education_code": "DU-001", "education_group": "직무교육", "is_active": True, "education_name": "직무교육"},
        {"id": "m3", "education_code": "TR-001", "education_group": "양성교육", "is_active": True, "education_name": "양성교육"},
    ]
    fake_sb.tables["education_history"] = [
        {"id": "h1", "factory_id": FAC, "education_code": "WS-001", "status_code": "PENDING", "due_date": TODAY},
        {"id": "h2", "factory_id": FAC, "education_code": "DU-001", "status_code": "PENDING", "due_date": TODAY},
        {"id": "h3", "factory_id": FAC, "education_code": "TR-001", "status_code": "PENDING", "due_date": TODAY},
    ]
    client = _make_app(fake_sb)
    r = client.get(f"/education-history?factory_id={FAC}&category=duty", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    codes = [i["education_code"] for i in items]
    assert "DU-001" in codes
    assert "TR-001" in codes
    assert "WS-001" not in codes
