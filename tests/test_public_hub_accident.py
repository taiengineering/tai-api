"""A01-A05: accident type hub list endpoint tests.
WO-SEO-HUB-EXPAND Part B.

GET /public/safety-search/hub/accident
Static curated list — no DB / network. No mocking needed.
"""
from __future__ import annotations

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


# A01 — endpoint reachable, returns 200
def test_a01_endpoint_returns_200(client):
    r = client.get("/public/safety-search/hub/accident")
    assert r.status_code == 200


# A02 — returns a non-empty list
def test_a02_returns_nonempty_list(client):
    data = client.get("/public/safety-search/hub/accident").json()
    assert isinstance(data, list)
    assert len(data) > 0


# A03 — each item has value and display_name
def test_a03_item_shape(client):
    data = client.get("/public/safety-search/hub/accident").json()
    for item in data:
        assert set(item.keys()) == {"value", "display_name"}, f"unexpected keys: {item}"
        assert isinstance(item["value"], str) and item["value"]
        assert isinstance(item["display_name"], str) and item["display_name"]


# A04 — all 13 accident types present
def test_a04_all_13_accident_types_present(client):
    data = client.get("/public/safety-search/hub/accident").json()
    values = {item["value"] for item in data}
    expected = {
        "물체에 맞음", "끼임", "넘어짐", "부딪힘", "떨어짐",
        "절단·베임", "깔림·뒤집힘", "찔림", "감전",
        "화재", "폭발", "질식", "산소결핍",
    }
    missing = expected - values
    assert not missing, f"accident types missing: {missing}"


# A05 — no duplicate values
def test_a05_no_duplicate_values(client):
    data = client.get("/public/safety-search/hub/accident").json()
    values = [item["value"] for item in data]
    assert len(values) == len(set(values)), "duplicate value found"
