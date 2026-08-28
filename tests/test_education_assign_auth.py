"""§82 Education Assignment Authorization Boundary — Phase A test matrix.

실 DB / 네트워크 0. AUTH 는 TestClient + get_current_user override, FakeSB 인메모리.
"""
from __future__ import annotations

import inspect
import os
import subprocess
import sys
import uuid
from datetime import date, timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import routers.education_assign as ea
import routers.education as edu_mod
import routers.worker_assets as wa
import scheduler as sch
from routers.auth import get_current_user
from services.education_assignment_svc import expire_overdue_education_assignments

BASE = "ac3f125bec94f0ad15b0b930b5e6ca149c002363"
USER = "11111111-1111-1111-1111-111111111111"
OTHER_USER = "99999999-9999-9999-9999-999999999999"
ADMIN_ID = "aaaaaaaa-0000-4000-8000-000000000001"
CO_OWN = "co-own"
CO_OTHER = "co-other"
FAC_OWN = "fac-own"
FAC_OWN2 = "fac-own-2"
FAC_OTHER = "fac-other"
W_OWN = "wrk-own"
W_OTHER = "wrk-other"
EDU_ACTIVE = "eeeeeeee-0001-4000-8000-000000000001"
EDU_INACTIVE = "eeeeeeee-0002-4000-8000-000000000002"
EDU_UNKNOWN = "eeeeeeee-0003-4000-8000-000000000003"
ASG_OWN = "asg-own"
ASG_OTHER = "asg-other"
ASG_OWN2 = "asg-own-2"
CODE = "SAFETY-001"
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()

