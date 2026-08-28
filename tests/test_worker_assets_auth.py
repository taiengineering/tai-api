"""§81 WorkerAssets Authorization Boundary — PHOTO / ASSIGNMENT / EDUCATION matrix.

실 DB / 네트워크 0. AUTH 는 TestClient + get_current_user override, FakeSB 인메모리.
DEDUP v1 은 동일 user+canonical code+server date retry 만 접는다(원자 UNIQUE 아님).
"""
from __future__ import annotations

import base64
import inspect
import os
import sys
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import routers.worker_assets as wa
from routers.auth import get_current_user
from services.upload_service import MAX_SIZE
import services.inspection_sets_svc.items as iss_items

USER = "11111111-1111-1111-1111-111111111111"
OTHER = "99999999-9999-9999-9999-999999999999"
INSP_OWN = "3f9cf36f-5bbc-4dad-9ba6-e71643020e9a"
INSP_OTHER = "217f0c15-56d5-48a4-88ef-8027e0a06057"
INSP_MISSING = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
WS_OWN = "ws-own-1"
WS_OTHER = "ws-other-1"
WA_OWN = "wa-own-1"
WA_OTHER = "wa-other-1"
WA_OWN_DONE = "wa-own-done"
SET_OWN = "set-own-1"
EDU_ACTIVE = "eeeeeeee-0001-4000-8000-000000000001"
EDU_INACTIVE = "eeeeeeee-0002-4000-8000-000000000002"
EDU_UNKNOWN = "eeeeeeee-0003-4000-8000-000000000003"
CODE = "SAFETY-001"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff" + b"\x00" * 32
CALLER = {
    "id": USER,
    "phone": "01012345678",
    "company_id": "co-1",
    "factory_id": "fa-1",
    "name": "나",
}


class _Resp:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, sb, name):
        self.sb = sb
        self.name = name
        self._eq = []
        self._in = []
        self._is = []
        self._neq = []
        self._order = None
        self._limit = None
        self._op = "select"
        self._row = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._eq.append((col, val))
        return self

    def in_(self, col, vals):
        self._in.append((col, list(vals)))
        return self

    def is_(self, col, val):
        self._is.append((col, val))
        return self

    def neq(self, col, val):
        self._neq.append((col, val))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, row):
        self._op = "insert"
        self._row = row
        return self

    def _match(self, row):
        for col, val in self._eq:
            if row.get(col) != val:
                return False
        for col, vals in self._in:
            if row.get(col) not in vals:
                return False
        for col, val in self._is:
            if val == "null" and row.get(col) is not None:
                return False
        for col, val in self._neq:
            if row.get(col) == val:
                return False
        return True

    def execute(self):
        table = self.sb.tables.setdefault(self.name, [])
        if self._op == "insert":
            row = dict(self._row)
            row.setdefault("id", str(uuid.uuid4()))
            table.append(row)
            self.sb.inserts.append({"table": self.name, "row": row})
            return _Resp([row])
        rows = [dict(r) for r in table if self._match(r)]
        if self._order:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col) or "", reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Resp(rows)


class _Bucket:
    def __init__(self, sb, bucket):
        self.sb = sb
        self.bucket = bucket

    def upload(self, path, file, file_options=None):
        if self.bucket != "company-docs":
            raise AssertionError("wrong bucket: %s" % self.bucket)
        self.sb.uploads.append({
            "bucket": self.bucket,
            "path": path,
            "options": file_options,
            "size": len(file) if file is not None else 0,
        })
        return True

    def create_signed_url(self, path, expires_in):
        if self.sb.fail_sign:
            raise RuntimeError("sign fail")
        url = "https://signed.example/%s?exp=%s" % (path, expires_in)
        self.sb.signed.append({"path": path, "expires": expires_in, "url": url})
        return {"signedURL": url, "signedUrl": url}

    def get_public_url(self, path):
        raise AssertionError("get_public_url must not be used for §81 private bucket")


