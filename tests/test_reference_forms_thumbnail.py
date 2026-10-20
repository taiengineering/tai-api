"""
WO-WWW-SS-THUMBNAIL-001 P2 — Thumbnail endpoint + service contract tests.
Migration required: 20261021000001_reference_forms_thumbnail.sql

Endpoint tests (T1-T10):
  T1  All gates pass → 200 image/webp
  T2  thumbnail_qa_status != QA_PASS → 404
  T3  thumbnail_ref is None → 404
  T4  thumbnail_input_sha256 is None → 404
  T5  source_file_sha256 mismatch (approved file changed) → 404
  T6  no file with has_preview → 404
  T7  form not published (view returns nothing) → 404
  T8  sources not cleared → 404
  T9  approval binding fails (TOCTOU) → 404
  T10 cross-form preview_artifact_id → 404
  T11 wrong storage bucket in thumbnail_ref → 500
  T12 signed URL fetch fails → 503
  T13 storage proxy fetch fails → 502

Service tests (T14-T19):
  T14 PNG → WebP, output ≤ 70KB, long edge ≤ 320px
  T15 RGBA PNG gets white background (no transparency in output)
  T16 input larger than MAX_INPUT_BYTES raises ThumbnailInputError
  T17 oversized image triggers decompression bomb guard
  T18 corrupt bytes raise ThumbnailInputError
  T19 sha256 in ThumbnailResult is consistent
"""
from __future__ import annotations

import hashlib
import io
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.reference_forms import router

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_FORM_ID    = "aaaa0000-0000-0000-0000-000000000001"
_SLUG       = "safety-training-record"
_FILE_ID    = "bbbb0000-0000-0000-0000-000000000002"
_SHA256     = "abcdef1234567890" * 4   # 64-char fake hex
_PA_ID      = "cccc0000-0000-0000-0000-000000000003"
_OTHER_FORM = "dddd0000-0000-0000-0000-000000000004"
_THUMB_REF  = "storage://reference-forms-preview/thumbnails/aaaa0000-0000-0000-0000-000000000001-v1.webp"
_THUMB_SHA  = "a8e1378cd74e08b2553bf313f676885cc7a6d590cfe79ca1b5f9d49215b5efa3"  # sha256(WEBP_1PX)
_INPUT_SHA  = "input" + "b" * 59

_VIEW_ROW = {
    "id": _FORM_ID,
    "canonical_slug": _SLUG,
    "title": "근로자 안전보건교육 일지",
    "description": "안전보건교육 일지 서식입니다.",
    "published_at": "2026-10-11T00:00:00+00:00",
    "updated_at":   "2026-10-11T00:00:00+00:00",
    "approval_id":  "ee000000-0000-0000-0000-000000000005",
    "content_approved": True,
    "qa_pass_files": [
        {
            "file_id":    _FILE_ID,
            "sha256":     _SHA256,
            "approved_at":"2026-10-11T00:00:00+00:00",
            "format":     "pdf",
            "has_preview": True,
            "filename":   "safety-training.pdf",
        }
    ],
    "formats":      ["pdf"],
    "legacy_codes": [],
}

_SOURCE_ROW = {"source_name": "한국산업안전보건공단(KOSHA)", "rights_status": "CLEARED"}

_FILE_ROW = {
    "id":                  _FILE_ID,
    "form_id":             _FORM_ID,
    "sha256":              _SHA256,
    "preview_artifact_id": _PA_ID,
    "is_active":           True,
    "qa_status":           "QA_PASS",
}

_PA_ROW = {
    "form_id":                      _FORM_ID,
    "source_file_sha256":           _SHA256,
    "is_published":                 True,
    "qa_status":                    "QA_PASS",
    "thumbnail_ref":                _THUMB_REF,
    "thumbnail_sha256":             _THUMB_SHA,
    "thumbnail_input_sha256":       _INPUT_SHA,
    "thumbnail_qa_status":          "QA_PASS",
    "thumbnail_bytes":              44,   # len(WEBP_1PX)
}

_APPROVAL_ROW = {
    "approved_file_hashes": [{"file_id": _FILE_ID, "sha256": _SHA256}]
}

