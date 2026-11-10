"""WO-DOC-G7-B1 Work B — document_digitize 라우터 응답 테스트.

DD-01: 신규 처리 성공 → extraction_storage_ref 응답 포함
DD-02: 중복 처리 → extraction_storage_ref=None 응답 포함
DD-03: DOC extraction_storage_ref=None → 응답에 null
DD-04: extraction_storage_warning → 응답에 안내 메시지 포함
DD-05: 기존 storage_warning 응답 유지
DD-06: 기존 권한 거부(관리자 아님) 동작 유지
DD-07: 기존 company_id 없음 거부 동작 유지

Production DB write = 0 (dependency_overrides + mock).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.auth import get_current_user
from routers.document_digitize import router
from services.doc_digitize_client import DocDigitizeResult


# ── 공통 user fixtures ─────────────────────────────────────────────────────────

def _admin_user(company_id: str = "co-001") -> dict:
    return {"role_code": "001", "company_id": company_id}


def _staff_user() -> dict:
    return {"role_code": "002", "company_id": "co-001"}


# ── 공통 mock helpers ─────────────────────────────────────────────────────────

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


def _post_file(client: TestClient) -> object:
    # router prefix="/digitize", @router.post("") → 전체 경로 /digitize
    return client.post(
        "/digitize",
        files={"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers={"Authorization": "Bearer test-token"},
    )


# ── DD-01: 신규 처리 → extraction_storage_ref 포함 ───────────────────────────

def test_DD01_new_upload_extraction_ref_in_response():
    mock_result = DocDigitizeResult(
        doc_log_id="log-001",
        duplicate=False,
        primitive_id="prim-001",
        v1_status="pass",
        v2_status="pass",
        file_hash="abc",
        file_size_bytes=100,
        storage_ref="doc-originals/co-001/2026/11/log-001_test.pdf",
        extraction_storage_ref="doc-extractions/co-001/2026/11/log-001_test.md",
    )
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=AsyncMock(return_value=mock_result)),
    ):
        resp = _post_file(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["doc_log_id"] == "log-001"
    assert body["extraction_storage_ref"] == "doc-extractions/co-001/2026/11/log-001_test.md"
    assert "storage_warning" not in body
    assert "extraction_storage_warning" not in body


# ── DD-02: 중복 처리 → extraction_storage_ref=None ───────────────────────────

def test_DD02_duplicate_extraction_ref_null():
    mock_result = DocDigitizeResult(
        doc_log_id="log-dup-001",
        duplicate=True,
    )
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=AsyncMock(return_value=mock_result)),
    ):
        resp = _post_file(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["duplicate"] is True
    assert body["extraction_storage_ref"] is None


# ── DD-03: DOC extraction_storage_ref=None → 응답에 null ─────────────────────

def test_DD03_extraction_ref_none_in_response():
    mock_result = DocDigitizeResult(
        doc_log_id="log-002",
        duplicate=False,
        primitive_id="prim-002",
        v1_status="pass",
        v2_status="partial",
        extraction_storage_ref=None,
    )
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=AsyncMock(return_value=mock_result)),
    ):
        resp = _post_file(client)

    assert resp.status_code == 200
    body = resp.json()
    assert "extraction_storage_ref" in body
    assert body["extraction_storage_ref"] is None


# ── DD-04: extraction_storage_warning → 안내 메시지 포함 ─────────────────────

def test_DD04_extraction_storage_warning_in_response():
    mock_result = DocDigitizeResult(
        doc_log_id="log-003",
        duplicate=False,
        primitive_id="prim-003",
        v1_status="pass",
        v2_status="pass",
        extraction_storage_ref=None,
        extraction_storage_warning="extraction_upload_failed: bucket error",
    )
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=AsyncMock(return_value=mock_result)),
    ):
        resp = _post_file(client)

    assert resp.status_code == 200
    body = resp.json()
    assert "extraction_storage_warning" in body
    # DOC 내부 오류 원문 미노출 — 일반 안내로 치환
    assert "추출 결과 저장" in body["extraction_storage_warning"]
    assert "bucket error" not in body["extraction_storage_warning"]


# ── DD-05: 기존 storage_warning 유지 ─────────────────────────────────────────

def test_DD05_existing_storage_warning_preserved():
    mock_result = DocDigitizeResult(
        doc_log_id="log-004",
        duplicate=False,
        primitive_id="prim-004",
        v1_status="pass",
        v2_status="pass",
        storage_warning="원본 파일 저장 실패 — 재업로드 필요",
        extraction_storage_ref="doc-extractions/co-001/2026/11/log-004_test.md",
    )
    app = _make_app(_admin_user())
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_supabase_company_exists()),
        patch("routers.document_digitize.digitize", new=AsyncMock(return_value=mock_result)),
    ):
        resp = _post_file(client)

    assert resp.status_code == 200
    body = resp.json()
    assert "storage_warning" in body
    assert "관리자 확인" in body["storage_warning"]
    # DOC 내부 오류 원문 미노출
    assert "재업로드 필요" not in body["storage_warning"]


# ── DD-06: 관리자 아님 → 403 ─────────────────────────────────────────────────

def test_DD06_non_admin_blocked():
    app = _make_app(_staff_user())
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_file(client)
    assert resp.status_code == 403


# ── DD-07: company_id 없음 → 403 ─────────────────────────────────────────────

def test_DD07_missing_company_id_blocked():
    app = _make_app({"role_code": "001", "company_id": ""})
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_file(client)
    assert resp.status_code == 403
