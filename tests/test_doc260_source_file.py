"""
tests/test_doc260_source_file.py
WO-DOC260-WPC-DOCUMENT-FIRST-004 — source file download endpoint

테스트 계약:
  T01 — 미인증 요청 → 401
  T02 — 경로 계산 불가 doc_id (형식 불일치) → 404
  T03 — route_group=F_SCOPE_OUT 문서 → 404 (서버 차단)
  T03b — route_group=A_INTERNAL 문서 → 404 (웹생성 경로 사용)
  T04 — 유효 doc_id + 활성 문서 + 스토리지 성공 → 200 + octet-stream + attachment
  T05 — 스토리지 일반 Exception → 503 (파일 없음 404와 구분)
  T06 — 경로 조작 시도 (형식 검증으로 차단) → None 반환
  T07 — 경로 계산 성공이지만 document_forms에 없음 → 404
  T08 — 스토리지 반환 bytes 비어 있음 → 404 (파일 미연결 상태)
  T09 — 기존 목록 엔드포인트 회귀 (source-file 추가로 중단 금지)
  T10 — StorageApiError(status=400, Object not found) → 404 (스토리지 SDK 예외 → 파일없음)
  T11 — StorageApiError(status=400, 비-not-found 메시지) → 503 (다른 SDK 오류 구분)
  T12 — B_OFFICIAL + official_status=HOLD → 404 (Gate 2b 차단)
  T13 — list_available_doc_ids: Storage 목록 → doc_id 집합 반환
  T14 — list_available_doc_ids: Storage 오류 → 빈 집합 (보수적 처리)
  T15 — _enrich_with_source_file_availability: 파일 있는 항목 True, 없는 항목 False

FORM647 단위 테스트 (인프라 검증 — 현재 라우터 미연결):
  flSeq(document_forms.file_url) ≠ FORM647 ek. doc_id→ek 크로스워크 미확립.
  F01 — extract_flseq: law.go.kr URL에서 추출
  F02 — extract_flseq: flSeq 없는 URL → None
  F03 — is_form647_service_gate_open: BLOCKED → False
  F04 — is_form647_service_gate_open: service_released=True + APPROVED → True
  F05 — is_form647_service_gate_open: service_released=False → False
"""
from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# 허용 목록 테스트 상수
# ---------------------------------------------------------------------------

_TEST_DOC_ID = "DOC-TST-001"
_TEST_STORAGE_PATH = "doc_forms/DOC-TST-001.hwp"
_TEST_FILE_BYTES = b"HWP_STUB_BYTES"
_MOCK_USER = {"id": "usr-001", "role_code": "002"}


def _make_sb(form_data: list, storage_result: bytes | Exception) -> MagicMock:
    """document_forms 조회 + storage.download() 목업."""
    sb = MagicMock()
    q = MagicMock()
    q.execute.return_value = MagicMock(data=form_data)
    q.select.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    sb.table.return_value = q

    bucket = MagicMock()
    if isinstance(storage_result, Exception):
        bucket.download.side_effect = storage_result
    else:
        bucket.download.return_value = storage_result
    sb.storage.from_.return_value = bucket
    return sb


def _build_app(
    *,
    authenticated: bool,
    verified_path: str | None,
    sb: MagicMock | None = None,
):
    """TestClient용 FastAPI 앱 조립."""
    from fastapi import FastAPI
    from routers.document_forms import router
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(router)

    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

    return app, verified_path, sb


# ---------------------------------------------------------------------------
# source_file_allowlist 단위 테스트
# ---------------------------------------------------------------------------

