"""WP-00 OD-DOC260-ROUTE-001 DRAFT — provision policy guard Smoke tests.

CONTRACT_CHANGE_PENDING: requires Owner approval of OD-DOC260-ROUTE-001
before production activation. Conflicts with WP-01 READ-ONLY contract.

Smoke coverage (5 groups, §7):
  G-A  A_INTERNAL → web_edit_allowed=True  → POST /documents proceeds
  G-B  B_OFFICIAL → web_edit_allowed=False → POST /documents 403
  G-U  U_UNRESOLVED → web_edit_allowed=False → POST /documents 403
  G-E  E_EXTERNAL → web_edit_allowed=False → POST /documents 403
  G-F  F_SCOPE_OUT → web_edit_allowed=False → POST /documents 403
  G-X  Unknown doc_id (not in matrix) → policy=None → fail-open, proceeds
  G-R  GET /catalog/{doc_id} — provision_policy present, can_create NOT blocked
"""
from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.document_engine_api import router
from routers.auth import get_current_user
from services.document_engine.r2_route_policy import get_provision_policy

SCHEMA_UUID  = "sch-uuid-0000-0000-0000-000000000001"
CAT_UUID     = "cat-uuid-0000-0000-0000-000000000001"
FACTORY_UUID = "fac-uuid-0000-0000-0000-000000000001"
COMPANY_UUID = "cmp-uuid-0000-0000-0000-000000000001"

_USER = {
    "id": "usr-uuid-001",
    "company_id": COMPANY_UUID,
    "factory_id": FACTORY_UUID,
    "roles": [],
}


def _make_app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _USER
    return app


def _make_client():
    return TestClient(_make_app(), raise_server_exceptions=False)


# ── Policy unit Smoke ─────────────────────────────────────────────────────────

REPRESENTATIVE_DOCS = {
    "A_INTERNAL":   ("DOC-OSH-001", True),
    "B_OFFICIAL":   ("DOC-FAC-022", False),
    "U_UNRESOLVED": ("DOC-BLD-001", False),
    "E_EXTERNAL":   ("DOC-BLD-033", False),
    "F_SCOPE_OUT":  ("DOC-CON-002", False),
}


@pytest.mark.parametrize("group,doc_id,expected_allowed", [
    (g, d, a) for g, (d, a) in REPRESENTATIVE_DOCS.items()
])
def test_provision_policy_web_edit_allowed(group, doc_id, expected_allowed):
    """G-A~G-F policy: get_provision_policy returns correct web_edit_allowed per group."""
    policy = get_provision_policy(doc_id)
    assert policy is not None, f"Policy not found for {doc_id}"
    assert policy["route_group"] == group
    assert policy["web_edit_allowed"] == expected_allowed


def test_unknown_doc_id_returns_none():
    """G-X policy: Unknown doc_id → None (fail-open guard)."""
    assert get_provision_policy("DOC-UNKNOWN-999") is None


# ── HTTP Smoke — POST /documents ─────────────────────────────────────────────

def _make_sb_for_create(doc_id: str) -> MagicMock:
    """Supabase mock for the manual create_document path.

    Chain used by the OD-DOC260-ROUTE-001 guard:
      sb.table("runtime_form_schema").select(...).eq(...).limit(1).execute().data
      sb.table("document_forms").select(...).eq(...).limit(1).execute().data
    All other table calls return generic success stubs.
    """
    sb = MagicMock()

    def _tbl(name: str):
        t = MagicMock()
        lim_exec = t.select.return_value.eq.return_value.limit.return_value.execute.return_value
        exec_ = t.select.return_value.eq.return_value.execute.return_value

        if name == "runtime_form_schema":
            lim_exec.data = [{"catalog_document_id": CAT_UUID}]
        elif name == "document_forms":
            lim_exec.data = [{"doc_id": doc_id}]
        else:
            lim_exec.data = [{"id": FACTORY_UUID, "company_id": COMPANY_UUID}]
            exec_.data = [{"id": FACTORY_UUID, "company_id": COMPANY_UUID}]
            t.insert.return_value.execute.return_value.data = [
                {"id": "rdd-new-001", "status": "DRAFT"}
            ]
        return t

    sb.table.side_effect = _tbl
    return sb


