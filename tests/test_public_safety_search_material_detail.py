"""M01-M16: SAFETY_MATERIAL search detail endpoint tests.
WO-MKT-SEARCH-04B-3A + PATCH1.

No real DB / network.
Store injected via dependency_overrides.
Signer injected via patch.object(_mat_signer_dep) — signer is no longer a Depends
so that eligibility checks run before any R2 initialization.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_safety_search as pss_mod
from services.kosha_safety_materials.display import MemoryDisplayStore


class _FakeSigner:
    def sign(self, bucket, key, *, mime=None, filename=None, disposition="inline") -> str:
        return f"https://r2.example.com/{key}?signed=1"


_FAKE_SIGNER = _FakeSigner()

_SNAP = {"id": "snap-001", "status": "COMPLETED", "completed_at": "2026-01-01T00:00:00+00:00"}
_MID = "MAT-001"


def _make_store(
    *,
    with_member: bool = True,
    with_hold: bool = False,
    hold_resolved: bool = False,
) -> MemoryDisplayStore:
    store = MemoryDisplayStore()
    store.snapshots.append(dict(_SNAP))
    if with_member:
        store.items.append({"snapshot_id": "snap-001", "material_id": _MID})
        store.catalog[_MID] = {
            "id": _MID,
            "title": "테스트 안전자료",
            "url": "https://kosha.or.kr/mat/001",
            "category": "GUIDE",
            "industry_category": "건설업",
            "collected_at": "2026-01-01T00:00:00+00:00",
        }
        store.details[_MID] = {
            "material_id": _MID,
            "enrichment_status": "OK",
            "kogl_type": "TYPE1",
            "content_type": "PDF",
            "source_url": "https://kosha.or.kr/mat/001",
            "source_published_at": "2026-01-01",
            "source_description": "안전자료 설명",
            "license_name": "공공누리 제1유형",
        }
    if with_hold:
        status = "RESOLVED" if hold_resolved else "OPEN"
        store.holds.append({"material_id": _MID, "status": status})
    return store


def _make_client(store: MemoryDisplayStore) -> TestClient:
    app = FastAPI()
    app.include_router(pss_mod.router)
    app.dependency_overrides[pss_mod._mat_store_dep] = lambda: store
    return TestClient(app)


def _req(client: TestClient, url: str, *, signer=None):
    """GET with _mat_signer_dep patched to return signer (default: _FAKE_SIGNER)."""
    s = _FAKE_SIGNER if signer is None else signer
    with patch.object(pss_mod, "_mat_signer_dep", return_value=s):
        return client.get(url)


_MAT_URL = f"/public/safety-search/material/{_MID}"


# ---------------------------------------------------------------------------
# M01 — snapshot member, no hold → 200
# ---------------------------------------------------------------------------
def test_m01_member_no_hold_returns_200():
    r = _req(_make_client(_make_store()), _MAT_URL)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# M02 — canonical identity: object_type=SAFETY_MATERIAL, canonical_id matches
# ---------------------------------------------------------------------------
def test_m02_canonical_identity():
    r = _req(_make_client(_make_store()), _MAT_URL)
    body = r.json()
    assert body["object_type"] == "SAFETY_MATERIAL"
    assert body["canonical_id"] == _MID
    assert body["detail"]["id"] == _MID


# ---------------------------------------------------------------------------
# M03 — non-member → 404 MATERIAL_NOT_FOUND
# ---------------------------------------------------------------------------
def test_m03_non_member_returns_404():
    r = _req(_make_client(_make_store(with_member=False)), _MAT_URL)
    assert r.status_code == 404
    assert r.json()["detail"] == "MATERIAL_NOT_FOUND"


# ---------------------------------------------------------------------------
# M04 — active hold → 404 MATERIAL_NOT_FOUND
# ---------------------------------------------------------------------------
def test_m04_active_hold_returns_404():
    r = _req(_make_client(_make_store(with_hold=True, hold_resolved=False)), _MAT_URL)
    assert r.status_code == 404
    assert r.json()["detail"] == "MATERIAL_NOT_FOUND"


# ---------------------------------------------------------------------------
# M05 — no completed snapshot → 503 CURRENT_SNAPSHOT_UNAVAILABLE
# ---------------------------------------------------------------------------
def test_m05_no_snapshot_returns_503():
    r = _req(_make_client(MemoryDisplayStore()), _MAT_URL)
    assert r.status_code == 503
    assert r.json()["detail"] == "CURRENT_SNAPSHOT_UNAVAILABLE"


# ---------------------------------------------------------------------------
# M06 — response includes required top-level and detail fields
# ---------------------------------------------------------------------------
def test_m06_response_fields():
    r = _req(_make_client(_make_store()), _MAT_URL)
    assert r.status_code == 200
    body = r.json()
    for field in ("object_type", "canonical_id", "title", "summary", "detail"):
        assert field in body, f"top-level field missing: {field}"
    detail = body["detail"]
    for field in ("id", "title", "category", "sector", "description", "source", "assets"):
        assert field in detail, f"detail field missing: {field}"


# ---------------------------------------------------------------------------
# M07 — RESOLVED hold → 200 (not blocked)
# ---------------------------------------------------------------------------
def test_m07_resolved_hold_not_blocked():
    r = _req(_make_client(_make_store(with_hold=True, hold_resolved=True)), _MAT_URL)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# M08 — GET /public/safety-search regression (route not broken by /material/*)
# ---------------------------------------------------------------------------
def test_m08_main_search_regression():
    r = _make_client(_make_store()).get("/public/safety-search")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# M09 — GET /public/safety-search/knowledge not shadowed by /material/{id}
# ---------------------------------------------------------------------------
def test_m09_knowledge_route_not_shadowed():
    row = {
        "doc_id": "FAQ-test", "type": "FAQ", "slug": "test-slug",
        "title": "제목", "question": "질문", "answer_short": "답변",
        "body": None, "menu_group": "app",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    with patch.object(pss_mod.safe_help_svc, "get_published_by_doc_id", return_value=row):
        r = _make_client(_make_store()).get("/public/safety-search/knowledge/FAQ-test")
    assert r.status_code == 200
    assert r.json()["object_type"] == "KNOWLEDGE"


# ---------------------------------------------------------------------------
# M10 — no Authorization header required (public endpoint)
# ---------------------------------------------------------------------------
def test_m10_no_auth_required():
    r = _req(_make_client(_make_store()), _MAT_URL)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# M11 — RESOLVED + OPEN holds coexist → active hold → 404
# ---------------------------------------------------------------------------
def test_m11_multiple_holds_open_wins():
    store = _make_store()
    store.holds.append({"material_id": _MID, "status": "RESOLVED"})
    store.holds.append({"material_id": _MID, "status": "OPEN"})
    r = _req(_make_client(store), _MAT_URL)
    assert r.status_code == 404
    assert r.json()["detail"] == "MATERIAL_NOT_FOUND"


# ---------------------------------------------------------------------------
# M12 — display.id ≠ canonical_id → 503 MATERIAL_IDENTITY_MISMATCH
# ---------------------------------------------------------------------------
def test_m12_identity_mismatch_returns_503():
    store = _make_store()
    store.catalog[_MID]["id"] = "MAT-OTHER"
    r = _req(_make_client(store), _MAT_URL)
    assert r.status_code == 503
    assert r.json()["detail"] == "MATERIAL_IDENTITY_MISMATCH"


# ---------------------------------------------------------------------------
# M13 — R2 signer NOT called for non-member
# ---------------------------------------------------------------------------
def test_m13_r2_not_called_for_non_member():
    store = _make_store(with_member=False)
    client = _make_client(store)
    mock_factory = MagicMock()
    with patch.object(pss_mod, "_mat_signer_dep", mock_factory):
        r = client.get(_MAT_URL)
    assert r.status_code == 404
    assert mock_factory.call_count == 0


# ---------------------------------------------------------------------------
# M14 — R2 signer NOT called for active hold
# ---------------------------------------------------------------------------
def test_m14_r2_not_called_for_active_hold():
    store = _make_store(with_hold=True, hold_resolved=False)
    client = _make_client(store)
    mock_factory = MagicMock()
    with patch.object(pss_mod, "_mat_signer_dep", mock_factory):
        r = client.get(_MAT_URL)
    assert r.status_code == 404
    assert mock_factory.call_count == 0


# ---------------------------------------------------------------------------
# M15 — eligible material + R2_INTEGRATION_BLOCKED → 503 STORAGE_UNAVAILABLE
# ---------------------------------------------------------------------------
def test_m15_eligible_r2_blocked_returns_503():
    from services.kosha_safety_materials.storage.r2_store import R2Error

    store = _make_store()
    client = _make_client(store)

    def _blocked():
        raise R2Error("R2_INTEGRATION_BLOCKED")

    with patch.object(pss_mod, "_mat_signer_dep", side_effect=_blocked):
        r = client.get(_MAT_URL)
    assert r.status_code == 503
    assert r.json()["detail"] == "STORAGE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# M16 — snapshot member but catalog missing → 404 MATERIAL_NOT_FOUND
# ---------------------------------------------------------------------------
def test_m16_catalog_missing_returns_404():
    store = MemoryDisplayStore()
    store.snapshots.append(dict(_SNAP))
    store.items.append({"snapshot_id": "snap-001", "material_id": _MID})
    # no catalog entry, no holds
    r = _req(_make_client(store), _MAT_URL)
    assert r.status_code == 404
    assert r.json()["detail"] == "MATERIAL_NOT_FOUND"
