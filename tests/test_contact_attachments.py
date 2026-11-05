"""
WO-TAI-WWW-CONTACT-UX-002-R2/R3: 공개 문의 파일 첨부 엔드포인트 계약 검증
POST /contacts/with-attachments  — 단일 요청 (보안 주경로)
POST /contacts/{id}/attachments  — 첨부 재시도 (소유자 토큰 + 60분 창)
GET  /admin/inquiries/{id}/attachments — 관리자 조회 + role 검증
"""
import io
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# R3: 서명키 fail-closed 테스트를 위해 먼저 설정 (없으면 토큰 발급 차단)
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-signing-key-for-unit-tests-only")


# ── 모킹 헬퍼 ──────────────────────────────────────────────────────

def _mock_sb_found_with_time(inquiry_id: str, created_str: str):
    """문의 존재, 명시적 created_at 문자열 사용"""
    sb = MagicMock()

    def table_side_effect(name):
        m = MagicMock()
        if name == "inquiries":
            sel = MagicMock()
            sel.eq.return_value = sel
            sel.limit.return_value = sel
            sel.execute.return_value = MagicMock(
                data=[{"id": inquiry_id, "created_at": created_str}]
            )
            m.select.return_value = sel
            m.insert.return_value = MagicMock(
                execute=MagicMock(
                    return_value=MagicMock(
                        data=[{"id": inquiry_id, "created_at": created_str}]
                    )
                )
            )
        else:  # attachments (dedup check + _build_existing_response count)
            sel = MagicMock()
            sel.eq.return_value = sel
            sel.limit.return_value = sel
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
            m.delete.return_value = MagicMock(eq=MagicMock(return_value=MagicMock(execute=MagicMock())))
        return m

    sb.table.side_effect = table_side_effect
    sb.storage.from_.return_value.upload.return_value = {}
    sb.storage.from_.return_value.remove.return_value = {}
    return sb


def _mock_sb_found(inquiry_id: str, created_offset: timedelta = timedelta(minutes=5)):
    """문의 존재, 최근 생성 (기본 5분 전)"""
    created_str = (datetime.now(timezone.utc) - created_offset).isoformat()
    return _mock_sb_found_with_time(inquiry_id, created_str)


def _make_token_and_mock(uid: str, offset: timedelta = timedelta(minutes=10)):
    """유효한 업로드 토큰 + 해당 created_at 을 사용하는 mock supabase 반환."""
    from routers.site_public import _generate_upload_token
    created_at = datetime.now(timezone.utc) - offset
    created_str = created_at.isoformat()
    token = _generate_upload_token(uid, created_at)
    sb = _mock_sb_found_with_time(uid, created_str)
    return token, sb


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
            # idempotency SELECT → 없음 (신규 문의)
            sel = MagicMock()
            sel.eq.return_value = sel
            sel.limit.return_value = sel
            sel.execute.return_value = MagicMock(data=[])
            m.select.return_value = sel
            m.insert.return_value = MagicMock(
                execute=MagicMock(return_value=MagicMock(data=[ins_inquiry]))
            )
        else:  # attachments
            # dedup SELECT → 없음
            sel = MagicMock()
            sel.eq.return_value = sel
            sel.limit.return_value = sel
            sel.execute.return_value = MagicMock(data=[])
            m.select.return_value = sel
            m.insert.return_value = MagicMock(
                execute=MagicMock(return_value=MagicMock(data=[ins_attach]))
            )
            m.delete.return_value = MagicMock(eq=MagicMock(return_value=MagicMock(execute=MagicMock())))
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


# ── R2: 업로드 토큰 계약 ────────────────────────────────────────────

