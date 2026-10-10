"""
WO-REF05-REF09-INTEGRATION-P0-REPAIR-007 — Reference Forms contract tests

10 test cases:
  T1  Published + CLEARED → 200 with correct shape
  T2  Unpublished / uncleared source → 404
  T3  View absent (DB schema not applied) → 503
  T4  Approved preview with SHA match → 200 binary
  T5  Unapproved / SHA-mismatch preview → 404
  T6  Anonymous download → 401
  T7  Authenticated download → 200 binary + correct filename
  T8  Cross-form file_id in download → 403 / 404
  T9  Unpublished (view row gone) → all 3 endpoints 404
  T10 Storage path / approval ID not in public detail response

Mock strategy: replace the 3 supabase helpers with controlled fakes.
Integration path: set REFERENCE_FORM_TEST_DB_URL to run against isolated Postgres
  with PR #594 migrations applied.
"""
from __future__ import annotations

import io
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.reference_forms import router

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FORM_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_SLUG = "safety-training-record"
_FILE_ID = "bbbbbbbb-0000-0000-0000-000000000002"
_SHA256 = "abc123def456" * 5  # 60-char fake hex
_PREVIEW_ID = "cccccccc-0000-0000-0000-000000000003"
_OTHER_FORM_ID = "dddddddd-0000-0000-0000-000000000004"

_VIEW_ROW = {
    "id": _FORM_ID,
    "canonical_slug": _SLUG,
    "title": "근로자 안전보건교육 일지",
    "description": "안전보건교육 일지 서식입니다.",
    "published_at": "2026-10-11T00:00:00+00:00",
    "updated_at": "2026-10-11T00:00:00+00:00",
    "approval_id": "ee000000-0000-0000-0000-000000000005",
    "content_approved": True,
    "qa_pass_files": [
        {"file_id": _FILE_ID, "sha256": _SHA256, "approved_at": "2026-10-11T00:00:00+00:00"}
    ],
    "formats": ["pdf"],
    "legacy_codes": [],
}

_SOURCE_ROW = {"source_name": "한국산업안전보건공단(KOSHA)", "rights_status": "CLEARED"}
_CONTENT_ROW = {"body_html": "<h2>작성 방법</h2><p>...</p>"}
_FILE_ROW = {
    "id": _FILE_ID,
    "form_id": _FORM_ID,
    "file_ref": "forms/safety-training.pdf",
    "sha256": _SHA256,
    "is_active": True,
    "qa_status": "QA_PASS",
    "approved_at": "2026-10-11T00:00:00+00:00",
    "preview_artifact_id": _PREVIEW_ID,
}
_PREVIEW_ROW = {
    "id": _PREVIEW_ID,
    "form_id": _FORM_ID,
    "preview_ref": "previews/safety-training-p1.jpg",
    "source_file_sha256": _SHA256,
    "is_published": True,
    "qa_status": "QA_PASS",
}
_PDF_BYTES = b"%PDF-1.4 fake"
_REVIEW_REQUIRED_SOURCE = {"source_name": "고용노동부", "rights_status": "REVIEW_REQUIRED"}


