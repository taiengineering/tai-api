"""M01-M10: SAFETY_MATERIAL search detail endpoint tests.
WO-MKT-SEARCH-04B-3A.

No real DB / network. Store and signer injected via dependency_overrides.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_safety_search as pss_mod
from services.kosha_safety_materials.display import MemoryDisplayStore


class _FakeSigner:
    def sign(self, bucket, key, *, mime=None, filename=None, disposition="inline") -> str:
        return f"https://r2.example.com/{key}?signed=1"


def _make_store(
    *,
    with_member: bool = True,
    with_hold: bool = False,
    hold_resolved: bool = False,
) -> MemoryDisplayStore:
    store = MemoryDisplayStore()
    snap = {"id": "snap-001", "status": "COMPLETED", "completed_at": "2026-01-01T00:00:00+00:00"}
    store.snapshots.append(snap)
    mid = "MAT-001"
    if with_member:
        store.items.append({"snapshot_id": "snap-001", "material_id": mid})
        store.catalog[mid] = {
            "id": mid,
            "title": "테스트 안전자료",
            "url": "https://kosha.or.kr/mat/001",
            "category": "GUIDE",
            "industry_category": "건설업",
            "collected_at": "2026-01-01T00:00:00+00:00",
        }
        store.details[mid] = {
            "material_id": mid,
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
        store.holds.append({"material_id": mid, "status": status})
    return store


def _make_client(store: MemoryDisplayStore, signer=None) -> TestClient:
    if signer is None:
        signer = _FakeSigner()
    app = FastAPI()
    app.include_router(pss_mod.router)
    app.dependency_overrides[pss_mod._mat_store_dep] = lambda: store
    app.dependency_overrides[pss_mod._mat_signer_dep] = lambda: signer
    return TestClient(app)


# ---------------------------------------------------------------------------
# M01 — snapshot member, no hold → 200
# ---------------------------------------------------------------------------
def test_m01_member_no_hold_returns_200():
    store = _make_store()
    r = _make_client(store).get("/public/safety-search/material/MAT-001")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# M02 — canonical identity: object_type=SAFETY_MATERIAL, canonical_id matches
# ---------------------------------------------------------------------------
def test_m02_canonical_identity():
    store = _make_store()
    r = _make_client(store).get("/public/safety-search/material/MAT-001")
    body = r.json()
    assert body["object_type"] == "SAFETY_MATERIAL"
    assert body["canonical_id"] == "MAT-001"
    assert body["detail"]["id"] == "MAT-001"


# ---------------------------------------------------------------------------
# M03 — non-member → 404 MATERIAL_NOT_FOUND
# ---------------------------------------------------------------------------
def test_m03_non_member_returns_404():
    store = _make_store(with_member=False)
    r = _make_client(store).get("/public/safety-search/material/MAT-001")
    assert r.status_code == 404
    assert r.json()["detail"] == "MATERIAL_NOT_FOUND"


# ---------------------------------------------------------------------------
# M04 — active hold → 404 MATERIAL_NOT_FOUND
# ---------------------------------------------------------------------------
def test_m04_active_hold_returns_404():
    store = _make_store(with_hold=True, hold_resolved=False)
    r = _make_client(store).get("/public/safety-search/material/MAT-001")
    assert r.status_code == 404
    assert r.json()["detail"] == "MATERIAL_NOT_FOUND"


# ---------------------------------------------------------------------------
# M05 — no completed snapshot → 503 CURRENT_SNAPSHOT_UNAVAILABLE
# ---------------------------------------------------------------------------
def test_m05_no_snapshot_returns_503():
    store = MemoryDisplayStore()  # no snapshots
    r = _make_client(store).get("/public/safety-search/material/MAT-001")
    assert r.status_code == 503
    assert r.json()["detail"] == "CURRENT_SNAPSHOT_UNAVAILABLE"


# ---------------------------------------------------------------------------
# M06 — response includes required top-level and detail fields
# ---------------------------------------------------------------------------
def test_m06_response_fields():
    store = _make_store()
    r = _make_client(store).get("/public/safety-search/material/MAT-001")
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
    store = _make_store(with_hold=True, hold_resolved=True)
    r = _make_client(store).get("/public/safety-search/material/MAT-001")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# M08 — GET /public/safety-search regression (route not broken by /material/*)
# ---------------------------------------------------------------------------
def test_m08_main_search_regression():
    store = _make_store()
    r = _make_client(store).get("/public/safety-search")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# M09 — GET /public/safety-search/knowledge not shadowed by /material/{id}
# ---------------------------------------------------------------------------
def test_m09_knowledge_route_not_shadowed():
    store = _make_store()
    row = {
        "doc_id": "FAQ-test", "type": "FAQ", "slug": "test-slug",
        "title": "제목", "question": "질문", "answer_short": "답변",
        "body": None, "menu_group": "app",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    with patch.object(pss_mod.safe_help_svc, "get_published_by_doc_id", return_value=row):
        r = _make_client(store).get("/public/safety-search/knowledge/FAQ-test")
    assert r.status_code == 200
    assert r.json()["object_type"] == "KNOWLEDGE"


# ---------------------------------------------------------------------------
# M10 — no Authorization header required (public endpoint)
# ---------------------------------------------------------------------------
def test_m10_no_auth_required():
    store = _make_store()
    r = _make_client(store).get(
        "/public/safety-search/material/MAT-001"
        # deliberately no Authorization header
    )
    assert r.status_code == 200
