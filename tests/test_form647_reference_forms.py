"""FORM647 Reference Forms integration tests
WO-TAI-FORM647-EXISTING-LIBRARY-INTEGRATION-001

Covers:
  F01  Gate BLOCKED → GET /reference-forms/f647-{ek} returns 404
  F02  Gate OPEN (mocked) → 200 detail with correct shape (licbyl HWP+PDF)
  F03  Gate OPEN (mocked) → 200 detail admbyl HWP-only
  F04  GET /reference-forms/f647-{ek}/files/hwp/download — no auth → 401
  F05  Authenticated HWP download, gate open → 200 binary + correct headers
  F06  Authenticated PDF download, gate open → 200 binary
  F07  HWP download on HWP-only form (admbyl) → 200; PDF → 404
  F08  Storage error → 500
  F09  File fetch error (httpx fail) → 502
  F10  Storage path not leaked in detail response
  F11  Existing 138-form slug bypasses f647 branch (no regression)
  F12  `f647-` slug skips reference_form_public_view query entirely

Mock strategy: patch get_form647_detail + form647_storage_path at import site,
  mock httpx.get for file proxy, mock Supabase storage for signed URL.
"""
from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.reference_forms import router

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EK_LIC = 15267319       # licbyl — HWP + PDF
_EK_ADM = 10000001       # admbyl — HWP only
_SLUG_LIC = f"f647-{_EK_LIC}"
_SLUG_ADM = f"f647-{_EK_ADM}"
_SLUG_EXISTING = "safety-training-record"  # existing 138-form slug (non-f647)

_DETAIL_LIC = {
    "ek": _EK_LIC,
    "frozen_name": "도급인의 안전·보건에 관한 정보 제공",
    "api_target": "licbyl",
    "file_types": ["HWP", "PDF"],
}
_DETAIL_ADM = {
    "ek": _EK_ADM,
    "frozen_name": "안전관리 계획서",
    "api_target": "admbyl",
    "file_types": ["HWP"],
}

_HWP_BYTES = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1fake-hwp-content"  # OLE2 header
_PDF_BYTES = b"%PDF-1.4 fake"
_SIGNED_URL = "https://signed.example/form-originals/file"


def _mock_httpx_resp(status_code: int, content: bytes, content_type: str) -> MagicMock:
    """Build a MagicMock that mimics httpx.Response for file proxy tests."""
    r = MagicMock()
    r.status_code = status_code
    r.content = content
    r.headers = {"content-type": content_type}
    if status_code >= 400:
        r.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=r
        )
    else:
        r.raise_for_status.return_value = None
    return r


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage_sb(url=_SIGNED_URL, error=False):
    """Build Supabase mock with only storage needed for download tests."""
    sb = MagicMock()
    sb.table.return_value = MagicMock(
        select=MagicMock(return_value=MagicMock(
            eq=MagicMock(return_value=MagicMock(
                limit=MagicMock(return_value=MagicMock(execute=MagicMock(return_value=MagicMock(data=[]))))
            ))
        ))
    )
    bucket = MagicMock()
    if error:
        bucket.create_signed_url.side_effect = Exception("storage error")
    else:
        bucket.create_signed_url.return_value = {"signedURL": url}
    sb.storage.from_ = MagicMock(return_value=bucket)
    return sb


def _make_view_sb():
    """Supabase mock that simulates no matching view row (for existing-form branch test)."""
    sb = MagicMock()

    def _table_side(name):
        t = MagicMock()
        t.select = MagicMock(return_value=t)
        t.eq = MagicMock(return_value=t)
        t.limit = MagicMock(return_value=t)
        res = MagicMock()
        res.data = []
        t.execute.return_value = res
        return t

    sb.table.side_effect = _table_side
    return sb


def _app(sb=None, user=None):
    from db.supabase_client import get_supabase
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    if sb is not None:
        app.dependency_overrides[get_supabase] = lambda: sb
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


_AUTHED_USER = {"id": "u-001", "email": "test@example.com", "status": "ACTIVE"}


def _client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# F01 — Gate BLOCKED → 404
# ---------------------------------------------------------------------------

