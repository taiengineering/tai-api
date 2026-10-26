"""R1-T01/T02: Catalog API /document-engine/catalog/{doc_id} response contract.

Verifies that resolved_evidence_connections is included in the catalog API response
(R1-01 defect fix) and that the frontend contract is compatible.
No live DB; catalog_resolver and supabase are mocked.
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.document_engine_api import router


def _make_app():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def _make_supabase_mock(doc_id="DOC-CON-048", catalog_uuid="cat-uuid-001"):
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": catalog_uuid, "doc_id": doc_id, "doc_name": "재하도급 승낙 통보서",
         "sector": "CON", "category": ""}
    ]
    return sb


SCHEMA_UUID = "schema-uuid-001"

_RESOLVED_NO_EVIDENCE = {
    "availability": "READY_FOR_EDIT",
    "active_schema_id": SCHEMA_UUID,
    "active_schema_status": "APPROVED_FOR_RUNTIME_USE",
    "candidate_schema_id": None,
    "candidate_schema_status": None,
    "schema": {"id": SCHEMA_UUID},
    "fields": [],
    "checklists": [],
    "evidence_fields": [],
    "resolved_evidence_connections": [],
}

_EV_FIELD_ID = "ev-field-001"
_RESOLVED_WITH_EVIDENCE = {
    **_RESOLVED_NO_EVIDENCE,
    "evidence_fields": [{"id": _EV_FIELD_ID, "evidence_type": "ATTACHMENT"}],
    "resolved_evidence_connections": [
        {
            "evidence_field_id": _EV_FIELD_ID,
            "status": "RESOLVED",
            "evidence_candidate_status": "APPROVED_FOR_RUNTIME_USE",
            "field_id": "f-uuid-001",
            "field_key": "attached_documents",
            "input_type": "file",
        }
    ],
}

_RESOLVED_WITH_UNRESOLVED = {
    **_RESOLVED_NO_EVIDENCE,
    "evidence_fields": [{"id": _EV_FIELD_ID, "evidence_type": "ATTACHMENT"}],
    "resolved_evidence_connections": [
        {
            "evidence_field_id": _EV_FIELD_ID,
            "status": "UNRESOLVED",
            "reason": "evidence_candidate_not_found",
        }
    ],
}


def test_R1_T01_catalog_response_includes_resolved_evidence_connections_key():
    """R1-T01: /catalog/{doc_id} response must include resolved_evidence_connections."""
    tc = _make_app()
    with (
        patch("routers.document_engine_api.get_supabase", return_value=_make_supabase_mock()),
        patch("routers.document_engine_api.resolve_catalog_runtime_schema", return_value=_RESOLVED_NO_EVIDENCE),
    ):
        resp = tc.get("/document-engine/catalog/DOC-CON-048")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "resolved_evidence_connections" in data, (
        "resolved_evidence_connections must be present in catalog response (R1-01 fix)"
    )
    assert data["resolved_evidence_connections"] == []


def test_R1_T01b_catalog_response_includes_resolved_connections_for_evidence_doc():
    """R1-T01b: When evidence_fields exist, resolved_evidence_connections passes through."""
    tc = _make_app()
    with (
        patch("routers.document_engine_api.get_supabase", return_value=_make_supabase_mock()),
        patch("routers.document_engine_api.resolve_catalog_runtime_schema",
              return_value=_RESOLVED_WITH_EVIDENCE),
    ):
        resp = tc.get("/document-engine/catalog/DOC-CON-048")
    assert resp.status_code == 200
    data = resp.json()["data"]
    conns = data.get("resolved_evidence_connections", "MISSING")
    assert conns != "MISSING", "resolved_evidence_connections must be in response"
    assert len(conns) == 1
    assert conns[0]["evidence_field_id"] == _EV_FIELD_ID
    assert conns[0]["status"] == "RESOLVED"


def test_R1_T01c_unresolved_connection_not_hidden():
    """R1-T01c: UNRESOLVED connections must be passed through, not hidden (frontend needs them)."""
    tc = _make_app()
    with (
        patch("routers.document_engine_api.get_supabase", return_value=_make_supabase_mock()),
        patch("routers.document_engine_api.resolve_catalog_runtime_schema",
              return_value=_RESOLVED_WITH_UNRESOLVED),
    ):
        resp = tc.get("/document-engine/catalog/DOC-CON-048")
    assert resp.status_code == 200
    data = resp.json()["data"]
    conns = data.get("resolved_evidence_connections", [])
    assert len(conns) == 1
    assert conns[0]["status"] == "UNRESOLVED", (
        "UNRESOLVED connections must not be hidden — frontend reads status to decide guard"
    )


def test_R1_T02_catalog_response_fields_satisfy_frontend_contract():
    """R1-T02: Response structure matches CatalogRuntimeResponse interface (frontend contract)."""
    tc = _make_app()
    with (
        patch("routers.document_engine_api.get_supabase", return_value=_make_supabase_mock()),
        patch("routers.document_engine_api.resolve_catalog_runtime_schema",
              return_value=_RESOLVED_WITH_EVIDENCE),
    ):
        resp = tc.get("/document-engine/catalog/DOC-CON-048")
    assert resp.status_code == 200
    data = resp.json()["data"]
    # Required top-level keys per CatalogRuntimeResponse
    for key in ("catalog", "runtime", "fields", "checklists", "evidence_fields",
                "resolved_evidence_connections", "supported_export_formats"):
        assert key in data, f"Missing required key: {key}"
    # Resolved connection fields
    conn = data["resolved_evidence_connections"][0]
    for field in ("evidence_field_id", "status"):
        assert field in conn, f"Missing required field in connection: {field}"