def _make_sb(*, view_rows=None, source_rows=None, content_rows=None, file_rows=None,
             preview_rows=None, related_rows=None, storage_url="https://signed.example/file",
             storage_error=False, view_error=False, source_error=False):
    """Build a controlled mock Supabase client."""
    sb = MagicMock()

    def _chain_result(rows, error=False):
        m = MagicMock()
        if error:
            m.execute.side_effect = Exception("DB error")
        else:
            result = MagicMock()
            result.data = rows
            m.execute.return_value = result
        return m

    def _table_side_effect(name):
        t = MagicMock()
        t.select = MagicMock(return_value=t)
        t.eq = MagicMock(return_value=t)
        t.in_ = MagicMock(return_value=t)
        t.limit = MagicMock(return_value=t)

        if name == "reference_form_public_view":
            if view_error:
                t.execute.side_effect = Exception("view error")
            else:
                res = MagicMock()
                res.data = view_rows if view_rows is not None else []
                t.execute.return_value = res
        elif name == "reference_form_sources":
            if source_error:
                t.execute.side_effect = Exception("sources error")
            else:
                res = MagicMock()
                res.data = source_rows if source_rows is not None else [_SOURCE_ROW]
                t.execute.return_value = res
        elif name == "reference_form_content":
            res = MagicMock()
            res.data = content_rows if content_rows is not None else [_CONTENT_ROW]
            t.execute.return_value = res
        elif name == "reference_form_files":
            res = MagicMock()
            res.data = file_rows if file_rows is not None else [_FILE_ROW]
            t.execute.return_value = res
        elif name == "reference_form_preview_artifacts":
            res = MagicMock()
            res.data = preview_rows if preview_rows is not None else [_PREVIEW_ROW]
            t.execute.return_value = res
        elif name == "reference_form_relations":
            res = MagicMock()
            res.data = related_rows if related_rows is not None else []
            t.execute.return_value = res
        else:
            t.execute.return_value = MagicMock(data=[])
        return t

    sb.table.side_effect = _table_side_effect

    # Storage
    bucket = MagicMock()
    if storage_error:
        bucket.create_signed_url.side_effect = Exception("storage error")
    else:
        bucket.create_signed_url.return_value = {"signedURL": storage_url}
    sb.storage.from_ = MagicMock(return_value=bucket)

    return sb


def _app(sb_override=None, user_override=None):
    """Build test FastAPI app with optional dependency overrides."""
    from db.supabase_client import get_supabase
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(router)

    if sb_override is not None:
        app.dependency_overrides[get_supabase] = lambda: sb_override
    if user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: user_override
    return app


_AUTHED_USER = {"id": "user-001", "email": "test@example.com", "status": "ACTIVE"}


def _client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# T1: Published + CLEARED → 200 with correct shape
# ---------------------------------------------------------------------------

def test_t1_published_cleared_200():
    sb = _make_sb(view_rows=[_VIEW_ROW])
    app = _app(sb)
    c = _client(app)
    res = c.get(f"/reference-forms/{_SLUG}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ok"
    d = body["data"]
    assert d["slug"] == _SLUG
    assert d["title"] == "근로자 안전보건교육 일지"
    assert d["source_name"] == "한국산업안전보건공단(KOSHA)"
    assert "body_html" in d
    assert "qa_pass_files" in d
    # T10 guard: storage paths and approval IDs must not appear
    assert "file_ref" not in str(d)
    assert "storage_path" not in str(d)
    assert "approval_id" not in str(d)
    assert "approved_content_hash" not in str(d)


# ---------------------------------------------------------------------------
# T2: Unpublished / uncleared source → 404
# ---------------------------------------------------------------------------

def test_t2_uncleared_source_404():
    sb = _make_sb(view_rows=[_VIEW_ROW], source_rows=[_REVIEW_REQUIRED_SOURCE])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}").status_code == 404


def test_t2_no_source_404():
    sb = _make_sb(view_rows=[_VIEW_ROW], source_rows=[])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}").status_code == 404


def test_t2_view_miss_404():
    sb = _make_sb(view_rows=[])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}").status_code == 404


# ---------------------------------------------------------------------------
# T3: View absent (DB schema not applied) → 503
# ---------------------------------------------------------------------------

def test_t3_view_error_503():
    sb = _make_sb(view_error=True)
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}").status_code == 503


def test_t3_source_error_503():
    sb = _make_sb(view_rows=[_VIEW_ROW], source_error=True)
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}").status_code == 503


# ---------------------------------------------------------------------------
# T4: Approved preview with SHA match → 200 binary
# ---------------------------------------------------------------------------