WEBP_1PX = (
    b"RIFF$\x00\x00\x00WEBPVP8 "
    b"\x18\x00\x00\x000\x01\x00\x9d\x01*"
    b"\x01\x00\x01\x00\x02\x00\x34\x25\xa4\x00\x03p\x00\xfe\xfb\x94\x00\x00"
)


def _sb_mock(
    view=_VIEW_ROW,
    sources=_SOURCE_ROW,
    file=_FILE_ROW,
    pa=_PA_ROW,
    approval=_APPROVAL_ROW,
):
    """
    Build a Supabase mock that handles arbitrary chainable query methods
    (.select / .eq / .in_ / .limit / .order / .update) ending in .execute().
    All chain methods return the same chain object so multi-.eq() calls work correctly.
    """
    sb = MagicMock()

    _data = {
        "reference_form_public_view":      [view] if view else [],
        "reference_form_sources":           [sources] if sources else [],
        "reference_form_files":             [file] if file else [],
        "reference_form_preview_artifacts": [pa] if pa else [],
        "reference_form_approvals":         [approval] if approval else [],
    }

    def _make_chain(data_list):
        chain = MagicMock()
        result = MagicMock()
        result.data = data_list
        chain.execute.return_value = result
        # All chainable methods return the same chain — multi-.eq() safe
        for method in ("select", "update", "eq", "in_", "limit", "order"):
            getattr(chain, method).return_value = chain
        tbl = MagicMock()
        tbl.select.return_value = chain
        tbl.update.return_value = chain
        return tbl

    sb.table.side_effect = lambda name: _make_chain(_data.get(name, []))

    signed = MagicMock()
    signed.get = lambda k, default=None: (
        "https://storage.example.com/signed" if k in ("signedURL", "signedUrl") else default
    )
    sb.storage.from_.return_value.create_signed_url.return_value = signed
    return sb


def _make_app(sb):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides = {}

    from db.supabase_client import get_supabase
    app.dependency_overrides[get_supabase] = lambda: sb
    return app


# ---------------------------------------------------------------------------
# T1 — happy path
# ---------------------------------------------------------------------------

def test_T1_thumbnail_200_webp():
    sb = _sb_mock()
    app = _make_app(sb)

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, content=WEBP_1PX,
            headers={"content-type": "image/webp"},
            raise_for_status=lambda: None,
        )
        client = TestClient(app)
        resp = client.get(f"/reference-forms/{_SLUG}/thumbnail")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    assert resp.headers["cache-control"] == "no-store"


# ---------------------------------------------------------------------------
# T2 — thumbnail_qa_status != QA_PASS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", [None, "PENDING", "QA_FAIL"])
def test_T2_thumbnail_qa_not_pass_404(status):
    pa = {**_PA_ROW, "thumbnail_qa_status": status}
    sb = _sb_mock(pa=pa)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T3 — thumbnail_ref is None
# ---------------------------------------------------------------------------

def test_T3_thumbnail_ref_none_404():
    pa = {**_PA_ROW, "thumbnail_ref": None}
    sb = _sb_mock(pa=pa)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T4 — thumbnail_input_sha256 is None
# ---------------------------------------------------------------------------

def test_T4_thumbnail_input_sha_none_404():
    pa = {**_PA_ROW, "thumbnail_input_sha256": None}
    sb = _sb_mock(pa=pa)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T5 — source_file_sha256 mismatch (approved file replaced)
# ---------------------------------------------------------------------------

def test_T5_source_sha_mismatch_404():
    pa = {**_PA_ROW, "source_file_sha256": "different" + "x" * 55}
    sb = _sb_mock(pa=pa)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T6 — no file with has_preview
# ---------------------------------------------------------------------------

def test_T6_no_has_preview_404():
    view = {
        **_VIEW_ROW,
        "qa_pass_files": [
            {**_VIEW_ROW["qa_pass_files"][0], "has_preview": False}
        ],
    }
    sb = _sb_mock(view=view)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T7 — form not published (view returns nothing)
# ---------------------------------------------------------------------------

def test_T7_form_not_published_404():
    sb = _sb_mock(view=None)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T8 — sources not CLEARED
# ---------------------------------------------------------------------------

def test_T8_sources_not_cleared_404():
    source = {**_SOURCE_ROW, "rights_status": "REVIEW_REQUIRED"}
    sb = _sb_mock(sources=source)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T9 — approval binding fails (TOCTOU)