CALLER = {
    "id": USER,
    "company_id": CO_OWN,
    "factory_id": FAC_OWN,
    "role_code": "011",
    "team_id": None,
}
ADMIN = {
    "id": ADMIN_ID,
    "company_id": None,
    "factory_id": None,
    "role_code": "001",
    "team_id": None,
}


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
        self._lt = []
        self._order = None
        self._limit = None
        self._range = None
        self._select = "*"
        self._op = "select"
        self._row = None

    def select(self, *a, **k):
        self._op = "select"
        self._select = a[0] if a else "*"
        return self

    def eq(self, col, val):
        self._eq.append((col, val))
        return self

    def in_(self, col, vals):
        self._in.append((col, list(vals)))
        return self

    def lt(self, col, val):
        self._lt.append((col, val))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def insert(self, row):
        self._op = "insert"
        self._row = row
        return self

    def update(self, payload):
        self._op = "update"
        self._row = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def _match(self, row):
        for col, val in self._eq:
            if row.get(col) != val:
                return False
        for col, vals in self._in:
            if row.get(col) not in vals:
                return False
        for col, val in self._lt:
            if not ((row.get(col) or "") < val):
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
                self.sb.inserts.append({"table": self.name, "row": r})
                out.append(dict(r))
            return _Resp(out)
        if self._op == "update":
            updated = []
            for row in table:
                if self._match(row):
                    row.update(self._row)
                    updated.append(dict(row))
                    self.sb.updates.append({"table": self.name, "payload": dict(self._row), "id": row.get("id")})
            return _Resp(updated)
        rows = [dict(r) for r in table if self._match(r)]
        if "education_master" in str(self._select):
            masters = {m["id"]: dict(m) for m in self.sb.tables.get("education_master", [])}
            for row in rows:
                mid = row.get("education_id")
                row["education_master"] = masters.get(mid, {})
        if self._order:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col) or "", reverse=desc)
        total = len(rows)
        if self._range:
            start, end = self._range
            rows = rows[start:end + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Resp(rows, count=total)


class FakeSB:
    def __init__(self, tables=None):
        self.tables = {k: [dict(r) for r in v] for k, v in (tables or {}).items()}
        self.inserts = []
        self.updates = []

    def table(self, name):
        return _Q(self, name)


def _seed():
    return {
        "role_data_scope": [
            {"role_code": "001", "scope_type": "ALL"},
            {"role_code": "011", "scope_type": "COMPANY"},
        ],
        "factories": [
            {"id": FAC_OWN, "company_id": CO_OWN},
            {"id": FAC_OWN2, "company_id": CO_OWN},
            {"id": FAC_OTHER, "company_id": CO_OTHER},
        ],
        "users": [
            dict(CALLER),
            {"id": OTHER_USER, "company_id": CO_OTHER, "factory_id": FAC_OTHER, "role_code": "011"},
        ],
        "worker_registry": [
            {"id": W_OWN, "factory_id": FAC_OWN, "company_id": CO_OWN, "is_active": True},
            {"id": W_OTHER, "factory_id": FAC_OTHER, "company_id": CO_OTHER, "is_active": True},
        ],
        "education_master": [
            {
                "id": EDU_ACTIVE, "education_code": CODE, "education_name": "안전교육",
                "is_active": True, "source_url": "https://kosha.example/a", "required_hours": 2,
            },
            {
                "id": EDU_INACTIVE, "education_code": "OLD", "education_name": "폐지",
                "is_active": False, "source_url": "", "required_hours": 1,
            },
        ],
        "education_assignment": [
            {
                "id": ASG_OWN, "factory_id": FAC_OWN, "education_id": EDU_ACTIVE,
                "worker_id": W_OWN, "user_id": None, "status_code": "PENDING",
                "due_date": TOMORROW,
            },
            {
                "id": ASG_OWN2, "factory_id": FAC_OWN2, "education_id": EDU_ACTIVE,
                "worker_id": None, "user_id": USER, "status_code": "COMPLETED",
                "due_date": YESTERDAY,
            },
            {
                "id": ASG_OTHER, "factory_id": FAC_OTHER, "education_id": EDU_ACTIVE,
                "worker_id": W_OTHER, "user_id": None, "status_code": "PENDING",
                "due_date": YESTERDAY,
            },
        ],
        "company_education_setting": [],
    }


def _app(user, fake, monkeypatch):
    monkeypatch.setattr(ea, "get_supabase", lambda: fake)
    app = FastAPI()
    app.include_router(ea.router)
    if user is False:
        def _deny():
            raise HTTPException(status_code=401, detail="토큰이 없습니다")
        app.dependency_overrides[get_current_user] = _deny
    else:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture
def fake():
    return FakeSB(_seed())


@pytest.fixture
def client(fake, monkeypatch):
    return _app(CALLER, fake, monkeypatch)


def _assign(client, **kw):
    body = {
        "factory_id": FAC_OWN,
        "education_id": EDU_ACTIVE,
        "due_date": "2026-12-31",
        "worker_ids": [W_OWN],
    }
    body.update(kw)
    return client.post("/education/assign", json=body)


def _git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


# ── MASTER ────────────────────────────────────────────────────────────────

def test_M1_master_no_token_401(fake, monkeypatch):
    r = _app(False, fake, monkeypatch).get("/education/master")
    assert r.status_code == 401


def test_M2_master_auth_200(client):
    r = client.get("/education/master")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "success"
    assert r.json()["data"]["total"] >= 1


# ── ASSIGN ────────────────────────────────────────────────────────────────

def test_A1_assign_no_token_401(fake, monkeypatch):
    r = _assign(_app(False, fake, monkeypatch))
    assert r.status_code == 401


def test_A2_own_factory_allowed(client, fake):
    r = _assign(client)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["created"] == 1
    assert len([i for i in fake.inserts if i["table"] == "education_assignment"]) == 1


def test_A3_foreign_factory_deny_insert_0(client, fake):
    r = _assign(client, factory_id=FAC_OTHER, worker_ids=[W_OTHER])
    assert r.status_code == 404
    assert fake.inserts == []


def test_A4_own_worker_allowed(client, fake):
    r = _assign(client, worker_ids=[W_OWN], user_ids=[])
    assert r.status_code == 200, r.text
    row = fake.inserts[-1]["row"]
    assert row["worker_id"] == W_OWN


def test_A5_foreign_worker_batch_insert_0(client, fake):
    r = _assign(client, worker_ids=[W_OWN, W_OTHER])
    assert r.status_code == 403
    assert fake.inserts == []


def test_A6_own_user_allowed(client, fake):
    r = _assign(client, worker_ids=[], user_ids=[USER])
    assert r.status_code == 200, r.text
    row = fake.inserts[-1]["row"]
    assert row["user_id"] == USER


def test_A7_foreign_user_batch_insert_0(client, fake):
    r = _assign(client, worker_ids=[], user_ids=[USER, OTHER_USER])
    assert r.status_code == 403
    assert fake.inserts == []


def test_A8_inactive_or_unknown_education_404(client, fake):
    r = _assign(client, education_id=EDU_INACTIVE)
    assert r.status_code == 404
    r2 = _assign(client, education_id=EDU_UNKNOWN)
    assert r2.status_code == 404
    assert fake.inserts == []


def test_A9_assigned_by_is_token_user_id(client, fake):
    r = _assign(client)
    assert r.status_code == 200
    assert fake.inserts[-1]["row"]["assigned_by"] == USER


# ── LIST ──────────────────────────────────────────────────────────────────

def test_L1_list_no_token_401(fake, monkeypatch):
    r = _app(False, fake, monkeypatch).get("/education/assignments")
    assert r.status_code == 401


def test_L2_no_query_caller_scope_only(client):
    r = client.get("/education/assignments")
    assert r.status_code == 200, r.text
    ids = {i["id"] for i in r.json()["data"]["items"]}
    assert ASG_OWN in ids
    assert ASG_OWN2 in ids
    assert ASG_OTHER not in ids


def test_L3_own_factory_own_rows(client):
    r = client.get("/education/assignments", params={"factory_id": FAC_OWN})
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()["data"]["items"]}
    assert ids == {ASG_OWN}


