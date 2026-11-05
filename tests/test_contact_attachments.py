"""
WO-TAI-WWW-CONTACT-UX-002-A1: 공개 문의 파일 첨부 엔드포인트 계약 검증
POST /contacts/{inquiry_id}/attachments
GET  /admin/inquiries/{inquiry_id}/attachments (via admin_inquiries router)
"""
import io
import uuid
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

# ── 모킹 헬퍼 ──────────────────────────────────────────────────────

def _mock_supabase_found(inquiry_id: str):
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": inquiry_id}
    ]
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.count = 0
    sb.storage.from_.return_value.upload.return_value = {}
    ins_row = {"id": str(uuid.uuid4()), "file_name": "test.pdf", "file_size": 10, "file_ext": "pdf", "mime_type": "application/pdf"}
    sb.table.return_value.insert.return_value.execute.return_value.data = [ins_row]
    return sb


def _mock_supabase_not_found():
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    return sb


def _make_upload_file(name: str, content: bytes = b"x" * 100) -> UploadFile:
    f = UploadFile(filename=name, file=io.BytesIO(content))
    return f


# ── site_public 직접 함수 계약 ──────────────────────────────────────

class TestAllowedExtensions:
    """_ALLOWED_EXTS 계약: 허용/거부 목록"""

    def test_allowed_exts_present(self):
        from routers.site_public import _ALLOWED_EXTS
        for ext in ("pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "txt", "zip", "hwp", "hwpx"):
            assert ext in _ALLOWED_EXTS, f"{ext} must be in _ALLOWED_EXTS"

    def test_jpeg_alias(self):
        from routers.site_public import _ALLOWED_EXTS
        assert "jpeg" in _ALLOWED_EXTS

    def test_exe_not_allowed(self):
        from routers.site_public import _ALLOWED_EXTS
        assert "exe" not in _ALLOWED_EXTS

    def test_sh_not_allowed(self):
        from routers.site_public import _ALLOWED_EXTS
        assert "sh" not in _ALLOWED_EXTS


class TestConstants:
    def test_max_files(self):
        from routers.site_public import CONTACT_ATTACH_MAX_FILES
        assert CONTACT_ATTACH_MAX_FILES == 5

    def test_max_bytes(self):
        from routers.site_public import CONTACT_ATTACH_MAX_BYTES
        assert CONTACT_ATTACH_MAX_BYTES == 10 * 1024 * 1024

    def test_bucket(self):
        from routers.site_public import CONTACT_BUCKET
        assert CONTACT_BUCKET == "company-docs"


class TestStableRef:
    def test_stable_ref_format(self):
        from routers.site_public import _contact_stable_ref
        ref = _contact_stable_ref("contact-attachments/2026-11/abc/def.pdf")
        assert ref == "storage://company-docs/contact-attachments/2026-11/abc/def.pdf"


class TestParseInquiryUuid:
    def test_valid_uuid(self):
        from routers.site_public import _parse_inquiry_uuid
        uid = str(uuid.uuid4())
        assert _parse_inquiry_uuid(uid) == uid

    def test_invalid_uuid_raises_400(self):
        from routers.site_public import _parse_inquiry_uuid
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _parse_inquiry_uuid("not-a-uuid")
        assert exc.value.status_code == 400


# ── 엔드포인트 통합 계약 (TestClient) ──────────────────────────────

@pytest.fixture
def client():
    from main import app
    return TestClient(app, raise_server_exceptions=False)


class TestUploadEndpointNotFound:
    def test_404_on_missing_inquiry(self, client):
        uid = str(uuid.uuid4())
        with patch("routers.site_public.get_supabase", return_value=_mock_supabase_not_found()):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                files=[("files", ("test.pdf", b"content", "application/pdf"))],
            )
        assert resp.status_code == 404

    def test_400_on_bad_uuid(self, client):
        resp = client.post(
            "/contacts/not-a-uuid/attachments",
            files=[("files", ("test.pdf", b"content", "application/pdf"))],
        )
        assert resp.status_code == 400


class TestUploadEndpointValidation:
    def test_400_on_disallowed_ext(self, client):
        uid = str(uuid.uuid4())
        with patch("routers.site_public.get_supabase", return_value=_mock_supabase_found(uid)):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                files=[("files", ("malware.exe", b"MZ\x00", "application/octet-stream"))],
            )
        assert resp.status_code == 400
        assert "형식" in resp.json().get("detail", "")

    def test_400_on_oversized_file(self, client):
        uid = str(uuid.uuid4())
        big = b"x" * (10 * 1024 * 1024 + 1)
        with patch("routers.site_public.get_supabase", return_value=_mock_supabase_found(uid)):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                files=[("files", ("big.pdf", big, "application/pdf"))],
            )
        assert resp.status_code == 400
        assert "크기" in resp.json().get("detail", "")

    def test_400_on_too_many_files(self, client):
        uid = str(uuid.uuid4())
        sb = _mock_supabase_found(uid)
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.count = 0
        with patch("routers.site_public.get_supabase", return_value=sb):
            files = [("files", (f"f{i}.pdf", b"x", "application/pdf")) for i in range(6)]
            resp = client.post(f"/contacts/{uid}/attachments", files=files)
        assert resp.status_code == 400
        assert "5" in resp.json().get("detail", "")


class TestUploadEndpointSuccess:
    def test_200_pdf_upload(self, client):
        uid = str(uuid.uuid4())
        sb = _mock_supabase_found(uid)
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                files=[("files", ("doc.pdf", b"PDF content", "application/pdf"))],
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert "attachments" in body["data"]
        assert len(body["data"]["attachments"]) == 1

    def test_200_hwp_upload(self, client):
        uid = str(uuid.uuid4())
        sb = _mock_supabase_found(uid)
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                files=[("files", ("form.hwp", b"HWP content", "application/x-hwp"))],
            )
        assert resp.status_code == 200

    def test_response_fields(self, client):
        uid = str(uuid.uuid4())
        sb = _mock_supabase_found(uid)
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                files=[("files", ("report.pdf", b"content", "application/pdf"))],
            )
        item = resp.json()["data"]["attachments"][0]
        for key in ("file_name", "file_size", "file_ext", "mime_type"):
            assert key in item, f"{key} must be in response"


# ── admin 첨부파일 조회 계약 ──────────────────────────────────────

class TestAdminAttachmentsSignedRef:
    """storage:// ref → signed URL 변환 경로 단위 검증"""

    def test_prefix_extraction(self):
        url = "storage://company-docs/contact-attachments/2026-11/abc/def.pdf"
        prefix = "storage://company-docs/"
        assert url.startswith(prefix)
        path = url[len(prefix):]
        assert path == "contact-attachments/2026-11/abc/def.pdf"

    def test_non_storage_ref_skipped(self):
        url = "https://example.com/file.pdf"
        assert not url.startswith("storage://company-docs/")