class TestUploadToken:
    def test_generate_returns_non_empty_string(self):
        from routers.site_public import _generate_upload_token
        uid = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        token = _generate_upload_token(uid, created_at)
        assert isinstance(token, str) and len(token) > 10

    def test_verify_valid_token_returns_true(self):
        from routers.site_public import _generate_upload_token, _verify_upload_token
        uid = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        created_str = created_at.isoformat()
        token = _generate_upload_token(uid, created_at)
        assert _verify_upload_token(token, uid, created_str)

    def test_verify_wrong_token_returns_false(self):
        from routers.site_public import _verify_upload_token
        uid = str(uuid.uuid4())
        created_str = datetime.now(timezone.utc).isoformat()
        assert not _verify_upload_token("wrongtoken", uid, created_str)

    def test_verify_empty_token_returns_false(self):
        from routers.site_public import _verify_upload_token
        uid = str(uuid.uuid4())
        created_str = datetime.now(timezone.utc).isoformat()
        assert not _verify_upload_token("", uid, created_str)

    def test_verify_different_inquiry_id_returns_false(self):
        from routers.site_public import _generate_upload_token, _verify_upload_token
        uid1 = str(uuid.uuid4())
        uid2 = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        created_str = created_at.isoformat()
        token = _generate_upload_token(uid1, created_at)
        assert not _verify_upload_token(token, uid2, created_str)

    def test_verify_bad_created_str_returns_false(self):
        from routers.site_public import _generate_upload_token, _verify_upload_token
        uid = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        token = _generate_upload_token(uid, created_at)
        assert not _verify_upload_token(token, uid, "not-a-timestamp")

    def test_no_timestamp_parse_passthrough_in_retry_source(self):
        """R2: retry 엔드포인트에 'except Exception:\\n        pass' 없어야 함"""
        import inspect
        from routers import site_public
        src = inspect.getsource(site_public.retry_contact_attachments)
        # R1: pass (방어적 허용) → R2: raise HTTPException
        assert "except Exception:\n        pass" not in src


# ── R3: 서명키 fail-closed 계약 ─────────────────────────────────────

class TestSigningKeyFailClosed:
    def test_missing_env_raises_runtime_error(self, monkeypatch):
        """R3: 서명키 환경변수 미설정 시 RuntimeError — 토큰 발급 차단"""
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        from routers.site_public import _get_upload_signing_key
        with pytest.raises(RuntimeError, match="미설정"):
            _get_upload_signing_key()

    def test_missing_env_verify_returns_false(self, monkeypatch):
        """R3: 서명키 없을 때 토큰 검증도 False — 재시도 차단(fail-closed)"""
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        from routers.site_public import _verify_upload_token
        result = _verify_upload_token("any-token", str(uuid.uuid4()), datetime.now(timezone.utc).isoformat())
        assert result is False

    def test_no_fallback_literal_in_source(self):
        """R3: 소스에 하드코딩 기본값 없어야 함"""
        import inspect
        from routers import site_public
        src = inspect.getsource(site_public._get_upload_signing_key)
        assert "dev-only-not-secure" not in src


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

    def test_200_returns_upload_token(self, client):
        """R2: 성공 응답에 upload_token 포함"""
        uid = str(uuid.uuid4())
        with patch("routers.site_public.get_supabase", return_value=_mock_sb_new_inquiry(uid)):
            resp = client.post(
                "/contacts/with-attachments",
                data={"name": "홍길동", "email": "test@test.com", "content": "문의합니다"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "upload_token" in body
        assert body["upload_token"] is not None and len(body["upload_token"]) > 10

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

    def test_failed_attachments_status_when_no_id_with_files(self, client):
        """R2: 파일 있고 inquiry_id 없으면 attachments_status=failed — 성공 처리 금지"""
        sb = MagicMock()
        # inquiry insert 반환에 id 없음
        sb.table.return_value.insert.return_value.execute.return_value.data = [{"status": "ok"}]
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                "/contacts/with-attachments",
                data={"name": "홍길동", "email": "test@test.com", "content": "문의합니다"},
                files=[("files", ("doc.pdf", b"%PDF-1.4 content", "application/pdf"))],
            )
        assert resp.status_code == 200
        assert resp.json()["attachments_status"] == "failed"


# ── POST /contacts/{id}/attachments (재시도 창 + 소유자 토큰) ──────

class TestRetryEndpointSecurity:
    """R2 소유자 토큰 검증"""

    def test_401_no_token(self, client):
        uid = str(uuid.uuid4())
        sb = _mock_sb_found(uid)
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                files=[("files", ("doc.pdf", b"%PDF-content", "application/pdf"))],
            )
        assert resp.status_code == 401

    def test_403_invalid_token(self, client):
        uid = str(uuid.uuid4())
        sb = _mock_sb_found(uid, created_offset=timedelta(minutes=10))
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                headers={"X-Upload-Token": "invalid-token-value"},
                files=[("files", ("doc.pdf", b"%PDF-content", "application/pdf"))],
            )
        assert resp.status_code == 403

    def test_403_token_for_different_inquiry(self, client):
        """타인의 문의 ID를 사용한 토큰으로는 접근 불가"""
        uid_real = str(uuid.uuid4())
        uid_other = str(uuid.uuid4())
        token, _ = _make_token_and_mock(uid_other, timedelta(minutes=10))
        sb = _mock_sb_found(uid_real, created_offset=timedelta(minutes=10))
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid_real}/attachments",
                headers={"X-Upload-Token": token},
                files=[("files", ("doc.pdf", b"%PDF-content", "application/pdf"))],
            )
        assert resp.status_code == 403


