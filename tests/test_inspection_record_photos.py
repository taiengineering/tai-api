"""OBJ-05 CLOSEOUT-01 — POST /inspection/{id}/photos authenticated upload tests."""
from __future__ import annotations

import inspect as _inspect

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routers.inspection_record_read as rr
from routers.auth import get_current_user

_UID = "user-1"
_IID = "11111111-1111-1111-1111-111111111111"
_CO = "co-1"

JPEG = b"\xff\xd8\xff" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64
PDF = b"%PDF-1.4" + b"\x00" * 64


def _app(user_dep):
    app = FastAPI()
    app.include_router(rr.router)
    app.dependency_overrides[get_current_user] = user_dep
    return app


def _auth_user():
    return {"id": _UID, "company_id": _CO, "role_code": "ADMIN"}


class _StorageBucket:
    def __init__(self, client, bucket):
        self.client = client
        self.bucket = bucket

    def create_signed_url(self, path, expires):
        self.client.signed.append({"bucket": self.bucket, "path": path, "expires": expires})
        return {"signedURL": f"https://signed.example/{path}?token=ephemeral"}

    def upload(self, *a, **k):
        raise AssertionError("router must use document_svc.upload_document, not raw storage.upload")


class _Storage:
    def __init__(self, client):
        self.client = client

    def from_(self, bucket):
        return _StorageBucket(self.client, bucket)


class _Q:
    def __init__(self, client, name):
        self.client = client
        self.name = name

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def update(self, *a, **k):
        raise AssertionError("photo upload must not UPDATE inspection/result")

    def insert(self, *a, **k):
        raise AssertionError("photo upload must not INSERT via router table()")

    def execute(self):
        if self.name == "safety_inspections":
            return type("Resp", (), {"data": [{
                "id": _IID, "assignment_id": "ws-1", "factory_id": "f1",
            }]})()
        if self.name == "work_schedules":
            return type("Resp", (), {"data": [{
                "id": "ws-1", "company_id": _CO, "factory_id": "f1",
            }]})()
        return type("Resp", (), {"data": []})()


class _SB:
    def __init__(self):
        self.signed = []
        self.storage = _Storage(self)
        self.table_names = []

    def table(self, name):
        self.table_names.append(name)
        return _Q(self, name)


@pytest.fixture
def photo_env(monkeypatch):
    sb = _SB()
    captured = {}

    async def _upload(**kwargs):
        captured.update(kwargs)
        return {"storage_path": f"{_CO}/inspection/2026-08/abc.jpg", "bucket_id": "company-docs"}

    monkeypatch.setattr(rr, "get_supabase", lambda: sb)
    monkeypatch.setattr(rr, "_ensure_inspection_own", lambda *a, **k: None)
    monkeypatch.setattr(rr.document_svc, "upload_document", _upload)
    return sb, captured


def test_unauthenticated_rejects():
    def _raise():
        raise HTTPException(status_code=401, detail="no auth")

    client = TestClient(_app(_raise))
    r = client.post(f"/inspection/{_IID}/photos", files={"file": ("a.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 401


def test_cross_tenant_404(monkeypatch, photo_env):
    called = {"n": 0}

    def _deny(*a, **k):
        raise HTTPException(status_code=404, detail="점검 레코드를 찾을 수 없습니다.")

    async def _upload(**kwargs):
        called["n"] += 1
        return {}

    monkeypatch.setattr(rr, "_ensure_inspection_own", _deny)
    monkeypatch.setattr(rr.document_svc, "upload_document", _upload)
    client = TestClient(_app(_auth_user))
    r = client.post(f"/inspection/{_IID}/photos", files={"file": ("a.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 404
    assert called["n"] == 0


def test_over_5mb_413(photo_env):
    client = TestClient(_app(_auth_user))
    big = b"\xff\xd8\xff" + b"\x00" * (5 * 1024 * 1024)
    r = client.post(f"/inspection/{_IID}/photos", files={"file": ("a.jpg", big, "image/jpeg")})
    assert r.status_code == 413
    assert photo_env[1] == {}


def test_bad_magic_415_ignores_content_type(photo_env):
    client = TestClient(_app(_auth_user))
    r = client.post(
        f"/inspection/{_IID}/photos",
        files={"file": ("a.jpg", PDF, "image/jpeg")},
    )
    assert r.status_code == 415
    assert photo_env[1] == {}


@pytest.mark.parametrize("name,blob,mime", [
    ("a.jpg", JPEG, "image/jpeg"),
    ("a.png", PNG, "image/png"),
    ("a.webp", WEBP, "image/webp"),
])
def test_allowed_mimes_private_store(photo_env, name, blob, mime):
    sb, captured = photo_env
    client = TestClient(_app(_auth_user))
    r = client.post(
        f"/inspection/{_IID}/photos",
        files={"file": (name, blob, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["photo_ref"] == f"storage://company-docs/{_CO}/inspection/2026-08/abc.jpg"
    assert "token=" not in body["photo_ref"]
    assert not body["photo_ref"].startswith("http")
    assert body["preview_url"].startswith("https://signed.example/")
    assert "token=" in body["preview_url"]
    assert captured["mime_type"] == mime
    assert captured["category"] == "inspection"
    assert captured["linked_table"] == "safety_inspections"
    assert captured["linked_id"] == _IID
    assert captured["company_id"] == _CO
    assert captured["factory_id"] == "f1"
    assert captured["uploaded_by"] == _UID
    assert captured["file_bytes"] == blob
    # storage filename is MIME-canonical; original name is title only
    assert captured["file_name"].startswith("inspection.")
    assert captured["title"] == name


def test_get_current_user_dependency_present():
    sig = _inspect.signature(rr.upload_inspection_photo)
    dep = sig.parameters["current"].default
    assert getattr(dep, "dependency", None) is rr.get_current_user


def test_does_not_import_worker_assets():
    import routers.inspection_record_read as mod
    src = _inspect.getsource(mod)
    assert "worker_assets" not in src
    assert "/uploads/inspection-photo" not in src