class TestSourceFilePathComputation(unittest.TestCase):

    def test_valid_doc_id_returns_standard_path(self):
        """유효한 DOC-{SECTOR}-{NUMBER} → 표준 경로 반환."""
        from services.document_engine.source_file_allowlist import get_verified_path
        self.assertEqual(get_verified_path(_TEST_DOC_ID), _TEST_STORAGE_PATH)
        self.assertEqual(get_verified_path("DOC-OSH-003"), "doc_forms/DOC-OSH-003.hwp")
        self.assertEqual(get_verified_path("DOC-BLD-013"), "doc_forms/DOC-BLD-013.hwp")
        self.assertEqual(get_verified_path("DOC-CHEM-009"), "doc_forms/DOC-CHEM-009.hwp")

    def test_invalid_format_returns_none(self):
        """잘못된 형식 doc_id → None."""
        from services.document_engine.source_file_allowlist import get_verified_path
        self.assertIsNone(get_verified_path("INVALID"))
        self.assertIsNone(get_verified_path("doc-osh-003"))   # 소문자 불허
        self.assertIsNone(get_verified_path("DOC-osh-003"))   # 섹터 소문자 불허
        self.assertIsNone(get_verified_path(""))              # 빈 문자열

    def test_T06_path_traversal_blocked(self):
        """T06 — 경로 조작 시도 → None (형식 불일치로 차단)."""
        from services.document_engine.source_file_allowlist import get_verified_path
        self.assertIsNone(get_verified_path("../etc/passwd"))
        self.assertIsNone(get_verified_path("DOC-OSH-003/../etc"))
        self.assertIsNone(get_verified_path("DOC-OSH-003/../../etc/passwd"))

    def test_bucket_name(self):
        from services.document_engine.source_file_allowlist import source_file_bucket
        self.assertEqual(source_file_bucket(), "form-originals")


# ---------------------------------------------------------------------------
# FORM647 매핑 단위 테스트
# ---------------------------------------------------------------------------

class TestForm647Mapping(unittest.TestCase):

    def test_F01_extract_flseq_from_law_url(self):
        """F01 — law.go.kr URL에서 flSeq 추출."""
        from services.document_engine.form647_mapping import extract_flseq
        url = "https://www.law.go.kr/LSW/flDownload.do?flSeq=17995183"
        self.assertEqual(extract_flseq(url), 17995183)

    def test_F01b_extract_flseq_query_param(self):
        """F01b — 다른 파라미터와 혼합된 URL에서 flSeq 추출."""
        from services.document_engine.form647_mapping import extract_flseq
        url = "https://www.law.go.kr/LSW/flDownload.do?type=hwp&flSeq=12345678&other=1"
        self.assertEqual(extract_flseq(url), 12345678)

    def test_F02_no_flseq_returns_none(self):
        """F02 — flSeq 없는 URL → None."""
        from services.document_engine.form647_mapping import extract_flseq
        self.assertIsNone(extract_flseq("https://example.com/no-flseq"))
        self.assertIsNone(extract_flseq(None))
        self.assertIsNone(extract_flseq(""))

    def test_F03_gate_blocked_returns_false(self):
        """F03 — service_sot_gate=BLOCKED → False."""
        from services.document_engine.form647_mapping import is_form647_service_gate_open
        self.assertFalse(is_form647_service_gate_open(
            {"service_released": False, "service_sot_gate": "BLOCKED"}
        ))
        self.assertFalse(is_form647_service_gate_open(
            {"service_released": True, "service_sot_gate": "BLOCKED"}
        ))

    def test_F04_gate_open_returns_true(self):
        """F04 — service_released=True + gate=APPROVED → True (gate 해제 후 미래 상태)."""
        from services.document_engine.form647_mapping import is_form647_service_gate_open
        self.assertTrue(is_form647_service_gate_open(
            {"service_released": True, "service_sot_gate": "APPROVED"}
        ))

    def test_F05_gate_open_requires_service_released(self):
        """F05 — service_released=False 이면 gate 값 무관하게 False."""
        from services.document_engine.form647_mapping import is_form647_service_gate_open
        self.assertFalse(is_form647_service_gate_open(
            {"service_released": False, "service_sot_gate": "APPROVED"}
        ))


