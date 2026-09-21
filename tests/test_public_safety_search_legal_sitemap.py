"""S01-S07: LEGAL sitemap list endpoint tests.
WO-SEO-LEGAL-ARTICLE-INDEX.

GET /public/safety-search/sitemap/legal-articles
No real DB / network. _legal_supabase_dep is mocked throughout.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_safety_search as pss_mod


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pss_mod.router)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app())


def _mock_supabase(masters_data: list[dict], articles_data: list[dict]) -> MagicMock:
    def _make_q(execute_data):
        result = MagicMock()
        result.data = execute_data
        q = MagicMock()
        for method in ("select", "eq", "in_", "filter", "order", "range"):
            getattr(q, method).return_value = q
        q.execute.return_value = result
        return q

    def table_side(name):
        tbl = MagicMock()
        if name == "law_master":
            tbl.select.return_value = _make_q(masters_data)
        else:
            tbl.select.return_value = _make_q(articles_data)
        return tbl

    sb = MagicMock()
    sb.table.side_effect = table_side
    return sb


# S01 — empty masters → empty list
def test_s01_empty_masters_returns_empty_list(client):
    sb = _mock_supabase([], [])
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles")
    assert r.status_code == 200
    assert r.json() == []


# S02 — happy path: returns id + updated_at
def test_s02_returns_id_and_updated_at(client):
    masters = [{"current_version_id": "ver-aaa"}]
    articles = [
        {"id": "art-uuid-001", "updated_at": "2026-09-01T00:00:00"},
        {"id": "art-uuid-002", "updated_at": "2026-09-02T00:00:00"},
    ]
    sb = _mock_supabase(masters, articles)
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["id"] == "art-uuid-001"
    assert data[0]["updated_at"] == "2026-09-01T00:00:00"
    assert data[1]["id"] == "art-uuid-002"


# S03 — only id and updated_at in each row (no article_text leakage)
def test_s03_only_id_and_updated_at_fields(client):
    masters = [{"current_version_id": "ver-bbb"}]
    articles = [{"id": "art-001", "updated_at": "2026-09-10T00:00:00"}]
    sb = _mock_supabase(masters, articles)
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles")
    row = r.json()[0]
    assert set(row.keys()) == {"id", "updated_at"}


# S04 — offset/limit query params accepted (200)
def test_s04_offset_limit_accepted(client):
    sb = _mock_supabase([{"current_version_id": "ver-ccc"}], [])
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles?offset=1000&limit=500")
    assert r.status_code == 200


# S05 — limit above 2000 is rejected (422 FastAPI validation)
def test_s05_limit_above_2000_rejected(client):
    r = client.get("/public/safety-search/sitemap/legal-articles?limit=9999")
    assert r.status_code == 422


# S06 — null updated_at rows are included (null is valid)
def test_s06_null_updated_at_included(client):
    masters = [{"current_version_id": "ver-ddd"}]
    articles = [{"id": "art-null-date", "updated_at": None}]
    sb = _mock_supabase(masters, articles)
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles")
    data = r.json()
    assert len(data) == 1
    assert data[0]["updated_at"] is None


# S07 — masters with None current_version_id are skipped
def test_s07_none_version_id_skipped(client):
    masters = [
        {"current_version_id": None},
        {"current_version_id": "ver-eee"},
    ]
    articles = [{"id": "art-valid", "updated_at": "2026-09-01T00:00:00"}]
    sb = _mock_supabase(masters, articles)
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles")
    assert r.status_code == 200
    assert len(r.json()) == 1