def test_t4_approved_preview_200():
    sb = _make_sb(view_rows=[_VIEW_ROW])
    app = _app(sb)
    img_bytes = b"\x89PNG\r\n"

    with patch("routers.reference_forms.httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.content = img_bytes
        mock_resp.headers = {"content-type": "image/png"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        res = _client(app).get(f"/reference-forms/{_SLUG}/preview/{_FILE_ID}")

    assert res.status_code == 200
    assert res.content == img_bytes
    assert res.headers.get("cache-control") == "no-store"


# ---------------------------------------------------------------------------
# T5: Unapproved / SHA-mismatch preview → 404
# ---------------------------------------------------------------------------

def test_t5_preview_file_not_in_qa_list():
    sb = _make_sb(view_rows=[_VIEW_ROW])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/preview/nonexistent-file-id").status_code == 404


def test_t5_preview_sha_mismatch():
    bad_file = {**_FILE_ROW, "sha256": "different-sha256"}
    sb = _make_sb(view_rows=[_VIEW_ROW], file_rows=[bad_file])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/preview/{_FILE_ID}").status_code == 404


def test_t5_preview_artifact_not_published():
    pa = {**_PREVIEW_ROW, "is_published": False}
    sb = _make_sb(view_rows=[_VIEW_ROW], preview_rows=[pa])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/preview/{_FILE_ID}").status_code == 404


def test_t5_preview_artifact_qa_fail():
    pa = {**_PREVIEW_ROW, "qa_status": "QA_FAIL"}
    sb = _make_sb(view_rows=[_VIEW_ROW], preview_rows=[pa])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/preview/{_FILE_ID}").status_code == 404


def test_t5_preview_source_file_sha_mismatch():
    pa = {**_PREVIEW_ROW, "source_file_sha256": "wrong-sha"}
    sb = _make_sb(view_rows=[_VIEW_ROW], preview_rows=[pa])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/preview/{_FILE_ID}").status_code == 404


# ---------------------------------------------------------------------------
# T6: Anonymous download → 401
# ---------------------------------------------------------------------------

def test_t6_anonymous_download_401():
    sb = _make_sb(view_rows=[_VIEW_ROW])
    c = _client(_app(sb))  # no user override → get_current_user raises 401
    res = c.get(f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# T7: Authenticated download → 200 binary + correct filename
# ---------------------------------------------------------------------------

def test_t7_authenticated_download_200():
    sb = _make_sb(view_rows=[_VIEW_ROW])
    app = _app(sb, user_override=_AUTHED_USER)

    with patch("routers.reference_forms.httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.content = _PDF_BYTES
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        res = _client(app).get(
            f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download"
        )

    assert res.status_code == 200
    assert res.content == _PDF_BYTES
    assert res.headers.get("cache-control") == "no-store"
    cd = res.headers.get("content-disposition", "")
    assert "safety-training.pdf" in cd


# ---------------------------------------------------------------------------
# T8: Cross-form file_id → 403 / 404
# ---------------------------------------------------------------------------

def test_t8_cross_form_file_id_in_download():
    """file_id in qa_pass_files but file_row.form_id is a different form → 403."""
    other_form_file = {**_FILE_ROW, "form_id": _OTHER_FORM_ID}
    sb = _make_sb(view_rows=[_VIEW_ROW], file_rows=[other_form_file])
    app = _app(sb, user_override=_AUTHED_USER)
    res = _client(app).get(
        f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download"
    )
    assert res.status_code in (403, 404)


def test_t8_file_not_in_qa_list_download():
    """file_id not in qa_pass_files → 404."""
    sb = _make_sb(view_rows=[_VIEW_ROW])
    app = _app(sb, user_override=_AUTHED_USER)
    res = _client(app).get(
        f"/reference-forms/{_SLUG}/files/unrelated-file-id/download"
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# T9: Unpublished → all 3 endpoints 404
# ---------------------------------------------------------------------------

def test_t9_unpublished_all_endpoints_404():
    sb = _make_sb(view_rows=[])  # view returns nothing (unpublished)
    app = _app(sb, user_override=_AUTHED_USER)
    c = _client(app)
    assert c.get(f"/reference-forms/{_SLUG}").status_code == 404
    assert c.get(f"/reference-forms/{_SLUG}/preview/{_FILE_ID}").status_code == 404
    assert c.get(f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download").status_code == 404


# ---------------------------------------------------------------------------
# T10: Storage paths + internal IDs never in public detail
# ---------------------------------------------------------------------------

def test_t10_no_internal_fields_in_response():
    sb = _make_sb(view_rows=[_VIEW_ROW])
    res = _client(_app(sb)).get(f"/reference-forms/{_SLUG}")
    assert res.status_code == 200
    raw = res.text
    for forbidden in ("file_ref", "storage_path", "preview_ref", "approval_id",
                      "approved_content_hash", "approved_file_hashes", "is_current"):
        assert forbidden not in raw, f"forbidden field '{forbidden}' found in response"