# ---------------------------------------------------------------------------
# 엔드포인트 통합 테스트
# ---------------------------------------------------------------------------

class TestSourceFileEndpoint(unittest.TestCase):

    def _client(self, *, authenticated: bool, verified_path: str | None,
                form_data: list = None, storage_result: bytes | Exception = b""):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(router)

        if authenticated:
            app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        sb = _make_sb(form_data or [], storage_result)

        with (
            patch("routers.document_forms.get_verified_path", return_value=verified_path),
            patch("routers.document_forms.get_supabase", return_value=sb),
        ):
            yield TestClient(app, raise_server_exceptions=False)

    # T01: 미인증
    def test_T01_unauthenticated(self):
        """T01 — Authorization 헤더 없음 → 401."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router

        app = FastAPI()
        app.include_router(router)
        # dependency_overrides 없음 → 실제 get_current_user 가 헤더 없음을 감지해 401
        with patch("routers.document_forms.get_verified_path", return_value=None), \
             patch("routers.document_forms.get_supabase", return_value=MagicMock()):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")
        self.assertEqual(resp.status_code, 401)

    # T02: 경로 계산 불가 (get_verified_path=None — 형식 불일치 등)
    def test_T02_invalid_doc_id(self):
        """T02 — get_verified_path가 None 반환 → 404."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        with patch("routers.document_forms.get_verified_path", return_value=None), \
             patch("routers.document_forms.get_supabase", return_value=MagicMock()):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")
        self.assertEqual(resp.status_code, 404)

    # T03: F_SCOPE_OUT → 서버 차단
    def test_T03_fscope_out_blocked(self):
        """T03 — route_group=F_SCOPE_OUT → 404 (서버 Gate 2 차단)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        with patch("routers.document_forms.get_verified_path", return_value=_TEST_STORAGE_PATH), \
             patch("routers.document_forms.get_provision_policy",
                   return_value={"route_group": "F_SCOPE_OUT", "investment_decision": "STOP"}), \
             patch("routers.document_forms.get_supabase", return_value=MagicMock()):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")
        self.assertEqual(resp.status_code, 404)

    # T03b: A_INTERNAL → 서버 차단
    def test_T03b_ainternal_blocked(self):
        """T03b — route_group=A_INTERNAL → 404 (웹생성 경로 사용)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        with patch("routers.document_forms.get_verified_path", return_value=_TEST_STORAGE_PATH), \
             patch("routers.document_forms.get_provision_policy",
                   return_value={"route_group": "A_INTERNAL", "investment_decision": "KEEP"}), \
             patch("routers.document_forms.get_supabase", return_value=MagicMock()):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")
        self.assertEqual(resp.status_code, 404)

    # T03c: A_INTERNAL + source_download_exception=True → 통과 (HWP 충돌 6종 예외)
    def test_T03c_ainternal_exception_allowed(self):
        """T03c — A_INTERNAL + source_download_exception=True → 200 (BLD-011/CON-047~051 예외)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        sb = _make_sb([{"id": "uuid-1", "doc_id": _TEST_DOC_ID}], _TEST_FILE_BYTES)

        with patch("routers.document_forms.get_verified_path", return_value=_TEST_STORAGE_PATH), \
             patch("routers.document_forms.get_provision_policy",
                   return_value={
                       "route_group": "A_INTERNAL",
                       "investment_decision": "KEEP",
                       "source_download_exception": True,
                   }), \
             patch("routers.document_forms.get_supabase", return_value=sb):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")
        self.assertEqual(resp.status_code, 200)

    # T03d: A_INTERNAL + source_download_exception=False → 차단 (일반 웹작성 경로)
    def test_T03d_ainternal_no_exception_blocked(self):
        """T03d — A_INTERNAL + source_download_exception=False → 404 (예외 미해당)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        with patch("routers.document_forms.get_verified_path", return_value=_TEST_STORAGE_PATH), \
             patch("routers.document_forms.get_provision_policy",
                   return_value={
                       "route_group": "A_INTERNAL",
                       "investment_decision": "KEEP",
                       "source_download_exception": False,
                   }), \
             patch("routers.document_forms.get_supabase", return_value=MagicMock()):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")
        self.assertEqual(resp.status_code, 404)

    # T04: 성공
    def test_T04_success(self):
        """T04 — 성공 → 200 + octet-stream + attachment + no-store."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        sb = _make_sb([{"id": "uuid-1", "doc_id": _TEST_DOC_ID}], _TEST_FILE_BYTES)

        with patch("routers.document_forms.get_verified_path", return_value=_TEST_STORAGE_PATH), \
             patch("routers.document_forms.get_provision_policy",
                   return_value={"route_group": "U_UNRESOLVED", "investment_decision": "HOLD"}), \
             patch("routers.document_forms.get_supabase", return_value=sb):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/octet-stream")
        self.assertIn("attachment", resp.headers.get("content-disposition", ""))
        self.assertIn(f"{_TEST_DOC_ID}.hwp", resp.headers.get("content-disposition", ""))
        self.assertEqual(resp.content, _TEST_FILE_BYTES)
        self.assertIn("no-store", resp.headers.get("cache-control", ""))

    # T05: 스토리지 오류 → 503
    def test_T05_storage_failure_503(self):
        """T05 — 스토리지 Exception → 503 (파일 없음 404와 구분)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        sb = _make_sb([{"id": "uuid-1", "doc_id": _TEST_DOC_ID}],
                      RuntimeError("storage unavailable"))

        with patch("routers.document_forms.get_verified_path", return_value=_TEST_STORAGE_PATH), \
             patch("routers.document_forms.get_provision_policy",
                   return_value={"route_group": "U_UNRESOLVED", "investment_decision": "HOLD"}), \
             patch("routers.document_forms.get_supabase", return_value=sb):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")

        self.assertEqual(resp.status_code, 503)

    # T07: document_forms에 없음
    def test_T07_doc_not_in_db(self):
        """T07 — 경로 계산 성공이지만 document_forms 조회 결과 없음 → 404."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        sb = _make_sb([], b"content")  # form_data=[] → doc 없음

        with patch("routers.document_forms.get_verified_path", return_value=_TEST_STORAGE_PATH), \
             patch("routers.document_forms.get_provision_policy",
                   return_value={"route_group": "U_UNRESOLVED", "investment_decision": "HOLD"}), \
             patch("routers.document_forms.get_supabase", return_value=sb):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")

        self.assertEqual(resp.status_code, 404)

    # T08: 빈 bytes → 404 (파일 미연결)
    def test_T08_empty_bytes_no_file(self):
        """T08 — doc_forms/ 빈 bytes → 404 (파일 미연결 상태)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        sb = _make_sb([{"id": "uuid-1", "doc_id": _TEST_DOC_ID}], b"")

        with patch("routers.document_forms.get_verified_path", return_value=_TEST_STORAGE_PATH), \
             patch("routers.document_forms.get_provision_policy",
                   return_value={"route_group": "U_UNRESOLVED", "investment_decision": "HOLD"}), \
             patch("routers.document_forms.get_supabase", return_value=sb):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")

        self.assertEqual(resp.status_code, 404)

    # T10: StorageApiError(400) → 404 (Supabase SDK "Object not found" 처리)
    def test_T10_storage_api_error_not_found_returns_404(self):
        """T10 — StorageApiError(status=400) → 404 (스토리지 SDK 파일 없음 예외)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user
        from storage3.exceptions import StorageApiError

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        sb = _make_sb([{"id": "uuid-1", "doc_id": _TEST_DOC_ID}],
                      StorageApiError("Object not found", "404", 400))

        with patch("routers.document_forms.get_verified_path", return_value=_TEST_STORAGE_PATH), \
             patch("routers.document_forms.get_provision_policy",
                   return_value={"route_group": "U_UNRESOLVED", "investment_decision": "HOLD"}), \
             patch("routers.document_forms.get_supabase", return_value=sb):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")

        self.assertEqual(resp.status_code, 404)

    # T11: StorageApiError(400) + 비-not-found 메시지 → 503 (범위 축소 검증)
    def test_T11_storage_api_error_other_400_returns_503(self):
        """T11 — StorageApiError(status=400, 비-not-found) → 503 (객체 미존재 외 SDK 오류)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user
        from storage3.exceptions import StorageApiError

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        sb = _make_sb([{"id": "uuid-1", "doc_id": _TEST_DOC_ID}],
                      StorageApiError("Invalid bucket name", "400", 400))

        with patch("routers.document_forms.get_verified_path", return_value=_TEST_STORAGE_PATH), \
             patch("routers.document_forms.get_provision_policy",
                   return_value={"route_group": "U_UNRESOLVED", "investment_decision": "HOLD",
                                 "official_status": None}), \
             patch("routers.document_forms.get_supabase", return_value=sb):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")

        self.assertEqual(resp.status_code, 503)

    # T12: B_OFFICIAL + HOLD → Gate 2b 차단 → 404
    def test_T12_b_official_hold_returns_404(self):
        """T12 — B_OFFICIAL + official_status=HOLD → 404 (Gate 2b — 미승인 공식 서식 차단)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: _MOCK_USER

        with patch("routers.document_forms.get_verified_path", return_value=_TEST_STORAGE_PATH), \
             patch("routers.document_forms.get_provision_policy",
                   return_value={"route_group": "B_OFFICIAL", "investment_decision": "STOP",
                                 "official_status": "HOLD"}):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/document-forms/{_TEST_DOC_ID}/source-file")

        self.assertEqual(resp.status_code, 404)

    # T09: 기존 목록 엔드포인트 회귀
    def test_T09_list_endpoint_regression(self):
        """T09 — GET /document-forms 목록 엔드포인트 정상 동작 (회귀)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_forms import router

        app = FastAPI()
        app.include_router(router)

        with patch("routers.document_forms.list_document_forms", return_value={
            "items": [], "total": 0, "page": 1, "per_page": 20,
        }):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/document-forms")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "success")


