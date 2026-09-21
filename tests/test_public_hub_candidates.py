"""H01-H10: hub-candidates aggregation endpoint tests.
WO-SEO-HUB-FROM-OPENSEARCH.

GET /public/safety-search/hub-candidates
Aggregates keyword_central_extracted by central_keyword × page_type.
No real DB. db.supabase_client.get_supabase mocked throughout.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_safety_search as pss_mod
import db.supabase_client as sb_mod


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pss_mod.router)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app())


def _mock_kce(rows: list[dict]) -> MagicMock:
    """Mock get_supabase() so keyword_central_extracted returns given rows."""
    result = MagicMock()
    result.data = rows
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.not_ = MagicMock()
    q.not_.is_.return_value = q
    q.execute.return_value = result

    tbl = MagicMock()
    tbl.select.return_value = q

    sb = MagicMock()
    sb.table.return_value = tbl
    return sb


# H01 — empty table → empty list
def test_h01_empty_table_returns_empty_list(client):
    sb = _mock_kce([])
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        r = client.get("/public/safety-search/hub-candidates")
    assert r.status_code == 200
    assert r.json() == []


# H02 — happy path: keyword spanning 2 domains returned
def test_h02_keyword_spanning_2_domains_returned(client):
    rows = [
        {"page_type": "accident_csi", "central_keyword": "지게차"},
        {"page_type": "accident_csi", "central_keyword": "지게차"},
        {"page_type": "accident_csi", "central_keyword": "지게차"},
        {"page_type": "guide", "central_keyword": "지게차"},
        {"page_type": "guide", "central_keyword": "지게차"},
    ]
    sb = _mock_kce(rows)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        r = client.get("/public/safety-search/hub-candidates?min_domain_span=2&min_docs=2")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    item = data[0]
    assert item["keyword"] == "지게차"
    assert item["total_docs"] == 5
    assert item["domain_span"] == 2
    assert sorted(item["domains"]) == ["accident_csi", "guide"]
    assert item["per_domain_counts"]["accident_csi"] == 3
    assert item["per_domain_counts"]["guide"] == 2


# H03 — keyword with only 1 domain excluded when min_domain_span=2
def test_h03_single_domain_keyword_excluded(client):
    rows = [
        {"page_type": "accident_csi", "central_keyword": "비계"},
        {"page_type": "accident_csi", "central_keyword": "비계"},
        {"page_type": "accident_csi", "central_keyword": "비계"},
        {"page_type": "accident_csi", "central_keyword": "비계"},
        {"page_type": "accident_csi", "central_keyword": "비계"},
    ]
    sb = _mock_kce(rows)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        r = client.get("/public/safety-search/hub-candidates?min_domain_span=2&min_docs=1")
    assert r.status_code == 200
    assert r.json() == []


# H04 — keyword below min_docs excluded
def test_h04_below_min_docs_excluded(client):
    rows = [
        {"page_type": "accident_csi", "central_keyword": "크레인"},
        {"page_type": "guide", "central_keyword": "크레인"},
    ]
    sb = _mock_kce(rows)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        r = client.get("/public/safety-search/hub-candidates?min_domain_span=2&min_docs=10")
    assert r.status_code == 200
    assert r.json() == []


# H05 — sorted by domain_span desc, then total_docs desc
def test_h05_sorted_by_domain_span_desc_then_total_docs(client):
    rows = [
        # 크레인: 3 domains, 3 docs
        {"page_type": "accident_csi", "central_keyword": "크레인"},
        {"page_type": "guide", "central_keyword": "크레인"},
        {"page_type": "knowledge", "central_keyword": "크레인"},
        # 지게차: 2 domains, 10 docs
        *[{"page_type": "accident_csi", "central_keyword": "지게차"} for _ in range(8)],
        {"page_type": "guide", "central_keyword": "지게차"},
        {"page_type": "guide", "central_keyword": "지게차"},
        # 추락: 2 domains, 5 docs
        *[{"page_type": "accident_csi", "central_keyword": "추락"} for _ in range(4)],
        {"page_type": "guide", "central_keyword": "추락"},
    ]
    sb = _mock_kce(rows)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        r = client.get("/public/safety-search/hub-candidates?min_domain_span=2&min_docs=1")
    data = r.json()
    assert len(data) == 3
    assert data[0]["keyword"] == "크레인"   # domain_span=3
    assert data[1]["keyword"] == "지게차"   # domain_span=2, total=10
    assert data[2]["keyword"] == "추락"     # domain_span=2, total=5


# H06 — null central_keyword rows skipped
def test_h06_null_central_keyword_skipped(client):
    rows = [
        {"page_type": "accident_csi", "central_keyword": None},
        {"page_type": "guide", "central_keyword": None},
        {"page_type": "accident_csi", "central_keyword": "사다리"},
        {"page_type": "guide", "central_keyword": "사다리"},
    ]
    sb = _mock_kce(rows)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        r = client.get("/public/safety-search/hub-candidates?min_domain_span=2&min_docs=1")
    data = r.json()
    assert len(data) == 1
    assert data[0]["keyword"] == "사다리"


# H07 — empty page_type rows skipped
def test_h07_empty_page_type_skipped(client):
    rows = [
        {"page_type": "", "central_keyword": "굴착기"},
        {"page_type": None, "central_keyword": "굴착기"},
        {"page_type": "accident_csi", "central_keyword": "굴착기"},
        {"page_type": "guide", "central_keyword": "굴착기"},
    ]
    sb = _mock_kce(rows)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        r = client.get("/public/safety-search/hub-candidates?min_domain_span=2&min_docs=1")
    data = r.json()
    assert len(data) == 1
    # Only 2 valid rows (accident_csi + guide), both counted
    assert data[0]["total_docs"] == 2


# H08 — limit param respected
def test_h08_limit_param_respected(client):
    # 10 keywords each spanning 2 domains
    rows = []
    for i in range(10):
        kw = f"키워드{i}"
        rows.append({"page_type": "accident_csi", "central_keyword": kw})
        rows.append({"page_type": "guide", "central_keyword": kw})
    sb = _mock_kce(rows)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        r = client.get("/public/safety-search/hub-candidates?min_domain_span=2&min_docs=1&limit=3")
    assert r.status_code == 200
    assert len(r.json()) == 3


# H09 — limit > 500 rejected (422)
def test_h09_limit_above_500_rejected(client):
    r = client.get("/public/safety-search/hub-candidates?limit=999")
    assert r.status_code == 422


# H10 — response shape has all required fields
def test_h10_response_shape(client):
    rows = [
        {"page_type": "accident_csi", "central_keyword": "용접"},
        {"page_type": "guide", "central_keyword": "용접"},
        {"page_type": "knowledge", "central_keyword": "용접"},
    ]
    sb = _mock_kce(rows)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        r = client.get("/public/safety-search/hub-candidates?min_domain_span=1&min_docs=1")
    data = r.json()
    assert len(data) == 1
    item = data[0]
    assert set(item.keys()) == {"keyword", "total_docs", "domain_span", "domains", "per_domain_counts"}
    assert isinstance(item["keyword"], str)
    assert isinstance(item["total_docs"], int)
    assert isinstance(item["domain_span"], int)
    assert isinstance(item["domains"], list)
    assert isinstance(item["per_domain_counts"], dict)
