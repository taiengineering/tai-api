"""Tests for verify_file_snapshot_for_evidence (WO-024 E24-04/05/06)."""
import hashlib
from unittest.mock import MagicMock, patch

import pytest

from services.document_attachment_svc import AttachmentError, verify_file_snapshot_for_evidence

DOC_ID = "dddddddd-0001-0001-0001-000000000001"
FIELD_ID = "ffffffff-0001-0001-0001-000000000001"
FIELD_KEY = "attached_documents"
PDF_MAGIC = b"%PDF" + b"\x00" * 100  # minimal PDF magic
SHA256 = hashlib.sha256(PDF_MAGIC).hexdigest()


def _snap(**over):
    base = {
        "_type": "file_snapshot",
        "version": 1,
        "field_id": FIELD_ID,
        "field_key": FIELD_KEY,
        "storage_ref": f"storage://company-docs/attachments/document/{DOC_ID}/{FIELD_ID}/{SHA256}.pdf",
        "sha256": SHA256,
        "mime_type": "application/pdf",
        "byte_size": len(PDF_MAGIC),
        "original_file_name": "test.pdf",
        "uploaded_by_user_id": "user-001",
        "uploaded_at": "2026-10-26T00:00:00+09:00",
    }
    base.update(over)
    return base


def _fake_sb(file_bytes=None):
    sb = MagicMock()
    sb.storage.from_().download.return_value = file_bytes if file_bytes is not None else PDF_MAGIC
    return sb


def test_e24_04_correct_snapshot_returns_manifest_entry():
    """E24-04: valid FileSnapshot → manifest entry dict."""
    with patch("services.document_attachment_svc.get_supabase", return_value=_fake_sb()):
        entry = verify_file_snapshot_for_evidence(
            snapshot=_snap(),
            document_id=DOC_ID,
            field_id=FIELD_ID,
            field_key=FIELD_KEY,
        )
    assert entry["type"] == "attachment"
    assert entry["sha256"] == SHA256
    assert entry["field_id"] == FIELD_ID
    assert entry["field_key"] == FIELD_KEY


def test_e24_04_field_id_mismatch_raises():
    """E24-04: field_id mismatch in snapshot → AttachmentError."""
    with patch("services.document_attachment_svc.get_supabase", return_value=_fake_sb()):
        with pytest.raises(AttachmentError, match="field_id mismatch"):
            verify_file_snapshot_for_evidence(
                snapshot=_snap(field_id="wrong-id"),
                document_id=DOC_ID,
                field_id=FIELD_ID,
                field_key=FIELD_KEY,
            )


def test_e24_05_sha256_mismatch_raises():
    """E24-05: Storage file bytes differ from snapshot SHA256 → AttachmentError."""
    tampered = b"%PDF" + b"\xff" * 100  # different bytes
    with patch("services.document_attachment_svc.get_supabase", return_value=_fake_sb(file_bytes=tampered)):
        with pytest.raises(AttachmentError, match="sha256 mismatch"):
            verify_file_snapshot_for_evidence(
                snapshot=_snap(),
                document_id=DOC_ID,
                field_id=FIELD_ID,
                field_key=FIELD_KEY,
            )


def test_e24_06_mime_not_in_allowlist_raises():
    """E24-06: MIME type not in ALLOWED_FILE_MIME_TYPES → AttachmentError."""
    with patch("services.document_attachment_svc.get_supabase", return_value=_fake_sb()):
        with pytest.raises(AttachmentError, match="mime not in allowlist"):
            verify_file_snapshot_for_evidence(
                snapshot=_snap(mime_type="video/mp4"),
                document_id=DOC_ID,
                field_id=FIELD_ID,
                field_key=FIELD_KEY,
            )


def test_e24_06_path_outside_doc_field_prefix_raises():
    """E24-03 path mismatch: storage path for another doc → AttachmentError."""
    other_doc = "eeeeeeee-0002-0002-0002-000000000002"
    with patch("services.document_attachment_svc.get_supabase", return_value=_fake_sb()):
        with pytest.raises(AttachmentError, match="path mismatch"):
            verify_file_snapshot_for_evidence(
                snapshot=_snap(
                    storage_ref=f"storage://company-docs/attachments/document/{other_doc}/{FIELD_ID}/{SHA256}.pdf",
                ),
                document_id=DOC_ID,
                field_id=FIELD_ID,
                field_key=FIELD_KEY,
            )
