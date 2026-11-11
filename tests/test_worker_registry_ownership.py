"""WO-059 WP-01B — worker_registry PATCH/DELETE 소유사 검증 회귀 테스트.

실 DB / 네트워크 0. AUTH는 TestClient + get_current_user override, FakeSB 인메모리.
검증 항목:
  PATCH: 동일 회사 200, 타 회사 403, user/worker company_id NULL 403, ADMIN 우회 200,
         타 회사 factory_id 변경 403, 자사 factory_id 변경 200.
  DELETE: 동일 회사 200, 타 회사 403, NULL company_id 403, ADMIN 우회 200.
  공통: 미인증 401.
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import routers.worker_registry as wr
from routers.auth import get_current_user
import services.company_scope as cs

# ── 픽스처 ID ────────────────────────────────────────────────────────────────

WORKER_ID   = "ww-0001-aaaa-aaaa-aaaaaaaaaaaa"
CO_A        = "co-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CO_B        = "co-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
FAC_A1      = "fa-a1a1-a1a1-a1a1-a1a1a1a1a1a1"
FAC_B1      = "fa-b1b1-b1b1-b1b1-b1b1b1b1b1b1"

USER_A  = {"user_id": "u-aaaa", "company_id": CO_A, "factory_id": FAC_A1, "role_code": "RO_COMPANY"}
USER_B  = {"user_id": "u-bbbb", "company_id": CO_B, "factory_id": FAC_B1, "role_code": "RO_COMPANY"}
USER_ADMIN = {"user_id": "u-admin", "company_id": CO_A, "factory_id": FAC_A1, "role_code": "RO_ADMIN"}
USER_NULL_CID = {"user_id": "u-null", "company_id": None, "factory_id": None, "role_code": "RO_COMPANY"}


# ── FakeSB ────────────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, sb, name):
        self.sb = sb
        self.name = name
        self._eq = []
        self._limit = None
        self._op = "select"
        self._row = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._eq.append((col, val))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def update(self, row):
        self._op = "update"
        self._row = row
        return self

    def _match(self, row):
        return all(row.get(col) == val for col, val in self._eq)

    def execute(self):
        table = self.sb.tables.setdefault(self.name, [])
        if self._op == "update":
            updated = []
            for r in table:
                if self._match(r):
                    r.update(self._row)
                    updated.append(r)
            return _Resp(updated)
        rows = [dict(r) for r in table if self._match(r)]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Resp(rows)


class FakeSB:
    def __init__(self, tables=None):
        self.tables = {k: [dict(r) for r in v] for k, v in (tables or {}).items()}

    def table(self, name):
        return _Q(self, name)


def _seed():
    return {
        "worker_registry": [
            {"id": WORKER_ID, "company_id": CO_A, "factory_id": FAC_A1, "is_active": True},
        ],
        "role_data_scope": [
            {"role_code": "RO_COMPANY", "scope_type": "COMPANY"},
            {"role_code": "RO_ADMIN",   "scope_type": "ALL"},
        ],
        "factories": [
            {"id": FAC_A1, "company_id": CO_A},
            {"id": FAC_B1, "company_id": CO_B},
        ],
    }


def _app(user, monkeypatch):
    fake = FakeSB(_seed())
    monkeypatch.setattr(wr, "get_supabase", lambda: fake)
    app = FastAPI()
    app.include_router(wr.router)
    if user is None:
        def _deny():
            raise HTTPException(status_code=401, detail="미인증")
        app.dependency_overrides[get_current_user] = _deny
    else:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ── PATCH 테스트 ──────────────────────────────────────────────────────────────

def test_PATCH_same_company_200(monkeypatch):
    client = _app(USER_A, monkeypatch)
    r = client.patch(f"/worker-registry/{WORKER_ID}", json={"name": "변경"})
    assert r.status_code == 200


def test_PATCH_other_company_403(monkeypatch):
    client = _app(USER_B, monkeypatch)
    r = client.patch(f"/worker-registry/{WORKER_ID}", json={"name": "변경"})
    assert r.status_code == 403


def test_PATCH_null_user_company_403(monkeypatch):
    client = _app(USER_NULL_CID, monkeypatch)
    r = client.patch(f"/worker-registry/{WORKER_ID}", json={"name": "변경"})
    assert r.status_code == 403


def test_PATCH_null_worker_company_403(monkeypatch):
    fake = FakeSB({
        **_seed(),
        "worker_registry": [{"id": WORKER_ID, "company_id": None, "is_active": True}],
    })
    app = FastAPI()
    monkeypatch.setattr(wr, "get_supabase", lambda: fake)
    app.include_router(wr.router)
    app.dependency_overrides[get_current_user] = lambda: USER_A
    client = TestClient(app)
    r = client.patch(f"/worker-registry/{WORKER_ID}", json={"name": "변경"})
    assert r.status_code == 403


def test_PATCH_admin_bypass_200(monkeypatch):
    client = _app(USER_ADMIN, monkeypatch)
    r = client.patch(f"/worker-registry/{WORKER_ID}", json={"name": "변경"})
    assert r.status_code == 200


def test_PATCH_foreign_factory_403(monkeypatch):
    client = _app(USER_A, monkeypatch)
    r = client.patch(f"/worker-registry/{WORKER_ID}", json={"factory_id": FAC_B1})
    assert r.status_code == 403


def test_PATCH_own_factory_200(monkeypatch):
    client = _app(USER_A, monkeypatch)
    r = client.patch(f"/worker-registry/{WORKER_ID}", json={"factory_id": FAC_A1})
    assert r.status_code == 200


def test_PATCH_unauthenticated_401(monkeypatch):
    client = _app(None, monkeypatch)
    r = client.patch(f"/worker-registry/{WORKER_ID}", json={"name": "변경"})
    assert r.status_code == 401


# ── DELETE 테스트 ─────────────────────────────────────────────────────────────

def test_DELETE_same_company_200(monkeypatch):
    client = _app(USER_A, monkeypatch)
    r = client.delete(f"/worker-registry/{WORKER_ID}")
    assert r.status_code == 200


def test_DELETE_other_company_403(monkeypatch):
    client = _app(USER_B, monkeypatch)
    r = client.delete(f"/worker-registry/{WORKER_ID}")
    assert r.status_code == 403


def test_DELETE_null_user_company_403(monkeypatch):
    client = _app(USER_NULL_CID, monkeypatch)
    r = client.delete(f"/worker-registry/{WORKER_ID}")
    assert r.status_code == 403


def test_DELETE_null_worker_company_403(monkeypatch):
    fake = FakeSB({
        **_seed(),
        "worker_registry": [{"id": WORKER_ID, "company_id": None, "is_active": True}],
    })
    app = FastAPI()
    monkeypatch.setattr(wr, "get_supabase", lambda: fake)
    app.include_router(wr.router)
    app.dependency_overrides[get_current_user] = lambda: USER_A
    client = TestClient(app)
    r = client.delete(f"/worker-registry/{WORKER_ID}")
    assert r.status_code == 403


def test_DELETE_admin_bypass_200(monkeypatch):
    client = _app(USER_ADMIN, monkeypatch)
    r = client.delete(f"/worker-registry/{WORKER_ID}")
    assert r.status_code == 200


def test_DELETE_unauthenticated_401(monkeypatch):
    client = _app(None, monkeypatch)
    r = client.delete(f"/worker-registry/{WORKER_ID}")
    assert r.status_code == 401