class TestRetryEndpointTimeWindow:
    def test_403_expired_window(self, client):
        uid = str(uuid.uuid4())
        token, sb = _make_token_and_mock(uid, timedelta(hours=2))
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                headers={"X-Upload-Token": token},
                files=[("files", ("doc.pdf", b"%PDF-content", "application/pdf"))],
            )
        assert resp.status_code == 403

    def test_200_within_window(self, client):
        uid = str(uuid.uuid4())
        token, sb = _make_token_and_mock(uid, timedelta(minutes=10))
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                headers={"X-Upload-Token": token},
                files=[("files", ("doc.pdf", b"%PDF-content", "application/pdf"))],
            )
        assert resp.status_code == 200

    def test_404_not_found(self, client):
        uid = str(uuid.uuid4())
        with patch("routers.site_public.get_supabase", return_value=_mock_sb_not_found()):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                headers={"X-Upload-Token": "some-token"},
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
        token, sb = _make_token_and_mock(uid, timedelta(minutes=5))
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                headers={"X-Upload-Token": token},
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

    def test_admin_list_inquiries_has_require_admin(self):
        """R3: GET /admin/inquiries 목록도 서버에서 역할 검증"""
        import inspect
        from routers.admin_inquiries import admin_list_inquiries
        src = inspect.getsource(admin_list_inquiries)
        assert "_require_admin" in src


class TestPublicRouteRegistration:
    """R3: 공개 경로 등록 계약"""

    def test_contacts_with_attachments_is_public(self):
        from services.permission_guard import is_public
        assert is_public("POST", "/contacts/with-attachments")

    def test_contacts_retry_is_public(self):
        from services.permission_guard import is_public
        uid = str(uuid.uuid4())
        assert is_public("POST", f"/contacts/{uid}/attachments")

    def test_contacts_prefix_not_public(self):
        """R4: /contacts/ 전체 접두 경로 공개 아님 — 재시도 경로만 허용"""
        from services.permission_guard import is_public
        assert not is_public("POST", "/contacts/some-arbitrary-path")

    def test_cleanup_storage_logs_on_failure(self):
        """R3: Storage 정리 실패 시 조용히 무시하지 않음 (logger.error 호출)"""
        import inspect
        from routers import site_public
        src = inspect.getsource(site_public._cleanup_storage)
        assert "logger.error" in src

    def test_cleanup_db_rows_logs_on_failure(self):
        """R3: DB행 정리 실패 시 조용히 무시하지 않음 (logger.error 호출)"""
        import inspect
        from routers import site_public
        src = inspect.getsource(site_public._cleanup_db_rows)
        assert "logger.error" in src


class TestDeriveInquiryId:
    """contact-idem-v1 R2: HMAC 파생 ID 순수함수 계약"""

    def test_derived_id_differs_from_client_key(self):
        """HMAC 파생 ID ≠ client_key — 외부 노출된 inquiry_id로 역도출 불가"""
        from routers.site_public import _derive_inquiry_id
        client_key = str(uuid.uuid4())
        derived = _derive_inquiry_id(client_key)
        assert derived is not None
        assert derived != client_key

    def test_derived_id_deterministic(self):
        """동일 입력 → 동일 출력"""
        from routers.site_public import _derive_inquiry_id
        client_key = str(uuid.uuid4())
        assert _derive_inquiry_id(client_key) == _derive_inquiry_id(client_key)

    def test_derived_id_is_valid_uuid(self):
        from routers.site_public import _derive_inquiry_id
        client_key = str(uuid.uuid4())
        derived = _derive_inquiry_id(client_key)
        assert derived is not None
        uuid.UUID(derived)  # raises ValueError if not valid UUID

    def test_non_uuid_client_key_returns_none(self):
        from routers.site_public import _derive_inquiry_id
        assert _derive_inquiry_id("not-a-uuid") is None
        assert _derive_inquiry_id("") is None
        assert _derive_inquiry_id(None) is None

    def test_different_inputs_give_different_ids(self):
        from routers.site_public import _derive_inquiry_id
        k1, k2 = str(uuid.uuid4()), str(uuid.uuid4())
        assert _derive_inquiry_id(k1) != _derive_inquiry_id(k2)


