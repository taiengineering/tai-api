"""OBJ02-C2A router integration + tenant authz tests.

Covers:
  RT-tests: Router integration (auth, format, content-type)
  SEC-tests: Tenant authorization (cross-company/factory deny)
"""
from __future__ import annotations

import sys
import asyncio
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

# ── Fixtures ─────────────────────────────────────────────────────────────────

DOC_ID = "bbbbbbbb-0001-0001-0001-000000000001"
COMPANY_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COMPANY_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
FACTORY_A1 = "ffffffff-0001-0001-0001-000000000001"
FACTORY_A2 = "ffffffff-0002-0002-0002-000000000002"

_USER_COMPANY_A = {
    "id": "u1", "company_id": COMPANY_A, "factory_id": None,
    "role_code": "COMPANY_ADMIN", "is_active": True,
}
_USER_COMPANY_B = {
    "id": "u2", "company_id": COMPANY_B, "factory_id": None,
    "role_code": "COMPANY_ADMIN", "is_active": True,
}
_USER_FACTORY_A1 = {
    "id": "u3", "company_id": COMPANY_A, "factory_id": FACTORY_A1,
    "role_code": "FACTORY_MANAGER", "is_active": True,
}
_USER_FACTORY_A2 = {
    "id": "u4", "company_id": COMPANY_A, "factory_id": FACTORY_A2,
    "role_code": "FACTORY_MANAGER", "is_active": True,
}

_DOC_COMPANY_A = {
    "id": DOC_ID, "company_id": COMPANY_A, "factory_id": None,
    "status": "DRAFT", "form_schema_id": "schema-1",
    "runtime_data_json": {}, "evidence_links": [], "version": 1,
}
_DOC_FACTORY_A1 = {
    "id": DOC_ID, "company_id": COMPANY_A, "factory_id": FACTORY_A1,
    "status": "DRAFT", "form_schema_id": "schema-1",
    "runtime_data_json": {}, "evidence_links": [], "version": 1,
}

SAMPLE_HTML = "<!DOCTYPE html><html><body>test render</body></html>"
SAMPLE_PDF = b"%PDF-1.4 sample bytes"


# ── _ensure_own_company fake implementation ───────────────────────────────────

def _fake_ensure_own_company(resource_company_id, current, supabase, not_found, resource_factory_id=None):
    """Simplified scope check: company match + factory match for FACTORY tier."""
    if resource_company_id != current.get("company_id"):
        raise HTTPException(404, detail=not_found)
    if resource_factory_id is not None and current.get("factory_id") is not None:
        if resource_factory_id != current.get("factory_id"):
            raise HTTPException(404, detail=not_found)


def _fake_scoped_filter(current, sb, table_cols):
    cid = current.get("company_id")
    if not cid:
        # Import DENY here lazily to avoid import issues
        class _FakeDeny:
            pass
        return _FakeDeny()
    return {"company_id": cid}


def _fake_forced_company_id(current, sb, company_id=None):
    return current.get("company_id") or company_id


# ── Client builder ────────────────────────────────────────────────────────────