def test_f01_gate_blocked_returns_404():
    with patch("routers.reference_forms.get_form647_detail", return_value=None):
        c = _client(_app(sb=_make_storage_sb()))
        r = c.get(f"/reference-forms/{_SLUG_LIC}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# F02 — Gate OPEN, licbyl → 200 detail shape (HWP + PDF)
# ---------------------------------------------------------------------------

def test_f02_gate_open_licbyl_detail_shape():
    with patch("routers.reference_forms.get_form647_detail", return_value=_DETAIL_LIC):
        c = _client(_app(sb=_make_storage_sb()))
        r = c.get(f"/reference-forms/{_SLUG_LIC}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    d = body["data"]
    assert d["slug"] == _SLUG_LIC
    assert d["title"] == _DETAIL_LIC["frozen_name"]
    assert d["source_name"] == "국가법령정보센터"
    assert d["description"] == "법령별 서식"
    formats = [f["format"] for f in d["qa_pass_files"]]
    assert "hwp" in formats
    assert "pdf" in formats
    # PDF should come first (ORDER: pdf=0, hwp=1)
    assert formats.index("pdf") < formats.index("hwp")
    assert d["related_forms"] == []
    # Storage paths must not appear in response
    assert "storage_path" not in str(d)
    assert "form-originals" not in str(d)
    assert "form647" not in str(d)


# ---------------------------------------------------------------------------
# F03 — Gate OPEN, admbyl → HWP only
# ---------------------------------------------------------------------------

def test_f03_gate_open_admbyl_hwp_only():
    with patch("routers.reference_forms.get_form647_detail", return_value=_DETAIL_ADM):
        c = _client(_app(sb=_make_storage_sb()))
        r = c.get(f"/reference-forms/{_SLUG_ADM}")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["description"] == "행정규칙별 서식"
    formats = [f["format"] for f in d["qa_pass_files"]]
    assert formats == ["hwp"]
    assert "pdf" not in formats


# ---------------------------------------------------------------------------
# F04 — HWP download without auth → 401
# ---------------------------------------------------------------------------

def test_f04_hwp_download_no_auth():
    with patch("routers.reference_forms.get_form647_detail", return_value=_DETAIL_LIC):
        app = _app(sb=_make_storage_sb())
        # No user override → dependency uses real get_current_user → 401
        c = _client(app)
        r = c.get(f"/reference-forms/{_SLUG_LIC}/files/hwp/download")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# F05 — Authenticated HWP download, gate open → 200 + correct headers
# ---------------------------------------------------------------------------

def test_f05_authenticated_hwp_download():
    mock_resp = _mock_httpx_resp(200, _HWP_BYTES, "application/x-hwp")
    with patch("routers.reference_forms.get_form647_detail", return_value=_DETAIL_LIC), \
         patch("routers.reference_forms.form647_storage_path",
               return_value="form647/run-id/hwp/15267319_licbyl.hwp"), \
         patch("httpx.get", return_value=mock_resp):
        c = _client(_app(sb=_make_storage_sb(), user=_AUTHED_USER))
        r = c.get(f"/reference-forms/{_SLUG_LIC}/files/hwp/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/x-hwp"
    assert "attachment" in r.headers.get("content-disposition", "")
    assert ".hwp" in r.headers.get("content-disposition", "").lower()
    assert "no-store" in r.headers.get("cache-control", "")
    assert r.content == _HWP_BYTES


# ---------------------------------------------------------------------------
# F06 — Authenticated PDF download, gate open → 200
# ---------------------------------------------------------------------------

def test_f06_authenticated_pdf_download():
    mock_resp = _mock_httpx_resp(200, _PDF_BYTES, "application/pdf")
    with patch("routers.reference_forms.get_form647_detail", return_value=_DETAIL_LIC), \
         patch("routers.reference_forms.form647_storage_path",
               return_value="form647/run-id/pdf/15267319_licbyl.pdf"), \
         patch("httpx.get", return_value=mock_resp):
        c = _client(_app(sb=_make_storage_sb(), user=_AUTHED_USER))
        r = c.get(f"/reference-forms/{_SLUG_LIC}/files/pdf/download")
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "")
    assert ".pdf" in r.headers.get("content-disposition", "").lower()


# ---------------------------------------------------------------------------
# F07 — admbyl (HWP only): HWP → 200, PDF → 404
# ---------------------------------------------------------------------------

def test_f07_admbyl_hwp_ok_pdf_404():
    mock_resp = _mock_httpx_resp(200, _HWP_BYTES, "application/x-hwp")
    with patch("routers.reference_forms.get_form647_detail", return_value=_DETAIL_ADM), \
         patch("routers.reference_forms.form647_storage_path",
               return_value="form647/run-id/hwp/10000001_admbyl.hwp"), \
         patch("httpx.get", return_value=mock_resp):
        c = _client(_app(sb=_make_storage_sb(), user=_AUTHED_USER))
        r_hwp = c.get(f"/reference-forms/{_SLUG_ADM}/files/hwp/download")
    assert r_hwp.status_code == 200

    with patch("routers.reference_forms.get_form647_detail", return_value=_DETAIL_ADM):
        c = _client(_app(sb=_make_storage_sb(), user=_AUTHED_USER))
        r_pdf = c.get(f"/reference-forms/{_SLUG_ADM}/files/pdf/download")
    assert r_pdf.status_code == 404


# ---------------------------------------------------------------------------
# F08 — Storage error → 500
# ---------------------------------------------------------------------------

def test_f08_storage_signed_url_error():
    with patch("routers.reference_forms.get_form647_detail", return_value=_DETAIL_LIC), \
         patch("routers.reference_forms.form647_storage_path",
               return_value="form647/run-id/hwp/15267319_licbyl.hwp"):
        c = _client(_app(sb=_make_storage_sb(error=True), user=_AUTHED_USER))
        r = c.get(f"/reference-forms/{_SLUG_LIC}/files/hwp/download")
    assert r.status_code == 500


# ---------------------------------------------------------------------------
# F09 — httpx fetch error → 502
# ---------------------------------------------------------------------------

def test_f09_file_fetch_error():
    with patch("routers.reference_forms.get_form647_detail", return_value=_DETAIL_LIC), \
         patch("routers.reference_forms.form647_storage_path",
               return_value="form647/run-id/hwp/15267319_licbyl.hwp"), \
         patch("httpx.get", side_effect=Exception("network error")):
        c = _client(_app(sb=_make_storage_sb(), user=_AUTHED_USER))
        r = c.get(f"/reference-forms/{_SLUG_LIC}/files/hwp/download")
    assert r.status_code == 502


# ---------------------------------------------------------------------------
# F10 — Storage path not leaked in detail response
# ---------------------------------------------------------------------------

def test_f10_storage_path_not_in_detail_response():
    with patch("routers.reference_forms.get_form647_detail", return_value=_DETAIL_LIC):
        c = _client(_app(sb=_make_storage_sb()))
        r = c.get(f"/reference-forms/{_SLUG_LIC}")
    assert r.status_code == 200
    text = r.text
    assert "form-originals" not in text
    assert "form647-remediation" not in text
    assert "private_storage_path" not in text
    assert "signed" not in text.lower()


# ---------------------------------------------------------------------------
# F11 — Existing non-f647 slug bypasses FORM647 branch → hits view (404 from empty mock)
# ---------------------------------------------------------------------------

def test_f11_existing_slug_not_intercepted_by_f647_branch():
    """Non-f647 slug must reach reference_form_public_view, not the FORM647 branch."""
    get_detail_mock = MagicMock(return_value=None)
    with patch("routers.reference_forms.get_form647_detail", get_detail_mock):
        c = _client(_app(sb=_make_view_sb()))
        r = c.get(f"/reference-forms/{_SLUG_EXISTING}")
    # View returns no data → 404, but FORM647 path not invoked
    assert r.status_code == 404
    get_detail_mock.assert_not_called()


# ---------------------------------------------------------------------------
# F12 — f647 slug does NOT query reference_form_public_view
# ---------------------------------------------------------------------------

def test_f12_f647_slug_skips_view_query():
    """Gate BLOCKED: f647 slug → 404 without touching reference_form_public_view."""
    sb = _make_view_sb()
    with patch("routers.reference_forms.get_form647_detail", return_value=None):
        c = _client(_app(sb=sb))
        r = c.get(f"/reference-forms/{_SLUG_LIC}")
    assert r.status_code == 404
    # Supabase table() must NOT have been called with the view name
    for call_args in sb.table.call_args_list:
        assert call_args.args[0] != "reference_form_public_view", \
            "f647 slug must not query reference_form_public_view"
