"""WO-DOC260-OBJ10-R2-COMMON-ROUTE-BINDING-001 — R2 route policy tests

STAGE: SOURCE_DRAFT
R2_PLAN_SHA256:   f5145184c0f8265524c6704cb8044c70818c53da7af141c3a5885f2733ff4ecd
R2_MATRIX_SHA256: 0a95c6a238796ab90c4be75afa8516906b6cb71f6e34eb75979057ea524971b0
CLASSIFICATION_ROWS: 260

Tests:
  RP-T01: A_INTERNAL doc_id → web_edit_allowed=True
  RP-T02: B_OFFICIAL doc_id → web_edit_allowed=False
  RP-T03: F_SCOPE_OUT doc_id → web_edit_allowed=False
  RP-T04: E_EXTERNAL doc_id → web_edit_allowed=False
  RP-T05: U_UNRESOLVED doc_id → web_edit_allowed=False
  RP-T06: Unknown doc_id → None (not in matrix)
  RP-T07: Total entries = 260, all unique
  RP-T08: A_INTERNAL count = 63
  RP-T09: Non-A_INTERNAL count = 197
  RP-T10: catalog endpoint returns provision_policy field
  RP-T11: catalog can_create=False for non-A_INTERNAL with approved schema
  RP-T12: catalog can_create=True for A_INTERNAL with approved schema
  RP-T13: POST /documents raises 422 for non-A_INTERNAL
  RP-T14: POST /documents allows creation for A_INTERNAL
  RP-T15: compute_channel_state WEB_EDIT=BLOCKED for non-A_INTERNAL route_group
  RP-T16: compute_channel_state WEB_EDIT unchanged for A_INTERNAL (schema-gate still applies)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.document_engine.r2_route_policy import (
    get_all_policies,
    get_provision_policy,
    policy_count,
)
from services.catalog_aggregator import compute_channel_state


# ─── RP-T01~T06: 정책 조회 단위 테스트 ──────────────────────────────────────

def test_RP_T01_a_internal_web_edit_allowed():
    p = get_provision_policy("DOC-OSH-001")
    assert p is not None
    assert p["route_group"] == "A_INTERNAL"
    assert p["investment_decision"] == "KEEP"
    assert p["web_edit_allowed"] is True


def test_RP_T02_b_official_blocked():
    p = get_provision_policy("DOC-FAC-020")
    assert p is not None
    assert p["route_group"] == "B_OFFICIAL"
    assert p["web_edit_allowed"] is False


def test_RP_T03_f_scope_out_blocked():
    p = get_provision_policy("DOC-OSH-004")
    assert p is not None
    assert p["route_group"] == "F_SCOPE_OUT"
    assert p["web_edit_allowed"] is False


def test_RP_T04_e_external_blocked():
    p = get_provision_policy("DOC-BLD-033")
    assert p is not None
    assert p["route_group"] == "E_EXTERNAL"
    assert p["web_edit_allowed"] is False


def test_RP_T05_u_unresolved_blocked():
    p = get_provision_policy("DOC-BLD-001")
    assert p is not None
    assert p["route_group"] == "U_UNRESOLVED"
    assert p["web_edit_allowed"] is False


def test_RP_T06_unknown_doc_id_returns_none():
    assert get_provision_policy("DOC-UNKNOWN-999") is None
    assert get_provision_policy("") is None


# ─── RP-T07~T09: 전체 집계 검증 ───────────────────────────────────────────

def test_RP_T07_total_260_unique():
    all_p = get_all_policies()
    assert len(all_p) == 260
    assert len(set(all_p.keys())) == 260


def test_RP_T08_a_internal_count_63():
    counts = policy_count()
    assert counts.get("A_INTERNAL") == 63


def test_RP_T09_non_a_internal_count_197():
    counts = policy_count()
    non_a = sum(v for k, v in counts.items() if k != "A_INTERNAL")
    assert non_a == 197


# ─── RP-T10~T12: catalog/{doc_id} 엔드포인트 ────────────────────────────────

def _make_catalog_mock(doc_id: str, schema_status: str = "APPROVED_FOR_RUNTIME_USE"):
    """카탈로그 엔드포인트용 Supabase mock."""
    catalog_uuid = "cat-uuid-0001"
    schema_uuid = "schema-uuid-0001"

    mock_sb = MagicMock()
    # document_forms lookup by doc_id
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": catalog_uuid, "doc_id": doc_id, "doc_name": f"테스트 {doc_id}", "sector": "TEST", "category": "TEST"}
    ]
    return mock_sb, catalog_uuid, schema_uuid, schema_status


def test_RP_T10_catalog_returns_provision_policy():
    """RP-T10: 카탈로그 응답에 provision_policy 포함."""
    from routers.document_engine_api import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=True)

    resolved_mock = {
        "availability": "READY_FOR_EDIT",
        "active_schema_id": "s1",
        "active_schema_status": "APPROVED_FOR_RUNTIME_USE",
        "candidate_schema_id": None,
        "candidate_schema_status": None,
        "schema": {"id": "s1"},
        "fields": [],
        "checklists": [],
        "evidence_fields": [],
        "resolved_evidence_connections": [],
    }

    with patch("routers.document_engine_api.get_supabase") as mock_sb, \
         patch("routers.document_engine_api.resolve_catalog_runtime_schema", return_value=resolved_mock):

        sb = MagicMock()
        mock_sb.return_value = sb
        cat_res = MagicMock()
        cat_res.data = [{"id": "cat-1", "doc_id": "DOC-OSH-001", "doc_name": "테스트", "sector": "X", "category": "Y"}]
        sb.table.return_value.select.return_value.eq.return_value.execute.return_value = cat_res

        resp = client.get("/document-engine/catalog/DOC-OSH-001")

    assert resp.status_code == 200
    body = resp.json()
    runtime = body["data"]["runtime"]
    assert "provision_policy" in runtime
    assert runtime["provision_policy"]["route_group"] == "A_INTERNAL"
    assert runtime["provision_policy"]["web_edit_allowed"] is True


def test_RP_T11_catalog_can_create_false_for_non_a_internal():
    """RP-T11: non-A_INTERNAL doc는 schema approved여도 can_create=False."""
    from routers.document_engine_api import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=True)

    resolved_mock = {
        "availability": "READY_FOR_EDIT",
        "active_schema_id": "s2",
        "active_schema_status": "APPROVED_FOR_RUNTIME_USE",
        "candidate_schema_id": None,
        "candidate_schema_status": None,
        "schema": {"id": "s2"},
        "fields": [],
        "checklists": [],
        "evidence_fields": [],
        "resolved_evidence_connections": [],
    }

    with patch("routers.document_engine_api.get_supabase") as mock_sb, \
         patch("routers.document_engine_api.resolve_catalog_runtime_schema", return_value=resolved_mock):

        sb = MagicMock()
        mock_sb.return_value = sb
        cat_res = MagicMock()
        # DOC-FAC-020 = B_OFFICIAL
        cat_res.data = [{"id": "cat-2", "doc_id": "DOC-FAC-020", "doc_name": "테스트B", "sector": "X", "category": "Y"}]
        sb.table.return_value.select.return_value.eq.return_value.execute.return_value = cat_res

        resp = client.get("/document-engine/catalog/DOC-FAC-020")

    assert resp.status_code == 200
    runtime = resp.json()["data"]["runtime"]
    assert runtime["can_create"] is False
    assert runtime["provision_policy"]["route_group"] == "B_OFFICIAL"


def test_RP_T12_catalog_can_create_true_for_a_internal_approved():
    """RP-T12: A_INTERNAL + schema APPROVED → can_create=True."""
    from routers.document_engine_api import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=True)

    resolved_mock = {
        "availability": "READY_FOR_EDIT",
        "active_schema_id": "s3",
        "active_schema_status": "APPROVED_FOR_RUNTIME_USE",
        "candidate_schema_id": None,
        "candidate_schema_status": None,
        "schema": {"id": "s3"},
        "fields": [],
        "checklists": [],
        "evidence_fields": [],
        "resolved_evidence_connections": [],
    }

    with patch("routers.document_engine_api.get_supabase") as mock_sb, \
         patch("routers.document_engine_api.resolve_catalog_runtime_schema", return_value=resolved_mock):

        sb = MagicMock()
        mock_sb.return_value = sb
        cat_res = MagicMock()
        cat_res.data = [{"id": "cat-3", "doc_id": "DOC-OSH-001", "doc_name": "테스트A", "sector": "X", "category": "Y"}]
        sb.table.return_value.select.return_value.eq.return_value.execute.return_value = cat_res

        resp = client.get("/document-engine/catalog/DOC-OSH-001")

    assert resp.status_code == 200
    runtime = resp.json()["data"]["runtime"]
    assert runtime["can_create"] is True
    assert runtime["provision_policy"]["web_edit_allowed"] is True


# ─── RP-T13~T14: POST /documents 생성 경로 가드 ─────────────────────────────

def _make_create_mock_sb(doc_id: str, schema_id: str = "schema-uuid-001"):
    """POST /documents 테스트용 Supabase mock."""
    sb = MagicMock()

    def _table_side_effect(table_name):
        mock = MagicMock()
        if table_name == "runtime_form_schema":
            mock.select.return_value.eq.return_value.execute.return_value.data = [
                {"catalog_document_id": "cat-uuid-001"}
            ]
        elif table_name == "document_forms":
            mock.select.return_value.eq.return_value.execute.return_value.data = [
                {"doc_id": doc_id}
            ]
        else:
            mock.select.return_value.eq.return_value.execute.return_value.data = []
        return mock

    sb.table.side_effect = _table_side_effect
    return sb


def test_RP_T13_create_document_blocked_for_non_a_internal():
    """RP-T13: POST /documents 422 — B_OFFICIAL route_group."""
    from routers.document_engine_api import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "user-001", "company_id": "co-001", "factory_id": "fac-001",
        "role_code": "003", "is_active": True,
    }
    client = TestClient(app, raise_server_exceptions=False)

    with patch("routers.document_engine_api.get_supabase") as mock_sb, \
         patch("services.company_scope.require_scope_ids") as mock_scope:

        mock_sb.return_value = _make_create_mock_sb("DOC-FAC-020")  # B_OFFICIAL
        mock_scope.return_value = {"company_id": "co-001", "factory_id": "fac-001"}

        resp = client.post("/document-engine/documents", json={"form_schema_id": "schema-uuid-001"})

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "ROUTE_POLICY_BLOCKED"
    assert detail["route_group"] == "B_OFFICIAL"
    assert detail["doc_id"] == "DOC-FAC-020"


def test_RP_T14_create_document_allowed_for_a_internal(monkeypatch):
    """RP-T14: POST /documents allowed — A_INTERNAL (schema gate 통과 전제)."""
    from routers.document_engine_api import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.auth import get_current_user
    import services.document_engine_svc as svc

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "user-001", "company_id": "co-001", "factory_id": "fac-001",
        "role_code": "003", "is_active": True,
    }
    client = TestClient(app, raise_server_exceptions=False)

    with patch("routers.document_engine_api.get_supabase") as mock_sb, \
         patch("services.company_scope.require_scope_ids") as mock_scope, \
         patch("routers.document_engine_api.svc") as mock_svc:

        mock_sb.return_value = _make_create_mock_sb("DOC-OSH-001")  # A_INTERNAL
        mock_scope.return_value = {"company_id": "co-001", "factory_id": "fac-001"}
        mock_svc.create_document.return_value = {"id": "new-doc-001", "status": "DRAFT"}

        resp = client.post("/document-engine/documents", json={"form_schema_id": "schema-uuid-001"})

    # Policy guard passes; result depends on svc mock
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == "new-doc-001"


# ─── RP-T15~T16: compute_channel_state route_group 반영 ─────────────────────

def test_RP_T15_channel_web_edit_blocked_for_non_a_internal():
    """RP-T15: route_group=B_OFFICIAL이면 schema approved여도 WEB_EDIT=BLOCKED."""
    ch = compute_channel_state(
        record_type="SAAS",
        schema_status="APPROVED_FOR_RUNTIME_USE",
        file_count=0,
        file_url=None,
        rights_state=None,
        factory_scope_verified=True,
        route_group="B_OFFICIAL",
    )
    assert ch.WEB_EDIT.state == "BLOCKED"
    assert "B_OFFICIAL" in ch.WEB_EDIT.reason


def test_RP_T16_channel_web_edit_schema_gate_still_applies_for_a_internal():
    """RP-T16: route_group=A_INTERNAL이지만 factory_scope_verified=False → BLOCKED (기존 조건 보존)."""
    ch = compute_channel_state(
        record_type="SAAS",
        schema_status="APPROVED_FOR_RUNTIME_USE",
        file_count=0,
        file_url=None,
        rights_state=None,
        factory_scope_verified=False,
        route_group="A_INTERNAL",
    )
    assert ch.WEB_EDIT.state == "BLOCKED"
    assert "factory scope" in ch.WEB_EDIT.reason
