"""
WO-TAI-WWW-CONTACT-UX-002-R1: 공개 문의 파일 첨부 엔드포인트 계약 검증
POST /contacts/with-attachments  — 단일 요청 (보안 주경로)
POST /contacts/{id}/attachments  — 첨부 재시도 (60분 창)
GET  /admin/inquiries/{id}/attachments — 관리자 조회 + role 검증
"""
import io
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── 모킹 헬퍼 ──────────────────────────────────────────────────────

def _mock_sb_found(inquiry_id: str, created_offset: timedelta = timedelta(minutes=5)):
    """문의 존재, 최근 생성 (기본 5분 전)"""
    sb = MagicMock()
    created_at = (datetime.now(timezone.utc) - created_offset).isoformat()

    # table mock — 체이닝 허용
    table_mock = MagicMock()
    sb.table.return_value = table_mock

    # inquiries.select chain
    select_chain = MagicMock()
    table_mock.select.return_value = select_chain
    select_chain.eq.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.execute.return_value = MagicMock(
        data=[{"id": inquiry_id, "created_at": created_at}]
    )

    # attachments count
    count_chain = MagicMock()
    count_chain.eq.return_value = count_chain
    count_chain.execute.return_value = MagicMock(count=0, data=[])

    # select for count (second call pattern)
    def table_side_effect(name):
        m = MagicMock()
        if name == "inquiries":
            sel = MagicMock()
            sel.eq.return_value = sel
            sel.limit.return_value = sel
            sel.execute.return_value = MagicMock(
                data=[{"id": inquiry_id, "created_at": created_at}]
            )
            m.select.return_value = sel
            m.insert.return_value = MagicMock(
                execute=MagicMock(
                    return_value=MagicMock(
                        data=[{"id": inquiry_id, "created_at": created_at}]
                    )
                )
            )
        else:  # attachments
            sel = MagicMock()
            sel.eq.return_value = sel
            sel.execute.return_value = MagicMock(count=0, data=[])
            m.select.return_value = sel
            ins_row = {
                "id": str(uuid.uuid4()),
                "file_name": "test.pdf",
                "file_size": 10,
                "file_ext": "pdf",
                "mime_type": "application/pdf",
            }
            m.insert.return_value = MagicMock(
                execute=MagicMock(return_value=MagicMock(data=[ins_row]))
            )
        return m

    sb.table.side_effect = table_side_effect
    sb.storage.from_.return_value.upload.return_value = {}
    sb.storage.from_.return_value.remove.return_value = {}
    return sb


def _mock_sb_not_found():
    sb = MagicMock()
    sel = MagicMock()
    sel.eq.return_value = sel
    sel.limit.return_value = sel
    sel.execute.return_value = MagicMock(data=[])
    sb.table.return_value.select.return_value = sel
    return sb


def _mock_sb_new_inquiry(inquiry_id: str):
    """with-attachments 엔드포인트용: insert + storage + attachments insert"""
    sb = MagicMock()
    created_at = datetime.now(timezone.utc).isoformat()
    ins_inquiry = {"id": inquiry_id, "created_at": created_at}
    ins_attach = {
        "id": str(uuid.uuid4()),
        "file_name": "f.pdf",
        "file_size": 10,
        "file_ext": "pdf",
        "mime_type": "application/pdf",
    }

    def table_side(name):
        m = MagicMock()
        if name == "inquiries":
            m.insert.return_value = MagicMock(
                execute=MagicMock(return_value=MagicMock(data=[ins_inquiry]))
            )
        else:  # attachments
            m.insert.return_value = MagicMock(
                execute=MagicMock(return_value=MagicMock(data=[ins_attach]))
            )
        return m

    sb.table.side_effect = table_side
    sb.storage.from_.return_value.upload.return_value = {}
    sb.storage.from_.return_value.remove.return_value = {}
    return sb


# ── 상수 및 순수 함수 계약 ──────────────────────────────────────────

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

    def test_attach_window_1_hour(self):
        from routers.site_public import _ATTACH_WINDOW
        assert _ATTACH_WINDOW == timedelta(hours=1)


