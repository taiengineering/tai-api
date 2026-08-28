"""§83 Cron Manager Authorization Boundary — platform ALL-only /cron/*.

실 DB / 네트워크 0. AUTH 는 TestClient + get_current_user override, FakeSB 인메모리.
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import routers.cron_manager as cm
from routers.auth import get_current_user

ADMIN_ID = "aaaaaaaa-0000-4000-8000-000000000001"
USER_ID = "11111111-1111-1111-1111-111111111111"
ADMIN = {"id": ADMIN_ID, "email": "admin@taieng.co.kr", "role_code": "001", "company_id": None}
NONALL = {"id": USER_ID, "email": "user@co.com", "role_code": "011", "company_id": "co-own"}
CREATE_BODY = {
    "job_code": "JOB_NEW",
    "job_name": "new job",
    "category": "ops",
    "endpoint_url": "/internal/x",
    "cron_expression": "0 1 * * *",
    "schedule_desc": "daily",
}
SENSITIVE = {"cron_job_master", "cron_job_log", "cron_schedule_config"}


class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        if count is not None:
            self.count = count
        elif isinstance(data, list):
            self.count = len(data)
        else:
            self.count = 1 if data else 0


class _Q:
    def __init__(self, sb, name):
        self.sb = sb
        self.name = name
        self._eq = []
        self._gte = []
        self._order = None
        self._limit = None
        self._single = False
        self._op = "select"
        self._row = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._eq.append((col, val))
        return self

    def gte(self, col, val):
        self._gte.append((col, val))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        self._single = True
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
        for col, val in self._gte:
            if not ((row.get(col) or "") >= val):
                return False
        return True

    def execute(self):
        self.sb.table_ops.append((self._op, self.name))
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
                    self.sb.updates.append({"table": self.name, "id": row.get("id")})
            return _Resp(updated)
        if self._op == "delete":
            kept, removed = [], []
            for row in table:
                if self._match(row):
                    removed.append(dict(row))
                    self.sb.deletes.append({"table": self.name, "id": row.get("id")})
                else:
                    kept.append(row)
            self.sb.tables[self.name] = kept
            return _Resp(removed)
        rows = [dict(r) for r in table if self._match(r)]
        if self._order:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col) or "", reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._single:
            return _Resp(rows[0] if rows else None)
        return _Resp(rows)


class FakeSB:
    def __init__(self, tables=None):
        self.tables = {k: [dict(r) for r in v] for k, v in (tables or {}).items()}
        self.inserts = []
        self.updates = []
        self.deletes = []
        self.table_ops = []

    def table(self, name):
        return _Q(self, name)


class FakeSched:
    def __init__(self, spies):
        self.running = False
        self.spies = spies
        self._jobs = [type("J", (), {"id": "aps-1", "next_run_time": None})()]

    def start(self):
        self.spies["start"].append("start")
        self.running = True

    def get_jobs(self):
        return list(self._jobs)


class _HttpResp:
    status_code = 200

    def json(self):
        return {"ok": True}


def _seed():
    return {
        "role_data_scope": [
            {"role_code": "001", "scope_type": "ALL"},
            {"role_code": "011", "scope_type": "COMPANY"},
        ],
        "cron_job_master": [
            {
                "id": "jid-http", "job_code": "JOB_HTTP", "job_name": "http",
                "endpoint_url": "/internal/tick", "http_method": "POST",
                "is_system": False, "is_active": True,
                "request_payload": {}, "timeout_seconds": 5, "category": "ops",
            },
            {
                "id": "jid-direct", "job_code": "JOB_DIRECT", "job_name": "direct",
                "endpoint_url": "direct://education_assignment_expire", "http_method": "POST",
                "is_system": False, "is_active": True,
                "request_payload": {}, "timeout_seconds": 5, "category": "ops",
            },
            {
                "id": "jid-sys", "job_code": "JOB_SYS", "job_name": "sys",
                "endpoint_url": "direct://integrity_evaluate", "http_method": "POST",
                "is_system": True, "is_active": True,
                "request_payload": {}, "timeout_seconds": 5, "category": "sys",
            },
        ],
        "cron_job_log": [],
        "cron_schedule_config": [],
    }


def _app(user, fake, monkeypatch, spies=None):
    spies = spies if spies is not None else {"direct": [], "http": [], "load": [], "start": []}
    sched = FakeSched(spies)
    monkeypatch.setattr(cm, "get_supabase", lambda: fake)
    monkeypatch.setattr("scheduler.load_jobs_from_db", lambda: spies["load"].append("load") or None)
    monkeypatch.setattr("scheduler.scheduler", sched)
    monkeypatch.setattr("scheduler._execute_direct", lambda url, payload: spies["direct"].append((url, payload)) or {"ok": True})

    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: spies["http"].append(("post", a, k)) or _HttpResp())
    monkeypatch.setattr(requests, "get", lambda *a, **k: spies["http"].append(("get", a, k)) or _HttpResp())

    app = FastAPI()
    app.include_router(cm.router)
    if user is False:
        def _deny():
            raise HTTPException(status_code=401, detail="토큰이 없습니다")
        app.dependency_overrides[get_current_user] = _deny
    else:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), spies, sched


@pytest.fixture
def fake():
    return FakeSB(_seed())


def _idle(fake, spies):
    assert fake.inserts == []
    assert fake.updates == []
    assert fake.deletes == []
    assert spies["direct"] == []
    assert spies["http"] == []
    assert spies["load"] == []
    assert spies["start"] == []
    assert not any(name in SENSITIVE for op, name in fake.table_ops)


# ── GET /cron/jobs ────────────────────────────────────────────────────────

def test_J1_list_no_token_401(fake, monkeypatch):
    client, spies, _ = _app(False, fake, monkeypatch)
    r = client.get("/cron/jobs")
    assert r.status_code == 401
    _idle(fake, spies)


def test_J2_list_non_all_403(fake, monkeypatch):
    client, spies, _ = _app(NONALL, fake, monkeypatch)
    r = client.get("/cron/jobs")
    assert r.status_code == 403
    _idle(fake, spies)


def test_J3_list_all_200(fake, monkeypatch):
    client, spies, _ = _app(ADMIN, fake, monkeypatch)
    r = client.get("/cron/jobs")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "success"
    assert len(r.json()["data"]) == 3
    assert spies["direct"] == []


# ── GET /cron/jobs/{job_code} ─────────────────────────────────────────────

def test_D1_detail_no_token_401(fake, monkeypatch):
    client, spies, _ = _app(False, fake, monkeypatch)
    r = client.get("/cron/jobs/JOB_HTTP")
    assert r.status_code == 401
    _idle(fake, spies)


def test_D2_detail_non_all_403(fake, monkeypatch):
    client, spies, _ = _app(NONALL, fake, monkeypatch)
    r = client.get("/cron/jobs/JOB_HTTP")
    assert r.status_code == 403
    _idle(fake, spies)


def test_D3_detail_all_200(fake, monkeypatch):
    client, _, _ = _app(ADMIN, fake, monkeypatch)
    r = client.get("/cron/jobs/JOB_HTTP")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["job_code"] == "JOB_HTTP"


# ── POST /cron/jobs ───────────────────────────────────────────────────────

def test_C1_create_no_token_401(fake, monkeypatch):
    client, spies, _ = _app(False, fake, monkeypatch)
    r = client.post("/cron/jobs", json=CREATE_BODY)
    assert r.status_code == 401
    _idle(fake, spies)


def test_C2_create_non_all_403_insert_0(fake, monkeypatch):
    client, spies, _ = _app(NONALL, fake, monkeypatch)
    r = client.post("/cron/jobs", json=CREATE_BODY)
    assert r.status_code == 403
    _idle(fake, spies)


def test_C3_create_all_inserts(fake, monkeypatch):
    client, spies, _ = _app(ADMIN, fake, monkeypatch)
    r = client.post("/cron/jobs", json=CREATE_BODY)
    assert r.status_code == 200, r.text
    assert any(i["table"] == "cron_job_master" for i in fake.inserts)
    assert spies["load"] == ["load"]


# ── PATCH /cron/jobs/{job_code} ───────────────────────────────────────────

def test_P1_patch_no_token_401(fake, monkeypatch):
    client, spies, _ = _app(False, fake, monkeypatch)
    r = client.patch("/cron/jobs/JOB_HTTP", json={"job_name": "x"})
    assert r.status_code == 401
    _idle(fake, spies)


def test_P2_patch_non_all_403_update_0(fake, monkeypatch):
    client, spies, _ = _app(NONALL, fake, monkeypatch)
    r = client.patch("/cron/jobs/JOB_HTTP", json={"job_name": "x"})
    assert r.status_code == 403
    _idle(fake, spies)


def test_P3_patch_all_updates(fake, monkeypatch):
    client, spies, _ = _app(ADMIN, fake, monkeypatch)
    r = client.patch("/cron/jobs/JOB_HTTP", json={"job_name": "renamed"})
    assert r.status_code == 200, r.text
    assert fake.updates
    assert spies["load"] == ["load"]


# ── DELETE ────────────────────────────────────────────────────────────────

def test_X1_delete_no_token_401(fake, monkeypatch):
    client, spies, _ = _app(False, fake, monkeypatch)
    r = client.delete("/cron/jobs/JOB_HTTP")
    assert r.status_code == 401
    _idle(fake, spies)


def test_X2_delete_non_all_403_delete_0(fake, monkeypatch):
    client, spies, _ = _app(NONALL, fake, monkeypatch)
    r = client.delete("/cron/jobs/JOB_HTTP")
    assert r.status_code == 403
    _idle(fake, spies)


def test_X3_delete_all_non_system(fake, monkeypatch):
    client, _, _ = _app(ADMIN, fake, monkeypatch)
    r = client.delete("/cron/jobs/JOB_HTTP")
    assert r.status_code == 200, r.text
    assert any(d["table"] == "cron_job_master" for d in fake.deletes)
    codes = [j["job_code"] for j in fake.tables["cron_job_master"]]
    assert "JOB_HTTP" not in codes


def test_X4_delete_all_system_403(fake, monkeypatch):
    client, spies, _ = _app(ADMIN, fake, monkeypatch)
    r = client.delete("/cron/jobs/JOB_SYS")
    assert r.status_code == 403
    assert fake.deletes == []
    assert spies["direct"] == []
    codes = [j["job_code"] for j in fake.tables["cron_job_master"]]
    assert "JOB_SYS" in codes


# ── RUN ───────────────────────────────────────────────────────────────────

def test_R1_run_no_token_401(fake, monkeypatch):
    client, spies, _ = _app(False, fake, monkeypatch)
    r = client.post("/cron/jobs/JOB_DIRECT/run")
    assert r.status_code == 401
    _idle(fake, spies)
    assert not any(i["table"] == "cron_job_log" for i in fake.inserts)


def test_R2_run_non_all_403(fake, monkeypatch):
    client, spies, _ = _app(NONALL, fake, monkeypatch)
    r = client.post("/cron/jobs/JOB_DIRECT/run")
    assert r.status_code == 403
    _idle(fake, spies)


def test_R3_run_all_direct_path(fake, monkeypatch):
    client, spies, _ = _app(ADMIN, fake, monkeypatch)
    r = client.post("/cron/jobs/JOB_DIRECT/run")
    assert r.status_code == 200, r.text
    assert spies["direct"]
    assert spies["direct"][0][0] == "direct://education_assignment_expire"
    assert spies["http"] == []
    assert any(i["table"] == "cron_job_log" for i in fake.inserts)


def test_R4_run_all_http_path(fake, monkeypatch):
    client, spies, _ = _app(ADMIN, fake, monkeypatch)
    r = client.post("/cron/jobs/JOB_HTTP/run")
    assert r.status_code == 200, r.text
    assert spies["http"]
    assert spies["direct"] == []
    assert r.json()["http_status"] == 200


def test_R5_audit_identity_email_or_id(fake, monkeypatch):
    client, _, _ = _app(ADMIN, fake, monkeypatch)
    r = client.post("/cron/jobs/JOB_DIRECT/run")
    assert r.status_code == 200
    log = [i["row"] for i in fake.inserts if i["table"] == "cron_job_log"][0]
    assert log["triggered_by"] == "MANUAL"
    assert log["triggered_by_user"] == "admin@taieng.co.kr"

    fake2 = FakeSB(_seed())
    no_email = {"id": ADMIN_ID, "role_code": "001"}
    client2, _, _ = _app(no_email, fake2, monkeypatch)
    r2 = client2.post("/cron/jobs/JOB_DIRECT/run")
    assert r2.status_code == 200
    log2 = [i["row"] for i in fake2.inserts if i["table"] == "cron_job_log"][0]
    assert log2["triggered_by_user"] == ADMIN_ID


def test_R6_client_user_email_ignored(fake, monkeypatch):
    client, _, _ = _app(ADMIN, fake, monkeypatch)
    r = client.post("/cron/jobs/JOB_DIRECT/run", params={"user_email": "evil@x.com"})
    assert r.status_code == 200, r.text
    log = [i["row"] for i in fake.inserts if i["table"] == "cron_job_log"][0]
    assert log["triggered_by_user"] == "admin@taieng.co.kr"
    assert log["triggered_by_user"] != "evil@x.com"


# ── RELOAD ────────────────────────────────────────────────────────────────

def test_RL1_reload_no_token_401(fake, monkeypatch):
    client, spies, _ = _app(False, fake, monkeypatch)
    r = client.post("/cron/reload")
    assert r.status_code == 401
    _idle(fake, spies)


def test_RL2_reload_non_all_403(fake, monkeypatch):
    client, spies, _ = _app(NONALL, fake, monkeypatch)
    r = client.post("/cron/reload")
    assert r.status_code == 403
    _idle(fake, spies)


def test_RL3_reload_all_existing_path(fake, monkeypatch):
    client, spies, sched = _app(ADMIN, fake, monkeypatch)
    r = client.post("/cron/reload")
    assert r.status_code == 200, r.text
    assert spies["load"] == ["load"]
    assert spies["start"] == ["start"]
    assert sched.running is True
    assert r.json()["scheduler_running"] is True


# ── status / logs / stats ─────────────────────────────────────────────────

def test_ST1_status_no_token_401(fake, monkeypatch):
    client, spies, _ = _app(False, fake, monkeypatch)
    r = client.get("/cron/scheduler-status")
    assert r.status_code == 401
    _idle(fake, spies)


def test_ST2_status_non_all_403(fake, monkeypatch):
    client, spies, _ = _app(NONALL, fake, monkeypatch)
    r = client.get("/cron/scheduler-status")
    assert r.status_code == 403
    _idle(fake, spies)


def test_ST3_status_all_200(fake, monkeypatch):
    client, _, _ = _app(ADMIN, fake, monkeypatch)
    r = client.get("/cron/scheduler-status")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "success"
    assert "scheduler_running" in r.json()["data"]


def test_LG1_logs_no_token_401(fake, monkeypatch):
    client, spies, _ = _app(False, fake, monkeypatch)
    r = client.get("/cron/logs")
    assert r.status_code == 401
    _idle(fake, spies)


def test_LG2_logs_non_all_403(fake, monkeypatch):
    client, spies, _ = _app(NONALL, fake, monkeypatch)
    r = client.get("/cron/logs")
    assert r.status_code == 403
    _idle(fake, spies)


def test_LG3_logs_all_200(fake, monkeypatch):
    client, _, _ = _app(ADMIN, fake, monkeypatch)
    r = client.get("/cron/logs")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "success"


def test_SS1_stats_no_token_401(fake, monkeypatch):
    client, spies, _ = _app(False, fake, monkeypatch)
    r = client.get("/cron/stats")
    assert r.status_code == 401
    _idle(fake, spies)


def test_SS2_stats_non_all_403(fake, monkeypatch):
    client, spies, _ = _app(NONALL, fake, monkeypatch)
    r = client.get("/cron/stats")
    assert r.status_code == 403
    _idle(fake, spies)


def test_SS3_stats_all_200(fake, monkeypatch):
    client, _, _ = _app(ADMIN, fake, monkeypatch)
    r = client.get("/cron/stats")
    assert r.status_code == 200, r.text
    assert r.json()["total_jobs"] == 3
    assert r.json()["active_jobs"] == 3
