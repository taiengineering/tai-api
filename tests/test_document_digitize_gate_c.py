"""tests/test_document_digitize_gate_c.py — WO-TAI-DOC-SITE-CONTEXT-GUARD-001 Gate C.

GC-01~06: 라우터 수준 — factory_id 전달·검증·차단
GC-07~08: doc_digitize_client — X-Factory-Id 헤더 포함 여부
GC-09~10: doc_lookup_client  — X-Factory-Id 헤더 포함 여부

Production DB write = 0 (dependency_overrides + mock).
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers.auth import get_current_user
from routers.document_digitize import router
from services.doc_digitize_client import DocDigitizeResult, digitize
from services.doc_lookup_client import DocLookupContentResult, lookup_extraction_content
from services.doc_site_context import SiteContextResult


# ── 공통 헬퍼 ──────────────────────────────────────────────────────────────────

def _admin_user(company_id: str = "co-001", factory_id: str = "") -> dict:
    return {"role_code": "001", "company_id": company_id, "factory_id": factory_id}


def _mock_supabase_company_exists(company_id: str = "co-001"):
    mock_sb = MagicMock()
    (mock_sb.table.return_value
     .select.return_value
     .eq.return_value
     .limit.return_value
     .execute.return_value.data) = [{"id": company_id}]
    return mock_sb


def _make_app(user: dict) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _post_file(client: TestClient, **extra_data) -> object:
    return client.post(
        "/digitize",
        files={"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
        data=extra_data,
        headers={"Authorization": "Bearer test-token"},
    )


_DEFAULT_RESULT = DocDigitizeResult(
    doc_log_id="log-001",
    duplicate=False,
    primitive_id="prim-001",
    v1_status="pass",
    v2_status="pass",
)

_DEFAULT_LOOKUP_RESULT = DocLookupContentResult(
    doc_log_id="log-001",
    status="FOUND",
    content="# 추출된 문서\n내용",
)

_DEFAULT_SITE_CTX = SiteContextResult(
    company_id="co-001",
    factory_id="fac-001",
    scope_type="ALL",
)


# ── GC-01: factory_id 없음 → factory_id=None으로 digitize() 호출 ───────────────

def test_GC_01_no_factory_id_calls_digitize_with_none():
    mock_digitize = AsyncMock(return_value=_DEFAULT_RESULT)
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=mock_digitize),
    ):
        resp = _post_file(client)

    assert resp.status_code == 200
    assert mock_digitize.call_args.kwargs["factory_id"] is None


# ── GC-02: factory_id 제공 → resolve_document_site_context 거쳐 검증된 ID 전달 ──

def test_GC_02_factory_id_resolved_and_passed_to_digitize():
    mock_digitize = AsyncMock(return_value=_DEFAULT_RESULT)
    mock_resolve = MagicMock(return_value=_DEFAULT_SITE_CTX)
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.resolve_document_site_context", new=mock_resolve),
        patch("routers.document_digitize.digitize", new=mock_digitize),
    ):
        resp = _post_file(client, factory_id="fac-001")

    assert resp.status_code == 200
    assert mock_resolve.call_args.kwargs["factory_id"] == "fac-001"
    assert mock_digitize.call_args.kwargs["factory_id"] == "fac-001"


# ── GC-03: 권한 불일치 → resolve_document_site_context 403 → 업로드 차단 ──────

def test_GC_03_factory_scope_mismatch_blocks_upload():
    mock_resolve = MagicMock(side_effect=HTTPException(403, "배정된 사업장이 아닙니다"))
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.resolve_document_site_context", new=mock_resolve),
    ):
        resp = _post_file(client, factory_id="fac-other")

    assert resp.status_code == 403


# ── GC-04: factory_id 빈 문자열 → None으로 처리 ──────────────────────────────

def test_GC_04_empty_factory_id_treated_as_none():
    mock_digitize = AsyncMock(return_value=_DEFAULT_RESULT)
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=mock_digitize),
    ):
        resp = _post_file(client, factory_id="")

    assert resp.status_code == 200
    assert mock_digitize.call_args.kwargs["factory_id"] is None


# ── GC-05: GET result, factory_id 없음 → factory_id=None으로 조회 ─────────────

def test_GC_05_result_no_factory_id_calls_lookup_with_none():
    mock_lookup = AsyncMock(return_value=_DEFAULT_LOOKUP_RESULT)
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.lookup_extraction_content", new=mock_lookup),
    ):
        resp = client.get(
            "/digitize/log-001/result",
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 200
    assert mock_lookup.call_args.kwargs["factory_id"] is None


# ── GC-06: GET result, factory_id 제공 → resolve_document_site_context 거쳐 전달 ─

def test_GC_06_result_factory_id_resolved_and_passed_to_lookup():
    mock_lookup = AsyncMock(return_value=_DEFAULT_LOOKUP_RESULT)
    mock_resolve = MagicMock(return_value=_DEFAULT_SITE_CTX)
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.resolve_document_site_context", new=mock_resolve),
        patch("routers.document_digitize.lookup_extraction_content", new=mock_lookup),
    ):
        resp = client.get(
            "/digitize/log-001/result",
            params={"factory_id": "fac-001"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 200
    assert mock_resolve.call_args.kwargs["factory_id"] == "fac-001"
    assert mock_lookup.call_args.kwargs["factory_id"] == "fac-001"


# ── GC-07: digitize client — factory_id=None → X-Factory-Id 헤더 없음 ─────────

def test_GC_07_digitize_client_no_factory_id_no_header():
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
                company_id="co-001", factory_id=None,
            ))

    sent_headers = mock_http.post.call_args.kwargs["headers"]
    assert "X-Factory-Id" not in sent_headers


# ── GC-08: digitize client — factory_id="fac-001" → X-Factory-Id: "fac-001" ──

def test_GC_08_digitize_client_factory_id_includes_header():
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
                company_id="co-001", factory_id="fac-001",
            ))

    sent_headers = mock_http.post.call_args.kwargs["headers"]
    assert sent_headers.get("X-Factory-Id") == "fac-001"


# ── GC-09: lookup client — factory_id=None → X-Factory-Id 헤더 없음 ───────────

def test_GC_09_lookup_client_no_factory_id_no_header():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "FOUND",
        "content": "# test",
    }
    mock_http = AsyncMock()
    mock_http.get.return_value = mock_resp
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_http)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("services.doc_lookup_client.httpx.AsyncClient", return_value=mock_ctx):
        with patch.dict(os.environ, {"DOC_LOOKUP_URL": "http://test-doc", "TAI_SERVICE_KEY": "k"}):
            asyncio.run(lookup_extraction_content(
                doc_log_id="log-001", company_id="co-001", factory_id=None,
            ))

    sent_headers = mock_http.get.call_args.kwargs["headers"]
    assert "X-Factory-Id" not in sent_headers


# ── GC-10: lookup client — factory_id="fac-001" → X-Factory-Id: "fac-001" ────

def test_GC_10_lookup_client_factory_id_includes_header():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "FOUND",
        "content": "# test",
    }
    mock_http = AsyncMock()
    mock_http.get.return_value = mock_resp
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_http)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("services.doc_lookup_client.httpx.AsyncClient", return_value=mock_ctx):
        with patch.dict(os.environ, {"DOC_LOOKUP_URL": "http://test-doc", "TAI_SERVICE_KEY": "k"}):
            asyncio.run(lookup_extraction_content(
                doc_log_id="log-001", company_id="co-001", factory_id="fac-001",
            ))

    sent_headers = mock_http.get.call_args.kwargs["headers"]
    assert sent_headers.get("X-Factory-Id") == "fac-001"