@contextmanager
def _build_client(current_user, doc_row=None, render_result=SAMPLE_HTML, pdf_result=SAMPLE_PDF):
    """Build a TestClient for the document_engine_api router with mocked deps."""

    # Create fake supabase that returns doc_row for _check_doc_scope
    class _FakeSingle:
        def __init__(self, d):
            self.data = d

        def execute(self):
            return self

    class _FakeQ:
        def __init__(self, doc):
            self._doc = doc

        def select(self, *a, **kw):
            return self

        def eq(self, *a, **kw):
            return self

        def single(self):
            return _FakeSingle(self._doc)

        def execute(self):
            class R:
                data = []
            return R()

    class _FakeSB:
        def __init__(self, doc):
            self._doc = doc

        def table(self, _):
            return _FakeQ(self._doc)

    fake_sb = _FakeSB(doc_row)

    # Remove cached module to force fresh import with patched deps
    sys.modules.pop("routers.document_engine_api", None)

    with patch("services.company_scope._ensure_own_company", side_effect=_fake_ensure_own_company), \
         patch("services.company_scope._ensure_factory_own", return_value=None), \
         patch("services.company_scope._forced_company_id", side_effect=_fake_forced_company_id), \
         patch("services.company_scope.scoped_filter", side_effect=_fake_scoped_filter), \
         patch("services.company_scope.apply_scoped_filter", side_effect=lambda q, f: q), \
         patch("db.supabase_client.get_supabase", return_value=fake_sb):
        from routers.document_engine_api import router as doc_router
        from routers.auth import get_current_user

        app = FastAPI()
        app.include_router(doc_router)

        # Override auth dependency
        app.dependency_overrides[get_current_user] = lambda: current_user

        # Patch svc and pdf adapter at module level
        import routers.document_engine_api as _rmod

        async def _mock_pdf(html):
            return pdf_result

        with patch.object(_rmod.svc, "render_document_html", return_value=render_result), \
             patch.object(_rmod.svc, "get_document", return_value=doc_row), \
             patch.object(_rmod.svc, "list_documents", return_value={"items": [], "total": 0, "page": 1, "page_size": 20}), \
             patch.object(_rmod.svc, "update_document", return_value=doc_row or {}), \
             patch.object(_rmod.svc, "link_evidence", return_value={}), \
             patch.object(_rmod.svc, "list_evidence", return_value=[]), \
             patch.object(_rmod.svc, "list_generated", return_value=[]), \
             patch.object(_rmod.svc, "get_audit_log", return_value=[]), \
             patch("routers.document_engine_api._html_to_pdf", side_effect=_mock_pdf), \
             patch("routers.document_engine_api.get_supabase", return_value=fake_sb):
            yield TestClient(app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════
# RT-tests: Router Integration
# ═══════════════════════════════════════════════════════

def test_RT1_unauthenticated_render_deny():
    """RT1: no auth token → render endpoint returns 401 or 403."""
    sys.modules.pop("routers.document_engine_api", None)
    with patch("services.company_scope._ensure_own_company", return_value=None), \
         patch("db.supabase_client.get_supabase", return_value=MagicMock()):
        from routers.document_engine_api import router as doc_router
        app = FastAPI()
        app.include_router(doc_router)
        # Do NOT override dependency — no auth override means real get_current_user which raises
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/document-engine/documents/{DOC_ID}/render")
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"


def test_RT2_unauthenticated_generate_deny():
    """RT2: no auth token → generate endpoint returns 401 or 403."""
    sys.modules.pop("routers.document_engine_api", None)
    with patch("services.company_scope._ensure_own_company", return_value=None), \
         patch("db.supabase_client.get_supabase", return_value=MagicMock()):
        from routers.document_engine_api import router as doc_router
        app = FastAPI()
        app.include_router(doc_router)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/document-engine/documents/{DOC_ID}/generate",
            json={"export_type": "HTML"},
        )
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"


