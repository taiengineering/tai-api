"""OBJ-05 CLOSEOUT-01 REV-2 — photo signing allowlist + upload owner/ext security (P1–P10)."""
from __future__ import annotations

import asyncio
import copy

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routers.inspection_record_read as rr
import routers.inspection_view as V
from routers.auth import get_current_user

POS_INSP = "3f9cf36f-5bbc-4dad-9ba6-e71643020e9a"
OTHER_INSP = "217f0c15-56d5-48a4-88ef-8027e0a06057"
WS_OWN = "ws-own-1"
WS_OTHER = "ws-other-1"
CO_OWN = "co-own"
CO_OTHER = "co-other"
PATH_OWN = "co-own/inspection/2026-08/own.jpg"
PATH_OTHER_CO = "co-other/inspection/2026-08/x.jpg"
PATH_OTHER_INSP = "co-own/inspection/2026-08/other-insp.jpg"
PATH_UNREG = "co-own/inspection/2026-08/random.jpg"

JPEG = b"\xff\xd8\xff" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64


def _vm(photo_url=None, photo_urls=None):
    return {
        "inspection_id": POS_INSP,
        "inspection_set_id": "set-1",
        "schema_id": "schema-1",
        "form_code": "GEN-INSPECT-RESULT-001",
        "schema_version": 1,
        "fields": {
            "inspection_subject": None,
            "inspected_at": "2026-05-14T00:00:00",
            "inspection_title": "소방시설공사업법 점검",
            "inspector_display": None,
            "inspection_results": [
                {
                    "result_id": "r1",
                    "item_name": "소화기",
                    "raw_code": "NORMAL",
                    "photo_url": photo_url,
                    "photo_urls": photo_urls,
                },
            ],
        },
        "completeness": {"is_complete": True, "missing_required_fields": []},
    }


class _Q:
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self._eq = {}
        self._in = {}
        self._is = {}

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def in_(self, col, vals):
        self._in[col] = list(vals)
        return self

    def is_(self, col, val):
        self._is[col] = val
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        self.client.table_calls.append({
            "name": self.name, "eq": dict(self._eq), "in_": dict(self._in),
        })
        if self.name == "safety_inspections":
            iid = self._eq.get("id")
            for row in self.client.inspections:
                if row["id"] == iid:
                    return type("Resp", (), {"data": [row]})()
            return type("Resp", (), {"data": []})()
        if self.name == "work_schedules":
            wid = self._eq.get("id")
            for row in self.client.schedules:
                if row["id"] == wid:
                    return type("Resp", (), {"data": [row]})()
            return type("Resp", (), {"data": []})()
        if self.name == "documents":
            want = set(self._in.get("storage_path") or [])
            rows = []
            for doc in self.client.docs:
                if doc.get("storage_path") not in want:
                    continue
                if any(doc.get(k) != self._eq.get(k) for k in (
                    "bucket_id", "linked_table", "linked_id", "company_id",
                ) if k in self._eq):
                    continue
                if self._eq.get("is_active") is True and doc.get("is_active") is not True:
                    continue
                if self._is.get("deleted_at") == "null" and doc.get("deleted_at") is not None:
                    continue
                rows.append({"storage_path": doc["storage_path"]})
            return type("Resp", (), {"data": rows})()
        return type("Resp", (), {"data": []})()


class _SB:
    def __init__(self, *, docs=None, inspections=None, schedules=None, fail_sign=False):
        self.docs = list(docs or [])
        self.inspections = list(inspections or [
            {"id": POS_INSP, "assignment_id": WS_OWN, "factory_id": "f1"},
            {"id": OTHER_INSP, "assignment_id": WS_OTHER, "factory_id": "f2"},
        ])
        self.schedules = list(schedules or [
            {"id": WS_OWN, "company_id": CO_OWN, "factory_id": "f1"},
            {"id": WS_OTHER, "company_id": CO_OTHER, "factory_id": "f2"},
        ])
        self.table_calls = []
        self.signed = []
        self.fail_sign = fail_sign
        self.storage = self

    def table(self, name):
        return _Q(self, name)

    def from_(self, bucket):
        return self

    def create_signed_url(self, path, expires):
        if self.fail_sign:
            raise RuntimeError("sign fail")
        self.signed.append(path)
        return {"signedURL": f"https://signed.example/{path}?token=ephemeral"}


