"""K01-K10: KNOWLEDGE canonical detail endpoint tests.
WO-MKT-SEARCH-04B-2A §33-§42.

No real DB / network. safe_help_svc.get_published_by_doc_id is mocked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_safety_search as pss_mod


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pss_mod.router)
    return app


def _published_row(
    doc_id: str = "FAQ-test",
    slug: str = "test-slug",
) -> dict:
    return {
        "doc_id": doc_id,
        "type": "FAQ",
        "slug": slug,
        "title": "테스트 제목",
        "question": "질문입니다",
        "answer_short": "짧은 답변",
        "body": "<p>본문 내용</p>",
        "menu_group": "app",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app())


# ---------------------------------------------------------------------------
# K01 — PUBLISHED row → 200
# ---------------------------------------------------------------------------
def test_k01_published_returns_200(client):
    with patch.object(pss_mod.safe_help_svc, "get_published_by_doc_id", return_value=_published_row()):
        r = client.get("/public/safety-search/knowledge/FAQ-test")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# K02 — canonical identity: object_type=KNOWLEDGE, canonical_id == detail.doc_id
# ---------------------------------------------------------------------------
def test_k02_canonical_identity(client):
    with patch.object(pss_mod.safe_help_svc, "get_published_by_doc_id", return_value=_published_row(doc_id="FAQ-test")):
        r = client.get("/public/safety-search/knowledge/FAQ-test")
    body = r.json()
    assert body["object_type"] == "KNOWLEDGE"
    assert body["canonical_id"] == "FAQ-test"
    assert body["detail"]["doc_id"] == "FAQ-test"


# ---------------------------------------------------------------------------
# K03 — slug is NOT the lookup key; doc_id is
# ---------------------------------------------------------------------------
def test_k03_slug_not_identity(client):
    row = _published_row(doc_id="FAQ-test", slug="completely-different")
    called_with: list[str] = []

    def mock_fn(doc_id: str):
        called_with.append(doc_id)
        return row

    with patch.object(pss_mod.safe_help_svc, "get_published_by_doc_id", side_effect=mock_fn):
        r = client.get("/public/safety-search/knowledge/FAQ-test")

    assert r.status_code == 200
    assert called_with == ["FAQ-test"]  # lookup used doc_id, not slug


# ---------------------------------------------------------------------------
# K04 — DRAFT (service returns None) → 404
# ---------------------------------------------------------------------------
def test_k04_draft_returns_404(client):
    with patch.object(pss_mod.safe_help_svc, "get_published_by_doc_id", return_value=None):
        r = client.get("/public/safety-search/knowledge/FAQ-draft")
    assert r.status_code == 404
    assert r.json()["detail"] == "KNOWLEDGE_NOT_FOUND"


# ---------------------------------------------------------------------------
# K05 — missing doc_id → 404
# ---------------------------------------------------------------------------
def test_k05_missing_returns_404(client):
    with patch.object(pss_mod.safe_help_svc, "get_published_by_doc_id", return_value=None):
        r = client.get("/public/safety-search/knowledge/nonexistent-id")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# K06 — response includes all required top-level and detail fields
# ---------------------------------------------------------------------------
def test_k06_response_fields(client):
    with patch.object(pss_mod.safe_help_svc, "get_published_by_doc_id", return_value=_published_row()):
        r = client.get("/public/safety-search/knowledge/FAQ-test")
    body = r.json()
    for field in ("object_type", "canonical_id", "title", "summary"):
        assert field in body, f"top-level field missing: {field}"
    detail = body["detail"]
    for field in ("doc_id", "type", "slug", "question", "answer_short", "body", "menu_group", "updated_at"):
        assert field in detail, f"detail field missing: {field}"


# ---------------------------------------------------------------------------
# K07 — extra DB fields do not leak into the response
# ---------------------------------------------------------------------------
def test_k07_no_internal_field_leakage(client):
    row = _published_row()
    row["internal_secret"] = "must-not-appear"
    row["search_tsv"] = "internal-vector"
    row["id"] = "some-uuid"
    with patch.object(pss_mod.safe_help_svc, "get_published_by_doc_id", return_value=row):
        r = client.get("/public/safety-search/knowledge/FAQ-test")
    body = r.json()
    for forbidden in ("internal_secret", "search_tsv", "id"):
        assert forbidden not in body, f"leaked in top-level: {forbidden}"
        assert forbidden not in body.get("detail", {}), f"leaked in detail: {forbidden}"


# ---------------------------------------------------------------------------
# K08 — GET /public/safety-search regression (route not broken by new /knowledge/*)
# ---------------------------------------------------------------------------
def test_k08_main_search_regression(client):
    # Missing 'q' → 422 confirms the main search route still exists and routes correctly
    r = client.get("/public/safety-search")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# K09 — GET /public/safety-search/kosha not shadowed by /knowledge/{canonical_id}
# ---------------------------------------------------------------------------
def test_k09_kosha_route_regression(client):
    mock_result = {"items": [], "total": 0, "page": 1, "page_size": 10}
    with patch.object(pss_mod, "search_kosha_public", new=AsyncMock(return_value=mock_result)):
        r = client.get("/public/safety-search/kosha?q=test")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# K10 — no Authorization header required (public endpoint)
# ---------------------------------------------------------------------------
def test_k10_no_auth_required(client):
    with patch.object(pss_mod.safe_help_svc, "get_published_by_doc_id", return_value=_published_row()):
        r = client.get(
            "/public/safety-search/knowledge/FAQ-test"
            # deliberately no Authorization header
        )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# K11 — body fallback summary is exactly 200 chars (contract alignment)
# ---------------------------------------------------------------------------
def test_k11_body_fallback_summary_exactly_200(client):
    row = _published_row()
    row["answer_short"] = None
    row["body"] = "<p>" + ("가" * 230) + "</p>"
    with patch.object(pss_mod.safe_help_svc, "get_published_by_doc_id", return_value=row):
        r = client.get("/public/safety-search/knowledge/FAQ-test")
    assert r.status_code == 200
    summary = r.json()["summary"]
    assert "<" not in summary, "HTML tag leaked into summary"
    assert len(summary) == 200
    assert summary == "가" * 200
