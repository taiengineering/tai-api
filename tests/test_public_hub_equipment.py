"""E01-E07: equipment hub list endpoint tests (DB-backed).
WO-SEO-HUB-EXPAND Part A.

GET /public/safety-search/hub/equipment
DB-backed from csi_accident_snapshot_items.object_minor.
Blocklist applied. Labels normalized. get_supabase mocked throughout.
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


def _mock_csi_items(raw_values: list[str]) -> MagicMock:
    """Mock get_supabase() so csi_accident_snapshot_items returns given object_minor values."""
    result = MagicMock()
    result.data = [{"object_minor": v} for v in raw_values]

    q = MagicMock()
    q.select.return_value = q
    q.not_ = MagicMock()
    q.not_.is_.return_value = q
    q.range.return_value = q
    q.execute.return_value = result

    tbl = MagicMock()
    tbl.select.return_value = q

    sb = MagicMock()
    sb.table.return_value = tbl
    return sb


# E01 — endpoint reachable, returns 200
def test_e01_endpoint_returns_200(client):
    sb = _mock_csi_items(["비계", "사다리"])
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        r = client.get("/public/safety-search/hub/equipment")
    assert r.status_code == 200


# E02 — returns a non-empty list
def test_e02_returns_nonempty_list(client):
    sb = _mock_csi_items(["비계", "사다리", "지게차"])
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/equipment").json()
    assert isinstance(data, list)
    assert len(data) > 0


# E03 — each item has value and display_name
def test_e03_item_shape(client):
    sb = _mock_csi_items(["비계", "사다리"])
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/equipment").json()
    for item in data:
        assert set(item.keys()) == {"value", "display_name"}, f"unexpected keys: {item}"
        assert isinstance(item["value"], str) and item["value"]
        assert isinstance(item["display_name"], str) and item["display_name"]


# E04 — pilot 10 keywords all present when DB contains them
def test_e04_pilot_10_keywords_present(client):
    pilot = ["비계", "거푸집", "굴착기", "사다리", "지게차", "타워크레인", "고소작업대", "작업발판", "시스템동바리", "배관"]
    sb = _mock_csi_items(pilot)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/equipment").json()
    values = {item["value"] for item in data}
    missing = set(pilot) - values
    assert not missing, f"pilot keywords missing: {missing}"


# E05 — blocklist terms absent even when DB contains them
def test_e05_blocklist_terms_absent(client):
    blocklist = ["기타", "자재", "공구류", "건물", "질병", "차량", "지반", "지지대", "벽체",
                 "핀", "비산물", "부석", "건설폐기물", "지하매설물"]
    sb = _mock_csi_items(["비계"] + blocklist)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/equipment").json()
    values = {item["value"] for item in data}
    found = set(blocklist) & values
    assert not found, f"blocklist terms found in hub list: {found}"


# E06 — no duplicate values even when DB contains duplicates
def test_e06_no_duplicate_values(client):
    sb = _mock_csi_items(["비계", "비계", "사다리", "사다리", "사다리"])
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/equipment").json()
    values = [item["value"] for item in data]
    assert len(values) == len(set(values)), "duplicate value found"


# E07 — raw parenthetical forms normalized; raw forms absent
def test_e07_normalized_labels(client):
    raw = [
        "기중기(이동식크레인 등)",
        "고소작업차(고소작업대 등)",
        "특수거푸집(갱폼 등)",
        "항타 및 항발기",
    ]
    sb = _mock_csi_items(raw)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/equipment").json()
    values = {item["value"] for item in data}
    # raw forms must NOT appear
    assert "기중기(이동식크레인 등)" not in values
    assert "고소작업차(고소작업대 등)" not in values
    assert "특수거푸집(갱폼 등)" not in values
    assert "항타 및 항발기" not in values
    # normalized forms must appear
    assert "이동식크레인" in values
    assert "고소작업대" in values
    assert "갱폼" in values
    assert "항타기" in values
