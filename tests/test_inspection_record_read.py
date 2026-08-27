"""OBJ-05 CLOSEOUT-01 — GET /inspection/{id}/record thin router tests."""
from __future__ import annotations

import asyncio
import inspect as _inspect

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routers.inspection_record_read as rr
from routers.auth import get_current_user
from services.inspection_record_resolver import InspectionRecordError

_UID = "user-1"
_IID = "11111111-1111-1111-1111-111111111111"
_RECORD = {
    "inspection_id": _IID,
    "revision": 3,
    "is_active": True,
    "inspection_status": "COMPLETED",
    "inspection_date": "2026-08-01",
    "asset_id": "a1",
    "inspector_id": "u1",
    "assignment_id": "ws-1",
    "factory_id": "f1",
    "overall_result": "NORMAL",
    "results": [{"result_id": "r1", "result_code": "NORMAL", "photo_url": None}],
}


def _app(user_dep):
    app = FastAPI()
    app.include_router(rr.router)
    app.dependency_overrides[get_current_user] = user_dep
    return app


def _auth_user():
    return {"id": _UID, "company_id": "co-1", "role_code": "ADMIN"}


class _ForbidWriteSB:
    def table(self, name):
        raise AssertionError(f"GET /record must not touch table({name})")

    def rpc(self, *a, **k):
        raise AssertionError("router must call resolver, not rpc directly")


@pytest.fixture(autouse=True)
def _no_supabase(monkeypatch):
    monkeypatch.setattr(rr, "get_supabase", lambda: _ForbidWriteSB())
    monkeypatch.setattr(rr, "_ensure_inspection_own", lambda sb, iid, cur: None)


def test_unauthenticated_blocks():
    def _raise():
        raise HTTPException(status_code=401, detail="no auth")

    client = TestClient(_app(_raise))
    r = client.get(f"/inspection/{_IID}/record")
    assert r.status_code == 401


def test_foreign_company_404_resolver_not_called(monkeypatch):
    def _deny(sb, iid, cur):
        raise HTTPException(status_code=404, detail="점검 레코드를 찾을 수 없습니다.")

    monkeypatch.setattr(rr, "_ensure_inspection_own", _deny)
    called = {"n": 0}

    def _resolve(*a, **k):
        called["n"] += 1
        return _RECORD

    monkeypatch.setattr(rr, "resolve_inspection_record", _resolve)
    client = TestClient(_app(_auth_user))
    r = client.get(f"/inspection/{_IID}/record")
    assert r.status_code == 404
    assert called["n"] == 0


def test_resolver_passthrough_exact(monkeypatch):
    seen = {}

    def _resolve(iid, sb):
        seen["iid"] = iid
        seen["sb"] = sb
        return _RECORD

    monkeypatch.setattr(rr, "resolve_inspection_record", _resolve)
    client = TestClient(_app(_auth_user))
    r = client.get(f"/inspection/{_IID}/record")
    assert r.status_code == 200
    body = r.json()
    assert body == _RECORD
    assert body is not _RECORD  # JSON roundtrip
    for key in (
        "inspection_id", "revision", "is_active", "inspection_status",
        "inspection_date", "asset_id", "inspector_id", "assignment_id",
        "factory_id", "overall_result", "results",
    ):
        assert key in body
    assert seen["iid"] == _IID


def test_resolver_passthrough_identity_handler(monkeypatch):
    sb = object()
    monkeypatch.setattr(rr, "get_supabase", lambda: sb)

    def _resolve(iid, supabase):
        assert iid == _IID
        assert supabase is sb
        return _RECORD

    monkeypatch.setattr(rr, "resolve_inspection_record", _resolve)
    out = asyncio.run(rr.get_inspection_record(_IID, current=_auth_user()))
    assert out is _RECORD


def test_get_current_user_dependency_present():
    sig = _inspect.signature(rr.get_inspection_record)
    dep = sig.parameters["current"].default
    assert getattr(dep, "dependency", None) is rr.get_current_user


def test_guard_before_resolver_order(monkeypatch):
    order = []
    monkeypatch.setattr(rr, "_ensure_inspection_own", lambda sb, iid, cur: order.append("guard"))
    monkeypatch.setattr(
        rr, "resolve_inspection_record",
        lambda iid, sb: order.append("resolver") or _RECORD,
    )
    asyncio.run(rr.get_inspection_record(_IID, current=_auth_user()))
    assert order == ["guard", "resolver"]


@pytest.mark.parametrize("code,status", [
    ("INSPECTION_NOT_FOUND", 404),
    ("LEGACY_STATUS_UNRESOLVED", 409),
    ("RESULT_CODE_UNRESOLVED", 409),
    ("JOURNAL_REVISION_GAP", 409),
    ("RESOLVER_MALFORMED_RESPONSE", 500),
])
def test_resolver_error_mapping(monkeypatch, code, status):
    def _raise(*a, **k):
        raise InspectionRecordError(code, "internal-leak")

    monkeypatch.setattr(rr, "resolve_inspection_record", _raise)
    client = TestClient(_app(_auth_user))
    r = client.get(f"/inspection/{_IID}/record")
    assert r.status_code == status
    assert r.json()["detail"]["code"] == code
    assert "internal-leak" not in r.text


def test_no_wrapper_keys(monkeypatch):
    monkeypatch.setattr(rr, "resolve_inspection_record", lambda *a, **k: _RECORD)
    client = TestClient(_app(_auth_user))
    body = client.get(f"/inspection/{_IID}/record").json()
    assert "status" not in body or body.get("status") == _RECORD.get("inspection_status")
    assert "ok" not in body
    assert "data" not in body or isinstance(body.get("data"), type(_RECORD.get("data")))