class TestSourceFileAvailability(unittest.TestCase):
    """T13~T15 — source_file_available 목록 enrichment."""

    # T13: list_available_doc_ids Storage 정상 응답 → doc_id 집합
    def test_T13_list_available_doc_ids_returns_set(self):
        """T13 — Storage 목록 조회 성공 → doc_id frozenset 반환."""
        from services.document_engine.source_file_allowlist import list_available_doc_ids

        sb = MagicMock()
        sb.storage.from_.return_value.list.return_value = [
            {"name": "DOC-FAC-020.hwp"},
            {"name": "DOC-FAC-022.hwp"},
            {"name": "readme.txt"},   # .hwp 아님 → 제외
        ]

        result = list_available_doc_ids(sb)

        self.assertIn("DOC-FAC-020", result)
        self.assertIn("DOC-FAC-022", result)
        self.assertNotIn("readme.txt", result)
        self.assertNotIn("readme", result)

    # T14: list_available_doc_ids Storage 오류 → 빈 집합
    def test_T14_list_available_doc_ids_storage_error_returns_empty(self):
        """T14 — Storage 조회 실패 → frozenset() (보수적: 버튼 미표시)."""
        from services.document_engine.source_file_allowlist import list_available_doc_ids

        sb = MagicMock()
        sb.storage.from_.return_value.list.side_effect = Exception("connection error")

        result = list_available_doc_ids(sb)

        self.assertEqual(result, frozenset())

    # T15: _enrich_with_source_file_availability — 파일 있는/없는 항목 구분
    def test_T15_enrich_source_file_availability(self):
        """T15 — Storage에 있는 doc_id → True, 없는 doc_id(DOC-FAC-019 등) → False."""
        from services.document_forms_service import _enrich_with_source_file_availability

        sb = MagicMock()
        # DOC-FAC-020은 있고, DOC-FAC-019는 없음 (file_url 있어도 Storage 파일 없는 케이스)
        sb.storage.from_.return_value.list.return_value = [
            {"name": "DOC-FAC-020.hwp"},
        ]

        items = [
            {"doc_id": "DOC-FAC-020", "file_url": "https://www.law.go.kr/..."},
            {"doc_id": "DOC-FAC-019", "file_url": "https://www.law.go.kr/...flSeq=123"},
        ]

        _enrich_with_source_file_availability(sb, items)

        self.assertTrue(items[0]["source_file_available"])
        self.assertFalse(items[1]["source_file_available"])


