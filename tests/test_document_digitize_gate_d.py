"""tests/test_document_digitize_gate_d.py — Gate D 사업장 사용자 개방.

GD-01: FACTORY scope 사용자 + factory_id → 허용
GD-02: FACTORY scope 사용자 + factory_id 없음 → 403
GD-03: FACTORY scope 사용자 + factory_id 빈 문자열 → 403
GD-04: FACTORY scope 사용자 + 타 사업장 factory_id → 403 (resolve_document_site_context 차단)
GD-05: COMPANY scope 사용자 + factory_id → 허용
GD-06: 비관리자 form company_id → 무시, 토큰 company_id 사용
GD-07: role_code=001 + factory_id 없음 → 허용 (admin 기존 경로 불변)
GD-08: ASSIGNED scope → 403
GD-09: GET result, FACTORY scope + factory_id → 허용
GD-10: GET result, 비관리자 + factory_id 없음 → 403

Production DB write = 0 (dependency_overrides + mock).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers.auth import get_current_user
from routers.document_digitize import router
from services.doc_digitize_client import DocDigitizeResult
from services.doc_lookup_client import DocLookupContentResult
from services.doc_site_context import SiteContextResult


# ── 공통 헬퍼 ──────────────────────────────────────────────────────────────────

def _user(role_code: str, company_id: str = "co-001", factory_id: str = "") -> dict:
    return {"role_code": role_code, "company_id": company_id, "factory_id": factory_id}


def _mock_sb(company_id: str = "co-001"):
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


def _post(client: TestClient, **data) -> object:
    return client.post(
        "/digitize",
        files={"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
        data=data,
        headers={"Authorization": "Bearer test-token"},
    )


_OK_RESULT = DocDigitizeResult(
    doc_log_id="log-001", duplicate=False, primitive_id="prim-001",
    v1_status="pass", v2_status="pass",
)
_OK_LOOKUP = DocLookupContentResult(doc_log_id="log-001", status="FOUND", content="# doc")

_CTX_FAC = SiteContextResult(company_id="co-001", factory_id="fac-001", scope_type="FACTORY")
_CTX_COM = SiteContextResult(company_id="co-001", factory_id="fac-001", scope_type="COMPANY")


# ── GD-01: FACTORY scope + factory_id → 허용 ──────────────────────────────────

def test_GD_01_factory_user_with_factory_id_allowed():
    mock_dig = AsyncMock(return_value=_OK_RESULT)
    mock_res = MagicMock(return_value=_CTX_FAC)
    user = _user("FACTORY_ROLE", factory_id="fac-001")
    app = _make_app(user)
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_sb()),
        patch("routers.document_digitize.resolve_document_site_context", new=mock_res),
        patch("routers.document_digitize.digitize", new=mock_dig),
    ):
        resp = _post(client, factory_id="fac-001")

    assert resp.status_code == 200
    assert mock_dig.call_args.kwargs["factory_id"] == "fac-001"


# ── GD-02: 비관리자 + factory_id 없음 → 403 ──────────────────────────────────

def test_GD_02_non_admin_no_factory_id_blocked():
    user = _user("FACTORY_ROLE")
    app = _make_app(user)
    client = TestClient(app, raise_server_exceptions=False)
    with patch("routers.document_digitize.get_supabase", return_value=_mock_sb()):
        resp = _post(client)

    assert resp.status_code == 403


# ── GD-03: 비관리자 + factory_id 빈 문자열 → 403 ─────────────────────────────

def test_GD_03_non_admin_empty_factory_id_blocked():
    user = _user("FACTORY_ROLE")
    app = _make_app(user)
    client = TestClient(app, raise_server_exceptions=False)
    with patch("routers.document_digitize.get_supabase", return_value=_mock_sb()):
        resp = _post(client, factory_id="")

    assert resp.status_code == 403


# ── GD-04: 타 사업장 factory_id → resolve 차단 → 403 ─────────────────────────

def test_GD_04_wrong_factory_id_blocked_by_resolve():
    mock_res = MagicMock(side_effect=HTTPException(403, "배정된 사업장이 아닙니다"))
    user = _user("FACTORY_ROLE", factory_id="fac-001")
    app = _make_app(user)
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_sb()),
        patch("routers.document_digitize.resolve_document_site_context", new=mock_res),
    ):
        resp = _post(client, factory_id="fac-other")

    assert resp.status_code == 403


# ── GD-05: COMPANY scope + factory_id → 허용 ─────────────────────────────────

def test_GD_05_company_scope_with_factory_id_allowed():
    mock_dig = AsyncMock(return_value=_OK_RESULT)
    mock_res = MagicMock(return_value=_CTX_COM)
    user = _user("COMPANY_ROLE")
    app = _make_app(user)
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_sb()),
        patch("routers.document_digitize.resolve_document_site_context", new=mock_res),
        patch("routers.document_digitize.digitize", new=mock_dig),
    ):
        resp = _post(client, factory_id="fac-001")

    assert resp.status_code == 200


# ── GD-06: 비관리자 form company_id 무시 → 토큰 company_id 사용 ───────────────

def test_GD_06_non_admin_form_company_id_ignored():
    mock_dig = AsyncMock(return_value=_OK_RESULT)
    mock_res = MagicMock(return_value=_CTX_FAC)
    user = _user("FACTORY_ROLE", company_id="co-token", factory_id="fac-001")
    app = _make_app(user)
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_sb("co-token")),
        patch("routers.document_digitize.resolve_document_site_context", new=mock_res),
        patch("routers.document_digitize.digitize", new=mock_dig),
    ):
        resp = _post(client, factory_id="fac-001", company_id="co-other")

    assert resp.status_code == 200
    # resolve에 전달된 company_id는 토큰 값(co-token)이어야 함
    assert mock_res.call_args.kwargs["company_id"] == "co-token"


# ── GD-07: role_code=001 + factory_id 없음 → 허용 (admin 기존 경로) ────────────

def test_GD_07_admin_no_factory_id_still_allowed():
    mock_dig = AsyncMock(return_value=_OK_RESULT)
    user = _user("001")
    app = _make_app(user)
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_sb()),
        patch("routers.document_digitize.digitize", new=mock_dig),
    ):
        resp = _post(client)

    assert resp.status_code == 200
    assert mock_dig.call_args.kwargs["factory_id"] is None


# ── GD-08: ASSIGNED scope → 403 ──────────────────────────────────────────────

def test_GD_08_assigned_scope_blocked():
    mock_res = MagicMock(side_effect=HTTPException(403, "문서 접근 권한 계약이 확정되지 않았습니다"))
    user = _user("ASSIGNED_ROLE", factory_id="fac-001")
    app = _make_app(user)
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_sb()),
        patch("routers.document_digitize.resolve_document_site_context", new=mock_res),
    ):
        resp = _post(client, factory_id="fac-001")

    assert resp.status_code == 403


# ── GD-09: GET result, FACTORY scope + factory_id → 허용 ─────────────────────

def test_GD_09_get_result_factory_user_with_factory_id_allowed():
    mock_lookup = AsyncMock(return_value=_OK_LOOKUP)
    mock_res = MagicMock(return_value=_CTX_FAC)
    user = _user("FACTORY_ROLE", factory_id="fac-001")
    app = _make_app(user)
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch("routers.document_digitize.get_supabase", return_value=_mock_sb()),
        patch("routers.document_digitize.resolve_document_site_context", new=mock_res),
        patch("routers.document_digitize.lookup_extraction_content", new=mock_lookup),
    ):
        resp = client.get(
            "/digitize/log-001/result",
            params={"factory_id": "fac-001"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 200
    assert mock_lookup.call_args.kwargs["factory_id"] == "fac-001"


# ── GD-10: GET result, 비관리자 + factory_id 없음 → 403 ──────────────────────

def test_GD_10_get_result_non_admin_no_factory_id_blocked():
    user = _user("FACTORY_ROLE")
    app = _make_app(user)
    client = TestClient(app, raise_server_exceptions=False)
    with patch("routers.document_digitize.get_supabase", return_value=_mock_sb()):
        resp = client.get(
            "/digitize/log-001/result",
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 403
