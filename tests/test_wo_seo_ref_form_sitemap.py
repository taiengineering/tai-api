"""WO-SEO-REF-FORM-SITEMAP-001: /sitemap/reference-forms endpoint tests.

SM-T01~SM-T15: cursor pagination, rights gate, field contract,
multi-chunk pagination, rights error → 503, latest-updated-at endpoint.
No real DB / network. _ref_form_sitemap_dep patched throughout.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_safety_search as pss_mod

UUID_A = "aaaaaaaa-0000-0000-0000-000000000001"
UUID_B = "aaaaaaaa-0000-0000-0000-000000000002"
UUID_C = "aaaaaaaa-0000-0000-0000-000000000003"


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pss_mod.router)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app())


def _row(form_id: str, slug: str, updated_at: str = "2026-10-11T00:00:00+09:00") -> dict:
    return {"id": form_id, "canonical_slug": slug, "updated_at": updated_at}


def _make_sb(pages: list[list[dict]], cleared_per_call: list[list[str]] | None = None) -> MagicMock:
    """Multi-page mock for the reference-forms sitemap endpoint.

    pages: list of batches, one per execute() call on reference_form_public_view.
    cleared_per_call: per-batch cleared id lists (defaults to all ids in each batch).
    """
    page_iter = iter(pages)
    sources_iter: "list[list[str]] | None" = None
    if cleared_per_call is not None:
        sources_iter = list(cleared_per_call)
    sources_call_count = [0]

    def _table(name: str):
        mock_q = MagicMock()
        for method in ("select", "eq", "order", "limit", "gt", "in_"):
            getattr(mock_q, method).return_value = mock_q

        if name == "reference_form_public_view":
            def _execute():
                batch = next(page_iter, [])
                result = MagicMock()
                result.data = batch
                return result
            mock_q.execute.side_effect = _execute
        elif name == "reference_form_sources":
            def _sources_execute():
                idx = sources_call_count[0]
                if sources_iter is not None and idx < len(sources_iter):
                    cleared = sources_iter[idx]
                else:
                    # default: take all form_ids from the current view call as cleared
                    cleared = []
                sources_call_count[0] += 1
                src_data = [{"form_id": fid, "rights_status": "CLEARED"} for fid in cleared]
                result = MagicMock()
                result.data = src_data
                return result
            mock_q.execute.side_effect = _sources_execute
        else:
            result = MagicMock()
            result.data = []
            mock_q.execute.return_value = result

        tbl = MagicMock()
        tbl.select.return_value = mock_q
        return tbl

    sb = MagicMock()
    sb.table.side_effect = _table
    return sb


def _sb_single(rows: list[dict], cleared_ids: list[str] | None = None) -> MagicMock:
    """Single-page convenience wrapper."""
    if cleared_ids is None:
        cleared_ids = [str(r.get("id", "")) for r in rows if r.get("id")]
    return _make_sb([rows], [cleared_ids])


# ---------------------------------------------------------------------------
# SM-T01 — eligible rows returned as {id, slug, updated_at}
# ---------------------------------------------------------------------------
def test_t01_eligible_rows_returned(client):
    rows = [_row(UUID_A, "ref-c001"), _row(UUID_B, "ref-c002")]
    sb = _sb_single(rows)
    with patch.object(pss_mod, "_ref_form_sitemap_dep", return_value=sb):
        resp = client.get("/public/safety-search/sitemap/reference-forms")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0] == {"id": UUID_A, "slug": "ref-c001", "updated_at": "2026-10-11T00:00:00+09:00"}
    assert data[1] == {"id": UUID_B, "slug": "ref-c002", "updated_at": "2026-10-11T00:00:00+09:00"}


# ---------------------------------------------------------------------------
# SM-T02 — rights filter: non-CLEARED form excluded
# ---------------------------------------------------------------------------
def test_t02_non_cleared_excluded(client):
    rows = [_row(UUID_A, "ref-c001"), _row(UUID_B, "ref-c002")]
    sb = _sb_single(rows, cleared_ids=[UUID_A])
    with patch.object(pss_mod, "_ref_form_sitemap_dep", return_value=sb):
        resp = client.get("/public/safety-search/sitemap/reference-forms")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == UUID_A


# ---------------------------------------------------------------------------
# SM-T03 — empty view → empty response
# ---------------------------------------------------------------------------
def test_t03_empty_view_returns_empty(client):
    sb = _sb_single([])
    with patch.object(pss_mod, "_ref_form_sitemap_dep", return_value=sb):
        resp = client.get("/public/safety-search/sitemap/reference-forms")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# SM-T04 — response contains only id, slug, updated_at
# ---------------------------------------------------------------------------
def test_t04_response_field_contract(client):
    rows = [_row(UUID_A, "ref-c005", "2026-10-01T00:00:00+00:00")]
    sb = _sb_single(rows)
    with patch.object(pss_mod, "_ref_form_sitemap_dep", return_value=sb):
        resp = client.get("/public/safety-search/sitemap/reference-forms")
    assert resp.status_code == 200
    item = resp.json()[0]
    assert set(item.keys()) == {"id", "slug", "updated_at"}


# ---------------------------------------------------------------------------
# SM-T05 — after_id cursor forwarded to query
# ---------------------------------------------------------------------------
def test_t05_after_id_cursor_applied(client):
    called_gt = []

    def _table(name: str):
        mock_q = MagicMock()
        for method in ("select", "eq", "order", "limit", "in_"):
            getattr(mock_q, method).return_value = mock_q

        def _gt(field, val):
            called_gt.append((field, val))
            return mock_q

        mock_q.gt.side_effect = _gt
        result = MagicMock()
        result.data = []
        mock_q.execute.return_value = result
        tbl = MagicMock()
        tbl.select.return_value = mock_q
        return tbl

    sb = MagicMock()
    sb.table.side_effect = _table

    with patch.object(pss_mod, "_ref_form_sitemap_dep", return_value=sb):
        client.get(f"/public/safety-search/sitemap/reference-forms?after_id={UUID_A}")

    assert ("id", UUID_A) in called_gt


# ---------------------------------------------------------------------------
# SM-T06 — limit default = 1000
# ---------------------------------------------------------------------------
def test_t06_limit_default(client):
    call_args = []

    def _table(name: str):
        mock_q = MagicMock()

        def _limit(n):
            call_args.append(n)
            return mock_q

        mock_q.limit.side_effect = _limit
        for method in ("select", "eq", "order", "gt", "in_"):
            getattr(mock_q, method).return_value = mock_q
        result = MagicMock()
        result.data = []
        mock_q.execute.return_value = result
        tbl = MagicMock()
        tbl.select.return_value = mock_q
        return tbl

    sb = MagicMock()
    sb.table.side_effect = _table

    with patch.object(pss_mod, "_ref_form_sitemap_dep", return_value=sb):
        client.get("/public/safety-search/sitemap/reference-forms")

    assert 1000 in call_args


# ---------------------------------------------------------------------------
# SM-T07 — limit=2001 rejected
# ---------------------------------------------------------------------------
def test_t07_limit_exceeds_max_rejected(client):
    sb = _sb_single([])
    with patch.object(pss_mod, "_ref_form_sitemap_dep", return_value=sb):
        resp = client.get("/public/safety-search/sitemap/reference-forms?limit=2001")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# SM-T08 — rights DB error → 503 (NOT silent empty)
# ---------------------------------------------------------------------------
def test_t08_rights_query_error_returns_503(client):
    rows = [_row(UUID_A, "ref-c001")]

    def _table(name: str):
        mock_q = MagicMock()
        for method in ("select", "eq", "order", "limit", "gt", "in_"):
            getattr(mock_q, method).return_value = mock_q

        if name == "reference_form_public_view":
            result = MagicMock()
            result.data = rows
            mock_q.execute.return_value = result
        elif name == "reference_form_sources":
            mock_q.execute.side_effect = Exception("DB error")

        tbl = MagicMock()
        tbl.select.return_value = mock_q
        return tbl

    sb = MagicMock()
    sb.table.side_effect = _table

    with patch.object(pss_mod, "_ref_form_sitemap_dep", return_value=sb):
        resp = client.get("/public/safety-search/sitemap/reference-forms")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# SM-T09 — cleared_form_ids: all CLEARED → included
# ---------------------------------------------------------------------------
def test_t09_cleared_form_ids_function():
    from services.shared_search.adapters.reference_form import cleared_form_ids
    mock_result = MagicMock()
    mock_result.data = [
        {"form_id": UUID_A, "rights_status": "CLEARED"},
        {"form_id": UUID_B, "rights_status": "CLEARED"},
    ]
    mock_q = MagicMock()
    for m in ("select", "in_", "eq"):
        getattr(mock_q, m).return_value = mock_q
    mock_q.execute.return_value = mock_result
    tbl = MagicMock()
    tbl.select.return_value = mock_q
    cm = MagicMock()
    cm.table.return_value = tbl

    result = cleared_form_ids(cm, [UUID_A, UUID_B])
    assert UUID_A in result
    assert UUID_B in result


# ---------------------------------------------------------------------------
# SM-T10 — cleared_form_ids: mixed → only CLEARED
# ---------------------------------------------------------------------------
def test_t10_cleared_form_ids_partial():
    from services.shared_search.adapters.reference_form import cleared_form_ids
    mock_result = MagicMock()
    mock_result.data = [
        {"form_id": UUID_A, "rights_status": "CLEARED"},
        {"form_id": UUID_B, "rights_status": "BLOCKED"},
    ]
    mock_q = MagicMock()
    for m in ("select", "in_", "eq"):
        getattr(mock_q, m).return_value = mock_q
    mock_q.execute.return_value = mock_result
    tbl = MagicMock()
    tbl.select.return_value = mock_q
    cm = MagicMock()
    cm.table.return_value = tbl

    result = cleared_form_ids(cm, [UUID_A, UUID_B])
    assert UUID_A in result
    assert UUID_B not in result


# ---------------------------------------------------------------------------
# SM-T11 — P2: multi-chunk — blocked batch followed by eligible on next page
# ---------------------------------------------------------------------------
def test_t11_pagination_continues_past_blocked_batch(client):
    """Page 1: 2 rows, both blocked. Page 2: 1 row, CLEARED. Must return the page-2 row."""
    page1 = [_row(UUID_A, "ref-c001"), _row(UUID_B, "ref-c002")]
    page2 = [_row(UUID_C, "ref-c003")]
    sb = _make_sb(
        pages=[page1, page2],
        cleared_per_call=[[], [UUID_C]],  # page1 all blocked, page2 all CLEARED
    )
    with patch.object(pss_mod, "_ref_form_sitemap_dep", return_value=sb):
        resp = client.get("/public/safety-search/sitemap/reference-forms?limit=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == UUID_C


# ---------------------------------------------------------------------------
# SM-T12 — P2: source exhausted on partial page → no premature termination
# ---------------------------------------------------------------------------
def test_t12_partial_page_signals_source_exhausted(client):
    """Page 1: 2 rows (all CLEARED). Since len(2) < limit(1000), loop ends. Return 2."""
    rows = [_row(UUID_A, "ref-c001"), _row(UUID_B, "ref-c002")]
    sb = _sb_single(rows)
    with patch.object(pss_mod, "_ref_form_sitemap_dep", return_value=sb):
        resp = client.get("/public/safety-search/sitemap/reference-forms")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# SM-T13 — P3: cleared_form_ids_or_raise propagates error
# ---------------------------------------------------------------------------
def test_t13_cleared_form_ids_or_raise_on_error():
    from services.shared_search.adapters.reference_form import cleared_form_ids_or_raise
    mock_q = MagicMock()
    for m in ("select", "in_", "eq"):
        getattr(mock_q, m).return_value = mock_q
    mock_q.execute.side_effect = Exception("DB error")
    tbl = MagicMock()
    tbl.select.return_value = mock_q
    cm = MagicMock()
    cm.table.return_value = tbl

    with pytest.raises(RuntimeError):
        cleared_form_ids_or_raise(cm, [UUID_A])


# ---------------------------------------------------------------------------
# SM-T14 — P3: cleared_form_ids_or_raise returns frozenset on success
# ---------------------------------------------------------------------------
def test_t14_cleared_form_ids_or_raise_on_success():
    from services.shared_search.adapters.reference_form import cleared_form_ids_or_raise
    mock_result = MagicMock()
    mock_result.data = [{"form_id": UUID_A, "rights_status": "CLEARED"}]
    mock_q = MagicMock()
    for m in ("select", "in_", "eq"):
        getattr(mock_q, m).return_value = mock_q
    mock_q.execute.return_value = mock_result
    tbl = MagicMock()
    tbl.select.return_value = mock_q
    cm = MagicMock()
    cm.table.return_value = tbl

    result = cleared_form_ids_or_raise(cm, [UUID_A])
    assert UUID_A in result


# ---------------------------------------------------------------------------
# SM-T15 — P4: /sitemap/reference-forms/latest-updated-at returns updated_at
# ---------------------------------------------------------------------------
def test_t15_latest_updated_at_endpoint(client):
    rows = [{"updated_at": "2026-10-11T15:25:58.613483+09:00"}]

    def _table(name: str):
        mock_q = MagicMock()
        for method in ("select", "order", "limit"):
            getattr(mock_q, method).return_value = mock_q
        result = MagicMock()
        result.data = rows if name == "reference_form_public_view" else []
        mock_q.execute.return_value = result
        tbl = MagicMock()
        tbl.select.return_value = mock_q
        return tbl

    sb = MagicMock()
    sb.table.side_effect = _table

    with patch.object(pss_mod, "_ref_form_sitemap_dep", return_value=sb):
        resp = client.get("/public/safety-search/sitemap/reference-forms/latest-updated-at")
    assert resp.status_code == 200
    data = resp.json()
    assert "updated_at" in data
    assert data["updated_at"] == "2026-10-11T15:25:58.613483+09:00"