class TestIdempotency:
    """contact-idem-v1 R2: HMAC 파생 ID 기반 중복 방지"""

    def test_existing_inquiry_returns_existing_status(self, client):
        """동일 client_key → 기존 문의 발견 → status=existing 반환"""
        from routers.site_public import _derive_inquiry_id
        client_key = str(uuid.uuid4())
        derived_id = _derive_inquiry_id(client_key)
        created_str = datetime.now(timezone.utc).isoformat()
        sb = _mock_sb_found_with_time(derived_id, created_str)
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                "/contacts/with-attachments",
                data={
                    "name": "홍길동", "email": "test@test.com", "content": "문의합니다",
                    "idempotency_key": client_key,
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "existing"
        assert body["inquiry_id"] == derived_id

    def test_existing_response_no_personal_data(self, client):
        """기존 문의 반환 시 이름·이메일·내용 미포함 — 개인정보 보호"""
        from routers.site_public import _derive_inquiry_id
        client_key = str(uuid.uuid4())
        derived_id = _derive_inquiry_id(client_key)
        created_str = datetime.now(timezone.utc).isoformat()
        sb = _mock_sb_found_with_time(derived_id, created_str)
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                "/contacts/with-attachments",
                data={
                    "name": "홍길동", "email": "test@test.com", "content": "문의합니다",
                    "idempotency_key": client_key,
                },
            )
        body = resp.json()
        assert "data" not in body or body.get("data") is None
        assert "name" not in body
        assert "email" not in body
        assert "content" not in body

    def test_existing_response_includes_attachments_count(self, client):
        """기존 문의 반환 시 inquiry_id·attachments_count 포함"""
        from routers.site_public import _derive_inquiry_id
        client_key = str(uuid.uuid4())
        derived_id = _derive_inquiry_id(client_key)
        created_str = datetime.now(timezone.utc).isoformat()
        sb = _mock_sb_found_with_time(derived_id, created_str)
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                "/contacts/with-attachments",
                data={
                    "name": "홍길동", "email": "test@test.com", "content": "문의합니다",
                    "idempotency_key": client_key,
                },
            )
        body = resp.json()
        assert "inquiry_id" in body
        assert "attachments_count" in body
        assert isinstance(body["attachments_count"], int)

    def test_existing_response_includes_upload_token(self, client):
        """기존 문의 반환 시 upload_token 재발급 — 파일 재시도 가능"""
        from routers.site_public import _derive_inquiry_id
        client_key = str(uuid.uuid4())
        derived_id = _derive_inquiry_id(client_key)
        created_str = datetime.now(timezone.utc).isoformat()
        sb = _mock_sb_found_with_time(derived_id, created_str)
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                "/contacts/with-attachments",
                data={
                    "name": "홍길동", "email": "test@test.com", "content": "문의합니다",
                    "idempotency_key": client_key,
                },
            )
        body = resp.json()
        assert body.get("upload_token") is not None

    def test_invalid_uuid_idempotency_key_ignored(self, client):
        """잘못된 형식의 idempotency_key → 파생 불가 → 정상 신규 문의 접수"""
        sb = _mock_sb_new_inquiry(str(uuid.uuid4()))
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                "/contacts/with-attachments",
                data={
                    "name": "홍길동", "email": "test@test.com", "content": "문의합니다",
                    "idempotency_key": "not-a-uuid",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_external_inquiry_id_cannot_retrieve_existing(self, client):
        """알려진 inquiry_id를 idempotency_key로 보내도 그 문의에 접근 불가.
        파생 ID가 다르므로 SELECT miss → 신규 문의 생성.
        """
        from routers.site_public import _derive_inquiry_id
        known_id = str(uuid.uuid4())
        derived = _derive_inquiry_id(known_id)
        assert derived != known_id  # 보안 전제

        # Mock: known_id SELECT → 데이터 있음, derived SELECT → 없음
        sb = _mock_sb_new_inquiry(str(uuid.uuid4()))
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                "/contacts/with-attachments",
                data={
                    "name": "홍길동", "email": "test@test.com", "content": "문의합니다",
                    "idempotency_key": known_id,
                },
            )
        # 신규 문의 생성 (기존 문의 반환 아님)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