def _own_doc(path=PATH_OWN, linked_id=POS_INSP, company_id=CO_OWN, **extra):
    row = {
        "storage_path": path,
        "bucket_id": "company-docs",
        "linked_table": "safety_inspections",
        "linked_id": linked_id,
        "company_id": company_id,
        "is_active": True,
        "deleted_at": None,
    }
    row.update(extra)
    return row


def _run_view(vm, sb, inspection_id=POS_INSP):
    orig = {
        "g": V.get_supabase,
        "e": V._ensure_inspection_own,
        "c": V.compose_inspection_view,
    }
    V.get_supabase = lambda: sb
    V._ensure_inspection_own = lambda *a, **k: None
    V.compose_inspection_view = lambda iid, supabase=None: copy.deepcopy(vm)
    try:
        return asyncio.run(V.get_inspection_view(inspection_id, current={"id": "u1", "company_id": CO_OWN}))
    finally:
        V.get_supabase = orig["g"]
        V._ensure_inspection_own = orig["e"]
        V.compose_inspection_view = orig["c"]


def test_P1_own_registered_photo_signed_once():
    sb = _SB(docs=[_own_doc()])
    out = _run_view(_vm(photo_url=f"storage://company-docs/{PATH_OWN}"), sb)
    assert out["fields"]["inspection_results"][0]["photo_url"] == (
        f"https://signed.example/{PATH_OWN}?token=ephemeral"
    )
    assert sb.signed == [PATH_OWN]
    assert len([c for c in sb.table_calls if c["name"] == "documents"]) == 1


def test_P2_foreign_company_storage_ref_not_signed():
    sb = _SB(docs=[
        _own_doc(),
        _own_doc(path=PATH_OTHER_CO, company_id=CO_OTHER, linked_id=OTHER_INSP),
    ])
    out = _run_view(_vm(photo_url=f"storage://company-docs/{PATH_OTHER_CO}"), sb)
    assert out["fields"]["inspection_results"][0]["photo_url"] == f"storage://company-docs/{PATH_OTHER_CO}"
    assert sb.signed == []


def test_P3_same_company_other_inspection_not_signed():
    sb = _SB(docs=[
        _own_doc(),
        _own_doc(path=PATH_OTHER_INSP, linked_id=OTHER_INSP, company_id=CO_OWN),
    ])
    out = _run_view(_vm(photo_url=f"storage://company-docs/{PATH_OTHER_INSP}"), sb)
    assert out["fields"]["inspection_results"][0]["photo_url"] == (
        f"storage://company-docs/{PATH_OTHER_INSP}"
    )
    assert sb.signed == []


def test_P4_unregistered_storage_ref_not_signed():
    sb = _SB(docs=[_own_doc()])
    out = _run_view(_vm(photo_url=f"storage://company-docs/{PATH_UNREG}"), sb)
    assert out["fields"]["inspection_results"][0]["photo_url"] == f"storage://company-docs/{PATH_UNREG}"
    assert sb.signed == []


def test_P5_w3_arbitrary_storage_ref_not_signed():
    # W3 가 client photo_url 을 그대로 저장한 경우와 동일: documents 미등록 → 서명 0
    sb = _SB(docs=[])
    evil = "storage://company-docs/victim-co/secret/private.pdf"
    out = _run_view(_vm(photo_url=evil), sb)
    assert out["fields"]["inspection_results"][0]["photo_url"] == evil
    assert sb.signed == []


def test_P6_correction_arbitrary_storage_ref_not_signed():
    # correction 으로 photo_url 을 임의 storage:// 로 바꿔도 allowlist 밖이면 서명 0
    sb = _SB(docs=[_own_doc()])
    evil = "storage://company-docs/victim-co/secret/private.jpg"
    out = _run_view(
        _vm(photo_url=evil, photo_urls=[f"storage://company-docs/{PATH_OWN}", evil]),
        sb,
    )
    row = out["fields"]["inspection_results"][0]
    assert row["photo_url"] == evil
    assert row["photo_urls"][0] == f"https://signed.example/{PATH_OWN}?token=ephemeral"
    assert row["photo_urls"][1] == evil
    assert sb.signed == [PATH_OWN]