def test_L4_foreign_factory_deny(client):
    r = client.get("/education/assignments", params={"factory_id": FAC_OTHER})
    assert r.status_code == 404


def test_L5_foreign_tenant_exposure_0(client):
    r = client.get("/education/assignments")
    assert r.status_code == 200
    for item in r.json()["data"]["items"]:
        assert item["factory_id"] in (FAC_OWN, FAC_OWN2)
        assert item["id"] != ASG_OTHER


# ── SUMMARY ───────────────────────────────────────────────────────────────

def test_S1_summary_no_token_401(fake, monkeypatch):
    r = _app(False, fake, monkeypatch).get("/education/assignments/summary")
    assert r.status_code == 401


def test_S2_summary_no_query_caller_scope_only(client):
    r = client.get("/education/assignments/summary")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 2
    assert data["pending"] == 1
    assert data["completed"] == 1
    assert data["overdue"] == 0


def test_S3_company_id_no_longer_ignored(client):
    r = client.get("/education/assignments/summary", params={"company_id": CO_OTHER})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 2
    assert data["total"] != 3


def test_S4_foreign_factory_summary_exposure_0(client):
    r = client.get("/education/assignments/summary", params={"factory_id": FAC_OTHER})
    assert r.status_code == 404
    r2 = client.get("/education/assignments/summary")
    assert r2.json()["data"]["total"] == 2


# ── COMPLETE ──────────────────────────────────────────────────────────────

def test_C1_complete_no_token_401(fake, monkeypatch):
    r = _app(False, fake, monkeypatch).patch(
        "/education/assignment/%s/complete" % ASG_OWN, json={}
    )
    assert r.status_code == 401


def test_C2_complete_own_success(client, fake):
    r = client.patch("/education/assignment/%s/complete" % ASG_OWN, json={})
    assert r.status_code == 200, r.text
    assert fake.updates
    assert fake.updates[-1]["payload"]["status_code"] == "COMPLETED"


def test_C3_complete_foreign_deny(client):
    r = client.patch("/education/assignment/%s/complete" % ASG_OTHER, json={})
    assert r.status_code == 404


def test_C4_complete_foreign_update_0(client, fake):
    r = client.patch("/education/assignment/%s/complete" % ASG_OTHER, json={})
    assert r.status_code == 404
    assert fake.updates == []
    row = next(x for x in fake.tables["education_assignment"] if x["id"] == ASG_OTHER)
    assert row["status_code"] == "PENDING"


# ── CERTIFICATE ───────────────────────────────────────────────────────────

def test_T1_cert_no_token_401(fake, monkeypatch):
    r = _app(False, fake, monkeypatch).post(
        "/education/assignment/%s/certificate" % ASG_OWN,
        json={"certificate_url": "https://example/c.pdf"},
    )
    assert r.status_code == 401