# ---------------------------------------------------------------------------

def test_T9_approval_binding_fails_404():
    approval = {"approved_file_hashes": [{"file_id": _FILE_ID, "sha256": "different" + "z" * 55}]}
    sb = _sb_mock(approval=approval)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T10 — cross-form file (form_id mismatch in file row)
# ---------------------------------------------------------------------------

def test_T10_cross_form_file_404():
    file_row = {**_FILE_ROW, "form_id": _OTHER_FORM}
    sb = _sb_mock(file=file_row)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T11 — wrong bucket in thumbnail_ref → 500
# ---------------------------------------------------------------------------

def test_T11_wrong_bucket_500():
    pa = {**_PA_ROW, "thumbnail_ref": "storage://reference-forms/thumbnails/evil.webp"}
    sb = _sb_mock(pa=pa)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# T12 — signed URL creation fails → 503
# ---------------------------------------------------------------------------

def test_T12_signed_url_fails_503():
    sb = _sb_mock()
    sb.storage.from_.return_value.create_signed_url.side_effect = Exception("storage unavailable")
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# T13 — httpx fetch fails → 502
# ---------------------------------------------------------------------------

def test_T13_proxy_fetch_fails_502():
    sb = _sb_mock()
    app = _make_app(sb)
    with patch("httpx.get", side_effect=Exception("network error")):
        resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 502


# ===========================================================================
# Service tests
# ===========================================================================

def _make_png(w: int = 400, h: int = 600, mode: str = "RGB") -> bytes:
    """Create a minimal in-memory PNG for testing."""
    try:
        from PIL import Image as PILImage
    except ImportError:
        pytest.skip("Pillow not installed")
    buf = io.BytesIO()
    img = PILImage.new(mode, (w, h), color=(100, 150, 200))
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_rgba_png(w: int = 200, h: int = 300) -> bytes:
    try:
        from PIL import Image as PILImage
    except ImportError:
        pytest.skip("Pillow not installed")
    buf = io.BytesIO()
    img = PILImage.new("RGBA", (w, h), color=(255, 0, 0, 128))
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# T14 — PNG → WebP, output ≤ 70KB, long edge ≤ 320px
# ---------------------------------------------------------------------------

def test_T14_png_to_webp_within_limits():
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail, MAX_OUTPUT_BYTES, MAX_LONG_EDGE
    except ImportError:
        pytest.skip("Pillow not installed")
    png_bytes = _make_png(800, 1200)
    result = generate_thumbnail(png_bytes)
    assert result.byte_count <= MAX_OUTPUT_BYTES
    assert result.byte_count == len(result.webp_bytes)

    from PIL import Image as PILImage
    img = PILImage.open(io.BytesIO(result.webp_bytes))
    assert max(img.width, img.height) <= MAX_LONG_EDGE
    assert img.format == "WEBP"

    assert result.output_sha256 == hashlib.sha256(result.webp_bytes).hexdigest()


# ---------------------------------------------------------------------------
# T15 — RGBA PNG → white background, no alpha channel
# ---------------------------------------------------------------------------

def test_T15_rgba_white_background():
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail
        from PIL import Image as PILImage
    except ImportError:
        pytest.skip("Pillow not installed")
    rgba_png = _make_rgba_png()
    result = generate_thumbnail(rgba_png)
    img = PILImage.open(io.BytesIO(result.webp_bytes))
    assert img.mode in ("RGB",), f"Expected RGB, got {img.mode}"


# ---------------------------------------------------------------------------
# T16 — input > MAX_INPUT_BYTES raises ThumbnailInputError
# ---------------------------------------------------------------------------

def test_T16_oversized_input_raises():
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail, ThumbnailInputError, MAX_INPUT_BYTES
    except ImportError:
        pytest.skip("Pillow not installed")
    big = b"x" * (MAX_INPUT_BYTES + 1)
    with pytest.raises(ThumbnailInputError):
        generate_thumbnail(big)


# ---------------------------------------------------------------------------
# T17 — oversized image (> MAX_INPUT_PIXELS) raises ThumbnailInputError
# ---------------------------------------------------------------------------