class TestSera009SplitPolicyChanges(unittest.TestCase):
    """WO-DOC260-U83-SERA009-SPLIT — SERA-009 단독 A_INTERNAL 재분류 검증."""

    def setUp(self):
        from services.document_engine.r2_route_policy import (
            get_provision_policy, policy_count,
            _SOURCE_DOWNLOAD_EXCEPTION_IDS, _SUBMISSION_CATEGORY,
        )
        self.get_policy = get_provision_policy
        self.policy_count = policy_count
        self.exception_ids = _SOURCE_DOWNLOAD_EXCEPTION_IDS
        self.submission_cat = _SUBMISSION_CATEGORY

    def test_SS01_sera009_is_a_internal(self):
        p = self.get_policy('DOC-SERA-009')
        self.assertEqual(p['route_group'], 'A_INTERNAL')

    def test_SS02_sera009_web_edit_allowed(self):
        p = self.get_policy('DOC-SERA-009')
        self.assertTrue(p['web_edit_allowed'])

    def test_SS03_sera009_submission_category_none(self):
        p = self.get_policy('DOC-SERA-009')
        self.assertIsNone(p['submission_category'])

    def test_SS04_sera009_download_exception_false(self):
        p = self.get_policy('DOC-SERA-009')
        self.assertFalse(p['source_download_exception'])

    def test_SS05_bld015_unchanged_u_unresolved(self):
        """BLD-015는 이번 변경 대상 아님 — U_UNRESOLVED 유지."""
        p = self.get_policy('DOC-BLD-015')
        self.assertEqual(p['route_group'], 'U_UNRESOLVED')

    def test_SS06_bld015_submission_category_g1_preserved(self):
        """BLD-015의 G1_DUAL_PATH는 그대로 유지."""
        self.assertEqual(self.submission_cat.get('DOC-BLD-015'), 'G1_DUAL_PATH')

    def test_SS07_policy_count(self):
        """SERA-009만 전환: A_INTERNAL=110, U_UNRESOLVED=82."""
        counts = self.policy_count()
        self.assertEqual(counts['A_INTERNAL'], 110)
        self.assertEqual(counts['U_UNRESOLVED'], 82)

    def test_SS08_g1_dual_path_eleven(self):
        """SERA-009 제거 후 G1_DUAL_PATH = 11종."""
        g1 = [k for k, v in self.submission_cat.items() if v == 'G1_DUAL_PATH']
        self.assertEqual(len(g1), 11)

    def test_SS09_sera009_not_in_g1(self):
        self.assertNotEqual(self.submission_cat.get('DOC-SERA-009'), 'G1_DUAL_PATH')

    def test_SS10_exceptions_unchanged_six(self):
        """다운로드 예외는 기존 6종 그대로."""
        self.assertEqual(len(self.exception_ids), 6)
        self.assertNotIn('DOC-SERA-009', self.exception_ids)
        self.assertNotIn('DOC-BLD-015', self.exception_ids)


if __name__ == "__main__":
    unittest.main()
