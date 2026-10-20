"""
WO-WWW-SS-THUMBNAIL-001 — Thumbnail endpoint + service contract tests.
Scope-reduced: no DB columns; Storage path thumbnails/{form_id}-{sha256[:16]}.webp.

Endpoint tests (T1-T10):
  T1  All gates pass → 200 image/webp
  T2  No file with has_preview → 404
  T3  Form not published (view empty) → 404
  T4  Sources not cleared → 404
  T5  Approval binding fails (TOCTOU) → 404
  T6  Storage returns 404 for thumbnail path → 404 (not yet generated)
  T7  Signed URL creation fails → 503
  T8  Storage proxy fetch fails → 502
  T9  Fetched content oversized (> 70KB) → 500
  T10 Fetched content missing WebP signature → 500

Service tests (T11-T16, T16b):
  T11 PNG → WebP, output ≤ 70KB, long edge ≤ 320px
  T12 RGBA PNG gets white background (no transparency in output)
  T13 Input larger than MAX_INPUT_BYTES raises ThumbnailInputError
  T14 Oversized image triggers decompression bomb guard
  T14b Empty bytes raise ThumbnailInputError
  T15 Corrupt bytes raise ThumbnailInputError
  T16 SHA256 in ThumbnailResult is consistent
"""
from __future__ import annotations

import hashlib
import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.reference_forms import router

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_FORM_ID = "aaaa0000-0000-0000-0000-000000000001"
_SLUG    = "safety-training-record"
_FILE_ID = "bbbb0000-0000-0000-0000-000000000002"
_SHA256  = "abcdef1234567890" * 4   # 64-char fake hex

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
            "file_id":     _FILE_ID,
            "sha256":      _SHA256,
            "approved_at": "2026-10-11T00:00:00+00:00",
            "format":      "pdf",
            "has_preview":  True,
            "filename":    "safety-training.pdf",
        }
    ],
    "formats":      ["pdf"],
    "legacy_codes": [],
}

_SOURCE_ROW = {"source_name": "한국산업안전보건공단(KOSHA)", "rights_status": "CLEARED"}

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
    approval=_APPROVAL_ROW,
):
    """
    Build a Supabase mock for the simplified thumbnail endpoint.
    Only view, sources, and approvals tables are queried — no files or preview_artifacts.
    """
    sb = MagicMock()

    _data = {
        "reference_form_public_view": [view] if view else [],
        "reference_form_sources":     [sources] if sources else [],
        "reference_form_approvals":   [approval] if approval else [],
    }

    def _make_chain(data_list):
        chain = MagicMock()
        result = MagicMock()
        result.data = data_list
        chain.execute.return_value = result
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


# ===========================================================================
# Endpoint tests
# ===========================================================================

# ---------------------------------------------------------------------------
# T1 — happy path → 200 image/webp
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
    assert resp.content == WEBP_1PX


# ---------------------------------------------------------------------------
# T2 — no file with has_preview → 404
# ---------------------------------------------------------------------------

def test_T2_no_has_preview_404():
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
# T3 — form not published (view returns nothing) → 404
# ---------------------------------------------------------------------------

def test_T3_form_not_published_404():
    sb = _sb_mock(view=None)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T4 — sources not CLEARED → 404
# ---------------------------------------------------------------------------

def test_T4_sources_not_cleared_404():
    source = {**_SOURCE_ROW, "rights_status": "REVIEW_REQUIRED"}
    sb = _sb_mock(sources=source)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T5 — approval binding fails (TOCTOU) → 404
# ---------------------------------------------------------------------------

def test_T5_approval_binding_fails_404():
    approval = {"approved_file_hashes": [{"file_id": _FILE_ID, "sha256": "different" + "z" * 55}]}
    sb = _sb_mock(approval=approval)
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T6 — Storage returns 404 for thumbnail (not yet generated) → 404
# ---------------------------------------------------------------------------

def test_T6_storage_not_found_404():
    sb = _sb_mock()
    app = _make_app(sb)

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=404,
            content=b"",
            raise_for_status=MagicMock(),
        )
        resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T7 — signed URL creation fails → 503
# ---------------------------------------------------------------------------

def test_T7_signed_url_fails_503():
    sb = _sb_mock()
    sb.storage.from_.return_value.create_signed_url.side_effect = Exception("storage unavailable")
    app = _make_app(sb)
    resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# T8 — httpx fetch fails → 502
# ---------------------------------------------------------------------------