class FakeSB:
    def __init__(self, tables=None, fail_sign=False):
        self.tables = {k: [dict(r) for r in v] for k, v in (tables or {}).items()}
        self.inserts = []
        self.uploads = []
        self.signed = []
        self.fail_sign = fail_sign
        self.storage = self

    def table(self, name):
        return _Q(self, name)

    def from_(self, bucket):
        return _Bucket(self, bucket)


def _seed():
    return {
        "users": [
            dict(CALLER),
            {"id": OTHER, "phone": "01099999999", "company_id": "co-2", "factory_id": "fa-2", "name": "다른사람"},
        ],
        "safety_inspections": [
            {"id": INSP_OWN, "assignment_id": WS_OWN},
            {"id": INSP_OTHER, "assignment_id": WS_OTHER},
        ],
        "work_schedules": [
            {"id": WS_OWN, "assigned_user_id": USER, "inspection_set_id": SET_OWN},
            {"id": WS_OTHER, "assigned_user_id": OTHER, "inspection_set_id": "set-other"},
        ],
        "work_assignments": [
            {
                "id": WA_OWN, "assigned_user_id": USER, "schedule_id": WS_OWN,
                "status_code": "PENDING", "overdue_level": 1, "resolved_at": None,
                "scheduled_date": "2026-01-01", "due_date": "2026-01-02",
            },
            {
                "id": WA_OWN_DONE, "assigned_user_id": USER, "schedule_id": WS_OWN,
                "status_code": "DONE", "overdue_level": 0, "resolved_at": "2026-01-03",
                "scheduled_date": "2026-01-03", "due_date": "2026-01-03",
            },
            {
                "id": WA_OTHER, "assigned_user_id": OTHER, "schedule_id": WS_OTHER,
                "status_code": "PENDING", "overdue_level": 9, "resolved_at": None,
                "scheduled_date": "2026-01-01", "due_date": "2026-01-02",
            },
        ],
        "inspection_sets": [{"id": SET_OWN}],
        "inspection_set_items": [
            {
                "id": "item-1", "inspection_set_id": SET_OWN, "item_seq": 1,
                "item_name": "소화기", "description": None, "risk_type": None,
                "is_required": True, "check_type": "OX", "is_active": True,
            },
        ],
        "education_master": [
            {"id": EDU_ACTIVE, "education_code": CODE, "is_active": True},
            {"id": EDU_INACTIVE, "education_code": "OLD-CODE", "is_active": False},
        ],
        "education_history": [],
        "attachments": [],
        "worker_registry": [],
    }


def _app(user, fake, monkeypatch):
    monkeypatch.setattr(wa, "get_supabase", lambda: fake)
    monkeypatch.setattr(iss_items, "get_supabase", lambda: fake)
    app = FastAPI()
    app.include_router(wa.router)
    if user is False:
        def _deny():
            raise HTTPException(status_code=401, detail="토큰이 없습니다")
        app.dependency_overrides[get_current_user] = _deny
    else:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[wa._optional_auth] = lambda: user
    return TestClient(app)


@pytest.fixture
def fake():
    return FakeSB(_seed())


@pytest.fixture
def client(fake, monkeypatch):
    return _app(CALLER, fake, monkeypatch)


def _photo(client, *, context="inspection", inspection_id=INSP_OWN, filename="photo.png",
           content=PNG, content_type="image/png", extra=None):
    data = {"context": context}
    if inspection_id is not None:
        data["inspection_id"] = inspection_id
    if extra:
        data.update(extra)
    return client.post(
        "/uploads/inspection-photo",
        files={"file": (filename, content, content_type)},
        data=data,
    )


def _edu(client, **body):
    payload = {"edu_id": EDU_ACTIVE}
    payload.update(body)
    return client.post("/education/worker-complete", json=payload)


def _png_data_url(raw=PNG):
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


