"""
WO-REF05-REF09-INTEGRATION-P0-REPAIR-007 — Reference Forms contract tests
WO-REF05-REF09-INTEGRATION-FINAL-P0-008 — P0-1 storage ref + P0-2 approval binding
WO-REF05-REF09-FINAL-GATE-CLOSE-010 — related form rights filter + sanitizer edge cases

10 original test cases:
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

P0-008 additions:
  T11 Storage ref parsing — correct path extracted; wrong bucket → 500; traversal → 500
  T12 Approval binding — file not in approved_file_hashes → 404; SHA mismatch → 404;
      no current approval record → 404; approval query error → 503

Gate-010 additions:
  T13 Related form rights filter — REVIEW_REQUIRED source excluded; no source excluded;
      mix of CLEARED + REVIEW_REQUIRED → only CLEARED returned; sources query fail → []
  (HTML sanitizer edge cases are in tests/test_html_sanitize.mjs — Node.js test)

WO-WWW-B2-REF-THUMB-STAGE1-IMPLEMENTATION-004 additions:
  T01-T09 thumbnail endpoint tests (see bottom of file)

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

# P0-1: file_ref and preview_ref use storage:// prefix (PR #594 contract)
_FILE_ROW = {
    "id": _FILE_ID,
    "form_id": _FORM_ID,
    "file_ref": "storage://reference-forms/forms/safety-training.pdf",
    "sha256": _SHA256,
    "is_active": True,
    "qa_status": "QA_PASS",
    "approved_at": "2026-10-11T00:00:00+00:00",
    "preview_artifact_id": _PREVIEW_ID,
}
_PREVIEW_ROW = {
    "id": _PREVIEW_ID,
    "form_id": _FORM_ID,
    "preview_ref": "storage://reference-forms-preview/previews/safety-training-p1.jpg",
    "source_file_sha256": _SHA256,
    "is_published": True,
    "qa_status": "QA_PASS",
}

# P0-2: current APPROVED approval record with approved_file_hashes
_APPROVAL_ROW = {
    "form_id": _FORM_ID,
    "approved_file_hashes": [
        {"file_id": _FILE_ID, "sha256": _SHA256}
    ],
}

_PDF_BYTES = b"%PDF-1.4 fake"
_REVIEW_REQUIRED_SOURCE = {"source_name": "고용노동부", "rights_status": "REVIEW_REQUIRED"}


def _make_sb(*, view_rows=None, source_rows=None, content_rows=None, file_rows=None,
             preview_rows=None, related_rows=None, approval_rows=None,
             storage_url="https://signed.example/file",
             storage_error=False, view_error=False, source_error=False,
             approval_error=False):
    """Build a controlled mock Supabase client."""
    sb = MagicMock()

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
        elif name == "reference_form_approvals":
            if approval_error:
                t.execute.side_effect = Exception("approval error")
            else:
                res = MagicMock()
                res.data = approval_rows if approval_rows is not None else [_APPROVAL_ROW]
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


# ---------------------------------------------------------------------------
# T11: P0-1 — Storage ref parsing
# ---------------------------------------------------------------------------

def test_t11_storage_ref_correct_path_extracted():
    """Valid storage:// ref → signed URL called with bucket-relative path."""
    sb = _make_sb(view_rows=[_VIEW_ROW])
    app = _app(sb, user_override=_AUTHED_USER)

    with patch("routers.reference_forms.httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.content = _PDF_BYTES
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        res = _client(app).get(f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download")

    assert res.status_code == 200
    # Verify create_signed_url received the relative path (not storage:// form)
    bucket_mock = sb.storage.from_.return_value
    call_args = bucket_mock.create_signed_url.call_args
    assert call_args is not None
    path_arg = call_args[0][0] if call_args[0] else call_args[1].get("path", "")
    assert path_arg == "forms/safety-training.pdf"
    assert not path_arg.startswith("storage://")


def test_t11_missing_storage_prefix_download_500():
    """file_ref without storage:// prefix → 500 (DB data contract violation)."""
    bad_file = {**_FILE_ROW, "file_ref": "forms/safety-training.pdf"}
    sb = _make_sb(view_rows=[_VIEW_ROW], file_rows=[bad_file])
    app = _app(sb, user_override=_AUTHED_USER)
    res = _client(app).get(f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download")
    assert res.status_code == 500


def test_t11_wrong_bucket_download_500():
    """file_ref pointing to unexpected bucket → 500."""
    bad_file = {**_FILE_ROW, "file_ref": "storage://wrong-bucket/forms/safety-training.pdf"}
    sb = _make_sb(view_rows=[_VIEW_ROW], file_rows=[bad_file])
    app = _app(sb, user_override=_AUTHED_USER)
    res = _client(app).get(f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download")
    assert res.status_code == 500


def test_t11_traversal_in_storage_ref_download_500():
    """file_ref with .. traversal → 500."""
    bad_file = {**_FILE_ROW, "file_ref": "storage://reference-forms/../secrets/key.pem"}
    sb = _make_sb(view_rows=[_VIEW_ROW], file_rows=[bad_file])
    app = _app(sb, user_override=_AUTHED_USER)
    res = _client(app).get(f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download")
    assert res.status_code == 500


def test_t11_wrong_bucket_preview_500():
    """preview_ref pointing to wrong bucket → 500."""
    bad_pa = {**_PREVIEW_ROW, "preview_ref": "storage://reference-forms/wrong/file.jpg"}
    sb = _make_sb(view_rows=[_VIEW_ROW], preview_rows=[bad_pa])
    c = _client(_app(sb))
    res = c.get(f"/reference-forms/{_SLUG}/preview/{_FILE_ID}")
    assert res.status_code == 500


# ---------------------------------------------------------------------------
# T12: P0-2 — Approval binding (TOCTOU guard)
# ---------------------------------------------------------------------------

def test_t12_file_not_in_approved_hashes_download_404():
    """File not in approved_file_hashes → 404 even if view + file row pass."""
    no_hash_approval = {**_APPROVAL_ROW, "approved_file_hashes": []}
    sb = _make_sb(view_rows=[_VIEW_ROW], approval_rows=[no_hash_approval])
    app = _app(sb, user_override=_AUTHED_USER)
    res = _client(app).get(f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download")
    assert res.status_code == 404


def test_t12_sha_mismatch_in_approved_hashes_download_404():
    """SHA in approved_file_hashes changed post-approval → 404."""
    stale_hash_approval = {
        **_APPROVAL_ROW,
        "approved_file_hashes": [{"file_id": _FILE_ID, "sha256": "changed-sha256"}],
    }
    sb = _make_sb(view_rows=[_VIEW_ROW], approval_rows=[stale_hash_approval])
    app = _app(sb, user_override=_AUTHED_USER)
    res = _client(app).get(f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download")
    assert res.status_code == 404


def test_t12_no_current_approval_record_download_404():
    """No current APPROVED approval record → 404."""
    sb = _make_sb(view_rows=[_VIEW_ROW], approval_rows=[])
    app = _app(sb, user_override=_AUTHED_USER)
    res = _client(app).get(f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download")
    assert res.status_code == 404


def test_t12_approval_query_error_503():
    """Approval query failure → 503."""
    sb = _make_sb(view_rows=[_VIEW_ROW], approval_error=True)
    app = _app(sb, user_override=_AUTHED_USER)
    res = _client(app).get(f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download")
    assert res.status_code == 503


def test_t12_approval_binding_preview_404():
    """Approval revoked between view load and preview serve → 404 on preview."""
    no_hash_approval = {**_APPROVAL_ROW, "approved_file_hashes": []}
    sb = _make_sb(view_rows=[_VIEW_ROW], approval_rows=[no_hash_approval])
    c = _client(_app(sb))
    res = c.get(f"/reference-forms/{_SLUG}/preview/{_FILE_ID}")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# T13: Gate-010 — Related form rights filter (_load_related_forms)
# Tests call the function directly to avoid mock ambiguity between
# _check_sources_cleared (.eq) and the batch sources query (.in_).
# ---------------------------------------------------------------------------

_RELATED_ID_A = "ff000000-0000-0000-0000-000000000010"
_RELATED_ID_B = "ff000000-0000-0000-0000-000000000011"


def _make_related_sb(*, view_rows, sources_data, sources_error=False):
    """Minimal mock for _load_related_forms unit tests."""
    sb = MagicMock()

    def _table_side_effect(name):
        t = MagicMock()
        t.select = MagicMock(return_value=t)
        t.eq = MagicMock(return_value=t)
        t.in_ = MagicMock(return_value=t)
        t.limit = MagicMock(return_value=t)

        if name == "reference_form_relations":
            res = MagicMock()
            res.data = [
                {"related_form_id": _RELATED_ID_A},
                {"related_form_id": _RELATED_ID_B},
            ]
            t.execute.return_value = res
        elif name == "reference_form_public_view":
            res = MagicMock()
            res.data = view_rows
            t.execute.return_value = res
        elif name == "reference_form_sources":
            if sources_error:
                t.execute.side_effect = Exception("sources error")
            else:
                res = MagicMock()
                res.data = sources_data
                t.execute.return_value = res
        return t

    sb.table.side_effect = _table_side_effect
    return sb


def test_t13_related_cleared_source_included():
    """Related form with CLEARED source → appears in result."""
    from routers.reference_forms import _load_related_forms
    sb = _make_related_sb(
        view_rows=[{"id": _RELATED_ID_A, "canonical_slug": "form-a", "title": "Form A"}],
        sources_data=[{"form_id": _RELATED_ID_A, "rights_status": "CLEARED"}],
    )
    result = _load_related_forms(sb, _FORM_ID)
    assert len(result) == 1
    assert result[0]["slug"] == "form-a"


def test_t13_related_review_required_source_excluded():
    """Related form with REVIEW_REQUIRED source → excluded."""
    from routers.reference_forms import _load_related_forms
    sb = _make_related_sb(
        view_rows=[{"id": _RELATED_ID_A, "canonical_slug": "form-a", "title": "Form A"}],
        sources_data=[{"form_id": _RELATED_ID_A, "rights_status": "REVIEW_REQUIRED"}],
    )
    result = _load_related_forms(sb, _FORM_ID)
    assert result == []


def test_t13_related_no_active_source_excluded():
    """Related form with no active source → excluded (empty sources_data)."""
    from routers.reference_forms import _load_related_forms
    sb = _make_related_sb(
        view_rows=[{"id": _RELATED_ID_A, "canonical_slug": "form-a", "title": "Form A"}],
        sources_data=[],
    )
    result = _load_related_forms(sb, _FORM_ID)
    assert result == []


def test_t13_related_mixed_cleared_and_blocked():
    """One CLEARED form, one REVIEW_REQUIRED form → only CLEARED returned."""
    from routers.reference_forms import _load_related_forms
    sb = _make_related_sb(
        view_rows=[
            {"id": _RELATED_ID_A, "canonical_slug": "form-cleared", "title": "Cleared"},
            {"id": _RELATED_ID_B, "canonical_slug": "form-blocked", "title": "Blocked"},
        ],
        sources_data=[
            {"form_id": _RELATED_ID_A, "rights_status": "CLEARED"},
            {"form_id": _RELATED_ID_B, "rights_status": "REVIEW_REQUIRED"},
        ],
    )
    result = _load_related_forms(sb, _FORM_ID)
    assert len(result) == 1
    assert result[0]["slug"] == "form-cleared"


def test_t13_related_sources_query_error_fail_closed():
    """Sources query failure for related forms → fail-closed, return []."""
    from routers.reference_forms import _load_related_forms
    sb = _make_related_sb(
        view_rows=[{"id": _RELATED_ID_A, "canonical_slug": "form-a", "title": "Form A"}],
        sources_data=[],
        sources_error=True,
    )
    result = _load_related_forms(sb, _FORM_ID)
    assert result == []


# ---------------------------------------------------------------------------
# Thumbnail endpoint fixtures (WO-WWW-B2-REF-THUMB-STAGE1-IMPLEMENTATION-004)
# Do NOT modify legacy _PREVIEW_ROW (.jpg) or _PDF_BYTES above.
# ---------------------------------------------------------------------------

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PNG_BYTES = _PNG_MAGIC + b"\x00" * 50  # minimal valid fixture (magic + padding)

# View row with has_preview=True + format='pdf' in qa_pass_files (thumbnail gate G3)
_THUMB_VIEW_ROW = {
    **_VIEW_ROW,
    "qa_pass_files": [
        {
            "file_id": _FILE_ID,
            "sha256": _SHA256,
            "approved_at": "2026-10-11T00:00:00+00:00",
            "has_preview": True,
            "format": "pdf",
        }
    ],
}

# Preview artifact with .png path (distinct from legacy _PREVIEW_ROW which uses .jpg)
_THUMB_PREVIEW_ROW = {
    "form_id": _FORM_ID,
    "preview_ref": "storage://reference-forms-preview/previews/safety-training-p1.png",
    "source_file_sha256": _SHA256,
    "is_published": True,
    "qa_status": "QA_PASS",
}

# File row with explicit approved_at (thumbnail gate G4 requires IS NOT NULL)
_THUMB_FILE_ROW = {
    **_FILE_ROW,
    "approved_at": "2026-10-11T00:00:00+00:00",
}

_THUMBNAIL_MAX_BYTES = 512 * 1024  # mirror for size assertion in T07


def _mock_thumb_stream(*, content_type="image/png", chunks=None, raise_on_status=False,
                       raise_fetch=False):
    """Build a controlled httpx.stream mock context manager for thumbnail tests."""
    mock_ctx = MagicMock()
    mock_ctx.headers = {"content-type": content_type}
    if raise_on_status:
        mock_ctx.raise_for_status.side_effect = Exception("http error")
    else:
        mock_ctx.raise_for_status = MagicMock()
    mock_ctx.iter_bytes = MagicMock(return_value=iter(chunks if chunks is not None else [_PNG_BYTES]))

    mock_stream = MagicMock()
    if raise_fetch:
        mock_stream.side_effect = Exception("network error")
    else:
        mock_stream.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_stream.return_value.__exit__ = MagicMock(return_value=False)
    return mock_stream


def _thumb_sb(**kwargs):
    """Shorthand: _make_sb with thumbnail-appropriate defaults."""
    defaults = dict(
        view_rows=[_THUMB_VIEW_ROW],
        file_rows=[_THUMB_FILE_ROW],
        preview_rows=[_THUMB_PREVIEW_ROW],
        approval_rows=[_APPROVAL_ROW],
    )
    defaults.update(kwargs)
    return _make_sb(**defaults)


# ---------------------------------------------------------------------------
# T01: 200 PNG response — magic bytes, no-store, nosniff
# ---------------------------------------------------------------------------

def test_t01_thumb_200_png_magic_and_headers():
    """Valid ref slug → 200, image/png, Cache-Control: no-store, X-Content-Type-Options: nosniff."""
    sb = _thumb_sb()
    app = _app(sb)
    with patch("routers.reference_forms.httpx.stream", _mock_thumb_stream()):
        res = _client(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert res.status_code == 200, res.text
    assert res.headers.get("content-type") == "image/png"
    assert res.headers.get("cache-control") == "no-store"
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.content[:8] == _PNG_MAGIC


def test_t01_thumb_200_body_matches_png_bytes():
    """Response body matches the controlled PNG fixture bytes."""
    sb = _thumb_sb()
    app = _app(sb)
    with patch("routers.reference_forms.httpx.stream", _mock_thumb_stream()):
        res = _client(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert res.content == _PNG_BYTES


# ---------------------------------------------------------------------------
# T02: 404 — unknown slug, unpublished, uncleared source
# ---------------------------------------------------------------------------

def test_t02_thumb_unknown_slug_404():
    sb = _thumb_sb(view_rows=[])
    c = _client(_app(sb))
    assert c.get("/reference-forms/nonexistent-slug/thumbnail").status_code == 404


def test_t02_thumb_unpublished_404():
    """View returns no row for unpublished form."""
    sb = _thumb_sb(view_rows=[])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t02_thumb_uncleared_source_404():
    sb = _thumb_sb(source_rows=[_REVIEW_REQUIRED_SOURCE])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


# ---------------------------------------------------------------------------
# T03: 404 — no has_preview, non-PDF format, missing approved_at in qa_pass_files
# ---------------------------------------------------------------------------

def test_t03_thumb_no_has_preview_404():
    """qa_pass_files entry with has_preview=False → no candidates → 404."""
    vr = {**_THUMB_VIEW_ROW, "qa_pass_files": [{
        "file_id": _FILE_ID, "sha256": _SHA256,
        "approved_at": "2026-10-11T00:00:00+00:00",
        "has_preview": False, "format": "pdf",
    }]}
    sb = _thumb_sb(view_rows=[vr])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t03_thumb_non_pdf_format_404():
    """qa_pass_files entry with format='hwp' → no candidates → 404."""
    vr = {**_THUMB_VIEW_ROW, "qa_pass_files": [{
        "file_id": _FILE_ID, "sha256": _SHA256,
        "approved_at": "2026-10-11T00:00:00+00:00",
        "has_preview": True, "format": "hwp",
    }]}
    sb = _thumb_sb(view_rows=[vr])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t03_thumb_missing_approved_at_in_qa_files_404():
    """qa_pass_files entry without approved_at → no candidates → 404."""
    vr = {**_THUMB_VIEW_ROW, "qa_pass_files": [{
        "file_id": _FILE_ID, "sha256": _SHA256,
        "has_preview": True, "format": "pdf",
    }]}
    sb = _thumb_sb(view_rows=[vr])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t03_thumb_empty_qa_pass_files_404():
    """qa_pass_files empty list → 404."""
    vr = {**_THUMB_VIEW_ROW, "qa_pass_files": []}
    sb = _thumb_sb(view_rows=[vr])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


# ---------------------------------------------------------------------------
# T04: 404 — file row inactive, no approved_at, qa_status not QA_PASS
# ---------------------------------------------------------------------------

def test_t04_thumb_inactive_file_404():
    fr = {**_THUMB_FILE_ROW, "is_active": False}
    sb = _thumb_sb(file_rows=[fr])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t04_thumb_file_qa_fail_404():
    fr = {**_THUMB_FILE_ROW, "qa_status": "QA_FAIL"}
    sb = _thumb_sb(file_rows=[fr])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t04_thumb_file_no_approved_at_404():
    fr = {**_THUMB_FILE_ROW, "approved_at": None}
    sb = _thumb_sb(file_rows=[fr])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t04_thumb_no_preview_artifact_id_404():
    fr = {**_THUMB_FILE_ROW, "preview_artifact_id": None}
    sb = _thumb_sb(file_rows=[fr])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


# ---------------------------------------------------------------------------
# T05: 404 — SHA mismatch, revoked approval, cross-form
# ---------------------------------------------------------------------------

def test_t05_thumb_file_sha_mismatch_404():
    """file_row.sha256 != qa_pass_files.sha256 → 404."""
    fr = {**_THUMB_FILE_ROW, "sha256": "different-sha256"}
    sb = _thumb_sb(file_rows=[fr])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t05_thumb_artifact_sha_mismatch_404():
    """preview_artifact.source_file_sha256 != qa sha → 404."""
    pa = {**_THUMB_PREVIEW_ROW, "source_file_sha256": "wrong-sha"}
    sb = _thumb_sb(preview_rows=[pa])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t05_thumb_revoked_approval_404():
    """approved_file_hashes empty (approval revoked) → 404."""
    no_hash = {**_APPROVAL_ROW, "approved_file_hashes": []}
    sb = _thumb_sb(approval_rows=[no_hash])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t05_thumb_cross_form_artifact_404():
    """preview_artifact.form_id != current form_id → 404."""
    pa = {**_THUMB_PREVIEW_ROW, "form_id": _OTHER_FORM_ID}
    sb = _thumb_sb(preview_rows=[pa])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t05_thumb_artifact_not_published_404():
    pa = {**_THUMB_PREVIEW_ROW, "is_published": False}
    sb = _thumb_sb(preview_rows=[pa])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


def test_t05_thumb_artifact_qa_fail_404():
    pa = {**_THUMB_PREVIEW_ROW, "qa_status": "QA_FAIL"}
    sb = _thumb_sb(preview_rows=[pa])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 404


# ---------------------------------------------------------------------------
# T06: storage ref — bad bucket, traversal → fail closed (500)
# ---------------------------------------------------------------------------

def test_t06_thumb_bad_storage_bucket_500():
    pa = {**_THUMB_PREVIEW_ROW, "preview_ref": "storage://wrong-bucket/previews/p1.png"}
    sb = _thumb_sb(preview_rows=[pa])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 500


def test_t06_thumb_traversal_500():
    pa = {**_THUMB_PREVIEW_ROW, "preview_ref": "storage://reference-forms-preview/../secrets/key"}
    sb = _thumb_sb(preview_rows=[pa])
    c = _client(_app(sb))
    assert c.get(f"/reference-forms/{_SLUG}/thumbnail").status_code == 500


# ---------------------------------------------------------------------------
# T07: PNG content validation — MIME mismatch, magic mismatch, zero-length, oversized → 502
# ---------------------------------------------------------------------------

def test_t07_thumb_mime_mismatch_502():
    sb = _thumb_sb()
    app = _app(sb)
    with patch("routers.reference_forms.httpx.stream",
               _mock_thumb_stream(content_type="application/pdf")):
        res = _client(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert res.status_code == 502


def test_t07_thumb_magic_mismatch_502():
    """Valid PNG MIME but body has wrong magic bytes → 502."""
    bad_body = b"\x00\x00\x00\x00bad" + b"\x00" * 50
    sb = _thumb_sb()
    app = _app(sb)
    with patch("routers.reference_forms.httpx.stream",
               _mock_thumb_stream(chunks=[bad_body])):
        res = _client(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert res.status_code == 502


def test_t07_thumb_zero_length_502():
    """Empty body → 502 (MIME mismatch path)."""
    sb = _thumb_sb()
    app = _app(sb)
    with patch("routers.reference_forms.httpx.stream",
               _mock_thumb_stream(chunks=[b""])):
        res = _client(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert res.status_code == 502


def test_t07_thumb_oversized_502():
    """Body exceeding 512 KiB enforced during receive → 502 THUMBNAIL_TOO_LARGE."""
    # One chunk just over the limit
    oversized_chunk = _PNG_MAGIC + b"\x00" * (_THUMBNAIL_MAX_BYTES + 1)
    sb = _thumb_sb()
    app = _app(sb)
    with patch("routers.reference_forms.httpx.stream",
               _mock_thumb_stream(chunks=[oversized_chunk])):
        res = _client(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert res.status_code == 502
    assert "THUMBNAIL_TOO_LARGE" in res.text


# ---------------------------------------------------------------------------
# T08: storage and DB transient errors → 502/503; no sensitive data in response
# ---------------------------------------------------------------------------

def test_t08_thumb_db_error_503():
    """View query failure → 503."""
    sb = _thumb_sb(view_error=True)
    c = _client(_app(sb))
    res = c.get(f"/reference-forms/{_SLUG}/thumbnail")
    assert res.status_code == 503
    for secret in ("storage://", "reference-forms-preview", _SHA256):
        assert secret not in res.text


def test_t08_thumb_signed_url_error_503():
    """Storage signed URL failure → 503."""
    sb = _thumb_sb(storage_error=True)
    c = _client(_app(sb))
    res = c.get(f"/reference-forms/{_SLUG}/thumbnail")
    assert res.status_code == 503


def test_t08_thumb_fetch_network_error_502():
    """httpx.stream network error → 502."""
    sb = _thumb_sb()
    app = _app(sb)
    with patch("routers.reference_forms.httpx.stream",
               _mock_thumb_stream(raise_fetch=True)):
        res = _client(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert res.status_code == 502


# ---------------------------------------------------------------------------
# T09: Route uniqueness — 4 routes registered, none shadow each other
# ---------------------------------------------------------------------------

def test_t09_four_routes_registered_no_conflict():
    """Route table has all 4 endpoints; thumbnail path does not shadow detail/preview/download."""
    from fastapi import FastAPI as _FA
    app = _FA()
    app.include_router(router)

    route_map = {
        r.path: set(r.methods)
        for r in app.routes
        if hasattr(r, "methods") and hasattr(r, "path")
    }
    expected = [
        "/reference-forms/{slug}",
        "/reference-forms/{slug}/thumbnail",
        "/reference-forms/{slug}/preview/{file_id}",
        "/reference-forms/{slug}/files/{file_id}/download",
    ]
    for path in expected:
        assert path in route_map, f"Route not registered: {path}"
        assert "GET" in route_map[path], f"GET method missing for {path}"


def test_t09_detail_route_returns_json():
    """GET /{slug} reaches the detail handler (JSON response)."""
    sb = _thumb_sb()
    res = _client(_app(sb)).get(f"/reference-forms/{_SLUG}")
    assert res.status_code == 200
    assert res.headers.get("content-type", "").startswith("application/json")
    assert res.json()["status"] == "ok"


def test_t09_thumbnail_route_returns_png():
    """GET /{slug}/thumbnail reaches the thumbnail handler (PNG response)."""
    sb = _thumb_sb()
    app = _app(sb)
    with patch("routers.reference_forms.httpx.stream", _mock_thumb_stream()):
        res = _client(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert res.status_code == 200
    assert res.headers.get("content-type") == "image/png"


def test_t09_preview_route_returns_binary():
    """GET /{slug}/preview/{file_id} reaches the preview handler (binary response)."""
    # Use standard _VIEW_ROW (legacy qa_pass_files without has_preview/format) for preview
    sb = _make_sb(view_rows=[_VIEW_ROW])
    app = _app(sb)
    with patch("routers.reference_forms.httpx.get") as mock_get:
        mr = MagicMock()
        mr.content = _PDF_BYTES
        mr.headers = {"content-type": "application/pdf"}
        mr.raise_for_status = MagicMock()
        mock_get.return_value = mr
        res = _client(app).get(f"/reference-forms/{_SLUG}/preview/{_FILE_ID}")
    assert res.status_code == 200
    assert res.content == _PDF_BYTES


def test_t09_download_route_requires_auth():
    """GET /{slug}/files/{file_id}/download reaches the download handler (401 without auth)."""
    sb = _make_sb(view_rows=[_VIEW_ROW])
    res = _client(_app(sb)).get(f"/reference-forms/{_SLUG}/files/{_FILE_ID}/download")
    assert res.status_code == 401