def _post(client, doc_id: str):
    sb = _make_sb_for_create(doc_id)
    with (
        patch("routers.document_engine_api.get_supabase", return_value=sb),
        patch(
            "routers.document_engine_api.require_scope_ids",
            return_value={"company_id": COMPANY_UUID, "factory_id": FACTORY_UUID},
        ),
        patch(
            "routers.document_engine_api.svc.create_document",
            return_value={"id": "rdd-new-001", "status": "DRAFT"},
        ),
    ):
        return client.post(
            "/document-engine/documents",
            json={"form_schema_id": SCHEMA_UUID},
            headers={"Authorization": "Bearer test"},
        )


def test_create_a_internal_proceeds():
    """G-A HTTP: A_INTERNAL → 200 (creation permitted)."""
    resp = _post(_make_client(), "DOC-OSH-001")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.parametrize("group,doc_id", [
    ("B_OFFICIAL",   "DOC-FAC-022"),
    ("U_UNRESOLVED", "DOC-BLD-001"),
    ("E_EXTERNAL",   "DOC-BLD-033"),
    ("F_SCOPE_OUT",  "DOC-CON-002"),
])
def test_create_non_a_blocked(group, doc_id):
    """G-B/U/E/F HTTP: Non-A_INTERNAL → 403 NEW_CREATION_NOT_PERMITTED."""
    resp = _post(_make_client(), doc_id)
    assert resp.status_code == 403, (
        f"{group}/{doc_id}: Expected 403, got {resp.status_code}: {resp.text}"
    )
    assert "NEW_CREATION_NOT_PERMITTED" in resp.text


def test_create_unknown_doc_proceeds():
    """G-X HTTP: Unknown doc_id (policy=None) → fail-open, 200."""
    resp = _post(_make_client(), "DOC-UNKNOWN-999")
    assert resp.status_code == 200, f"Expected 200 (fail-open), got {resp.status_code}: {resp.text}"


# ── HTTP Smoke — GET /catalog ─────────────────────────────────────────────────

_CATALOG_RESOLVED = {
    "availability": "READY_FOR_EDIT",
    "active_schema_id": SCHEMA_UUID,
    "active_schema_status": "APPROVED_FOR_RUNTIME_USE",
    "candidate_schema_id": None,
    "candidate_schema_status": None,
    "fields": [],
    "checklists": [],
    "evidence_fields": [],
    "resolved_evidence_connections": [],
}


def _catalog_sb(doc_id: str):
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": CAT_UUID, "doc_id": doc_id, "doc_name": "테스트문서",
         "sector": "OSH", "category": ""}
    ]
    return sb


@pytest.mark.parametrize("doc_id,expected_allowed,expected_can_create", [
    ("DOC-OSH-001", True,  True),
    ("DOC-FAC-022", False, True),  # can_create still True — WP-01 READ-ONLY contract
    ("DOC-BLD-001", False, True),
])
def test_catalog_api_provision_policy(doc_id, expected_allowed, expected_can_create):
    """G-R: GET /catalog/{doc_id} — provision_policy.web_edit_allowed correct,
    can_create NOT modified by web_edit_allowed (WP-01 contract preserved)."""
    client = _make_client()
    with (
        patch("routers.document_engine_api.get_supabase", return_value=_catalog_sb(doc_id)),
        patch(
            "routers.document_engine_api.resolve_catalog_runtime_schema",
            return_value=_CATALOG_RESOLVED,
        ),
    ):
        resp = client.get(f"/document-engine/catalog/{doc_id}")

    assert resp.status_code == 200
    data = resp.json()["data"]
    pp = data["runtime"]["provision_policy"]
    assert pp is not None
    assert pp["web_edit_allowed"] == expected_allowed
    assert data["runtime"]["can_create"] == expected_can_create, (
        "can_create must still reflect availability only (WP-01 contract preserved)"
    )