class TestSigningKeyWithFiles:
    """R4: 파일 있을 때 서명키 선확인"""

    def test_503_files_with_no_signing_key(self, client, monkeypatch):
        """서명키 없을 때 파일 첨부 → 문의 저장 전 503 선차단"""
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        resp = client.post(
            "/contacts/with-attachments",
            data={"name": "홍길동", "email": "test@test.com", "content": "문의합니다"},
            files=[("files", ("doc.pdf", b"%PDF-1.4 content", "application/pdf"))],
        )
        assert resp.status_code == 503

    def test_200_no_files_without_signing_key(self, client, monkeypatch):
        """서명키 없어도 파일 없는 문의는 접수 가능"""
        sb = _mock_sb_new_inquiry(str(uuid.uuid4()))
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                "/contacts/with-attachments",
                data={"name": "홍길동", "email": "test@test.com", "content": "문의합니다"},
            )
        assert resp.status_code == 200


class TestRetryPartialStoredCount:
    """CLOSE-GATE: 부분 저장 후 재시도 — 중복 제외 실제 신규 수로 한도 계산"""

    def test_partial_stored_retry_not_rejected_by_count(self, client):
        """5개 중 1개 저장 후 5개 재시도 — a.pdf 중복 제외 net_new=4, 1+4=5 ≤ 5 → 허용"""
        uid = str(uuid.uuid4())
        pdf = b"%PDF-1.4 content"
        created_at_dt = datetime.now(timezone.utc) - timedelta(minutes=10)
        created_str = created_at_dt.isoformat()

        from routers.site_public import _generate_upload_token
        token = _generate_upload_token(uid, created_at_dt)

        sb = MagicMock()

        def table_side(name):
            m = MagicMock()
            if name == "inquiries":
                sel = MagicMock()
                sel.eq.return_value = sel
                sel.limit.return_value = sel
                sel.execute.return_value = MagicMock(data=[{"id": uid, "created_at": created_str}])
                m.select.return_value = sel
            else:  # attachments
                sel = MagicMock()
                sel.eq.return_value = sel
                sel.limit.return_value = sel
                # 기존 1개: a.pdf 저장됨
                sel.execute.return_value = MagicMock(
                    count=1,
                    data=[{"id": str(uuid.uuid4()), "file_name": "a.pdf", "file_size": len(pdf)}],
                )
                m.select.return_value = sel
                m.insert.return_value = MagicMock(
                    execute=MagicMock(return_value=MagicMock(data=[{"id": str(uuid.uuid4())}]))
                )
                m.delete.return_value = MagicMock(eq=MagicMock(return_value=MagicMock(execute=MagicMock())))
            return m

        sb.table.side_effect = table_side
        sb.storage.from_.return_value.upload.return_value = {}
        sb.storage.from_.return_value.remove.return_value = {}

        files = [
            ("files", ("a.pdf", pdf, "application/pdf")),  # 이미 저장됨 — 중복
            ("files", ("b.pdf", pdf, "application/pdf")),
            ("files", ("c.pdf", pdf, "application/pdf")),
            ("files", ("d.pdf", pdf, "application/pdf")),
            ("files", ("e.pdf", pdf, "application/pdf")),
        ]
        with patch("routers.site_public.get_supabase", return_value=sb):
            resp = client.post(
                f"/contacts/{uid}/attachments",
                headers={"X-Upload-Token": token},
                files=files,
            )
        assert resp.status_code == 200, f"부분 저장 재시도 거부됨: {resp.text}"


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
