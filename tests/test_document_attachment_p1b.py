"""Document Attachment P1-B Tests
WO-TAI-DOCUMENT-260-P1B-FINAL-GATE-CORRECTION-002

Tests:
  A01 — PATCH file/image field blocked by _validate_runtime_keys()
  A02 — PATCH signature field blocked (regression)
  A03 — OD-B06 HOLD upload rejected server-side
  A04 — OD-B06 HOLD remove rejected server-side
  A05 — Download storage_ref path binding validation rejects mismatched path
  A06 — upload_file_to_field success → correct FileSnapshot returned
  A07 — Duplicate upload (is_new_upload=False): existing file NOT deleted on DB conflict
  A08 — New upload (is_new_upload=True): orphan deleted on DB conflict
  A09 — Magic bytes mismatch rejected
  A10 — Magic bytes match passes
  A11 — remove_file_from_field success → None written to runtime_data_json
  A12 — HTML renderer: file field → "[첨부] filename.pdf (KB)" label, no JSON
  A13 — HTML renderer: image field → inline <img> when attachment_images provided
  A14 — HTML renderer: image field → filename fallback when no attachment_images
  A15 — resolve_attachment_images_for_render: non-image fields skipped
  A16 — resolve_attachment_images_for_render: storage failure → omit (fail open)
  A17 — Signature rendering unchanged (regression)

Pure unit tests — no Production DB, no Production Storage writes.
Mocks: get_supabase() patched via unittest.mock.patch.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import struct
import zlib
from typing import Any, Dict, List
from unittest.mock import MagicMock, call, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

DOC_ID = "doc-att-001"
SCHEMA_ID = "schema-att-001"
FIELD_ID_FILE = "field-att-file-001"
FIELD_ID_IMG = "field-att-img-001"
USER_ID = "user-att-001"
SHA256 = "a" * 64

PDF_MAGIC = b"%PDF-1.4 " + b"\x00" * 100
PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 100

STORAGE_REF_FILE = f"storage://company-docs/attachments/document/{DOC_ID}/{FIELD_ID_FILE}/{SHA256}.pdf"
STORAGE_REF_IMG = f"storage://company-docs/attachments/document/{DOC_ID}/{FIELD_ID_IMG}/{SHA256}.png"

NOW = "2026-10-25T00:00:00Z"


def _make_doc(status="DRAFT", rdj=None):
    return {
        "id": DOC_ID,
        "form_schema_id": SCHEMA_ID,
        "runtime_data_json": rdj or {},
        "status": status,
        "version": 1,
        "updated_at": NOW,
    }


def _make_field_row(field_id=FIELD_ID_FILE, field_key="certificate", input_type="file"):
    return {"id": field_id, "field_key": field_key, "input_type": input_type}


_COMMON_TABLES = ("runtime_document_data", "runtime_field", "runtime_checklist_item")


def _make_sb():
    """Create a MagicMock Supabase client with per-table isolation.

    Pre-creates common tables so sb._tables["name"] is accessible before sb.table("name")
    is called by the code under test.
    """
    sb = MagicMock()
    _tables: Dict[str, MagicMock] = {}

    def _get_table(name: str) -> MagicMock:
        if name not in _tables:
            _tables[name] = MagicMock()
        return _tables[name]

    sb.table.side_effect = _get_table
    sb._tables = _tables

    for name in _COMMON_TABLES:
        _get_table(name)  # eagerly initialize

    return sb


# ─────────────────────────────────────────────────────────────────────────────
# A01 — PATCH file/image field blocked
# ─────────────────────────────────────────────────────────────────────────────

class TestPatchGuard:
    def _make_sb_for_validate(self, field_rows, checklist_rows=None):
        sb = _make_sb()
        sb._tables["runtime_field"].select.return_value.eq.return_value.execute.return_value.data = field_rows
        sb._tables["runtime_checklist_item"].select.return_value.eq.return_value.execute.return_value.data = checklist_rows or []
        return sb

    def test_a01_patch_file_field_blocked(self):
        from services.document_engine_svc import _validate_runtime_keys
        sb = self._make_sb_for_validate([
            {"field_key": "certificate", "input_type": "file"},
        ])
        with pytest.raises(ValueError, match="cannot be set via PATCH"):
            _validate_runtime_keys(sb, SCHEMA_ID, {"certificate": {"_type": "file_snapshot"}})

    def test_a01_patch_image_field_blocked(self):
        from services.document_engine_svc import _validate_runtime_keys
        sb = self._make_sb_for_validate([
            {"field_key": "site_photo", "input_type": "image"},
        ])
        with pytest.raises(ValueError, match="cannot be set via PATCH"):
            _validate_runtime_keys(sb, SCHEMA_ID, {"site_photo": {"_type": "file_snapshot"}})

    def test_a02_patch_signature_blocked_regression(self):
        from services.document_engine_svc import _validate_runtime_keys
        sb = self._make_sb_for_validate([
            {"field_key": "supervisor_sig", "input_type": "signature"},
        ])
        with pytest.raises(ValueError, match="cannot be set via PATCH"):
            _validate_runtime_keys(sb, SCHEMA_ID, {"supervisor_sig": {}})

    def test_a01_patch_text_field_allowed(self):
        from services.document_engine_svc import _validate_runtime_keys
        sb = self._make_sb_for_validate([
            {"field_key": "work_title", "input_type": "text"},
        ])
        # Should not raise
        _validate_runtime_keys(sb, SCHEMA_ID, {"work_title": "작업명"})


# ─────────────────────────────────────────────────────────────────────────────
# A03/A04 — OD-B06 HOLD server-side rejection
# ─────────────────────────────────────────────────────────────────────────────

class TestODB06Hold:
    def test_a03_hold_upload_rejected(self):
        from services.document_attachment_svc import upload_file_to_field, AttachmentError
        with patch("services.document_attachment_svc.get_supabase", return_value=MagicMock()):
            with pytest.raises(AttachmentError, match="OD-B06"):
                asyncio.run(upload_file_to_field(
                    doc_id=DOC_ID,
                    field_key="attached_documents_list",
                    file_bytes=PDF_MAGIC,
                    original_file_name="docs.pdf",
                    mime_type="application/pdf",
                    current_user={"id": USER_ID},
                ))

    def test_a03_hold_attached_plan_rejected(self):
        from services.document_attachment_svc import upload_file_to_field, AttachmentError
        with patch("services.document_attachment_svc.get_supabase", return_value=MagicMock()):
            with pytest.raises(AttachmentError, match="OD-B06"):
                asyncio.run(upload_file_to_field(
                    doc_id=DOC_ID,
                    field_key="attached_plan_list",
                    file_bytes=PDF_MAGIC,
                    original_file_name="plan.pdf",
                    mime_type="application/pdf",
                    current_user={"id": USER_ID},
                ))

    def test_a04_hold_remove_rejected(self):
        from services.document_attachment_svc import remove_file_from_field, AttachmentError
        with patch("services.document_attachment_svc.get_supabase", return_value=MagicMock()):
            with pytest.raises(AttachmentError, match="OD-B06"):
                asyncio.run(remove_file_from_field(
                    doc_id=DOC_ID,
                    field_key="attached_documents_list",
                    current_user={"id": USER_ID},
                ))


# ─────────────────────────────────────────────────────────────────────────────
# A05 — Download storage_ref path binding validation
# ─────────────────────────────────────────────────────────────────────────────

class TestDownloadBinding:
    def _make_sb_for_download(self, storage_ref: str, field_id=FIELD_ID_FILE):
        sb = _make_sb()
        # Doc lookup (with form_schema_id)
        sb._tables["runtime_document_data"].select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "id": DOC_ID,
            "form_schema_id": SCHEMA_ID,
            "runtime_data_json": {
                "certificate": {
                    "_type": "file_snapshot",
                    "storage_ref": storage_ref,
                }
            },
        }
        # Field lookup
        sb._tables["runtime_field"].select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": field_id, "field_key": "certificate", "input_type": "file"},
        ]
        return sb

    def test_a05_correct_path_passes(self):
        from services.document_attachment_svc import get_file_signed_url
        sb = self._make_sb_for_download(STORAGE_REF_FILE)
        sb.storage.from_.return_value.create_signed_url.return_value = {"signedURL": "https://example.com/signed"}

        with patch("services.document_attachment_svc.get_supabase", return_value=sb):
            url = get_file_signed_url(DOC_ID, "certificate", {"id": USER_ID})
        assert url == "https://example.com/signed"

    def test_a05_mismatched_path_rejected(self):
        from services.document_attachment_svc import get_file_signed_url, AttachmentError
        # storage_ref points to a different field_id
        wrong_ref = f"storage://company-docs/attachments/document/{DOC_ID}/WRONG-FIELD-ID/{SHA256}.pdf"
        sb = self._make_sb_for_download(wrong_ref)

        with patch("services.document_attachment_svc.get_supabase", return_value=sb):
            with pytest.raises(AttachmentError, match="path mismatch"):
                get_file_signed_url(DOC_ID, "certificate", {"id": USER_ID})


# ─────────────────────────────────────────────────────────────────────────────
# A06 — upload_file_to_field success
# ─────────────────────────────────────────────────────────────────────────────

def _make_sb_for_upload(
    is_new_upload: bool = True,
    db_conflict: bool = False,
) -> MagicMock:
    sb = _make_sb()
    # Doc lookup
    sb._tables["runtime_document_data"].select.return_value.eq.return_value.single.return_value.execute.return_value.data = _make_doc()
    # Field lookup
    sb._tables["runtime_field"].select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        _make_field_row(),
    ]
    # Storage upload — success or idempotent
    if is_new_upload:
        sb.storage.from_.return_value.upload.return_value = MagicMock()
    else:
        sb.storage.from_.return_value.upload.side_effect = Exception("already exists")

    # DB update
    if db_conflict:
        sb._tables["runtime_document_data"].update.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value.data = []
    else:
        sb._tables["runtime_document_data"].update.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value.data = [_make_doc()]

    return sb


class TestUploadSuccess:
    def test_a06_upload_success_returns_snapshot(self):
        from services.document_attachment_svc import upload_file_to_field
        sb = _make_sb_for_upload(is_new_upload=True, db_conflict=False)

        with patch("services.document_attachment_svc.get_supabase", return_value=sb):
            result = asyncio.run(upload_file_to_field(
                doc_id=DOC_ID,
                field_key="certificate",
                file_bytes=PDF_MAGIC,
                original_file_name="cert.pdf",
                mime_type="application/pdf",
                current_user={"id": USER_ID},
            ))

        snap = result["file_snapshot"]
        assert snap["_type"] == "file_snapshot"
        assert snap["version"] == 1
        assert snap["field_id"] == FIELD_ID_FILE
        assert snap["field_key"] == "certificate"
        assert snap["mime_type"] == "application/pdf"
        assert snap["byte_size"] == len(PDF_MAGIC)
        assert snap["original_file_name"] == "cert.pdf"
        assert snap["uploaded_by_user_id"] == USER_ID
        assert len(snap["sha256"]) == 64
        assert snap["storage_ref"].startswith(
            f"storage://company-docs/attachments/document/{DOC_ID}/{FIELD_ID_FILE}/"
        )


# ─────────────────────────────────────────────────────────────────────────────
# A07/A08 — Orphan cleanup: reuse vs new upload
# ─────────────────────────────────────────────────────────────────────────────

class TestOrphanCleanup:
    def test_a08_new_upload_db_conflict_deletes_orphan(self):
        """is_new_upload=True + DB conflict → storage.remove() called."""
        from services.document_attachment_svc import upload_file_to_field, AttachmentError
        sb = _make_sb_for_upload(is_new_upload=True, db_conflict=True)
        sb.storage.from_.return_value.remove.return_value = MagicMock()

        with patch("services.document_attachment_svc.get_supabase", return_value=sb):
            with pytest.raises(AttachmentError, match="DOCUMENT_ATTACHMENT_CONFLICT"):
                asyncio.run(upload_file_to_field(
                    doc_id=DOC_ID,
                    field_key="certificate",
                    file_bytes=PDF_MAGIC,
                    original_file_name="cert.pdf",
                    mime_type="application/pdf",
                    current_user={"id": USER_ID},
                ))

        # Verify remove() was called
        assert sb.storage.from_.return_value.remove.called

    def test_a07_reused_upload_db_conflict_does_not_delete(self):
        """is_new_upload=False (idempotent reuse) + DB conflict → storage.remove() NOT called."""
        from services.document_attachment_svc import upload_file_to_field, AttachmentError
        sb = _make_sb_for_upload(is_new_upload=False, db_conflict=True)

        with patch("services.document_attachment_svc.get_supabase", return_value=sb):
            with pytest.raises(AttachmentError, match="DOCUMENT_ATTACHMENT_CONFLICT"):
                asyncio.run(upload_file_to_field(
                    doc_id=DOC_ID,
                    field_key="certificate",
                    file_bytes=PDF_MAGIC,
                    original_file_name="cert.pdf",
                    mime_type="application/pdf",
                    current_user={"id": USER_ID},
                ))

        # remove() must NOT have been called
        assert not sb.storage.from_.return_value.remove.called


# ─────────────────────────────────────────────────────────────────────────────
# A09/A10 — Magic bytes verification
# ─────────────────────────────────────────────────────────────────────────────

class TestMagicBytes:
    def test_a09_pdf_magic_mismatch_rejected(self):
        from services.document_attachment_svc import _verify_magic_bytes, AttachmentError
        with pytest.raises(AttachmentError, match="magic bytes"):
            _verify_magic_bytes(b"NOT A PDF FILE CONTENT", "application/pdf")

    def test_a09_jpeg_magic_mismatch_rejected(self):
        from services.document_attachment_svc import _verify_magic_bytes, AttachmentError
        with pytest.raises(AttachmentError, match="magic bytes"):
            _verify_magic_bytes(b"NOT JPEG CONTENT!!", "image/jpeg")

    def test_a09_png_magic_mismatch_rejected(self):
        from services.document_attachment_svc import _verify_magic_bytes, AttachmentError
        with pytest.raises(AttachmentError, match="magic bytes"):
            _verify_magic_bytes(b"NOT PNG CONTENT!!!!!", "image/png")

    def test_a10_pdf_magic_match_passes(self):
        from services.document_attachment_svc import _verify_magic_bytes
        _verify_magic_bytes(PDF_MAGIC, "application/pdf")  # no exception

    def test_a10_jpeg_magic_match_passes(self):
        from services.document_attachment_svc import _verify_magic_bytes
        _verify_magic_bytes(JPEG_MAGIC, "image/jpeg")

    def test_a10_png_magic_match_passes(self):
        from services.document_attachment_svc import _verify_magic_bytes
        _verify_magic_bytes(PNG_MAGIC, "image/png")

    def test_a10_ooxml_magic_match_passes(self):
        from services.document_attachment_svc import _verify_magic_bytes
        _verify_magic_bytes(b"PK\x03\x04" + b"\x00" * 30, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def test_a09_ooxml_magic_mismatch_rejected(self):
        from services.document_attachment_svc import _verify_magic_bytes, AttachmentError
        with pytest.raises(AttachmentError, match="magic bytes"):
            _verify_magic_bytes(b"NOT ZIP NOT OOXML!!", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ─────────────────────────────────────────────────────────────────────────────
# A11 — remove_file_from_field success
# ─────────────────────────────────────────────────────────────────────────────

class TestRemoveFile:
    def test_a11_remove_success_clears_field(self):
        from services.document_attachment_svc import remove_file_from_field
        sb = _make_sb()
        rdj = {"certificate": {"_type": "file_snapshot", "sha256": SHA256}}
        sb._tables["runtime_document_data"].select.return_value.eq.return_value.single.return_value.execute.return_value.data = _make_doc(rdj=rdj)
        sb._tables["runtime_field"].select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            _make_field_row(),
        ]
        sb._tables["runtime_document_data"].update.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value.data = [_make_doc()]

        with patch("services.document_attachment_svc.get_supabase", return_value=sb):
            asyncio.run(remove_file_from_field(DOC_ID, "certificate", {"id": USER_ID}))

        # Verify update was called with None for the field
        update_call = sb._tables["runtime_document_data"].update.call_args
        assert update_call is not None
        updated_rdj = update_call[0][0]["runtime_data_json"]
        assert updated_rdj["certificate"] is None


# ─────────────────────────────────────────────────────────────────────────────
# A12/A13/A14/A17 — HTML renderer
# ─────────────────────────────────────────────────────────────────────────────

_BASE_FIELD = {
    "id": FIELD_ID_FILE,
    "field_key": "certificate",
    "field_label": "자격증",
    "input_type": "file",
    "form_schema_id": SCHEMA_ID,
    "field_order": 1,
}
_IMG_FIELD = {
    "id": FIELD_ID_IMG,
    "field_key": "site_photo",
    "field_label": "현장 사진",
    "input_type": "image",
    "form_schema_id": SCHEMA_ID,
    "field_order": 2,
}
_FILE_SNAP = {
    "_type": "file_snapshot",
    "field_id": FIELD_ID_FILE,
    "field_key": "certificate",
    "storage_ref": STORAGE_REF_FILE,
    "sha256": SHA256,
    "mime_type": "application/pdf",
    "byte_size": 102400,
    "original_file_name": "certificate.pdf",
    "uploaded_by_user_id": USER_ID,
    "uploaded_at": NOW,
}
_IMG_SNAP = {
    "_type": "file_snapshot",
    "field_id": FIELD_ID_IMG,
    "field_key": "site_photo",
    "storage_ref": STORAGE_REF_IMG,
    "sha256": SHA256,
    "mime_type": "image/png",
    "byte_size": 4096,
    "original_file_name": "photo.png",
    "uploaded_by_user_id": USER_ID,
    "uploaded_at": NOW,
}


class TestHTMLRenderer:
    def _render(self, fields, data, attachment_images=None, signature_images=None):
        from services.document_schema_renderer import _render_rows
        consumed: set = set()
        return "\n".join(_render_rows(fields, data, consumed, signature_images, attachment_images))

    def test_a12_file_field_renders_filename_label(self):
        html = self._render([_BASE_FIELD], {"certificate": _FILE_SNAP})
        assert "[첨부]" in html
        assert "certificate.pdf" in html
        assert "_type" not in html  # snapshot JSON must not appear
        assert "file_snapshot" not in html

    def test_a12_file_field_renders_kb_size(self):
        html = self._render([_BASE_FIELD], {"certificate": _FILE_SNAP})
        assert "KB" in html

    def test_a13_image_field_inline_img_when_attachment_images_provided(self):
        data_uri = "data:image/png;base64,iVBORw0KGgo="
        html = self._render(
            [_IMG_FIELD],
            {"site_photo": _IMG_SNAP},
            attachment_images={"site_photo": data_uri},
        )
        assert '<img src="data:image/png' in html
        assert "photo.png" in html  # alt attribute
        assert "_type" not in html

    def test_a14_image_field_filename_fallback_without_attachment_images(self):
        html = self._render(
            [_IMG_FIELD],
            {"site_photo": _IMG_SNAP},
            attachment_images=None,
        )
        assert "photo.png" in html
        assert "<img" not in html  # no inline image
        assert "_type" not in html

    def test_a12_file_field_missing_when_no_snapshot(self):
        html = self._render([_BASE_FIELD], {})
        assert 'data-state="missing"' in html

    def test_a17_signature_field_unaffected_regression(self):
        """Signature rendering must be unchanged by attachment_images."""
        sig_field = {
            "id": "sig-field-001",
            "field_key": "supervisor_sig",
            "field_label": "서명",
            "input_type": "signature",
            "form_schema_id": SCHEMA_ID,
            "field_order": 3,
        }
        data_uri = "data:image/png;base64,iVBORw0KGgo="
        html = self._render(
            [sig_field],
            {"supervisor_sig": {"_type": "signature_snapshot"}},
            signature_images={"supervisor_sig": data_uri},
            attachment_images={"site_photo": "data:image/png;base64,OTHER"},
        )
        assert '<img src="data:image/png;base64,iVBORw0KGgo=' in html
        assert 'data-input-type="signature"' in html


# ─────────────────────────────────────────────────────────────────────────────
# A15/A16 — resolve_attachment_images_for_render
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveAttachmentImages:
    def test_a15_non_image_fields_skipped(self):
        """File fields are not resolved (only image fields)."""
        from services.document_attachment_svc import resolve_attachment_images_for_render
        sb = MagicMock()

        with patch("services.document_attachment_svc.get_supabase", return_value=sb):
            result = resolve_attachment_images_for_render(
                runtime_data_json={"certificate": _FILE_SNAP},
                fields=[_BASE_FIELD],  # input_type=file
            )

        assert result == {}
        sb.storage.from_.return_value.download.assert_not_called()

    def test_a15_image_field_resolved_to_data_uri(self):
        from services.document_attachment_svc import resolve_attachment_images_for_render
        sb = MagicMock()
        sb.storage.from_.return_value.download.return_value = PNG_MAGIC

        with patch("services.document_attachment_svc.get_supabase", return_value=sb):
            result = resolve_attachment_images_for_render(
                runtime_data_json={"site_photo": _IMG_SNAP},
                fields=[_IMG_FIELD],
            )

        assert "site_photo" in result
        assert result["site_photo"].startswith("data:image/png;base64,")
        expected_b64 = base64.b64encode(PNG_MAGIC).decode("ascii")
        assert expected_b64 in result["site_photo"]

    def test_a16_storage_failure_omits_field_fail_open(self):
        """Storage read failure → field omitted from result, no exception raised."""
        from services.document_attachment_svc import resolve_attachment_images_for_render
        sb = MagicMock()
        sb.storage.from_.return_value.download.side_effect = Exception("storage unreachable")

        with patch("services.document_attachment_svc.get_supabase", return_value=sb):
            result = resolve_attachment_images_for_render(
                runtime_data_json={"site_photo": _IMG_SNAP},
                fields=[_IMG_FIELD],
            )

        assert result == {}  # fail open — no crash, just omit


# ─────────────────────────────────────────────────────────────────────────────
# A18-A22 — resolve_attachment_images_for_render: C2 binding validation
# ─────────────────────────────────────────────────────────────────────────────

# Fixtures for binding tests — SHA256 derived from actual PNG bytes so integrity check passes
_BIND_DOC_ID = "doc-bind-001"
_BIND_FIELD_ID = "field-bind-img-001"
_PNG_BYTES_BIND = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
_BIND_SHA = hashlib.sha256(_PNG_BYTES_BIND).hexdigest()
_BIND_STORAGE_REF = (
    f"storage://company-docs/attachments/document/"
    f"{_BIND_DOC_ID}/{_BIND_FIELD_ID}/{_BIND_SHA}.png"
)
_BIND_SNAP = {
    "_type": "file_snapshot",
    "field_key": "site_photo",
    "field_id": _BIND_FIELD_ID,
    "storage_ref": _BIND_STORAGE_REF,
    "sha256": _BIND_SHA,
    "mime_type": "image/png",
    "byte_size": len(_PNG_BYTES_BIND),
    "original_file_name": "photo.png",
    "uploaded_by_user_id": USER_ID,
    "uploaded_at": NOW,
}
_BIND_FIELD = {
    "id": _BIND_FIELD_ID,
    "field_key": "site_photo",
    "input_type": "image",
    "field_label": "현장사진",
    "field_order": 1,
    "form_schema_id": SCHEMA_ID,
    "required_status": "OPTIONAL",
}


class TestResolveAttachmentBinding:
    def _run(self, snap_override=None, field_override=None, doc_id=_BIND_DOC_ID,
             strict=True, storage_bytes=_PNG_BYTES_BIND, storage_raises=None):
        from services.document_attachment_svc import resolve_attachment_images_for_render
        snap = {**_BIND_SNAP, **(snap_override or {})}
        field = {**_BIND_FIELD, **(field_override or {})}
        sb = MagicMock()
        if storage_raises:
            sb.storage.from_.return_value.download.side_effect = storage_raises
        else:
            sb.storage.from_.return_value.download.return_value = storage_bytes
        with patch("services.document_attachment_svc.get_supabase", return_value=sb):
            return resolve_attachment_images_for_render(
                runtime_data_json={"site_photo": snap},
                fields=[field],
                document_id=doc_id,
                strict=strict,
            )

    def test_a18_binding_pass_returns_data_uri(self):
        """Correct doc_id/field_id/sha256/magic → data URI returned."""
        result = self._run()
        assert "site_photo" in result
        assert result["site_photo"].startswith("data:image/png;base64,")
        expected_b64 = base64.b64encode(_PNG_BYTES_BIND).decode("ascii")
        assert expected_b64 in result["site_photo"]

    def test_a19_path_mismatch_strict_raises(self):
        """storage_ref with wrong doc_id → AttachmentError in strict mode."""
        from services.document_attachment_svc import AttachmentError
        wrong_ref = (
            "storage://company-docs/attachments/document/WRONG-DOC/field-xyz/abc.png"
        )
        with pytest.raises(AttachmentError, match="path_mismatch"):
            self._run(snap_override={"storage_ref": wrong_ref})

    def test_a19_path_mismatch_non_strict_skips(self):
        """storage_ref with wrong doc_id → field omitted in non-strict mode."""
        wrong_ref = (
            "storage://company-docs/attachments/document/WRONG-DOC/field-xyz/abc.png"
        )
        result = self._run(snap_override={"storage_ref": wrong_ref}, strict=False)
        assert result == {}

    def test_a20_sha256_mismatch_strict_raises(self):
        """Downloaded bytes whose SHA-256 doesn't match snap.sha256 → AttachmentError."""
        from services.document_attachment_svc import AttachmentError
        with pytest.raises(AttachmentError, match="sha256_mismatch"):
            self._run(
                snap_override={"sha256": "b" * 64},  # wrong SHA
                storage_bytes=_PNG_BYTES_BIND,
            )

    def test_a21_magic_bytes_mismatch_strict_raises(self):
        """MIME says image/jpeg but bytes are PNG → AttachmentError."""
        from services.document_attachment_svc import AttachmentError
        with pytest.raises(AttachmentError, match="magic"):
            self._run(
                snap_override={
                    "mime_type": "image/jpeg",
                    "sha256": hashlib.sha256(_PNG_BYTES_BIND).hexdigest(),
                },
            )

    def test_a22_fetch_fail_strict_raises(self):
        """Storage download error → AttachmentError in strict mode."""
        from services.document_attachment_svc import AttachmentError
        with pytest.raises(AttachmentError, match="fetch_failed"):
            self._run(storage_raises=RuntimeError("network error"))

    def test_a22_fetch_fail_non_strict_skips(self):
        """Storage download error → field omitted in non-strict mode."""
        result = self._run(storage_raises=RuntimeError("network error"), strict=False)
        assert result == {}

    def test_a18_field_key_mismatch_strict_raises(self):
        """snap.field_key doesn't match field_key → AttachmentError."""
        from services.document_attachment_svc import AttachmentError
        with pytest.raises(AttachmentError, match="binding_mismatch"):
            self._run(snap_override={"field_key": "OTHER_KEY"})

    def test_a18_field_id_mismatch_strict_raises(self):
        """snap.field_id doesn't match field.id → AttachmentError."""
        from services.document_attachment_svc import AttachmentError
        with pytest.raises(AttachmentError, match="binding_mismatch"):
            self._run(snap_override={"field_id": "WRONG-FIELD-ID"})


