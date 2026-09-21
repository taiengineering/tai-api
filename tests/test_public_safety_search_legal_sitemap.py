"""S01-S09: LEGAL sitemap list endpoint tests.
WO-SEO-LEGAL-ARTICLE-INDEX.

GET /public/safety-search/sitemap/legal-articles
Cursor pagination (after_id). 50-char thin content filter.
No real DB / network. _legal_supabase_dep mocked throughout.
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
    """Mock Supabase client. articles_data is returned for every law_article query."""

    def _make_q(execute_data):
        result = MagicMock()
        result.data = execute_data
        q = MagicMock()
        for method in ("select", "eq", "in_", "filter", "order", "range", "gt"):
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


# S02 — happy path: rows with article_text >= 50 chars are returned
def test_s02_returns_id_and_updated_at_for_eligible_rows(client):
    masters = [{"current_version_id": "ver-aaa"}]
    text_50 = "가" * 50  # exactly 50 chars
    articles = [
        {"id": "art-uuid-001", "updated_at": "2026-09-01T00:00:00", "article_text": text_50},
        {"id": "art-uuid-002", "updated_at": "2026-09-02T00:00:00", "article_text": text_50 + "extra"},
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


# S03 — thin content (< 50 chars) is excluded from response
def test_s03_thin_content_excluded(client):
    masters = [{"current_version_id": "ver-bbb"}]
    articles = [
        {"id": "art-thin-001", "updated_at": "2026-09-01T00:00:00", "article_text": "짧은"},
        {"id": "art-thin-002", "updated_at": "2026-09-01T00:00:00", "article_text": "가" * 49},
        {"id": "art-valid-003", "updated_at": "2026-09-02T00:00:00", "article_text": "가" * 50},
    ]
    sb = _mock_supabase(masters, articles)
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles")
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == "art-valid-003"


# S04 — article_text=None excluded (not.is.null filter at DB level + Python guard)
def test_s04_null_article_text_excluded(client):
    masters = [{"current_version_id": "ver-ccc"}]
    articles = [
        {"id": "art-null", "updated_at": "2026-09-01T00:00:00", "article_text": None},
        {"id": "art-valid", "updated_at": "2026-09-02T00:00:00", "article_text": "가" * 50},
    ]
    sb = _mock_supabase(masters, articles)
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles")
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == "art-valid"


# S05 — response contains only id and updated_at (no article_text leakage)
def test_s05_no_article_text_in_response(client):
    masters = [{"current_version_id": "ver-ddd"}]
    articles = [{"id": "art-001", "updated_at": "2026-09-10T00:00:00", "article_text": "가" * 60}]
    sb = _mock_supabase(masters, articles)
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles")
    row = r.json()[0]
    assert "article_text" not in row
    assert set(row.keys()) == {"id", "updated_at"}


# S06 — after_id param accepted (cursor pagination)
def test_s06_after_id_param_accepted(client):
    sb = _mock_supabase([{"current_version_id": "ver-eee"}], [])
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles?after_id=some-uuid")
    assert r.status_code == 200


# S07 — limit > 2000 rejected (422 FastAPI validation)
def test_s07_limit_above_2000_rejected(client):
    r = client.get("/public/safety-search/sitemap/legal-articles?limit=9999")
    assert r.status_code == 422


# S08 — masters with None current_version_id are skipped
def test_s08_none_version_id_masters_skipped(client):
    masters = [
        {"current_version_id": None},
        {"current_version_id": "ver-fff"},
    ]
    articles = [{"id": "art-valid", "updated_at": "2026-09-01T00:00:00", "article_text": "가" * 50}]
    sb = _mock_supabase(masters, articles)
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles")
    assert r.status_code == 200
    assert len(r.json()) == 1


# S09 — exactly 50-char article is included (boundary)
def test_s09_exactly_50_chars_is_included(client):
    masters = [{"current_version_id": "ver-ggg"}]
    articles = [
        {"id": "art-49", "updated_at": "2026-09-01T00:00:00", "article_text": "가" * 49},
        {"id": "art-50", "updated_at": "2026-09-01T00:00:00", "article_text": "가" * 50},
        {"id": "art-51", "updated_at": "2026-09-01T00:00:00", "article_text": "가" * 51},
    ]
    sb = _mock_supabase(masters, articles)
    with patch.object(pss_mod, "_legal_supabase_dep", return_value=sb):
        r = client.get("/public/safety-search/sitemap/legal-articles")
    ids = [row["id"] for row in r.json()]
    assert "art-49" not in ids
    assert "art-50" in ids
    assert "art-51" in ids