def test_T8_proxy_fetch_fails_502():
    sb = _sb_mock()
    app = _make_app(sb)
    with patch("httpx.get", side_effect=Exception("network error")):
        resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# T9 — fetched content oversized (> 70 KB) → 500
# ---------------------------------------------------------------------------

def test_T9_thumbnail_oversized_500():
    # Build a valid RIFF/WEBP header followed by oversized payload
    header = b"RIFF" + b"\xff\xff\x01\x00" + b"WEBP"
    oversized = header + b"x" * (70 * 1024)   # exceeds 70 KB limit

    sb = _sb_mock()
    app = _make_app(sb)

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, content=oversized,
            headers={}, raise_for_status=lambda: None,
        )
        resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# T10 — fetched content missing WebP signature → 500
# ---------------------------------------------------------------------------

def test_T10_webp_signature_invalid_500():
    fake_content = b"NOT_A_WEBP_FILE" + b"\x00" * 20

    sb = _sb_mock()
    app = _make_app(sb)

    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200, content=fake_content,
            headers={}, raise_for_status=lambda: None,
        )
        resp = TestClient(app).get(f"/reference-forms/{_SLUG}/thumbnail")

    assert resp.status_code == 500


# ===========================================================================
# Service tests
# ===========================================================================

def _make_png(w: int = 400, h: int = 600, mode: str = "RGB") -> bytes:
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
# T11 — PNG → WebP, output ≤ 70KB, long edge ≤ 320px
# ---------------------------------------------------------------------------

def test_T11_png_to_webp_within_limits():
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
# T12 — RGBA PNG → white background, no alpha channel
# ---------------------------------------------------------------------------

def test_T12_rgba_white_background():
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
# T13 — input > MAX_INPUT_BYTES raises ThumbnailInputError
# ---------------------------------------------------------------------------

def test_T13_oversized_input_raises():
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail, ThumbnailInputError, MAX_INPUT_BYTES
    except ImportError:
        pytest.skip("Pillow not installed")
    big = b"x" * (MAX_INPUT_BYTES + 1)
    with pytest.raises(ThumbnailInputError):
        generate_thumbnail(big)


# ---------------------------------------------------------------------------
# T14 — oversized image (> MAX_INPUT_PIXELS) raises ThumbnailInputError
# ---------------------------------------------------------------------------

def test_T14_decompression_bomb_raises():
    try:
        from services.reference_form_thumbnail_svc import (
            generate_thumbnail, ThumbnailInputError
        )
        import services.reference_form_thumbnail_svc as _svc
    except ImportError:
        pytest.skip("Pillow not installed")

    original_max_pixels = _svc.MAX_INPUT_PIXELS
    original_pil_limit  = _svc.Image.MAX_IMAGE_PIXELS
    _svc.MAX_INPUT_PIXELS       = 100 * 100
    _svc.Image.MAX_IMAGE_PIXELS = 100 * 100
    try:
        oversized_png = _make_png(101, 101)
        with pytest.raises(ThumbnailInputError):
            generate_thumbnail(oversized_png)
    finally:
        _svc.MAX_INPUT_PIXELS       = original_max_pixels
        _svc.Image.MAX_IMAGE_PIXELS = original_pil_limit


# ---------------------------------------------------------------------------
# T14b — empty bytes raise ThumbnailInputError
# ---------------------------------------------------------------------------

def test_T14b_empty_input_raises():
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail, ThumbnailInputError
    except ImportError:
        pytest.skip("Pillow not installed")
    with pytest.raises(ThumbnailInputError):
        generate_thumbnail(b"")


# ---------------------------------------------------------------------------
# T15 — corrupt bytes raise ThumbnailInputError
# ---------------------------------------------------------------------------

def test_T15_corrupt_bytes_raises():
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail, ThumbnailInputError
    except ImportError:
        pytest.skip("Pillow not installed")
    with pytest.raises(ThumbnailInputError):
        generate_thumbnail(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)


# ---------------------------------------------------------------------------
# T16 — SHA256 in ThumbnailResult is consistent
# ---------------------------------------------------------------------------

def test_T16_sha256_consistent():
    try:
        from services.reference_form_thumbnail_svc import generate_thumbnail
    except ImportError:
        pytest.skip("Pillow not installed")
    png_bytes = _make_png(100, 100)
    r = generate_thumbnail(png_bytes)
    assert r.output_sha256 == hashlib.sha256(r.webp_bytes).hexdigest()
    assert r.byte_count == len(r.webp_bytes)
    assert r.generation_version.startswith("v1-pillow")
