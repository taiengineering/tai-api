"""L01-L12: LEGAL canonical detail endpoint tests.
WO-MKT-SEARCH-04B-5B-1.

No real DB / network. get_current_legal_article_by_id and
_legal_supabase_dep are mocked throughout.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_safety_search as pss_mod


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pss_mod.router)
    return app


_CANONICAL_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

_MOCK_CLIENT = object()


def _eligible_row(
    *,
    law_name: str = "산업안전보건법",
    article_no: str = "38",
    article_sub_no: str | None = None,
    article_title: str | None = "안전조치",
    article_text: str | None = "사업주는 다음 각 호의 위험으로 인한 산업재해를 예방하여야 한다.",
    enforcement_date: str | None = "2021-01-16",
    updated_at: str | None = "2024-03-01T00:00:00+00:00",
) -> dict:
    return {
        "id": _CANONICAL_ID,
        "law_id": "master-uuid",
        "law_version_id": "version-uuid",
        "law_name": law_name,
        "record_kind": "law_article",
        "article_no": article_no,
        "article_sub_no": article_sub_no,
        "article_title": article_title,
        "article_text": article_text,
        "is_deleted_in_version": False,
        "enforcement_date": enforcement_date,
        "updated_at": updated_at,
    }


def _get(client, path: str, **kwargs):
    return client.get(path, **kwargs)


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app())


def _patched(mock_row):
    """Context manager pair: supabase dep + get_current_legal_article_by_id."""
    sb_patch = patch.object(pss_mod, "_legal_supabase_dep", return_value=_MOCK_CLIENT)
    fn_patch = patch.object(pss_mod, "get_current_legal_article_by_id", return_value=mock_row)
    return sb_patch, fn_patch


# ---------------------------------------------------------------------------
# L01 — 200 for an eligible article
# ---------------------------------------------------------------------------
def test_l01_eligible_returns_200(client):
    sb, fn = _patched(_eligible_row())
    with sb, fn:
        r = client.get(f"/public/safety-search/legal/{_CANONICAL_ID}")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# L02 — 404 when helper returns None (any non-eligible case)
# ---------------------------------------------------------------------------
def test_l02_not_found_returns_404(client):
    sb, fn = _patched(None)
    with sb, fn:
        r = client.get(f"/public/safety-search/legal/{_CANONICAL_ID}")
    assert r.status_code == 404
    assert r.json()["detail"] == "LEGAL_NOT_FOUND"


# ---------------------------------------------------------------------------
# L03 — canonical identity: object_type=LEGAL, canonical_id matches path
# ---------------------------------------------------------------------------
def test_l03_canonical_identity(client):
    sb, fn = _patched(_eligible_row())
    with sb, fn:
        r = client.get(f"/public/safety-search/legal/{_CANONICAL_ID}")
    body = r.json()
    assert body["object_type"] == "LEGAL"
    assert body["canonical_id"] == _CANONICAL_ID


# ---------------------------------------------------------------------------
# L04 — all expected detail fields are present in response
# ---------------------------------------------------------------------------
def test_l04_detail_fields_present(client):
    sb, fn = _patched(_eligible_row())
    with sb, fn:
        r = client.get(f"/public/safety-search/legal/{_CANONICAL_ID}")
    body = r.json()
    for field in ("object_type", "canonical_id", "title", "summary"):
        assert field in body, f"top-level field missing: {field}"
    detail = body["detail"]
    for field in ("law_name", "article_no", "article_sub_no", "article_title",
                  "article_text", "enforcement_date", "updated_at"):
        assert field in detail, f"detail field missing: {field}"


# ---------------------------------------------------------------------------
# L05 — no internal field leakage (id, law_id, record_kind, etc.)
# ---------------------------------------------------------------------------
def test_l05_no_internal_field_leakage(client):
    row = _eligible_row()
    row["internal_col"] = "must-not-appear"
    sb = patch.object(pss_mod, "_legal_supabase_dep", return_value=_MOCK_CLIENT)
    fn = patch.object(pss_mod, "get_current_legal_article_by_id", return_value=row)
    with sb, fn:
        r = client.get(f"/public/safety-search/legal/{_CANONICAL_ID}")
    body = r.json()
    for forbidden in ("id", "law_id", "law_version_id", "record_kind",
                      "is_deleted_in_version", "internal_col"):
        assert forbidden not in body, f"leaked in top-level: {forbidden}"
        assert forbidden not in body.get("detail", {}), f"leaked in detail: {forbidden}"


# ---------------------------------------------------------------------------
# L06 — title: law_name + 제{no}조 + (article_title) — full format
# ---------------------------------------------------------------------------
def test_l06_title_full_format(client):
    row = _eligible_row(law_name="산업안전보건법", article_no="38",
                        article_sub_no=None, article_title="안전조치")
    sb, fn = _patched(row)
    with sb, fn:
        r = client.get(f"/public/safety-search/legal/{_CANONICAL_ID}")
    assert r.json()["title"] == "산업안전보건법 제38조 (안전조치)"


# ---------------------------------------------------------------------------
# L07 — title: law_name + 제{no}조의{sub} (sub_no present)
# ---------------------------------------------------------------------------
def test_l07_title_with_sub_no(client):
    row = _eligible_row(law_name="산업안전보건법", article_no="38",
                        article_sub_no="2", article_title=None)
    sb, fn = _patched(row)
    with sb, fn:
        r = client.get(f"/public/safety-search/legal/{_CANONICAL_ID}")
    assert r.json()["title"] == "산업안전보건법 제38조의2"


# ---------------------------------------------------------------------------
# L08 — title: law_name + 제{no}조 only (no sub, no article_title)
# ---------------------------------------------------------------------------
def test_l08_title_no_sub_no_article_title(client):
    row = _eligible_row(law_name="산업안전보건법", article_no="38",
                        article_sub_no=None, article_title=None)
    sb, fn = _patched(row)
    with sb, fn:
        r = client.get(f"/public/safety-search/legal/{_CANONICAL_ID}")
    assert r.json()["title"] == "산업안전보건법 제38조"


# ---------------------------------------------------------------------------
# L09 — title fallback: no law_name → use article_title
# ---------------------------------------------------------------------------
def test_l09_title_fallback_no_law_name(client):
    row = _eligible_row(law_name="", article_no="38", article_title="안전조치")
    sb, fn = _patched(row)
    with sb, fn:
        r = client.get(f"/public/safety-search/legal/{_CANONICAL_ID}")
    assert r.json()["title"] == "안전조치"


# ---------------------------------------------------------------------------
# L10 — title fallback: neither law_name nor article_title → "law_article/{id}"
# ---------------------------------------------------------------------------
def test_l10_title_fallback_neither(client):
    row = _eligible_row(law_name="", article_no=None, article_title=None)
    sb, fn = _patched(row)
    with sb, fn:
        r = client.get(f"/public/safety-search/legal/{_CANONICAL_ID}")
    assert r.json()["title"] == f"law_article/{_CANONICAL_ID}"


# ---------------------------------------------------------------------------
# L11 — summary is always None for LEGAL
# ---------------------------------------------------------------------------
def test_l11_summary_is_none(client):
    sb, fn = _patched(_eligible_row())
    with sb, fn:
        r = client.get(f"/public/safety-search/legal/{_CANONICAL_ID}")
    assert r.json()["summary"] is None


# ---------------------------------------------------------------------------
# L12 — regression: main search + kosha routes not broken
# ---------------------------------------------------------------------------
def test_l12_regression_other_routes(client):
    # Missing 'q' → 422 confirms the main search route still routes correctly
    r = client.get("/public/safety-search")
    assert r.status_code == 422

    mock_result = {"items": [], "total": 0, "page": 1, "page_size": 10}
    with patch.object(pss_mod, "search_kosha_public", new=AsyncMock(return_value=mock_result)):
        r = client.get("/public/safety-search/kosha?q=test")
    assert r.status_code == 200
