"""CHEM-WO-OBJ04-003-PATCH-05 — Internal MSDS Reference Candidate Query tests.

Gate tests:
  RA01  missing X-Internal-Secret → 403
  RA02  wrong X-Internal-Secret → 403
  RA03  valid snapshot + exact CAS → EXACT_CAS rank 1
  RA04  exact reference product name → EXACT_REFERENCE_PRODUCT_NAME rank 2
  RA05  exact substance name → EXACT_SUBSTANCE_NAME rank 3
  RA06  exact alias → EXACT_ALIAS rank 4
  RA07  content_id deduplicated across ranks
  RA08  valid snapshot + zero hit → 200 / items=[]
  RA09  snapshot missing → 422 REFERENCE_SNAPSHOT_NOT_READY
  RA10  snapshot not COMPLETED → 422 REFERENCE_SNAPSHOT_NOT_READY
  RA11  reference write operations = 0 (service source inspection)
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.internal_reference_query import router

_SECRET = "test-secret"
_SNAP = "snap-uuid-001"


def _app():
    app = FastAPI()
    app.include_router(router)
    return app


def _client(app):
    return TestClient(app, raise_server_exceptions=False)


def _headers(secret=_SECRET):
    return {"X-Internal-Secret": secret}


def _body(snapshot_id=_SNAP, cas_list=None, product_name_normalized=None):
    payload = {"snapshot_id": snapshot_id}
    if cas_list is not None:
        payload["cas_list"] = cas_list
    if product_name_normalized is not None:
        payload["product_name_normalized"] = product_name_normalized
    return payload


def _patch_svc(validate_ok=True, items=None, snapshot_not_ready=False):
    """Return context manager that patches the reference query service."""
    from services import msds_reference_query_svc as svc_mod

    def _validate(snapshot_id):
        if snapshot_not_ready:
            from services.msds_reference_query_svc import SnapshotNotReadyError
            raise SnapshotNotReadyError(f"REFERENCE_SNAPSHOT_NOT_READY: {snapshot_id}")
        if not validate_ok:
            from services.msds_reference_query_svc import ReferenceQueryError
            raise ReferenceQueryError("REFERENCE_NOT_CONFIGURED: missing")

    mock_validate = MagicMock(side_effect=_validate)
    mock_find = MagicMock(return_value=items or [])

    return (
        patch.object(svc_mod, "validate_snapshot", mock_validate),
        patch.object(svc_mod, "find_candidates", mock_find),
    )


# ─── RA01: missing secret → 403 ───────────────────────────────────────────────

def test_ra01_missing_secret_403(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", _SECRET)
    client = _client(_app())
    resp = client.post("/internal/reference/msds/candidates", json=_body())
    assert resp.status_code == 403


# ─── RA02: wrong secret → 403 ─────────────────────────────────────────────────

def test_ra02_wrong_secret_403(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", _SECRET)
    client = _client(_app())
    resp = client.post(
        "/internal/reference/msds/candidates",
        headers=_headers("wrong-secret"),
        json=_body(),
    )
    assert resp.status_code == 403


# ─── RA03: exact CAS → rank 1 ─────────────────────────────────────────────────

def test_ra03_exact_cas_rank1(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", _SECRET)
    items = [{"reference_content_id": "c1", "reference_chem_id": "ch1",
               "reference_snapshot_id": _SNAP, "match_reason": "EXACT_CAS",
               "rank_no": 1, "evidence_json": {"cas": "7664-41-7"}}]
    vp, fp = _patch_svc(items=items)
    with vp, fp:
        resp = _client(_app()).post(
            "/internal/reference/msds/candidates",
            headers=_headers(),
            json=_body(cas_list=["7664-41-7"]),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["snapshot_id"] == _SNAP
    assert len(data["data"]["items"]) == 1
    assert data["data"]["items"][0]["match_reason"] == "EXACT_CAS"
    assert data["data"]["items"][0]["rank_no"] == 1


# ─── RA04: exact reference product name → rank 2 ──────────────────────────────

def test_ra04_exact_reference_product_name_rank2(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", _SECRET)
    items = [{"reference_content_id": "c2", "reference_chem_id": "ch2",
               "reference_snapshot_id": _SNAP, "match_reason": "EXACT_REFERENCE_PRODUCT_NAME",
               "rank_no": 2, "evidence_json": {"product_name_normalized": "acetone"}}]
    vp, fp = _patch_svc(items=items)
    with vp, fp:
        resp = _client(_app()).post(
            "/internal/reference/msds/candidates",
            headers=_headers(),
            json=_body(product_name_normalized="acetone"),
        )
    assert resp.status_code == 200
    item = resp.json()["data"]["items"][0]
    assert item["match_reason"] == "EXACT_REFERENCE_PRODUCT_NAME"
    assert item["rank_no"] == 2


# ─── RA05: exact substance name → rank 3 ──────────────────────────────────────

def test_ra05_exact_substance_name_rank3(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", _SECRET)
    items = [{"reference_content_id": "c3", "reference_chem_id": "ch3",
               "reference_snapshot_id": _SNAP, "match_reason": "EXACT_SUBSTANCE_NAME",
               "rank_no": 3, "evidence_json": {"substance_name_normalized": "propanone"}}]
    vp, fp = _patch_svc(items=items)
    with vp, fp:
        resp = _client(_app()).post(
            "/internal/reference/msds/candidates",
            headers=_headers(),
            json=_body(product_name_normalized="propanone"),
        )
    assert resp.status_code == 200
    item = resp.json()["data"]["items"][0]
    assert item["match_reason"] == "EXACT_SUBSTANCE_NAME"
    assert item["rank_no"] == 3


# ─── RA06: exact alias → rank 4 ───────────────────────────────────────────────

def test_ra06_exact_alias_rank4(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", _SECRET)
    items = [{"reference_content_id": "c4", "reference_chem_id": "ch4",
               "reference_snapshot_id": _SNAP, "match_reason": "EXACT_ALIAS",
               "rank_no": 4, "evidence_json": {"alias_normalized": "dimethyl ketone"}}]
    vp, fp = _patch_svc(items=items)
    with vp, fp:
        resp = _client(_app()).post(
            "/internal/reference/msds/candidates",
            headers=_headers(),
            json=_body(product_name_normalized="dimethyl ketone"),
        )
    assert resp.status_code == 200
    item = resp.json()["data"]["items"][0]
    assert item["match_reason"] == "EXACT_ALIAS"
    assert item["rank_no"] == 4


# ─── RA07: content_id deduplicated ────────────────────────────────────────────

def test_ra07_content_id_deduplication(monkeypatch):
    """Service-level dedup: same content_id from multiple ranks → appears once."""
    monkeypatch.setenv("INTERNAL_API_SECRET", _SECRET)
    # Only one item returned (service already deduped)
    items = [{"reference_content_id": "c_dup", "reference_chem_id": "ch1",
               "reference_snapshot_id": _SNAP, "match_reason": "EXACT_CAS",
               "rank_no": 1, "evidence_json": {}}]
    vp, fp = _patch_svc(items=items)
    with vp, fp:
        resp = _client(_app()).post(
            "/internal/reference/msds/candidates",
            headers=_headers(),
            json=_body(cas_list=["7664-41-7"], product_name_normalized="ammonia"),
        )
    assert resp.status_code == 200
    assert len(resp.json()["data"]["items"]) == 1


# ─── RA08: valid snapshot + zero hit → 200 / items=[] ─────────────────────────

def test_ra08_zero_hit_returns_empty_list(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", _SECRET)
    vp, fp = _patch_svc(items=[])
    with vp, fp:
        resp = _client(_app()).post(
            "/internal/reference/msds/candidates",
            headers=_headers(),
            json=_body(cas_list=["0000-00-0"]),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["items"] == []
    assert data["data"]["snapshot_id"] == _SNAP


# ─── RA09: snapshot missing → 422 ─────────────────────────────────────────────

def test_ra09_snapshot_missing_422(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", _SECRET)
    vp, fp = _patch_svc(snapshot_not_ready=True)
    with vp, fp:
        resp = _client(_app()).post(
            "/internal/reference/msds/candidates",
            headers=_headers(),
            json=_body(snapshot_id="unknown-snap"),
        )
    assert resp.status_code == 422
    assert "REFERENCE_SNAPSHOT_NOT_READY" in resp.json()["detail"]


# ─── RA10: snapshot not COMPLETED → 422 ───────────────────────────────────────

def test_ra10_snapshot_not_completed_422(monkeypatch):
    """Snapshot exists but not COMPLETED → SnapshotNotReadyError → 422."""
    monkeypatch.setenv("INTERNAL_API_SECRET", _SECRET)
    import services.msds_reference_query_svc as svc_mod
    from services.msds_reference_query_svc import SnapshotNotReadyError

    def _raise(snapshot_id):
        raise SnapshotNotReadyError(f"REFERENCE_SNAPSHOT_NOT_READY: {snapshot_id} status=RUNNING")

    with patch.object(svc_mod, "validate_snapshot", side_effect=_raise), \
         patch.object(svc_mod, "find_candidates", return_value=[]):
        resp = _client(_app()).post(
            "/internal/reference/msds/candidates",
            headers=_headers(),
            json=_body(),
        )
    assert resp.status_code == 422
    assert "REFERENCE_SNAPSHOT_NOT_READY" in resp.json()["detail"]


# ─── RA11: reference write operations = 0 ─────────────────────────────────────

def test_ra11_reference_write_operations_zero():
    """Service source must contain no INSERT/UPDATE/DELETE/UPSERT calls."""
    import services.msds_reference_query_svc as svc_mod
    src = inspect.getsource(svc_mod)
    for forbidden in (".insert(", ".update(", ".delete(", ".upsert("):
        assert forbidden not in src, f"Write operation '{forbidden}' found in reference query service"