# ── PHOTO ─────────────────────────────────────────────────────────────────

def test_P1_photo_no_token_401(fake, monkeypatch):
    client = _app(False, fake, monkeypatch)
    r = _photo(client)
    assert r.status_code == 401


def test_P2_own_inspection_success(client, fake):
    r = _photo(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["url"].startswith("storage://company-docs/worker-photos/inspection/")
    assert fake.uploads and fake.uploads[0]["bucket"] == "company-docs"
    path = fake.uploads[0]["path"]
    assert path.startswith("worker-photos/inspection/")
    assert path.endswith(".png")


def test_P3_foreign_inspection_403(client):
    r = _photo(client, inspection_id=INSP_OTHER)
    assert r.status_code == 403


def test_P4_missing_inspection_404(client):
    r = _photo(client, inspection_id=INSP_MISSING)
    assert r.status_code == 404


def test_P4b_invalid_inspection_uuid_404(client):
    r = _photo(client, inspection_id="not-a-uuid")
    assert r.status_code == 404


def test_P5_oversize_413(client):
    r = _photo(client, content=PNG[:8] + b"\x00" * (MAX_SIZE + 1))
    assert r.status_code == 413


def test_P6_invalid_magic_415(client):
    r = _photo(client, filename="photo.png", content=b"not-an-image", content_type="image/png")
    assert r.status_code == 415


def test_P7_evil_exe_filename_canonical_png(client, fake):
    r = _photo(client, filename="evil.exe", content=PNG, content_type="application/octet-stream")
    assert r.status_code == 200, r.text
    path = fake.uploads[0]["path"]
    assert path.endswith(".png")
    att = fake.inserts[-1]["row"]
    assert att["file_ext"] == "png"
    assert att["mime_type"] == "image/png"


def test_P8_unknown_context_422(client, fake):
    r = _photo(client, context="evil_context")
    assert r.status_code == 422
    assert fake.uploads == []


def test_P9_uploaded_by_is_current_user(client, fake):
    r = _photo(client)
    assert r.status_code == 200
    att = [i["row"] for i in fake.inserts if i["table"] == "attachments"][-1]
    assert att["uploaded_by"] == USER


def test_P10_attachments_file_url_stable_ref(client, fake):
    r = _photo(client)
    assert r.status_code == 200
    att = [i["row"] for i in fake.inserts if i["table"] == "attachments"][-1]
    path = fake.uploads[0]["path"]
    assert att["file_url"] == "storage://company-docs/%s" % path
    assert "signed" not in att["file_url"]
    assert "http" not in att["file_url"]


def test_P11_response_url_is_stable_preview_is_signed(client, fake):
    r = _photo(client)
    assert r.status_code == 200
    body = r.json()
    att = [i["row"] for i in fake.inserts if i["table"] == "attachments"][-1]
    stable = body["url"]
    preview = body["data"]["preview_url"]
    assert stable == att["file_url"]
    assert stable.startswith("storage://company-docs/worker-photos/")
    assert body["data"]["url"] == stable
    assert preview.startswith("https://signed.example/")
    assert preview != stable


# ── WORK ASSIGNMENTS ──────────────────────────────────────────────────────

def test_W1_list_no_token_401(fake, monkeypatch):
    client = _app(False, fake, monkeypatch)
    r = client.get("/work-assignments")
    assert r.status_code == 401


def test_W2_omit_assigned_user_id_returns_self_only(client):
    r = client.get("/work-assignments")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert items
    assert all(a["assigned_user_id"] == USER for a in items)
    assert {a["id"] for a in items} == {WA_OWN, WA_OWN_DONE}


def test_W3_own_assigned_user_id_ok(client):
    r = client.get("/work-assignments", params={"assigned_user_id": USER})
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert all(a["assigned_user_id"] == USER for a in items)


def test_W4_foreign_assigned_user_id_403(client):
    r = client.get("/work-assignments", params={"assigned_user_id": OTHER})
    assert r.status_code == 403


def test_W5_no_query_does_not_expose_all_rows(client):
    r = client.get("/work-assignments")
    assert r.status_code == 200
    ids = {a["id"] for a in r.json()["data"]["items"]}
    assert WA_OTHER not in ids
    assert OTHER not in {a["assigned_user_id"] for a in r.json()["data"]["items"]}


def test_W6_status_and_overdue_filters_preserved(client):
    r = client.get(
        "/work-assignments",
        params={"status": "PENDING,OVERDUE", "overdue_only": True},
    )
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert [a["id"] for a in items] == [WA_OWN]
    assert items[0]["status_code"] == "PENDING"
    shape = r.json()
    assert shape["status"] == "success"
    assert "total" in shape["data"] and "items" in shape["data"]


# ── EDUCATION AUTH ────────────────────────────────────────────────────────

def test_E1_edu_no_token_401(fake, monkeypatch):
    client = _app(False, fake, monkeypatch)
    r = _edu(client)
    assert r.status_code == 401


def test_E2_no_worker_id_uses_current_user(client, fake):
    r = _edu(client)
    assert r.status_code == 200, r.text
    hist = [i["row"] for i in fake.inserts if i["table"] == "education_history"][-1]
    assert hist["user_id"] == USER
    assert r.json()["data"]["mode"] == "CREATED"


def test_E3_own_worker_id_ok(client, fake):
    r = _edu(client, worker_id=USER)
    assert r.status_code == 200, r.text
    hist = [i["row"] for i in fake.inserts if i["table"] == "education_history"][-1]
    assert hist["user_id"] == USER


def test_E4_foreign_worker_id_403(client, fake):
    r = _edu(client, worker_id=OTHER)
    assert r.status_code == 403
    assert fake.inserts == []


def test_E5_own_phone_ok(client, fake):
    r = _edu(client, phone="010-1234-5678")
    assert r.status_code == 200, r.text
    hist = [i["row"] for i in fake.inserts if i["table"] == "education_history"][-1]
    assert hist["user_id"] == USER


def test_E6_foreign_phone_403(client, fake):
    r = _edu(client, phone="01099999999")
    assert r.status_code == 403
    assert fake.inserts == []


def test_E7_unresolved_phone_403(client, fake):
    r = _edu(client, phone="01000000000")
    assert r.status_code == 403
    assert fake.inserts == []


# ── EDUCATION OBJECT ──────────────────────────────────────────────────────

def test_E8_active_master_maps_to_canonical_code(client, fake):
    r = _edu(client)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["education_code"] == CODE


def test_E9_unknown_master_404(client, fake):
    r = _edu(client, edu_id=EDU_UNKNOWN)
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "EDUCATION_NOT_FOUND"
    assert fake.inserts == []


def test_E10_inactive_master_404(client, fake):
    r = _edu(client, edu_id=EDU_INACTIVE)
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "EDUCATION_NOT_FOUND"
    assert fake.inserts == []


def test_E11_history_stores_master_education_code(client, fake):
    r = _edu(client)
    assert r.status_code == 200
    hist = [i["row"] for i in fake.inserts if i["table"] == "education_history"][-1]
    assert hist["education_code"] == CODE
    assert hist["company_id"] == "co-1"
    assert hist["factory_id"] == "fa-1"


def test_E12_raw_client_uuid_not_stored(client, fake):
    r = _edu(client, edu_id=EDU_ACTIVE)
    assert r.status_code == 200
    hist = [i["row"] for i in fake.inserts if i["table"] == "education_history"][-1]
    assert hist["education_code"] != EDU_ACTIVE
    assert hist["education_code"] == CODE


# ── EDUCATION RETRY (v1 same-day dedup, not global unique) ────────────────

def test_E13_first_complete_created_insert_1(client, fake):
    r = _edu(client)
    assert r.status_code == 200
    assert r.json()["data"]["mode"] == "CREATED"
    assert len([i for i in fake.inserts if i["table"] == "education_history"]) == 1


def test_E14_same_day_retry_replay_insert_0(client, fake):
    first = _edu(client)
    assert first.status_code == 200 and first.json()["data"]["mode"] == "CREATED"
    hid = first.json()["data"]["id"]
    second = _edu(client)
    assert second.status_code == 200
    assert second.json()["data"]["mode"] == "REPLAY"
    assert second.json()["data"]["id"] == hid
    assert len([i for i in fake.inserts if i["table"] == "education_history"]) == 1


def test_E15_same_code_other_date_not_globally_blocked(client, fake):
    fake.tables["education_history"].append({
        "id": "hist-old",
        "user_id": USER,
        "education_code": CODE,
        "completed_at": "2020-01-01",
        "status_code": "COMPLETED",
    })
    r = _edu(client)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["mode"] == "CREATED"
    assert r.json()["data"]["id"] != "hist-old"
    assert len([i for i in fake.inserts if i["table"] == "education_history"]) == 1


# ── SIGNATURE ─────────────────────────────────────────────────────────────

def test_E16_valid_png_signature_ok(client, fake):
    r = _edu(client, signature_data=_png_data_url())
    assert r.status_code == 200, r.text
    ups = [u for u in fake.uploads if u["path"].startswith("signatures/education/")]
    assert len(ups) == 1
    assert ups[0]["path"].endswith(".png")
    hist = [i["row"] for i in fake.inserts if i["table"] == "education_history"][-1]
    assert hist["memo"].startswith("작업자 확인 서명: storage://company-docs/signatures/education/")
    assert "signed" not in hist["memo"]
    assert "http" not in hist["memo"]


def test_E17_invalid_base64_rejected(client, fake):
    r = _edu(client, signature_data="data:image/png;base64,!!!!not-base64!!!!")
    assert r.status_code in (400, 422)
    assert fake.inserts == []
    assert fake.uploads == []


def test_E18_non_png_signature_415(client, fake):
    r = _edu(client, signature_data=_png_data_url(JPEG))
    assert r.status_code == 415
    assert fake.inserts == []


def test_E19_oversize_signature_413(client, fake):
    raw = PNG[:8] + b"\x00" * (MAX_SIZE + 1)
    r = _edu(client, signature_data=_png_data_url(raw))
    assert r.status_code == 413
    assert fake.inserts == []


# ── REV-1 PHOTO PERSISTENCE CONTRACT ──────────────────────────────────────

def test_rev1_R1_context_inspection_accepted(client, fake):
    r = _photo(client, context="inspection", inspection_id=None)
    assert r.status_code == 200, r.text
    path = fake.uploads[0]["path"]
    assert path.startswith("worker-photos/inspection/")


def test_rev1_R2_context_report_accepted(client, fake):
    r = _photo(client, context="report", inspection_id=None)
    assert r.status_code == 200, r.text
    path = fake.uploads[0]["path"]
    assert path.startswith("worker-photos/report/")


def test_rev1_R3_context_inspect_rejected(client, fake):
    r = _photo(client, context="inspect")
    assert r.status_code == 422
    assert fake.uploads == []


def test_rev1_R4_context_construction_inspect_rejected(client, fake):
    r = _photo(client, context="construction_inspect")
    assert r.status_code == 422
    assert fake.uploads == []


def test_rev1_R5_stable_ref_exact_storage_prefix(client, fake):
    r = _photo(client)
    assert r.status_code == 200
    path = fake.uploads[0]["path"]
    assert r.json()["url"] == "storage://company-docs/%s" % path


def test_rev1_R6_attachments_file_url_is_stable_ref(client, fake):
    r = _photo(client)
    assert r.status_code == 200
    att = [i["row"] for i in fake.inserts if i["table"] == "attachments"][-1]
    path = fake.uploads[0]["path"]
    assert att["file_url"] == "storage://company-docs/%s" % path


def test_rev1_R7_top_level_url_is_stable_ref(client, fake):
    r = _photo(client)
    assert r.status_code == 200
    assert r.json()["url"].startswith("storage://company-docs/")


def test_rev1_R8_data_url_is_stable_ref(client, fake):
    r = _photo(client)
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["url"] == body["url"]
    assert body["data"]["url"].startswith("storage://company-docs/")


def test_rev1_R9_data_preview_url_is_signed(client):
    r = _photo(client)
    assert r.status_code == 200
    preview = r.json()["data"]["preview_url"]
    assert preview.startswith("https://signed.example/")


def test_rev1_R10_signed_preview_failure_is_nonfatal(fake, monkeypatch):
    fake.fail_sign = True
    client = _app(CALLER, fake, monkeypatch)
    r = _photo(client)
    assert r.status_code == 200, r.text
    body = r.json()
    path = fake.uploads[0]["path"]
    stable = "storage://company-docs/%s" % path
    assert body["url"] == stable
    assert body["data"]["url"] == stable
    assert body["data"]["preview_url"] in (None, "")
    att = [i["row"] for i in fake.inserts if i["table"] == "attachments"][-1]
    assert att["file_url"] == stable


def test_rev1_R11_attachments_do_not_store_signed_url(client, fake):
    r = _photo(client)
    assert r.status_code == 200
    att = [i["row"] for i in fake.inserts if i["table"] == "attachments"][-1]
    assert "signed" not in att["file_url"]
    assert "http" not in att["file_url"]
    assert att["file_url"].startswith("storage://company-docs/")


def test_rev1_R12_education_signature_memo_storage_ref(client, fake):
    r = _edu(client, signature_data=_png_data_url())
    assert r.status_code == 200, r.text
    hist = [i["row"] for i in fake.inserts if i["table"] == "education_history"][-1]
    assert hist["memo"].startswith("작업자 확인 서명: storage://company-docs/signatures/education/")
    assert "signed" not in hist["memo"]
    assert "http" not in hist["memo"]


# ── REGRESSION: GET /work-assignments/{id}/items ──────────────────────────

def test_R1_items_no_token_401(fake, monkeypatch):
    monkeypatch.setattr(wa, "get_supabase", lambda: fake)
    monkeypatch.setattr(iss_items, "get_supabase", lambda: fake)
    app = FastAPI()
    app.include_router(wa.router)
    client = TestClient(app)
    r = client.get("/work-assignments/%s/items" % WA_OWN)
    assert r.status_code == 401


def test_R2_items_own_assignment_200(client):
    r = client.get("/work-assignments/%s/items" % WA_OWN)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "success"
    assert r.json()["data"]["items"][0]["item_name"] == "소화기"


def test_R3_items_foreign_assignment_403(client):
    r = client.get("/work-assignments/%s/items" % WA_OTHER)
    assert r.status_code == 403


def test_R4_items_missing_404(client):
    r = client.get("/work-assignments/wa-missing/items")
    assert r.status_code == 404


def test_contract_photo_response_shape(client):
    r = _photo(client)
    body = r.json()
    assert set(body) >= {"status", "url", "data"}
    assert set(body["data"]) >= {"url", "preview_url", "file_name", "size"}


def test_contract_edu_response_shape(client):
    r = _edu(client)
    body = r.json()
    assert body["status"] == "success"
    assert "message" in body
    assert set(body["data"]) >= {"id", "education_code", "completed_at"}


def test_does_not_import_private_validate_or_wrong_bucket_uploader():
    src = inspect.getsource(wa)
    assert "validate_image_file" in src
    assert "_validate_file" not in src
    assert "upload_service.upload_inspection_photo" not in src
    assert "get_public_url" not in src
