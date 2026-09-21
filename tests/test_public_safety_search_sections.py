"""S01-S12: /public/safety-search/sections endpoint contract tests.
WO-MKT-SEARCH-06R-1 §23-§34.

No real OpenSearch / DB. get_client and OpenSearchSearchReader are patched;
MemorySearchReader is injected so tests run fully in-process.
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_safety_search as pss_mod
from services.shared_search.retrieval import MemorySearchReader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECTION_ORDER = ["guide", "material", "accident", "chem", "knowledge", "precedent", "law"]
_SECTION_OBJECT_TYPES = {
    "guide":     "GUIDE",
    "material":  "SAFETY_MATERIAL",
    "accident":  "CSI_ACCIDENT",
    "chem":      "CHEM",
    "knowledge": "KNOWLEDGE",
    "precedent": "PRECEDENT",
    "law":       "LEGAL",
}


def _doc(
    object_type: str = "GUIDE",
    canonical_id: str = "obj-001",
    title: str = "Test",
    search_text: str = "test document",
    publication_status: str = "PUBLISHED",
    visibility_scopes: list[str] | None = None,
) -> dict:
    return {
        "object_type":        object_type,
        "canonical_id":       canonical_id,
        "title":              title,
        "source_id":          "TEST",
        "source_key":         None,
        "summary":            None,
        "aliases":            [],
        "keywords":           [],
        "subjects":           [],
        "context":            [],
        "public_url":         f"/{object_type.lower()}/{canonical_id}",
        "saas_url":           None,
        "search_text":        search_text,
        "publication_status": publication_status,
        "visibility_scopes":  visibility_scopes or ["PUBLIC"],
        "source_updated_at":  "2026-09-22T00:00:00+00:00",
        "content_hash":       "abc",
    }


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pss_mod.router)
    return app


def _patch_reader(docs: list[dict], monkeypatch: Any, chem_mode: str = "full"):
    """Patch get_client + OpenSearchSearchReader so the router uses MemorySearchReader."""
    memory_reader = MemorySearchReader(docs)
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", chem_mode)
    monkeypatch.setattr(pss_mod, "get_client", lambda: MagicMock())

    import services.shared_search.opensearch_reader as osr_mod
    monkeypatch.setattr(osr_mod, "OpenSearchSearchReader", lambda _client: memory_reader)

    return memory_reader


# ---------------------------------------------------------------------------
# S01 — 7 section keys in correct fixed order
# ---------------------------------------------------------------------------

def test_s01_seven_sections_correct_order(monkeypatch):
    docs = [_doc(object_type=ot, canonical_id=f"{ot}-1", search_text="지게차 test")
            for ot in _SECTION_OBJECT_TYPES.values()]
    _patch_reader(docs, monkeypatch)

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search/sections?q=지게차")
    assert r.status_code == 200
    sections = r.json()["sections"]
    assert len(sections) == 7
    assert [s["type"] for s in sections] == _SECTION_ORDER


# ---------------------------------------------------------------------------
# S02 — each section's object_type matches expected mapping
# ---------------------------------------------------------------------------

def test_s02_section_object_types_match(monkeypatch):
    docs = [_doc(object_type=ot, canonical_id=f"{ot}-1", search_text="test query")
            for ot in _SECTION_OBJECT_TYPES.values()]
    _patch_reader(docs, monkeypatch)

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search/sections?q=test+query")
    assert r.status_code == 200
    for s in r.json()["sections"]:
        assert s["object_type"] == _SECTION_OBJECT_TYPES[s["type"]], (
            f"section type={s['type']} has wrong object_type={s['object_type']}"
        )


# ---------------------------------------------------------------------------
# S03 — section_size=5 → items count <= 5 per section
# ---------------------------------------------------------------------------

def test_s03_items_capped_at_section_size(monkeypatch):
    # 10 docs per domain
    docs = []
    for ot in _SECTION_OBJECT_TYPES.values():
        for i in range(10):
            docs.append(_doc(object_type=ot, canonical_id=f"{ot}-{i}", search_text="키워드 test"))
    _patch_reader(docs, monkeypatch)

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search/sections?q=키워드+test&section_size=5")
    assert r.status_code == 200
    for s in r.json()["sections"]:
        if s["object_type"] == "CHEM":
            continue  # CHEM mode already covered by S08
        assert len(s["items"]) <= 5, f"section {s['type']} has {len(s['items'])} items > 5"


# ---------------------------------------------------------------------------
# S04 — has_more=true when results exceed section_size
# ---------------------------------------------------------------------------

def test_s04_has_more_true_when_results_exceed_section_size(monkeypatch):
    # 8 GUIDE docs — section_size default 5 → has_more should be True
    docs = [_doc(object_type="GUIDE", canonical_id=f"G-{i}", search_text="지게차 안전") for i in range(8)]
    _patch_reader(docs, monkeypatch)

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search/sections?q=지게차+안전&section_size=5")
    assert r.status_code == 200
    guide_section = next(s for s in r.json()["sections"] if s["type"] == "guide")
    assert guide_section["has_more"] is True
    assert len(guide_section["items"]) == 5


# ---------------------------------------------------------------------------
# S05 — zero result domain: items=[], has_more=false, status=empty
# ---------------------------------------------------------------------------

def test_s05_zero_result_section(monkeypatch):
    # Only LEGAL docs, all other domains empty
    docs = [_doc(object_type="LEGAL", canonical_id="L-1", search_text="법령 산업안전")]
    _patch_reader(docs, monkeypatch)

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search/sections?q=법령+산업안전")
    assert r.status_code == 200
    sections = r.json()["sections"]
    law_section = next(s for s in sections if s["type"] == "law")
    assert law_section["items"] != []  # LEGAL should have results

    # All other internal sections (except chem which has its own guard) should be empty
    for s in sections:
        if s["type"] in ("law", "chem"):
            continue
        assert s["items"] == [], f"{s['type']} should be empty"
        assert s["has_more"] is False, f"{s['type']} has_more should be False"
        assert s["status"] == "empty", f"{s['type']} status should be empty"


# ---------------------------------------------------------------------------
# S06 — within passed to all typed engine calls
# ---------------------------------------------------------------------------

def test_s06_within_applied_to_all_sections(monkeypatch):
    # All 7 domains have docs but only the ones with "충돌" in search_text should survive
    docs = []
    for ot in _SECTION_OBJECT_TYPES.values():
        docs.append(_doc(object_type=ot, canonical_id=f"{ot}-match",
                         search_text="지게차 충돌 사고"))
        docs.append(_doc(object_type=ot, canonical_id=f"{ot}-nomatch",
                         search_text="지게차 안전 가이드"))
    _patch_reader(docs, monkeypatch)

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search/sections?q=지게차&within=충돌")
    assert r.status_code == 200
    body = r.json()
    assert body["within"] == "충돌"

    for s in body["sections"]:
        if s["object_type"] == "CHEM":
            continue
        for item in s["items"]:
            assert item["canonical_id"].endswith("-match"), (
                f"section {s['type']} returned non-within item: {item['canonical_id']}"
            )


# ---------------------------------------------------------------------------
# S07 — LEGAL section items contain no forbidden applicability fields
# ---------------------------------------------------------------------------

_LEGAL_FORBIDDEN = {
    "legal_applicable", "is_required", "legal_score",
    "obligation", "violation", "compliance_score",
}


def test_s07_legal_section_no_forbidden_fields(monkeypatch):
    docs = [_doc(object_type="LEGAL", canonical_id="L-1", search_text="산업안전보건법 지게차")]
    _patch_reader(docs, monkeypatch)

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search/sections?q=지게차")
    assert r.status_code == 200
    law_section = next(s for s in r.json()["sections"] if s["type"] == "law")
    for item in law_section["items"]:
        forbidden_found = set(item.keys()) & _LEGAL_FORBIDDEN
        assert not forbidden_found, f"Forbidden keys in LEGAL item: {forbidden_found}"


# ---------------------------------------------------------------------------
# S08 — CHEM guard: mode OFF → CHEM section empty, mode ON → may have results
# ---------------------------------------------------------------------------

def test_s08_chem_guard_mode_off(monkeypatch):
    docs = [_doc(object_type="CHEM", canonical_id="C-1", search_text="sodium chemical")]
    _patch_reader(docs, monkeypatch, chem_mode="off")

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search/sections?q=sodium")
    assert r.status_code == 200
    chem_section = next(s for s in r.json()["sections"] if s["type"] == "chem")
    assert chem_section["items"] == []
    assert chem_section["has_more"] is False
    assert chem_section["status"] == "empty"


def test_s08_chem_guard_mode_on(monkeypatch):
    docs = [_doc(object_type="CHEM", canonical_id="C-1", search_text="sodium chemical")]
    _patch_reader(docs, monkeypatch, chem_mode="seo_preview")

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search/sections?q=sodium+chemical")
    assert r.status_code == 200
    chem_section = next(s for s in r.json()["sections"] if s["type"] == "chem")
    assert len(chem_section["items"]) > 0


# ---------------------------------------------------------------------------
# S09 — OpenSearch unavailable → 503 SHARED_SEARCH_UNAVAILABLE
# ---------------------------------------------------------------------------

def test_s09_opensearch_unavailable_returns_503(monkeypatch):
    from services.shared_search.opensearch_client import OpenSearchUnavailable
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "full")
    monkeypatch.setattr(pss_mod, "get_client",
                        lambda: (_ for _ in ()).throw(OpenSearchUnavailable("no config")))

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search/sections?q=지게차")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "SHARED_SEARCH_UNAVAILABLE"


# ---------------------------------------------------------------------------
# S10 — existing /public/safety-search regression
# ---------------------------------------------------------------------------

def test_s10_existing_endpoint_regression(monkeypatch):
    docs = [_doc(object_type="GUIDE", canonical_id="G-1", search_text="지게차 안전")]
    _patch_reader(docs, monkeypatch)

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search?q=지게차+안전")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "query" in body


# ---------------------------------------------------------------------------
# S11 — existing typed pagination regression: type=guide&page=2
# ---------------------------------------------------------------------------

def test_s11_typed_pagination_regression(monkeypatch):
    # 15 GUIDE docs so page 2 is non-empty
    docs = [_doc(object_type="GUIDE", canonical_id=f"G-{i}", search_text="지게차 안전 guide")
            for i in range(15)]
    _patch_reader(docs, monkeypatch)

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search?q=지게차+안전+guide&type=guide&page=2&page_size=5")
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 2
    assert isinstance(body["items"], list)


# ---------------------------------------------------------------------------
# S12 — KOSHA endpoint unchanged (still reachable, not part of /sections)
# ---------------------------------------------------------------------------

def test_s12_kosha_endpoint_unchanged(monkeypatch):
    from services.kosha_smart_search import SmartSearchQueryError

    async def _mock_kosha(*, q, page, page_size):
        return {"q": q, "items": [], "total": 0}

    monkeypatch.setattr(pss_mod, "search_kosha_public", _mock_kosha)

    with TestClient(_make_app()) as c:
        r = c.get("/public/safety-search/kosha?q=지게차")
    assert r.status_code == 200
    assert r.json()["q"] == "지게차"