# ─────────────────────────────────────────────────────────────────────────────
# A25 — renderer: image fallback state = "present-no-image"
# ─────────────────────────────────────────────────────────────────────────────

class TestRendererFallbackState:
    def _render(self, fields, data, attachment_images=None):
        from services.document_schema_renderer import _render_rows
        consumed: set = set()
        return "\n".join(_render_rows(fields, data, consumed, None, attachment_images))

    def test_a25_image_snap_without_uri_has_present_no_image_state(self):
        """Snap exists but no img_uri → data-state="present-no-image", not "present"."""
        html = self._render(
            [_IMG_FIELD],
            {"site_photo": _IMG_SNAP},
            attachment_images=None,  # no URI → fallback
        )
        assert 'data-state="present-no-image"' in html
        assert 'data-state="present"' not in html
        assert "photo.png" in html
        assert "<img" not in html

    def test_a25_image_with_uri_retains_present_state(self):
        """Snap with valid img_uri → data-state="present" (unchanged)."""
        data_uri = "data:image/png;base64,iVBORw0KGgo="
        html = self._render(
            [_IMG_FIELD],
            {"site_photo": _IMG_SNAP},
            attachment_images={"site_photo": data_uri},
        )
        assert 'data-state="present"' in html
        assert 'data-state="present-no-image"' not in html
        assert '<img src="data:image/png' in html