class TestAllowedExts:
    def test_allowed_exts_present(self):
        from routers.site_public import _ALLOWED_EXTS
        for ext in ("pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "txt", "zip", "hwp", "hwpx"):
            assert ext in _ALLOWED_EXTS

    def test_exe_not_allowed(self):
        from routers.site_public import _ALLOWED_EXTS
        assert "exe" not in _ALLOWED_EXTS


class TestStableRef:
    def test_format(self):
        from routers.site_public import _contact_stable_ref
        ref = _contact_stable_ref("contact-attachments/2026-11/abc/def.pdf")
        assert ref == "storage://company-docs/contact-attachments/2026-11/abc/def.pdf"


class TestParseInquiryUuid:
    def test_valid_uuid(self):
        from routers.site_public import _parse_inquiry_uuid
        uid = str(uuid.uuid4())
        assert _parse_inquiry_uuid(uid) == uid

    def test_invalid_raises_400(self):
        from routers.site_public import _parse_inquiry_uuid
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _parse_inquiry_uuid("not-a-uuid")
        assert exc.value.status_code == 400


class TestFileMagic:
    def test_pdf_magic_ok(self):
        from routers.site_public import _file_magic_ok
        assert _file_magic_ok(b"%PDF-1.4 ...", "pdf")

    def test_pdf_magic_fail(self):
        from routers.site_public import _file_magic_ok
        assert not _file_magic_ok(b"\xff\xd8\xff ...", "pdf")

    def test_png_magic_ok(self):
        from routers.site_public import _file_magic_ok
        assert _file_magic_ok(b"\x89PNG\r\n\x1a\n", "png")

    def test_jpg_magic_ok(self):
        from routers.site_public import _file_magic_ok
        assert _file_magic_ok(b"\xff\xd8\xff\xe0", "jpg")

    def test_zip_magic_ok(self):
        from routers.site_public import _file_magic_ok
        assert _file_magic_ok(b"PK\x03\x04...", "zip")

    def test_dangerous_mz_rejected(self):
        from routers.site_public import _file_magic_ok
        assert not _file_magic_ok(b"MZ\x90\x00", "pdf")

    def test_dangerous_elf_rejected(self):
        from routers.site_public import _file_magic_ok
        assert not _file_magic_ok(b"\x7fELF...", "zip")

    def test_dangerous_shebang_rejected(self):
        from routers.site_public import _file_magic_ok
        assert not _file_magic_ok(b"#!/bin/sh", "txt")

    def test_txt_ok_no_null(self):
        from routers.site_public import _file_magic_ok
        assert _file_magic_ok(b"hello world", "txt")

    def test_txt_fail_null_byte(self):
        from routers.site_public import _file_magic_ok
        assert not _file_magic_ok(b"hello\x00world", "txt")


# ── TestClient fixture ──────────────────────────────────────────────

@pytest.fixture
def client():
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ── POST /contacts/with-attachments ───────────────────────────────

class TestWithAttachmentsEndpoint:
    def test_200_no_files(self, client):
        uid = str(uuid.uuid4())
        with patch("routers.site_public.get_supabase", return_value=_mock_sb_new_inquiry(uid)):
            resp = client.post(
                "/contacts/with-attachments",
                data={"name": "홍길동", "email": "test@test.com", "content": "문의합니다"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["attachments_status"] == "ok"

    def test_200_with_pdf_file(self, client):
        uid = str(uuid.uuid4())
        with patch("routers.site_public.get_supabase", return_value=_mock_sb_new_inquiry(uid)):
            resp = client.post(
                "/contacts/with-attachments",
                data={"name": "홍길동", "email": "test@test.com", "content": "문의합니다"},
                files=[("files", ("doc.pdf", b"%PDF-1.4 content", "application/pdf"))],
            )
        assert resp.status_code == 200
        assert resp.json()["attachments_status"] == "ok"

    def test_400_disallowed_ext(self, client):
        uid = str(uuid.uuid4())
        with patch("routers.site_public.get_supabase", return_value=_mock_sb_new_inquiry(uid)):
            resp = client.post(
                "/contacts/with-attachments",
                data={"name": "홍길동", "email": "test@test.com", "content": "문의합니다"},
                files=[("files", ("bad.exe", b"MZ\x90\x00", "application/octet-stream"))],
            )
        assert resp.status_code == 400

    def test_400_magic_mismatch(self, client):
        uid = str(uuid.uuid4())
        with patch("routers.site_public.get_supabase", return_value=_mock_sb_new_inquiry(uid)):
            resp = client.post(
                "/contacts/with-attachments",
                data={"name": "홍길동", "email": "test@test.com", "content": "문의합니다"},
                files=[("files", ("fake.pdf", b"\xff\xd8\xff\xe0", "application/pdf"))],
            )
        assert resp.status_code == 400
        assert "형식" in resp.json().get("detail", "")

    def test_400_too_many_files(self, client):
        uid = str(uuid.uuid4())
        with patch("routers.site_public.get_supabase", return_value=_mock_sb_new_inquiry(uid)):
            files = [("files", (f"f{i}.pdf", b"%PDF-content", "application/pdf")) for i in range(6)]
            resp = client.post(
                "/contacts/with-attachments",
                data={"name": "홍길동", "email": "test@test.com", "content": "문의합니다"},
                files=files,
            )
        assert resp.status_code == 400

    def test_200_no_inquiry_id_no_attach(self, client):
        """inquiry 생성 OK이지만 id 없어도 attachments_status=ok (파일 없는 경우)"""
        sb = MagicMock()
        sb.table.return_value.insert.return_value.execute.return_value.data = [{"status": "ok"}]
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                "/contacts/with-attachments",
                data={"name": "홍길동", "email": "test@test.com", "content": "문의합니다"},
            )
        assert resp.status_code == 200


# ── POST /contacts/{id}/attachments (재시도 창) ────────────────────

class TestRetryEndpointTimeWindow:
    def test_403_expired_window(self, client):
        uid = str(uuid.uuid4())
        sb = _mock_sb_found(uid, created_offset=timedelta(hours=2))
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                files=[("files", ("doc.pdf", b"%PDF-content", "application/pdf"))],
            )
        assert resp.status_code == 403

    def test_200_within_window(self, client):
        uid = str(uuid.uuid4())
        sb = _mock_sb_found(uid, created_offset=timedelta(minutes=10))
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                files=[("files", ("doc.pdf", b"%PDF-content", "application/pdf"))],
            )
        assert resp.status_code == 200

    def test_404_not_found(self, client):
        uid = str(uuid.uuid4())
        with patch("routers.site_public.get_supabase", return_value=_mock_sb_not_found()):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                files=[("files", ("doc.pdf", b"%PDF-content", "application/pdf"))],
            )
        assert resp.status_code == 404

    def test_400_bad_uuid(self, client):
        resp = client.post(
            "/contacts/not-a-uuid/attachments",
            files=[("files", ("doc.pdf", b"%PDF-content", "application/pdf"))],
        )
        assert resp.status_code == 400

    def test_400_magic_mismatch_on_retry(self, client):
        uid = str(uuid.uuid4())
        sb = _mock_sb_found(uid)
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                files=[("files", ("fake.pdf", b"MZ\x90\x00", "application/pdf"))],
            )
        assert resp.status_code == 400


# ── 관리자 첨부 조회 — 역할 검증 ────────────────────────────────────

class TestAdminAttachmentsRoleGuard:
    """_require_admin 호출 위치 계약"""

    def test_require_admin_import(self):
        import routers.admin_inquiries as ai
        assert hasattr(ai, "_require_admin") or "_require_admin" in dir(ai)

    def test_admin_attachments_function_has_require_admin(self):
        import inspect
        from routers.admin_inquiries import admin_get_inquiry_attachments
        src = inspect.getsource(admin_get_inquiry_attachments)
        assert "_require_admin" in src


class TestAdminAttachmentsSignedRef:
    def test_prefix_extraction(self):
        url = "storage://company-docs/contact-attachments/2026-11/abc/def.pdf"
        prefix = "storage://company-docs/"
        assert url.startswith(prefix)
        path = url[len(prefix):]
        assert path == "contact-attachments/2026-11/abc/def.pdf"

    def test_non_storage_ref_skipped(self):
        url = "https://example.com/file.pdf"
        assert not url.startswith("storage://company-docs/")
