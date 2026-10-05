"""S01-S18: ChemRegulationAdapter unit tests.
R01-R07: CHEM_REGULATION in public_safety_search router.

No real DB. No real OpenSearch.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.shared_search.adapters.chem_regulation import (
    ChemRegulationAdapter,
    _normalize_chem_regulation,
)
from services.shared_search.adapters._common import MISSING_TIMESTAMP


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _row(
    source_record_id="NCISS-001",
    chemical_name_ko="포름알데히드",
    chemical_name_en="Formaldehyde",
    cas_no="50-00-0",
    updated_at="2026-10-01T00:00:00+00:00",
    last_seen_at="2026-09-30T00:00:00+00:00",
    korexst_raw="KE-99999",
    alias_name_ko="포르말린",
    alias_name_en="Formalin",
    molecular_formula="CH2O",
    cas_to_chem_ids=None,
    regulatory_facts=None,
) -> dict:
    return {
        "source_record_id": source_record_id,
        "chemical_name_ko": chemical_name_ko,
        "chemical_name_en": chemical_name_en,
        "cas_no": cas_no,
        "korexst_raw": korexst_raw,
        "alias_name_ko": alias_name_ko,
        "alias_name_en": alias_name_en,
        "molecular_formula": molecular_formula,
        "molecular_weight_raw": "30.03",
        "updated_at": updated_at,
        "last_seen_at": last_seen_at,
        "_cas_to_chem_ids": cas_to_chem_ids or {},
        "_regulatory_facts": regulatory_facts or [],
    }


def _adapter(rows) -> ChemRegulationAdapter:
    return ChemRegulationAdapter(
        fetch_current=lambda: rows,
        fetch_by_id=lambda cid: next(
            (r for r in rows if r.get("source_record_id") == cid), None
        ),
    )


# ---------------------------------------------------------------------------
# S01: iter_documents yields payload for valid row
# ---------------------------------------------------------------------------

def test_s01_iter_documents_valid_row():
    rows = [_row()]
    docs = list(_adapter(rows).iter_documents())
    assert len(docs) == 1
    assert docs[0]["title"] == "포름알데히드"


# ---------------------------------------------------------------------------
# S02: Row with no title (no ko/en/cas) → skipped
# ---------------------------------------------------------------------------

def test_s02_no_title_skipped():
    row = _row(chemical_name_ko="", chemical_name_en="", cas_no=None)
    docs = list(_adapter([row]).iter_documents())
    assert docs == []


# ---------------------------------------------------------------------------
# S03: MISSING_TIMESTAMP → row skipped
# ---------------------------------------------------------------------------

def test_s03_missing_timestamp_skipped():
    row = _row(updated_at=None, last_seen_at=None)
    docs = list(_adapter([row]).iter_documents())
    assert docs == []


# ---------------------------------------------------------------------------
# S04: canonical_id = source_record_id
# ---------------------------------------------------------------------------

def test_s04_canonical_id_is_source_record_id():
    row = _row(source_record_id="NCISS-42")
    docs = list(_adapter([row]).iter_documents())
    assert docs[0]["canonical_id"] == "NCISS-42"


# ---------------------------------------------------------------------------
# S05: source_id = KECO_15149420 (official contract constant)
# ---------------------------------------------------------------------------

def test_s05_source_id():
    from services.keco_chemical.contract import SOURCE_ID
    docs = list(_adapter([_row()]).iter_documents())
    assert docs[0]["source_id"] == SOURCE_ID
    assert docs[0]["source_id"] == "KECO_15149420"


# ---------------------------------------------------------------------------
# S06: visibility_scopes = ["PUBLIC", "SAAS", "PAID"] always
# ---------------------------------------------------------------------------

def test_s06_visibility_scopes_always_public():
    docs = list(_adapter([_row()]).iter_documents())
    assert docs[0]["visibility_scopes"] == ["PUBLIC", "SAAS", "PAID"]


# ---------------------------------------------------------------------------
# S07: public_url = /msds/{chem_id}#keco for 1 identity match
# ---------------------------------------------------------------------------

def test_s07_public_url_single_match():
    row = _row(cas_to_chem_ids={"50-00-0": ["CHEM-001"]})
    docs = list(_adapter([row]).iter_documents())
    assert docs[0]["public_url"] == "/msds/CHEM-001#keco"


# ---------------------------------------------------------------------------
# S08: public_url = /msds?q={cas} for ≥2 identity matches
# ---------------------------------------------------------------------------

def test_s08_public_url_multi_match():
    row = _row(cas_to_chem_ids={"50-00-0": ["CHEM-001", "CHEM-002"]})
    docs = list(_adapter([row]).iter_documents())
    assert docs[0]["public_url"] == "/msds?q=50-00-0"


# ---------------------------------------------------------------------------
# S09: public_url = null for 0 identity matches
# ---------------------------------------------------------------------------

def test_s09_public_url_no_match():
    row = _row(cas_to_chem_ids={})
    docs = list(_adapter([row]).iter_documents())
    assert docs[0]["public_url"] is None


# ---------------------------------------------------------------------------
# S10: public_url = null when CAS is None
# ---------------------------------------------------------------------------

def test_s10_public_url_null_when_no_cas():
    row = _row(cas_no=None)
    docs = list(_adapter([row]).iter_documents())
    assert docs[0]["public_url"] is None


# ---------------------------------------------------------------------------
# S11: object_reindex_payload returns correct payload
# ---------------------------------------------------------------------------

def test_s11_object_reindex_payload():
    rows = [_row(source_record_id="NCISS-10")]
    adapter = _adapter(rows)
    payload = adapter.object_reindex_payload("NCISS-10")
    assert payload is not None
    assert payload["canonical_id"] == "NCISS-10"
    assert payload["object_type"] == "CHEM_REGULATION"


# ---------------------------------------------------------------------------
# S12: object_reindex_payload returns None for unknown id
# ---------------------------------------------------------------------------

def test_s12_object_reindex_payload_unknown():
    adapter = _adapter([_row(source_record_id="NCISS-001")])
    assert adapter.object_reindex_payload("NCISS-999") is None


# ---------------------------------------------------------------------------
# S13: iter_expected_hashes returns hash dicts
# ---------------------------------------------------------------------------

def test_s13_iter_expected_hashes():
    adapter = _adapter([_row()])
    hashes = list(adapter.iter_expected_hashes())
    assert len(hashes) == 1
    assert "canonical_id" in hashes[0]
    assert "content_hash" in hashes[0]


# ---------------------------------------------------------------------------
# S14: search_text includes classification_type from regulatory_facts
# ---------------------------------------------------------------------------

def test_s14_regulatory_facts_in_search_text():
    fact = {"classification_type": "유독물질", "unique_no": "2024-001"}
    row = _row(regulatory_facts=[fact])
    docs = list(_adapter([row]).iter_documents())
    assert "유독물질" in docs[0]["search_text"]


# ---------------------------------------------------------------------------
# S15: aliases include en / alias_ko / alias_en / cas / korexst
# ---------------------------------------------------------------------------

def test_s15_aliases():
    row = _row(
        chemical_name_en="Formaldehyde",
        alias_name_ko="포르말린",
        alias_name_en="Formalin",
        cas_no="50-00-0",
        korexst_raw="KE-99999",
    )
    docs = list(_adapter([row]).iter_documents())
    aliases = docs[0]["aliases"]
    assert "Formaldehyde" in aliases
    assert "포르말린" in aliases
    assert "Formalin" in aliases
    assert "50-00-0" in aliases
    assert "KE-99999" in aliases


# ---------------------------------------------------------------------------
# S16: No forbidden keys in payload
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = {
    "company_id", "factory_id", "legal_applicable", "llm_inferred",
    "raw_payload",
}


def test_s16_no_forbidden_keys():
    docs = list(_adapter([_row()]).iter_documents())
    for doc in docs:
        for key in _FORBIDDEN_KEYS:
            assert key not in doc, f"Forbidden key found: {key}"


# ---------------------------------------------------------------------------
# S17: Row with only chemical_name_en (no ko) → uses en as title
# ---------------------------------------------------------------------------

def test_s17_en_only_title():
    row = _row(chemical_name_ko="", chemical_name_en="Benzene")
    docs = list(_adapter([row]).iter_documents())
    assert docs[0]["title"] == "Benzene"


# ---------------------------------------------------------------------------
# S18: Row with both ko and en → ko preferred as title
# ---------------------------------------------------------------------------

def test_s18_ko_preferred_as_title():
    row = _row(chemical_name_ko="벤젠", chemical_name_en="Benzene")
    docs = list(_adapter([row]).iter_documents())
    assert docs[0]["title"] == "벤젠"


# ===========================================================================
# R01-R07: CHEM_REGULATION in public_safety_search router
# ===========================================================================

import routers.public_safety_search as pss_mod
from services.shared_search.retrieval import MemorySearchReader


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pss_mod.router)
    return app


def _chem_reg_doc(
    canonical_id="cr-001",
    title="포름알데히드",
    visibility_scopes=None,
) -> dict:
    return {
        "object_type":        "CHEM_REGULATION",
        "canonical_id":       canonical_id,
        "title":              title,
        "source_id":          "KECO_15149420",
        "source_key":         canonical_id,
        "summary":            None,
        "aliases":            ["50-00-0"],
        "keywords":           [],
        "subjects":           [],
        "context":            [],
        "public_url":         None,
        "saas_url":           None,
        "search_text":        title,
        "publication_status": "PUBLISHED",
        "visibility_scopes":  visibility_scopes or ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at":  "2026-10-01T00:00:00+00:00",
        "content_hash":       "cr_hash_001",
    }


def _patch_reader(docs: list[dict], monkeypatch: Any):
    memory_reader = MemorySearchReader(docs)
    monkeypatch.setattr(pss_mod, "get_client", lambda: MagicMock())
    import services.shared_search.opensearch_reader as osr_mod
    monkeypatch.setattr(osr_mod, "OpenSearchSearchReader", lambda _client: memory_reader)


# ---------------------------------------------------------------------------
# R01: CHEM_REGULATION in _PUBLIC_OBJECT_TYPES
# ---------------------------------------------------------------------------

def test_r01_chem_regulation_in_public_types():
    assert "CHEM_REGULATION" in pss_mod._PUBLIC_OBJECT_TYPES


# ---------------------------------------------------------------------------
# R02: type=keco maps to CHEM_REGULATION
# ---------------------------------------------------------------------------

def test_r02_type_keco_maps_to_chem_regulation():
    assert pss_mod._TYPE_MAP.get("keco") == ["CHEM_REGULATION"]


# ---------------------------------------------------------------------------
# R03: CHEM_REGULATION in default search (no type filter) — included
# ---------------------------------------------------------------------------

def test_r03_chem_regulation_in_default_search(monkeypatch):
    docs = [_chem_reg_doc()]
    _patch_reader(docs, monkeypatch)
    client = TestClient(_make_app())
    resp = client.get("/public/safety-search", params={"q": "포름알데히드"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# R04: CHEM_REGULATION in /sections — has a section
# ---------------------------------------------------------------------------

def test_r04_chem_regulation_in_sections(monkeypatch):
    docs = [_chem_reg_doc()]
    _patch_reader(docs, monkeypatch)
    client = TestClient(_make_app())
    resp = client.get("/public/safety-search/sections", params={"q": "포름알데히드"})
    assert resp.status_code == 200
    section_types = [s["object_type"] for s in resp.json()["sections"]]
    assert "CHEM_REGULATION" in section_types


# ---------------------------------------------------------------------------
# R05: CHEM_REGULATION NOT gated by KOSHA_MSDS_PUBLIC_MODE
# ---------------------------------------------------------------------------

def test_r05_chem_regulation_not_gated_by_kosha_mode(monkeypatch):
    docs = [_chem_reg_doc()]
    _patch_reader(docs, monkeypatch)
    # KOSHA_MSDS_PUBLIC_MODE=off → CHEM excluded but CHEM_REGULATION must survive
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "off")
    client = TestClient(_make_app())
    resp = client.get("/public/safety-search/sections", params={"q": "포름알데히드"})
    assert resp.status_code == 200
    sections = resp.json()["sections"]
    keco_section = next((s for s in sections if s["object_type"] == "CHEM_REGULATION"), None)
    assert keco_section is not None
    # CHEM section should be empty (gated), but CHEM_REGULATION section exists
    chem_section = next((s for s in sections if s["object_type"] == "CHEM"), None)
    if chem_section:
        assert chem_section["status"] == "empty"


# ---------------------------------------------------------------------------
# R06: type=keco search returns CHEM_REGULATION items only
# ---------------------------------------------------------------------------

def test_r06_type_keco_search_returns_chem_regulation(monkeypatch):
    docs = [
        _chem_reg_doc(),
        {
            "object_type": "GUIDE", "canonical_id": "g-1", "title": "가이드",
            "source_id": "KOSHA", "source_key": None, "summary": None,
            "aliases": [], "keywords": [], "subjects": [], "context": [],
            "public_url": None, "saas_url": None,
            "search_text": "포름알데히드 가이드",
            "publication_status": "PUBLISHED",
            "visibility_scopes": ["PUBLIC"],
            "source_updated_at": "2026-10-01T00:00:00+00:00",
            "content_hash": "g_hash",
        },
    ]
    _patch_reader(docs, monkeypatch)
    client = TestClient(_make_app())
    resp = client.get(
        "/public/safety-search",
        params={"q": "포름알데히드", "type": "keco"},
    )
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    for item in items:
        assert item["object_type"] == "CHEM_REGULATION"


# ---------------------------------------------------------------------------
# R07: type=chem_regulation also maps correctly
# ---------------------------------------------------------------------------

def test_r07_type_chem_regulation_alias(monkeypatch):
    docs = [_chem_reg_doc()]
    _patch_reader(docs, monkeypatch)
    client = TestClient(_make_app())
    resp = client.get(
        "/public/safety-search",
        params={"q": "포름알데히드", "type": "chem_regulation"},
    )
    assert resp.status_code == 200


# ===========================================================================
# PATCH-001 tests (P01, P05-P14)
# ===========================================================================

# ---------------------------------------------------------------------------
# P01: Search adapter source_id == KECO_15149420
# ---------------------------------------------------------------------------

def test_p01_search_source_id_official():
    from services.keco_chemical.contract import SOURCE_ID
    docs = list(_adapter([_row()]).iter_documents())
    assert docs[0]["source_id"] == SOURCE_ID
    assert docs[0]["source_id"] == "KECO_15149420"


# ---------------------------------------------------------------------------
# P05: unique_no is searchable
# ---------------------------------------------------------------------------

def test_p05_unique_no_in_search_text():
    fact = {"classification_type": "유독물질", "unique_no": "UN-2024-001",
            "content_info": None, "exception_info": None, "notice_info": None}
    row = _row(regulatory_facts=[fact])
    docs = list(_adapter([row]).iter_documents())
    assert "UN-2024-001" in docs[0]["search_text"]


# ---------------------------------------------------------------------------
# P06: classification_type is searchable
# ---------------------------------------------------------------------------

def test_p06_classification_type_in_search_text():
    fact = {"classification_type": "사고대비물질", "unique_no": None,
            "content_info": None, "exception_info": None, "notice_info": None}
    row = _row(regulatory_facts=[fact])
    docs = list(_adapter([row]).iter_documents())
    assert "사고대비물질" in docs[0]["search_text"]


# ---------------------------------------------------------------------------
# P07: content_info is in search_text
# ---------------------------------------------------------------------------

def test_p07_content_info_in_search_text():
    fact = {"classification_type": None, "unique_no": None,
            "content_info": "취급제한물질", "exception_info": None, "notice_info": None}
    row = _row(regulatory_facts=[fact])
    docs = list(_adapter([row]).iter_documents())
    assert "취급제한물질" in docs[0]["search_text"]


# ---------------------------------------------------------------------------
# P08: exception_info is in search_text
# ---------------------------------------------------------------------------

def test_p08_exception_info_in_search_text():
    fact = {"classification_type": None, "unique_no": None,
            "content_info": None, "exception_info": "시험연구 제외", "notice_info": None}
    row = _row(regulatory_facts=[fact])
    docs = list(_adapter([row]).iter_documents())
    assert "시험연구 제외" in docs[0]["search_text"]


# ---------------------------------------------------------------------------
# P09: notice_info is in search_text
# ---------------------------------------------------------------------------

def test_p09_notice_info_in_search_text():
    fact = {"classification_type": None, "unique_no": None,
            "content_info": None, "exception_info": None, "notice_info": "고시 2024-01"}
    row = _row(regulatory_facts=[fact])
    docs = list(_adapter([row]).iter_documents())
    assert "고시 2024-01" in docs[0]["search_text"]


# ---------------------------------------------------------------------------
# P10: unique_no appears in aliases
# ---------------------------------------------------------------------------

def test_p10_unique_no_in_aliases():
    fact = {"classification_type": "유독물질", "unique_no": "UN-9999",
            "content_info": None, "exception_info": None, "notice_info": None}
    row = _row(regulatory_facts=[fact])
    docs = list(_adapter([row]).iter_documents())
    assert "UN-9999" in docs[0]["aliases"]


# ---------------------------------------------------------------------------
# P11: classification_type appears in aliases
# ---------------------------------------------------------------------------

def test_p11_classification_type_in_aliases():
    fact = {"classification_type": "허가물질", "unique_no": None,
            "content_info": None, "exception_info": None, "notice_info": None}
    row = _row(regulatory_facts=[fact])
    docs = list(_adapter([row]).iter_documents())
    assert "허가물질" in docs[0]["aliases"]


# ---------------------------------------------------------------------------
# P12: ko/en both blank + CAS exists → title = "CAS {cas}" (not dropped)
# ---------------------------------------------------------------------------

def test_p12_cas_fallback_title_not_dropped():
    row = _row(chemical_name_ko="", chemical_name_en="", cas_no="50-00-0")
    docs = list(_adapter([row]).iter_documents())
    assert len(docs) == 1
    assert docs[0]["title"] == "CAS 50-00-0"


# ---------------------------------------------------------------------------
# P13: No-match CAS remains HTTP 200 + chemicals=[]
# ---------------------------------------------------------------------------

def test_p13_no_match_cas_is_200_empty(monkeypatch):
    import routers.public_keco_chemical as keco_mod
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(keco_mod.router)
    monkeypatch.setattr(
        "services.keco_chemical.read._get_leg_client",
        lambda: _mock_leg_client_empty(),
    )
    client = TestClient(app)
    resp = client.get("/public/keco/chemicals/by-cas/7732-18-5")
    assert resp.status_code == 200
    assert resp.json()["chemicals"] == []


def _mock_leg_client_empty():
    from unittest.mock import MagicMock
    client = MagicMock()
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[])
    )
    client.schema.return_value = db
    return client


# ---------------------------------------------------------------------------
# P14: context_type=chemical remains unchanged
# ---------------------------------------------------------------------------

def test_p14_context_type_chemical():
    row = _row(cas_no="50-00-0")
    docs = list(_adapter([row]).iter_documents())
    ctx = docs[0]["context"]
    assert len(ctx) == 1
    assert ctx[0]["context_type"] == "chemical"
    assert ctx[0]["context_key"] == "50-00-0"
