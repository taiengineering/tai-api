"""API-T01~T08: CSI accident sitemap endpoint tests.
PATCH-B: WO-SEO-INDEX-RECOVERY-PHASE3-B-001.

GET /public/safety-search/sitemap/csi-accidents
Cursor pagination (after_id). identity_status=READY filter.
No real DB / network. _csi_sitemap_dep mocked throughout.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_safety_search as pss_mod

UUID_A = "aaaaaaaa-0000-0000-0000-000000000001"
UUID_B = "aaaaaaaa-0000-0000-0000-000000000002"
UUID_C = "aaaaaaaa-0000-0000-0000-000000000003"

CID_A = f"CSI:{UUID_A}"
CID_B = f"CSI:{UUID_B}"
CID_C = f"CSI:{UUID_C}"


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pss_mod.router)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app())


def _mock_sb(rows: list[dict]) -> MagicMock:
    """Mock Supabase client returning `rows` for any csi_accident_cases query."""
    result = MagicMock()
    result.data = rows
    q = MagicMock()
    for method in ("select", "eq", "order", "limit", "gt"):
        getattr(q, method).return_value = q
    q.execute.return_value = result
    tbl = MagicMock()
    tbl.select.return_value = q
    sb = MagicMock()
    sb.table.return_value = tbl
    return sb


def _row(cid: str, updated_at: str = "2026-09-01T00:00:00", status: str = "READY") -> dict:
    return {"content_id": cid, "updated_at": updated_at, "identity_status": status}


# API-T01 — READY rows returned as {id, updated_at}
def test_t01_ready_rows_returned(client):
    rows = [_row(CID_A, "2026-09-10T00:00:00"), _row(CID_B, "2026-09-11T00:00:00")]
    sb = _mock_sb(rows)
    with patch.object(pss_mod, "_csi_sitemap_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/csi-accidents")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["id"] == UUID_A
    assert data[0]["updated_at"] == "2026-09-10T00:00:00"
    assert data[1]["id"] == UUID_B


# API-T02 — non-READY rows not returned (DB filter enforced; mock returns only READY)
def test_t02_non_ready_excluded(client):
    """DB eq filter excludes non-READY. Mock simulates DB already filtered."""
    sb = _mock_sb([_row(CID_A)])
    with patch.object(pss_mod, "_csi_sitemap_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/csi-accidents")
    data = r.json()
    assert len(data) == 1
    # Verify eq("identity_status", "READY") was called on the query
    tbl = sb.table.return_value
    q = tbl.select.return_value
    q.eq.assert_any_call("identity_status", "READY")


# API-T03 — response fields: only id and updated_at (no content_id, no other fields)
def test_t03_minimal_response_fields(client):
    sb = _mock_sb([_row(CID_A, "2026-09-15T12:00:00")])
    with patch.object(pss_mod, "_csi_sitemap_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/csi-accidents")
    row = r.json()[0]
    assert set(row.keys()) == {"id", "updated_at"}
    assert "content_id" not in row
    assert "identity_status" not in row
    assert "identity_fingerprint" not in row


# API-T04 — after_id cursor: gt filter applied with CSI: prefix
def test_t04_after_id_cursor_applied(client):
    sb = _mock_sb([])
    with patch.object(pss_mod, "_csi_sitemap_dep", return_value=sb):
        r = client.get(f"/public/safety-search/sitemap/csi-accidents?after_id={UUID_A}")
    assert r.status_code == 200
    tbl = sb.table.return_value
    q = tbl.select.return_value
    q.gt.assert_called_once_with("content_id", CID_A)


# API-T05 — no after_id: gt not called (full scan from beginning)
def test_t05_no_after_id_no_gt_filter(client):
    sb = _mock_sb([_row(CID_A)])
    with patch.object(pss_mod, "_csi_sitemap_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/csi-accidents")
    assert r.status_code == 200
    tbl = sb.table.return_value
    q = tbl.select.return_value
    q.gt.assert_not_called()


# API-T06 — empty result is normal (no error)
def test_t06_empty_result_normal(client):
    sb = _mock_sb([])
    with patch.object(pss_mod, "_csi_sitemap_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/csi-accidents")
    assert r.status_code == 200
    assert r.json() == []


# API-T07 — limit > 2000 rejected (FastAPI validation)
def test_t07_limit_above_2000_rejected(client):
    r = client.get("/public/safety-search/sitemap/csi-accidents?limit=9999")
    assert r.status_code == 422


# API-T08 — CSI: prefix stripped from returned id
def test_t08_csi_prefix_stripped_from_id(client):
    """content_id = 'CSI:{uuid}' → id = '{uuid}' (no CSI: prefix in response)."""
    sb = _mock_sb([_row(CID_C, "2026-09-20T00:00:00")])
    with patch.object(pss_mod, "_csi_sitemap_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/csi-accidents")
    data = r.json()
    assert data[0]["id"] == UUID_C
    assert not data[0]["id"].startswith("CSI:")
