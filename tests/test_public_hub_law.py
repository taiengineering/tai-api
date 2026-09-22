"""L01-L07: law hub endpoints tests (DB-backed).
WO-SEO-HUB-LAW.

GET /public/safety-search/hub/law   — law list (min_articles filter)
GET /public/safety-search/hub/law/detail?name= — single law meta + articles
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


def _mock_law_client(masters: list[dict], articles: list[dict]) -> MagicMock:
    """Mock the legal supabase client for hub/law endpoints."""
    def _make_q(data):
        result = MagicMock()
        result.data = data
        q = MagicMock()
        q.select.return_value = q
        q.eq.return_value = q
        q.order.return_value = q
        q.limit.return_value = q
        q.range.return_value = q
        q.execute.return_value = result
        return q

    def table_side(name):
        tbl = MagicMock()
        if name == "law_master":
            tbl.select.return_value = _make_q(masters)
        elif name == "law_article":
            tbl.select.return_value = _make_q(articles)
        return tbl

    sb = MagicMock()
    sb.table.side_effect = table_side
    return sb


# L01 — hub/law returns 200
def test_l01_hub_law_returns_200(client):
    sb = _mock_law_client(
        masters=[{"id": "m1", "law_name": "산업안전보건법", "ministry_name": "고용노동부", "law_type_code": "법률", "current_version_id": "v1", "law_name_short": None}],
        articles=[{"law_version_id": "v1"} for _ in range(25)],
    )
    with patch.object(pss_mod, "_legal_supabase", sb):
        r = client.get("/public/safety-search/hub/law?min_articles=20")
    assert r.status_code == 200


# L02 — returns non-empty list when articles >= min_articles
def test_l02_returns_nonempty_list(client):
    sb = _mock_law_client(
        masters=[{"id": "m1", "law_name": "산업안전보건법", "ministry_name": "고용노동부", "law_type_code": "법률", "current_version_id": "v1", "law_name_short": None}],
        articles=[{"law_version_id": "v1"} for _ in range(25)],
    )
    with patch.object(pss_mod, "_legal_supabase", sb):
        data = client.get("/public/safety-search/hub/law?min_articles=20").json()
    assert isinstance(data, list) and len(data) == 1


# L03 — law below min_articles excluded
def test_l03_below_min_articles_excluded(client):
    sb = _mock_law_client(
        masters=[{"id": "m1", "law_name": "소규모법", "ministry_name": "부처", "law_type_code": "법률", "current_version_id": "v1", "law_name_short": None}],
        articles=[{"law_version_id": "v1"} for _ in range(5)],
    )
    with patch.object(pss_mod, "_legal_supabase", sb):
        data = client.get("/public/safety-search/hub/law?min_articles=20").json()
    assert data == []


# L04 — response shape has required fields
def test_l04_item_shape(client):
    sb = _mock_law_client(
        masters=[{"id": "m1", "law_name": "산업안전보건법", "ministry_name": "고용노동부", "law_type_code": "법률", "current_version_id": "v1", "law_name_short": None}],
        articles=[{"law_version_id": "v1"} for _ in range(25)],
    )
    with patch.object(pss_mod, "_legal_supabase", sb):
        data = client.get("/public/safety-search/hub/law?min_articles=20").json()
    item = data[0]
    assert "value" in item and "display_name" in item
    assert "article_count" in item and item["article_count"] == 25
    assert "ministry" in item and "law_type" in item


# L05 — law_name with brackets normalized in value
def test_l05_slug_normalization(client):
    sb = _mock_law_client(
        masters=[{"id": "m1", "law_name": "건설산업기본법(건설업법)", "ministry_name": "부처", "law_type_code": "법률", "current_version_id": "v1", "law_name_short": None}],
        articles=[{"law_version_id": "v1"} for _ in range(25)],
    )
    with patch.object(pss_mod, "_legal_supabase", sb):
        data = client.get("/public/safety-search/hub/law?min_articles=20").json()
    assert len(data) == 1
    assert data[0]["value"] == "건설산업기본법건설업법"  # brackets removed, content kept
    assert data[0]["display_name"] == "건설산업기본법(건설업법)"  # original preserved


# L06 — hub/law/detail returns 200 and correct shape
def test_l06_detail_returns_200(client):
    sb = _mock_law_client(
        masters=[{"id": "m1", "law_name": "산업안전보건법", "ministry_name": "고용노동부", "law_type_code": "법률", "current_version_id": "v1", "law_name_short": "산안법"}],
        articles=[{"id": "a1", "law_version_id": "v1", "article_no": "1", "article_sub_no": None, "article_title": "목적"}],
    )
    with patch.object(pss_mod, "_legal_supabase", sb):
        r = client.get("/public/safety-search/hub/law/detail?name=산업안전보건법")
    assert r.status_code == 200
    data = r.json()
    assert "meta" in data and "articles" in data
    assert data["meta"]["law_name"] == "산업안전보건법"
    assert len(data["articles"]) == 1
    assert data["articles"][0]["id"] == "a1"


# L07 — hub/law/detail returns 404 for unknown law
def test_l07_detail_404_for_unknown(client):
    sb = _mock_law_client(masters=[], articles=[])
    with patch.object(pss_mod, "_legal_supabase", sb):
        r = client.get("/public/safety-search/hub/law/detail?name=없는법령")
    assert r.status_code == 404
