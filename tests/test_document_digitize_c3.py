"""tests/test_document_digitize_c3.py — WO-DOC-HWR-001-C3 document_input_mode 연결 테스트.

C3-01~08: 라우터 수준 — Form 필드 검증·전달·에러 매핑
C3-09~11: 클라이언트 수준 — httpx 멀티파트 포함 여부·503 전달

Production DB write = 0 (dependency_overrides + mock).
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.auth import get_current_user
from routers.document_digitize import router
from services.doc_digitize_client import DocDigitizeError, DocDigitizeResult, digitize


# ── 공통 헬퍼 ──────────────────────────────────────────────────────────────────

def _admin_user(company_id: str = "co-001") -> dict:
    return {"role_code": "001", "company_id": company_id}


def _mock_supabase_company_exists():
    mock_sb = MagicMock()
    (mock_sb.table.return_value
     .select.return_value
     .eq.return_value
     .limit.return_value
     .execute.return_value.data) = [{"id": "co-001"}]
    return mock_sb


def _make_app(user: dict) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _post_file(client: TestClient, mode: str | None = None) -> object:
    """mode=None → document_input_mode 필드 미전송 (Form 기본값 None 경로)."""
    kwargs: dict = {
        "files": {"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
        "headers": {"Authorization": "Bearer test-token"},
    }
    if mode is not None:
        kwargs["data"] = {"document_input_mode": mode}
    return client.post("/digitize", **kwargs)


_DEFAULT_RESULT = DocDigitizeResult(
    doc_log_id="log-001",
    duplicate=False,
    primitive_id="prim-001",
    v1_status="pass",
    v2_status="pass",
)


# ── C3-01: mode 없음 → 200 + digitize() document_input_mode=None으로 호출 ────

def test_C3_01_no_mode_success_and_propagates_none():
    mock_digitize = AsyncMock(return_value=_DEFAULT_RESULT)
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=mock_digitize),
    ):
        resp = _post_file(client)

    assert resp.status_code == 200
    assert mock_digitize.call_args.kwargs["document_input_mode"] is None


# ── C3-02: mode="digital" → 200 + digitize() mode="digital"로 호출 ───────────

def test_C3_02_mode_digital_success_and_propagates():
    mock_digitize = AsyncMock(return_value=_DEFAULT_RESULT)
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=mock_digitize),
    ):
        resp = _post_file(client, mode="digital")

    assert resp.status_code == 200
    assert mock_digitize.call_args.kwargs["document_input_mode"] == "digital"


# ── C3-03: mode="scan" → 200 ─────────────────────────────────────────────────

def test_C3_03_mode_scan_success():
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=AsyncMock(return_value=_DEFAULT_RESULT)),
    ):
        resp = _post_file(client, mode="scan")

    assert resp.status_code == 200


# ── C3-04: mode="unsure" → 200 ───────────────────────────────────────────────

def test_C3_04_mode_unsure_success():
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=AsyncMock(return_value=_DEFAULT_RESULT)),
    ):
        resp = _post_file(client, mode="unsure")

    assert resp.status_code == 200


# ── C3-05: mode 허용 외 값 → 422 ─────────────────────────────────────────────

def test_C3_05_invalid_mode_422():
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()):
        resp = _post_file(client, mode="bad_mode")

    assert resp.status_code == 422


# ── C3-06: mode 빈 문자열 → FastAPI Form(None) None 변환 → 200 허용 ──────────
# FastAPI Optional[str] + Form(None): 빈 문자열 필드는 None으로 변환 → mode 미제공과 동일

def test_C3_06_empty_string_mode_treated_as_none():
    mock_digitize = AsyncMock(return_value=_DEFAULT_RESULT)
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=mock_digitize),
    ):
        resp = _post_file(client, mode="")

    assert resp.status_code == 200
    assert mock_digitize.call_args.kwargs["document_input_mode"] is None


# ── C3-07: DocDigitizeError(503) → TAI 503 (기존에는 502로 떨어졌던 경로) ────

def test_C3_07_doc_503_becomes_tai_503():
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    err = DocDigitizeError(stage="internal", reason="service unavailable", http_status=503)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=AsyncMock(side_effect=err)),
    ):
        resp = _post_file(client)

    assert resp.status_code == 503


# ── C3-08: DocDigitizeError(422) → TAI 422 (503 추가로 인한 회귀 없음) ────────

def test_C3_08_doc_422_still_becomes_tai_422():
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    err = DocDigitizeError(stage="v1", reason="validation failed", http_status=422)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=AsyncMock(side_effect=err)),
    ):
        resp = _post_file(client)

    assert resp.status_code == 422


# ── C3-09: httpx: mode=None → data 키 미포함 ─────────────────────────────────

def test_C3_09_client_no_mode_no_data_key():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "ok": True, "doc_log_id": "log-001", "duplicate": False, "primitive_id": "prim-001",
    }

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_resp

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_http)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("services.doc_digitize_client.httpx.AsyncClient", return_value=mock_ctx):
        with patch.dict(os.environ, {"DOC_ENGINE_URL": "http://test-doc", "TAI_SERVICE_KEY": "k"}):
            asyncio.run(digitize(
                file_bytes=b"x", original_filename="t.pdf",
                company_id="co-001", document_input_mode=None,
            ))

    assert "data" not in mock_http.post.call_args.kwargs


# ── C3-10: httpx: mode="scan" → data={"document_input_mode": "scan"} ─────────

def test_C3_10_client_scan_mode_includes_data_field():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "ok": True, "doc_log_id": "log-001", "duplicate": False, "primitive_id": "prim-001",
    }

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_resp

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_http)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("services.doc_digitize_client.httpx.AsyncClient", return_value=mock_ctx):
        with patch.dict(os.environ, {"DOC_ENGINE_URL": "http://test-doc", "TAI_SERVICE_KEY": "k"}):
            asyncio.run(digitize(
                file_bytes=b"x", original_filename="t.pdf",
                company_id="co-001", document_input_mode="scan",
            ))

    assert mock_http.post.call_args.kwargs.get("data") == {"document_input_mode": "scan"}


# ── C3-11: httpx: DOC 503 응답 → DocDigitizeError(http_status=503) ───────────

def test_C3_11_client_doc_503_raises_digitize_error_503():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.json.return_value = {"detail": "service unavailable"}

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_resp

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_http)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("services.doc_digitize_client.httpx.AsyncClient", return_value=mock_ctx):
        with patch.dict(os.environ, {"DOC_ENGINE_URL": "http://test-doc", "TAI_SERVICE_KEY": "k"}):
            with pytest.raises(DocDigitizeError) as exc_info:
                asyncio.run(digitize(
                    file_bytes=b"x", original_filename="t.pdf",
                    company_id="co-001",
                ))

    assert exc_info.value.http_status == 503