# ─────────────────────────────────────────────────────────────────────────────
# A26-A29 — IMAGE-INTEGRITY-CLOSE-004 (C1/C2 completeness)
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveAttachmentIntegrityClose:
    """C1: strict mode completeness — sha256 required, byte_size, malformed snap.
       C2: draft binding — cross-doc path skipped before storage read."""

    def _run_resolve(self, runtime_data, snap_override=None, field_override=None,
                     doc_id=_BIND_DOC_ID, strict=True,
                     storage_bytes=_PNG_BYTES_BIND, storage_raises=None):
        from services.document_attachment_svc import resolve_attachment_images_for_render
        if snap_override is not None:
            snap = {**_BIND_SNAP, **snap_override}
        else:
            snap = _BIND_SNAP
        field = {**_BIND_FIELD, **(field_override or {})}
        sb = MagicMock()
        if storage_raises:
            sb.storage.from_.return_value.download.side_effect = storage_raises
        else:
            sb.storage.from_.return_value.download.return_value = storage_bytes
        with patch("services.document_attachment_svc.get_supabase", return_value=sb):
            return resolve_attachment_images_for_render(
                runtime_data_json={"site_photo": snap},
                fields=[field],
                document_id=doc_id,
                strict=strict,
            ), sb

    def test_a26_sha256_missing_strict_raises(self):
        """sha256 absent → AttachmentError (sha256_missing_or_invalid) in strict mode."""
        from services.document_attachment_svc import AttachmentError
        with pytest.raises(AttachmentError, match="sha256_missing_or_invalid"):
            self._run_resolve(runtime_data=None, snap_override={"sha256": None})

    def test_a26_sha256_invalid_format_strict_raises(self):
        """sha256 with wrong length/chars → AttachmentError in strict mode."""
        from services.document_attachment_svc import AttachmentError
        with pytest.raises(AttachmentError, match="sha256_missing_or_invalid"):
            self._run_resolve(runtime_data=None, snap_override={"sha256": "tooshort"})

    def test_a27_malformed_snapshot_strict_raises(self):
        """Non-file_snapshot dict in image field → AttachmentError (malformed_snapshot)."""
        from services.document_attachment_svc import resolve_attachment_images_for_render, AttachmentError
        with pytest.raises(AttachmentError, match="malformed_snapshot"):
            resolve_attachment_images_for_render(
                runtime_data_json={"site_photo": {"_type": "WRONG", "data": 1}},
                fields=[_BIND_FIELD],
                document_id=_BIND_DOC_ID,
                strict=True,
            )

    def test_a27_none_value_is_not_malformed(self):
        """None value for optional image field → silently skipped, no error."""
        from services.document_attachment_svc import resolve_attachment_images_for_render
        result = resolve_attachment_images_for_render(
            runtime_data_json={"site_photo": None},
            fields=[_BIND_FIELD],
            document_id=_BIND_DOC_ID,
            strict=True,
        )
        assert result == {}

    def test_a28_byte_size_mismatch_strict_raises(self):
        """snap.byte_size != actual file size → AttachmentError in strict mode."""
        from services.document_attachment_svc import AttachmentError
        with pytest.raises(AttachmentError, match="byte_size_mismatch"):
            self._run_resolve(
                runtime_data=None,
                snap_override={"byte_size": 9999},  # actual = len(_PNG_BYTES_BIND) = 108
            )

    def test_a28_byte_size_missing_strict_raises(self):
        """snap.byte_size absent → AttachmentError (byte_size_missing_or_invalid) in strict."""
        from services.document_attachment_svc import AttachmentError
        with pytest.raises(AttachmentError, match="byte_size_missing_or_invalid"):
            self._run_resolve(runtime_data=None, snap_override={"byte_size": None})

    def test_a29_draft_cross_doc_path_skipped_no_storage_read(self):
        """Non-strict (draft), cross-doc storage_ref → field skipped AND storage not called."""
        wrong_ref = (
            "storage://company-docs/attachments/document/OTHER-DOC/field-xyz/abc.png"
        )
        result, sb = self._run_resolve(
            runtime_data=None,
            snap_override={"storage_ref": wrong_ref},
            strict=False,
        )
        assert result == {}
        sb.storage.from_.return_value.download.assert_not_called()
