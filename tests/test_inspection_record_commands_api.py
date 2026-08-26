"""OBJ-01 STEP-1A — Command API tests (FastAPI TestClient, mocked seams)."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routers.inspection_record_commands as rc
from routers.auth import get_current_user
from services.inspection_record_resolver import InspectionRecordError

_UID = "user-1"
_IID = "11111111-1111-1111-1111-111111111111"
_RID = "22222222-2222-2222-2222-222222222222"
_CID = "33333333-3333-3333-3333-333333333333"


def _app(user_dep):
    app = FastAPI()
    app.include_router(rc.router)
    app.dependency_overrides[get_current_user] = user_dep
    return app


def _auth_user():
    return {"id": _UID, "company_id": "co-1", "role_code": "ADMIN"}


@pytest.fixture(autouse=True)
def _no_supabase(monkeypatch):
    # get_supabase must never touch a real client in these tests
    monkeypatch.setattr(rc, "get_supabase", lambda: object())
    # ownership guard passes by default (own-company)
    monkeypatch.setattr(rc, "_ensure_inspection_own", lambda sb, iid, cur: None)


def test_unauthenticated_blocks():
    def _raise():
        raise HTTPException(status_code=401, detail="no auth")
    client = TestClient(_app(_raise))
    r = client.post(f"/inspection/{_IID}/status-changes",
                    json={"expected_revision": 0, "command_id": _CID, "to_status": "COMPLETED"})
    assert r.status_code == 401


def test_foreign_company_404(monkeypatch):
    def _deny(sb, iid, cur):
        raise HTTPException(status_code=404, detail="점검 레코드를 찾을 수 없습니다.")
    monkeypatch.setattr(rc, "_ensure_inspection_own", _deny)
    called = {"n": 0}
    monkeypatch.setattr(rc.cmd, "change_status", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    client = TestClient(_app(_auth_user))
    r = client.post(f"/inspection/{_IID}/status-changes",
                    json={"expected_revision": 0, "command_id": _CID, "to_status": "COMPLETED"})
    assert r.status_code == 404
    assert called["n"] == 0   # guard runs before service


def test_success(monkeypatch):
    monkeypatch.setattr(rc.cmd, "change_status",
                        lambda *a, **k: {"inspection_id": _IID, "revision": 1, "event_id": "e", "command_id": _CID})
    client = TestClient(_app(_auth_user))
    r = client.post(f"/inspection/{_IID}/status-changes",
                    json={"expected_revision": 0, "command_id": _CID, "to_status": "COMPLETED"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["data"]["revision"] == 1


@pytest.mark.parametrize("code,status", [
    ("INSPECTION_NOT_FOUND", 404),
    ("RESULT_NOT_FOUND", 404),
    ("REVISION_CONFLICT", 409),
    ("COMMAND_ID_REUSE_CONFLICT", 409),
    ("INVALID_STATUS_TRANSITION", 409),
    ("INSPECTION_INACTIVE", 409),
    ("RESULT_INACTIVE", 409),
    ("INVALID_CHANGE_FIELD", 400),
])
def test_error_mapping(monkeypatch, code, status):
    def _raise(*a, **k):
        raise InspectionRecordError(code, "d")
    monkeypatch.setattr(rc.cmd, "change_status", _raise)
    client = TestClient(_app(_auth_user))
    r = client.post(f"/inspection/{_IID}/status-changes",
                    json={"expected_revision": 0, "command_id": _CID, "to_status": "COMPLETED"})
    assert r.status_code == status
    assert r.json()["detail"]["code"] == code


def test_body_cannot_inject_actor_source(monkeypatch):
    captured = {}
    def _cap(sb, iid, **k):
        captured.update(k)
        return {"inspection_id": iid, "revision": 1, "event_id": "e", "command_id": _CID}
    monkeypatch.setattr(rc.cmd, "deactivate_inspection", _cap)
    client = TestClient(_app(_auth_user))
    # attempt to inject actor/source — schema ignores unknown fields
    r = client.post(f"/inspection/{_IID}/deactivations",
                    json={"expected_revision": 0, "command_id": _CID,
                          "actor_id": "attacker", "actor_type": "ADMIN", "source": "EVIL"})
    assert r.status_code == 200
    # actor_id passed to service is the authenticated user, never the body value
    assert captured["actor_id"] == _UID
    assert "actor_type" not in captured
    assert "source" not in captured


def test_result_correction_routes_result_id(monkeypatch):
    captured = {}
    def _cap(sb, iid, rid, **k):
        captured["iid"] = iid
        captured["rid"] = rid
        return {"inspection_id": iid, "revision": 1, "event_id": "e", "command_id": _CID}
    monkeypatch.setattr(rc.cmd, "correct_result", _cap)
    client = TestClient(_app(_auth_user))
    r = client.post(f"/inspection/{_IID}/results/{_RID}/corrections",
                    json={"expected_revision": 0, "command_id": _CID, "changes": {"note": "fix"}})
    assert r.status_code == 200
    assert captured["iid"] == _IID
    assert captured["rid"] == _RID