def test_P10_document_lookup_batch_once_n_plus_one_zero():
    sb = _SB(docs=[_own_doc(PATH_OWN), _own_doc("co-own/inspection/2026-08/b.jpg")])
    vm = _vm(
        photo_url=f"storage://company-docs/{PATH_OWN}",
        photo_urls=[
            "storage://company-docs/co-own/inspection/2026-08/b.jpg",
            "https://legacy.example/x.jpg",
        ],
    )
    # many result rows with storage refs — still 1 documents query
    vm["fields"]["inspection_results"] = [
        {"result_id": f"r{i}", "photo_url": f"storage://company-docs/{PATH_OWN}", "photo_urls": None}
        for i in range(8)
    ]
    _run_view(vm, sb)
    doc_calls = [c for c in sb.table_calls if c["name"] == "documents"]
    assert len(doc_calls) == 1
    assert set(doc_calls[0]["in_"]["storage_path"]) == {PATH_OWN}


# ── upload security (P7–P9 + P8) ──

def _photo_app(user_dep):
    app = FastAPI()
    app.include_router(rr.router)
    app.dependency_overrides[get_current_user] = user_dep
    return app


@pytest.fixture
def photo_env(monkeypatch):
    sb = _SB()
    captured = {}

    async def _upload(**kwargs):
        captured.update(kwargs)
        # simulate document_svc path build from file_name ext
        ext = (kwargs.get("file_name") or "").rsplit(".", 1)[-1]
        path = f"{kwargs['company_id']}/inspection/2026-08/abc.{ext}"
        return {"storage_path": path, "bucket_id": "company-docs"}

    monkeypatch.setattr(rr, "get_supabase", lambda: sb)
    monkeypatch.setattr(rr, "_ensure_inspection_own", lambda *a, **k: None)
    monkeypatch.setattr(rr.document_svc, "upload_document", _upload)
    return sb, captured


def test_P7_png_bytes_evil_exe_filename_uses_png_suffix(photo_env):
    sb, captured = photo_env
    client = TestClient(_photo_app(lambda: {"id": "u1", "company_id": CO_OWN, "role_code": "USER"}))
    r = client.post(
        f"/inspection/{POS_INSP}/photos",
        files={"file": ("evil.exe", PNG, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert captured["file_name"] == "inspection.png"
    assert captured["file_name"].endswith(".png")
    assert ".exe" not in captured["file_name"]
    assert captured["title"] == "evil.exe"  # display metadata only
    assert captured["mime_type"] == "image/png"
    assert r.json()["photo_ref"].endswith(".png")
    assert ".exe" not in r.json()["photo_ref"]


@pytest.mark.parametrize("name,blob,mime,ext", [
    ("a.jpg", JPEG, "image/jpeg", "jpg"),
    ("a.png", PNG, "image/png", "png"),
    ("a.webp", WEBP, "image/webp", "webp"),
])
def test_P8_jpeg_png_webp_upload_ok(photo_env, name, blob, mime, ext):
    _, captured = photo_env
    client = TestClient(_photo_app(lambda: {"id": "u1", "company_id": CO_OWN, "role_code": "USER"}))
    r = client.post(
        f"/inspection/{POS_INSP}/photos",
        files={"file": (name, blob, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert captured["file_name"] == f"inspection.{ext}"
    assert captured["mime_type"] == mime
    assert r.json()["photo_ref"].endswith(f".{ext}")
    assert "preview_url" in r.json()


def test_P9_admin_upload_uses_target_inspection_owner_company(photo_env):
    _, captured = photo_env
    # global/admin caller company ≠ inspection owner
    client = TestClient(_photo_app(lambda: {
        "id": "admin-1", "company_id": "admin-co", "role_code": "ADMIN",
    }))
    r = client.post(
        f"/inspection/{POS_INSP}/photos",
        files={"file": ("a.jpg", JPEG, "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    assert captured["company_id"] == CO_OWN
    assert captured["company_id"] != "admin-co"
    assert captured["factory_id"] == "f1"
    assert captured["linked_id"] == POS_INSP
