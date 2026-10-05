"""H3B1 — GET /internal/qa/runs/{run_id} tests.

H3B1-01  valid internal secret → 200
H3B1-02  missing secret → 403
H3B1-03  wrong secret → 403
H3B1-04  unknown run_id → 404 (svc.get_run raises 404)
H3B1-05  response data matches svc.get_run return contract
H3B1-06  DB mutation = 0
H3B1-07  GitHub dispatch = 0
H3B1-08  existing POST callback auth unchanged (403)
H3B1-09  existing targeted-dispatch auth unchanged (403)

Production API call = 0. All svc.get_run mocked.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers.internal_qa import router


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_run_data(run_id: str = "run-001") -> dict:
    return {
        "id":                run_id,
        "trigger_type":      "PR",
        "run_status":        "COMPLETED",
        "requested_by":      "targeted-qa",
        "github_run_id":     12345,
        "github_run_attempt": 1,
        "head_sha":          "abc" * 14,
        "branch_name":       "feat/test-branch",
        "targets": [
            {
                "qa_item_id":     "item-1",
                "ordinal":        1,
                "scenario_id":    "P0-AAA-001",
                "effective_status": "PASS",
            }
        ],
        "results": [
            {
                "qa_item_id":    "item-1",
                "result_status": "PASS",
                "attempt":       1,
            }
        ],
    }


def _make_client(monkeypatch, run_data=None, run_id="run-001", not_found=False):
    monkeypatch.setenv("INTERNAL_API_SECRET", "correct-secret")

    if not_found:
        monkeypatch.setattr(
            "routers.internal_qa.svc.get_run",
            lambda sb, rid: (_ for _ in ()).throw(HTTPException(404, "qa_run not found")),
        )
    else:
        data = run_data or _make_run_data(run_id)
        monkeypatch.setattr("routers.internal_qa.svc.get_run", lambda sb, rid: data)

    monkeypatch.setattr("routers.internal_qa.get_supabase", lambda: MagicMock())

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


# ── H3B1-01: valid secret → 200 ───────────────────────────────────────────────

def test_H3B1_01_valid_secret_200(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get(
        "/internal/qa/runs/run-001",
        headers={"X-Internal-Secret": "correct-secret"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


# ── H3B1-02: missing secret → 403 ─────────────────────────────────────────────

def test_H3B1_02_missing_secret_403(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get("/internal/qa/runs/run-001")
    assert resp.status_code == 403


# ── H3B1-03: wrong secret → 403 ───────────────────────────────────────────────

def test_H3B1_03_wrong_secret_403(monkeypatch):
    client = _make_client(monkeypatch)
    resp = client.get(
        "/internal/qa/runs/run-001",
        headers={"X-Internal-Secret": "wrong-secret"},
    )
    assert resp.status_code == 403


# ── H3B1-04: unknown run_id → 404 ─────────────────────────────────────────────

def test_H3B1_04_unknown_run_id_404(monkeypatch):
    client = _make_client(monkeypatch, not_found=True)
    resp = client.get(
        "/internal/qa/runs/nonexistent-run",
        headers={"X-Internal-Secret": "correct-secret"},
    )
    assert resp.status_code == 404


# ── H3B1-05: response data matches svc.get_run contract ───────────────────────

def test_H3B1_05_response_data_contract(monkeypatch):
    run_data = _make_run_data("run-abc")
    client = _make_client(monkeypatch, run_data=run_data)
    resp = client.get(
        "/internal/qa/runs/run-abc",
        headers={"X-Internal-Secret": "correct-secret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    data = body["data"]
    # Top-level run fields
    assert data["id"] == "run-abc"
    assert data["trigger_type"] == "PR"
    assert data["run_status"] == "COMPLETED"
    assert data["requested_by"] == "targeted-qa"
    # Targets and results present
    assert isinstance(data["targets"], list)
    assert len(data["targets"]) == 1
    assert data["targets"][0]["scenario_id"] == "P0-AAA-001"
    assert data["targets"][0]["effective_status"] == "PASS"
    assert isinstance(data["results"], list)
    assert len(data["results"]) == 1


# ── H3B1-06: DB mutation = 0 ──────────────────────────────────────────────────

def test_H3B1_06_db_mutation_zero(monkeypatch):
    insert_calls = []
    update_calls = []
    delete_calls = []

    class _FakeSB:
        def table(self, name):
            t = MagicMock()
            t.select.return_value = t
            t.eq.return_value = t
            t.in_.return_value = t
            t.limit.return_value = t
            t.order.return_value = t
            t.execute.return_value = MagicMock(data=[])

            def _insert(rows, **k):
                insert_calls.append(rows)
                return t
            def _update(data, **k):
                update_calls.append(data)
                return t
            def _delete():
                delete_calls.append(name)
                return t

            t.insert = _insert
            t.update = _update
            t.delete = _delete
            return t

    run_data = _make_run_data()
    monkeypatch.setenv("INTERNAL_API_SECRET", "correct-secret")
    monkeypatch.setattr("routers.internal_qa.svc.get_run", lambda sb, rid: run_data)
    monkeypatch.setattr("routers.internal_qa.get_supabase", lambda: _FakeSB())

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    client.get(
        "/internal/qa/runs/run-001",
        headers={"X-Internal-Secret": "correct-secret"},
    )

    assert insert_calls == [], f"INSERT called: {insert_calls}"
    assert update_calls == [], f"UPDATE called: {update_calls}"
    assert delete_calls == [], f"DELETE called: {delete_calls}"


# ── H3B1-07: GitHub dispatch = 0 ──────────────────────────────────────────────

def test_H3B1_07_github_dispatch_zero(monkeypatch):
    dispatch_calls = []

    async def _fake_dispatch(*a, **k):
        dispatch_calls.append((a, k))

    monkeypatch.setattr(
        "routers.internal_qa.svc.get_run",
        lambda sb, rid: _make_run_data(),
    )
    monkeypatch.setattr("routers.internal_qa.get_supabase", lambda: MagicMock())
    monkeypatch.setenv("INTERNAL_API_SECRET", "correct-secret")

    # Patch dispatch_qa_run if imported
    try:
        import services.github_dispatch_svc as gh_svc
        monkeypatch.setattr(gh_svc, "dispatch_qa_run", _fake_dispatch)
    except (ImportError, AttributeError):
        pass

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    client.get(
        "/internal/qa/runs/run-001",
        headers={"X-Internal-Secret": "correct-secret"},
    )
    assert dispatch_calls == [], f"dispatch called: {dispatch_calls}"


# ── H3B1-08: existing POST callback auth still works (403 on missing secret) ──

def test_H3B1_08_post_callback_auth_unchanged(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "correct-secret")
    monkeypatch.setattr("routers.internal_qa.get_supabase", lambda: MagicMock())

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    # POST without secret should still be 403
    resp = client.post("/internal/qa/runs/run-1/results", json={"results": []})
    assert resp.status_code == 403


# ── H3B1-09: existing targeted-dispatch auth unchanged (403) ──────────────────

def test_H3B1_09_targeted_dispatch_auth_unchanged(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "correct-secret")
    monkeypatch.setattr("routers.internal_qa.get_supabase", lambda: MagicMock())

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/internal/qa/targeted-dispatch",
        json={"scenario_ids": ["P0-AAA-001"]},
    )
    assert resp.status_code == 403