def test_RT3_unsupported_format_422():
    """RT3: unsupported export_type → 422."""
    with _build_client(_USER_COMPANY_A, doc_row=_DOC_COMPANY_A) as client:
        resp = client.post(
            f"/document-engine/documents/{DOC_ID}/generate",
            json={"export_type": "XLSX"},
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


def test_RT4_pdf_content_type():
    """RT4: PDF export → Content-Type application/pdf."""
    with _build_client(_USER_COMPANY_A, doc_row=_DOC_COMPANY_A, pdf_result=SAMPLE_PDF) as client:
        resp = client.post(
            f"/document-engine/documents/{DOC_ID}/generate",
            json={"export_type": "PDF"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "application/pdf" in resp.headers.get("content-type", "")


def test_RT5_pdf_bytes_returned():
    """RT5: PDF export → non-empty bytes body."""
    with _build_client(_USER_COMPANY_A, doc_row=_DOC_COMPANY_A, pdf_result=SAMPLE_PDF) as client:
        resp = client.post(
            f"/document-engine/documents/{DOC_ID}/generate",
            json={"export_type": "PDF"},
        )
        assert resp.status_code == 200
        assert len(resp.content) > 0


def test_RT6_html_content_type():
    """RT6: HTML export → text/html content-type."""
    with _build_client(_USER_COMPANY_A, doc_row=_DOC_COMPANY_A) as client:
        resp = client.post(
            f"/document-engine/documents/{DOC_ID}/generate",
            json={"export_type": "HTML"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        ct = resp.headers.get("content-type", "")
        assert "text/html" in ct, f"Expected text/html content-type, got {ct!r}"


# ═══════════════════════════════════════════════════════
# SEC-tests: Tenant authorization
# ═══════════════════════════════════════════════════════

def test_SEC1_same_company_render_allow():
    """SEC1: same company document → render allowed (200)."""
    with _build_client(_USER_COMPANY_A, doc_row=_DOC_COMPANY_A) as client:
        resp = client.get(f"/document-engine/documents/{DOC_ID}/render")
        assert resp.status_code == 200


def test_SEC2_cross_company_render_deny():
    """SEC2: different company document → render denied (404)."""
    with _build_client(_USER_COMPANY_B, doc_row=_DOC_COMPANY_A) as client:
        resp = client.get(f"/document-engine/documents/{DOC_ID}/render")
        assert resp.status_code == 404


def test_SEC3_cross_factory_render_deny():
    """SEC3: same company, different factory → render denied (404)."""
    with _build_client(_USER_FACTORY_A2, doc_row=_DOC_FACTORY_A1) as client:
        resp = client.get(f"/document-engine/documents/{DOC_ID}/render")
        assert resp.status_code == 404


def test_SEC4_own_factory_render_allow():
    """SEC4: same company + own factory → render allowed (200)."""
    with _build_client(_USER_FACTORY_A1, doc_row=_DOC_FACTORY_A1) as client:
        resp = client.get(f"/document-engine/documents/{DOC_ID}/render")
        assert resp.status_code == 200


def test_SEC5_unauthenticated_patch_deny():
    """SEC5: no auth → PATCH denied (401/403)."""
    sys.modules.pop("routers.document_engine_api", None)
    with patch("services.company_scope._ensure_own_company", return_value=None), \
         patch("db.supabase_client.get_supabase", return_value=MagicMock()):
        from routers.document_engine_api import router as doc_router
        app = FastAPI()
        app.include_router(doc_router)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch(
            f"/document-engine/documents/{DOC_ID}",
            json={"runtime_data_json": {}},
        )
        assert resp.status_code in (401, 403)


def test_SEC6_cross_company_patch_deny():
    """SEC6: different company → PATCH denied (404)."""
    with _build_client(_USER_COMPANY_B, doc_row=_DOC_COMPANY_A) as client:
        resp = client.patch(
            f"/document-engine/documents/{DOC_ID}",
            json={"runtime_data_json": {}},
        )
        assert resp.status_code == 404


def test_SEC7_cross_company_evidence_deny():
    """SEC7: different company → GET evidence denied (404)."""
    with _build_client(_USER_COMPANY_B, doc_row=_DOC_COMPANY_A) as client:
        resp = client.get(f"/document-engine/documents/{DOC_ID}/evidence")
        assert resp.status_code == 404


def test_SEC8_cross_company_pdf_deny():
    """SEC8: different company → PDF generation denied (404)."""
    with _build_client(_USER_COMPANY_B, doc_row=_DOC_COMPANY_A) as client:
        resp = client.post(
            f"/document-engine/documents/{DOC_ID}/generate",
            json={"export_type": "PDF"},
        )
        assert resp.status_code == 404