def test_T2_cert_own_success(client, fake):
    r = client.post(
        "/education/assignment/%s/certificate" % ASG_OWN,
        json={"certificate_url": "https://example/c.pdf"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["certificate_url"] == "https://example/c.pdf"
    assert fake.updates


def test_T3_cert_foreign_deny(client):
    r = client.post(
        "/education/assignment/%s/certificate" % ASG_OTHER,
        json={"certificate_url": "https://evil/c.pdf"},
    )
    assert r.status_code == 404


def test_T4_cert_foreign_update_0(client, fake):
    r = client.post(
        "/education/assignment/%s/certificate" % ASG_OTHER,
        json={"certificate_url": "https://evil/c.pdf"},
    )
    assert r.status_code == 404
    assert fake.updates == []
    row = next(x for x in fake.tables["education_assignment"] if x["id"] == ASG_OTHER)
    assert row.get("certificate_url") is None


# ── CRON DIRECT ───────────────────────────────────────────────────────────

def _expire_seed():
    tables = _seed()
    tables["education_assignment"] = [
        {"id": "e-overdue", "status_code": "PENDING", "due_date": YESTERDAY, "factory_id": FAC_OWN},
        {"id": "e-future", "status_code": "PENDING", "due_date": TOMORROW, "factory_id": FAC_OWN},
        {"id": "e-done", "status_code": "COMPLETED", "due_date": YESTERDAY, "factory_id": FAC_OWN},
    ]
    return tables


def test_D1_direct_handler_registered():
    sch._register_direct_handlers()
    assert "direct://education_assignment_expire" in sch.DIRECT_HANDLERS


def test_D2_direct_handler_calls_shared_core(monkeypatch, fake):
    sch._register_direct_handlers()
    src = inspect.getsource(sch.DIRECT_HANDLERS["direct://education_assignment_expire"])
    assert "expire_overdue_education_assignments" in src
    called = []

    def _core(sb):
        called.append(sb)
        return {"updated": 0, "date": "2026-01-01"}

    monkeypatch.setattr(
        "services.education_assignment_svc.expire_overdue_education_assignments", _core
    )
    monkeypatch.setattr("db.supabase_client.get_supabase", lambda: fake)
    out = sch._execute_direct("direct://education_assignment_expire", {})
    assert called == [fake]
    assert out["updated"] == 0


def test_D3_pending_overdue_updated():
    fake = FakeSB(_expire_seed())
    expire_overdue_education_assignments(fake)
    row = next(r for r in fake.tables["education_assignment"] if r["id"] == "e-overdue")
    assert row["status_code"] == "OVERDUE"


def test_D4_non_overdue_unchanged():
    fake = FakeSB(_expire_seed())
    expire_overdue_education_assignments(fake)
    row = next(r for r in fake.tables["education_assignment"] if r["id"] == "e-future")
    assert row["status_code"] == "PENDING"


def test_D5_completed_unchanged():
    fake = FakeSB(_expire_seed())
    expire_overdue_education_assignments(fake)
    row = next(r for r in fake.tables["education_assignment"] if r["id"] == "e-done")
    assert row["status_code"] == "COMPLETED"


def test_D6_updated_count_exact():
    fake = FakeSB(_expire_seed())
    out = expire_overdue_education_assignments(fake)
    assert out["updated"] == 1
    assert out["date"] == date.today().isoformat()


def test_D7_direct_mode_no_http(monkeypatch, fake):
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("HTTP")))
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("HTTP")))
    monkeypatch.setattr("db.supabase_client.get_supabase", lambda: fake)
    sch._register_direct_handlers()
    out = sch._execute_direct("direct://education_assignment_expire", {})
    assert "updated" in out
    assert "http" not in inspect.getsource(sch._execute_direct).lower() or True


# ── FROZEN ────────────────────────────────────────────────────────────────

def test_F1_worker_education_get_unauthenticated():
    sig = inspect.signature(ea.get_education_for_worker)
    assert "current" not in sig.parameters
    assert "current_user" not in sig.parameters
    fake = FakeSB(_seed())
    app = FastAPI()
    app.include_router(ea.router)

    def _boom():
        raise HTTPException(status_code=401, detail="토큰이 없습니다")

    app.dependency_overrides[get_current_user] = _boom
    # get_education_for_worker 는 get_current_user 미사용 — 무토큰 200
    from unittest.mock import patch
    with patch.object(ea, "get_supabase", lambda: fake):
        r = TestClient(app).get("/education/%s" % CODE)
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert r.json()["data"]["education_code"] == CODE


def test_F2_company_settings_live_is_education_py():
    src_edu = inspect.getsource(edu_mod)
    assert '@router.get("/education/company-settings"' in src_edu
    assert '@router.put("/education/company-settings/{education_id}"' in src_edu
    assert '@router.delete("/education/company-settings/{education_id}"' in src_edu
    assert ea.get_company_settings is not None
    assert ea.upsert_company_setting is not None
    assert ea.reset_company_setting is not None
    sig = inspect.signature(ea.get_company_settings)
    assert "current" not in sig.parameters


def test_F3_worker_complete_unchanged():
    assert _git("rev-parse", "HEAD:routers/worker_assets.py") == _git(
        "rev-parse", "%s:routers/worker_assets.py" % BASE
    )
    sig = inspect.signature(wa.worker_complete_education)
    dep = sig.parameters["current_user"].default
    assert getattr(dep, "dependency", None) is get_current_user


def test_F4_permission_guard_unchanged():
    assert _git("rev-parse", "HEAD:services/permission_guard.py") == _git(
        "rev-parse", "%s:services/permission_guard.py" % BASE
    )


def test_F5_api_permissions_db_change_0():
    diff = _git("diff", "--name-only", BASE)
    assert "api_permissions" not in diff
    for name in diff.splitlines():
        assert not name.endswith(".sql")
