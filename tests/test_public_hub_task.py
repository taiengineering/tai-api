"""T01-T07: work process hub list endpoint tests (DB-backed).
WO-SEO-HUB-TASK.

GET /public/safety-search/hub/task
DB-backed from csi_accident_snapshot_items.work_process.
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


def _mock_csi_tasks(raw_values: list[str]) -> MagicMock:
    """Mock get_supabase() so csi_accident_snapshot_items returns given work_process values."""
    result = MagicMock()
    result.data = [{"work_process": v} for v in raw_values]

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


# T01 — endpoint reachable, returns 200
def test_t01_endpoint_returns_200(client):
    sb = _mock_csi_tasks(["용접작업", "설치작업"])
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        r = client.get("/public/safety-search/hub/task")
    assert r.status_code == 200


# T02 — returns a non-empty list
def test_t02_returns_nonempty_list(client):
    sb = _mock_csi_tasks(["용접작업", "설치작업", "해체작업"])
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/task").json()
    assert isinstance(data, list)
    assert len(data) > 0


# T03 — each item has value and display_name
def test_t03_item_shape(client):
    sb = _mock_csi_tasks(["용접작업", "굴착작업"])
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/task").json()
    for item in data:
        assert set(item.keys()) == {"value", "display_name"}, f"unexpected keys: {item}"
        assert isinstance(item["value"], str) and item["value"]
        assert isinstance(item["display_name"], str) and item["display_name"]


# T04 — core task keywords present when DB contains them
def test_t04_core_tasks_present(client):
    core = ["설치작업", "해체작업", "운반작업", "조립작업", "타설작업", "용접작업", "굴착작업"]
    sb = _mock_csi_tasks(core)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/task").json()
    values = {item["value"] for item in data}
    missing = set(core) - values
    assert not missing, f"core tasks missing: {missing}"


# T05 — blocklist terms absent even when DB contains them
def test_t05_blocklist_terms_absent(client):
    blocklist = ["기타", "이동", "정리작업", "준비작업", "확인 및 점검작업", "물뿌리기 작업", "반출작업"]
    sb = _mock_csi_tasks(["용접작업"] + blocklist)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/task").json()
    values = {item["value"] for item in data}
    found = set(blocklist) & values
    assert not found, f"blocklist terms found: {found}"


# T06 — no duplicate values even when DB contains duplicates
def test_t06_no_duplicate_values(client):
    sb = _mock_csi_tasks(["용접작업", "용접작업", "설치작업", "설치작업"])
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/task").json()
    values = [item["value"] for item in data]
    assert len(values) == len(set(values)), "duplicate value found"


# T07 — raw compound forms normalized; raw forms absent
def test_t07_normalized_labels(client):
    raw = [
        "상차 및 하역작업",
        "보수 및 교체작업",
        "장약 및 발파작업",
        "항타 및 항발작업",
    ]
    sb = _mock_csi_tasks(raw)
    with patch.object(sb_mod, "get_supabase", return_value=sb):
        data = client.get("/public/safety-search/hub/task").json()
    values = {item["value"] for item in data}
    # raw compound forms must NOT appear
    assert "상차 및 하역작업" not in values
    assert "보수 및 교체작업" not in values
    assert "장약 및 발파작업" not in values
    assert "항타 및 항발작업" not in values
    # normalized forms must appear
    assert "하역작업" in values
    assert "보수작업" in values
    assert "발파작업" in values
    assert "항타작업" in values