def test_T17_decompression_bomb_raises():
    try:
        from services.reference_form_thumbnail_svc import (
            generate_thumbnail, ThumbnailInputError
        )
        import services.reference_form_thumbnail_svc as _svc
    except ImportError:
        pytest.skip("Pillow not installed")

    # Patch both the module constant and Pillow's PIL limit so the explicit pixel
    # guard fires on a small test image without needing a real 50 MP file.
    original_max_pixels = _svc.MAX_INPUT_PIXELS
    original_pil_limit  = _svc.Image.MAX_IMAGE_PIXELS
    _svc.MAX_INPUT_PIXELS       = 100 * 100  # 10 000 pixels
    _svc.Image.MAX_IMAGE_PIXELS = 100 * 100
    try:
        oversized_png = _make_png(101, 101)  # 10 201 pixels — exceeds patched limit
        with pytest.raises(ThumbnailInputError):
            generate_thumbnail(oversized_png)
    finally:
        _svc.MAX_INPUT_PIXELS       = original_max_pixels
        _svc.Image.MAX_IMAGE_PIXELS = original_pil_limit


# ---------------------------------------------------------------------------
# T17b — empty bytes raise ThumbnailInputError
# ---------------------------------------------------------------------------

def test_T17b_empty_input_raises():
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail, ThumbnailInputError
    except ImportError:
        pytest.skip("Pillow not installed")
    with pytest.raises(ThumbnailInputError):
        generate_thumbnail(b"")


# ---------------------------------------------------------------------------
# T18 — corrupt bytes raise ThumbnailInputError
# ---------------------------------------------------------------------------

def test_T18_corrupt_bytes_raises():
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail, ThumbnailInputError
    except ImportError:
        pytest.skip("Pillow not installed")
    with pytest.raises(ThumbnailInputError):
        generate_thumbnail(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)


# ---------------------------------------------------------------------------
# T19 — sha256 in result is consistent with webp_bytes
# ---------------------------------------------------------------------------

def test_T19_sha256_consistent():
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail
    except ImportError:
        pytest.skip("Pillow not installed")
    png_bytes = _make_png(100, 100)
    r = generate_thumbnail(png_bytes)
    assert r.output_sha256 == hashlib.sha256(r.webp_bytes).hexdigest()
    assert r.byte_count == len(r.webp_bytes)
    assert r.generation_version.startswith("v1-pillow")


# ===========================================================================
# Integrity gate tests (endpoint — FIX-01 verifications)
# ===========================================================================

# ---------------------------------------------------------------------------
# T20 — SHA256 in DB does not match fetched bytes → 500
# ---------------------------------------------------------------------------

def test_T20_sha256_mismatch_500():
    pa = {**_PA_ROW, "thumbnail_sha256": "0" * 64}  # wrong hash
    sb = _sb_mock(pa=pa)
    app = _make_app(sb)

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, content=WEBP_1PX,
            headers={"content-type": "image/webp"},
            raise_for_status=lambda: None,
        )
        resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# T21 — thumbnail_bytes in DB does not match fetched size → 500
# ---------------------------------------------------------------------------

def test_T21_size_mismatch_500():
    # DB says thumbnail_bytes=99999 but we'll return WEBP_1PX (much smaller)
    pa = {**_PA_ROW, "thumbnail_bytes": 99999}
    sb = _sb_mock(pa=pa)
    app = _make_app(sb)

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, content=WEBP_1PX,
            headers={"content-type": "image/webp"},
            raise_for_status=lambda: None,
        )
        resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# T22 — fetched bytes have no WebP signature → 500
# ---------------------------------------------------------------------------

def test_T22_webp_signature_invalid_500():
    fake_content = b"NOT_A_WEBP_FILE" + b"\x00" * 20
    fake_sha = hashlib.sha256(fake_content).hexdigest()
    pa = {
        **_PA_ROW,
        "thumbnail_sha256": fake_sha,
        "thumbnail_bytes": len(fake_content),
    }
    sb = _sb_mock(pa=pa)
    app = _make_app(sb)

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, content=fake_content,
            headers={"content-type": "image/webp"},
            raise_for_status=lambda: None,
        )
        resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# T23 — thumbnail_sha256 missing in DB → 404
# ---------------------------------------------------------------------------

def test_T23_thumbnail_sha256_missing_404():
    pa = {**_PA_ROW, "thumbnail_sha256": None}
    sb = _sb_mock(pa=pa)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404
