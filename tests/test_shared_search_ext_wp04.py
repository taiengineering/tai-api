"""TAI-WO-P0-CONTENT-WP04-001 — EXT-037/132/165 Shared Search adapter tests.

A01-A12: ChemSafetyAdapter (EXT-037)
B01-B12: HazardousMaterialAdapter (EXT-132)
C01-C12: ChemAccidentAdapter (EXT-165)
R01-R06: public_safety_search router — new type keys registered

No real DB. No real OpenSearch. No RPC.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from services.shared_search.adapters.ext037_chem_safety import (
    ChemSafetyAdapter,
    _normalize_chem_safety,
)
from services.shared_search.adapters.ext132_hazardous import (
    HazardousMaterialAdapter,
    _normalize_hazardous,
)
from services.shared_search.adapters.ext165_chem_accident import (
    ChemAccidentAdapter,
    _normalize_chem_accident,
)
from services.shared_search.adapters._common import MISSING_TIMESTAMP


# ============================================================================
# Helpers
# ============================================================================

_TS = "2026-10-01T00:00:00+00:00"


def _row037(
    datano="D001",
    chem_ko="암모니아",
    chem_en="Ammonia",
    cas_no="7664-41-7",
    symptom="호흡기 자극",
    oral="",
    skin="",
    inhale="",
    eyeball="",
    etc="",
    snapshot_completed_at=_TS,
) -> dict:
    return {
        "datano": datano,
        "raw": {
            "dataNo": datano,
            "chemKo": chem_ko,
            "chemEn": chem_en,
            "casNo": cas_no,
            "symptom": symptom,
            "oral": oral,
            "skin": skin,
            "inhale": inhale,
            "eyeball": eyeball,
            "etc": etc,
        },
        "_snapshot_completed_at": snapshot_completed_at,
    }


def _row132(
    chemicalno="C001",
    chemical_name="아세톤",
    cas_no="67-64-1",
    un_no="UN1090",
    hazard_class="4류 위험물",
    snapshot_completed_at=_TS,
) -> dict:
    return {
        "chemicalno": chemicalno,
        "raw": {
            "chemicalname": chemical_name,
            "casno": cas_no,
            "unno": un_no,
            "hazardmaterialclass": hazard_class,
        },
        "_snapshot_completed_at": snapshot_completed_at,
    }


def _row165(
    datano="1001",
    cscTy="폭발",
    area="경기도",
    place="화학공장",
    chem="암모니아",
    cause="밸브 오작동",
    summary="누출 사고",
    cscDe="2023-05-12",
    snapshot_completed_at=_TS,
) -> dict:
    return {
        "datano": datano,
        "raw": {
            "dataNo": datano,
            "cscTy": cscTy,
            "area": area,
            "place": place,
            "chem": chem,
            "cause": cause,
            "summary": summary,
            "cscDe": cscDe,
        },
        "_snapshot_completed_at": snapshot_completed_at,
    }


def _adapter037(rows):
    return ChemSafetyAdapter(
        fetch_current=lambda: rows,
        fetch_by_id=lambda d: next(
            (r for r in rows if r.get("datano") == d), None
        ),
    )


def _adapter132(rows):
    return HazardousMaterialAdapter(
        fetch_current=lambda: rows,
        fetch_by_id=lambda c: next(
            (r for r in rows if r.get("chemicalno") == c), None
        ),
    )


def _adapter165(rows):
    return ChemAccidentAdapter(
        fetch_current=lambda: rows,
        fetch_by_id=lambda d: next(
            (r for r in rows if r.get("datano") == d), None
        ),
    )


# ============================================================================
# A01-A12: ChemSafetyAdapter (EXT-037)
# ============================================================================

def test_a01_iter_documents_valid_row():
    docs = list(_adapter037([_row037()]).iter_documents())
    assert len(docs) == 1
    assert docs[0]["title"] == "암모니아"


def test_a02_no_datano_skipped():
    row = _row037(datano="")
    row["raw"]["dataNo"] = ""
    docs = list(_adapter037([row]).iter_documents())
    assert docs == []


def test_a03_missing_timestamp_skipped():
    docs = list(_adapter037([_row037(snapshot_completed_at=None)]).iter_documents())
    assert docs == []


def test_a04_chem_ko_title():
    p = _normalize_chem_safety(_row037(chem_ko="포름알데히드", chem_en="Formaldehyde"))
    assert p["title"] == "포름알데히드"


def test_a05_chem_en_fallback_title():
    p = _normalize_chem_safety(_row037(chem_ko="", chem_en="Formaldehyde"))
    assert p["title"] == "Formaldehyde"


def test_a06_datano_fallback_title():
    p = _normalize_chem_safety(_row037(chem_ko="", chem_en=""))
    assert p["title"] == "dataNo D001"


def test_a07_aliases_include_chem_en_and_cas():
    p = _normalize_chem_safety(_row037(chem_en="Ammonia", cas_no="7664-41-7"))
    assert "Ammonia" in p["aliases"]
    assert "7664-41-7" in p["aliases"]


def test_a08_context_chemical_when_cas_present():
    p = _normalize_chem_safety(_row037(cas_no="7664-41-7"))
    assert p["context"] == [{"context_type": "chemical", "context_key": "7664-41-7"}]


def test_a09_context_empty_without_cas():
    p = _normalize_chem_safety(_row037(cas_no=""))
    assert p["context"] == []


def test_a10_public_url_is_none():
    p = _normalize_chem_safety(_row037())
    assert p["public_url"] is None


def test_a11_visibility_scopes_public():
    p = _normalize_chem_safety(_row037())
    assert p["visibility_scopes"] == ["PUBLIC"]


def test_a12_object_reindex_payload():
    rows = [_row037()]
    adapter = _adapter037(rows)
    p = adapter.object_reindex_payload("D001")
    assert p is not None
    assert p["canonical_id"] == "D001"


# ============================================================================
# B01-B12: HazardousMaterialAdapter (EXT-132)
# ============================================================================

def test_b01_iter_documents_valid_row():
    docs = list(_adapter132([_row132()]).iter_documents())
    assert len(docs) == 1
    assert docs[0]["title"] == "아세톤"


def test_b02_no_chemicalno_skipped():
    row = _row132(chemicalno="")
    row["raw"].pop("chemaicalno", None)
    docs = list(_adapter132([row]).iter_documents())
    assert docs == []


def test_b03_missing_timestamp_skipped():
    docs = list(_adapter132([_row132(snapshot_completed_at=None)]).iter_documents())
    assert docs == []


def test_b04_chemical_name_title():
    p = _normalize_hazardous(_row132(chemical_name="벤젠"))
    assert p["title"] == "벤젠"


def test_b05_fallback_title_chemicalno():
    p = _normalize_hazardous(_row132(chemical_name=""))
    assert p["title"] == "No C001"


def test_b06_aliases_include_cas_and_un():
    p = _normalize_hazardous(_row132(cas_no="67-64-1", un_no="UN1090"))
    assert "67-64-1" in p["aliases"]
    assert "UN1090" in p["aliases"]


def test_b07_context_chemical_when_cas_present():
    p = _normalize_hazardous(_row132(cas_no="67-64-1"))
    assert p["context"] == [{"context_type": "chemical", "context_key": "67-64-1"}]


def test_b08_context_empty_without_cas():
    p = _normalize_hazardous(_row132(cas_no=""))
    assert p["context"] == []


def test_b09_public_url_is_none():
    p = _normalize_hazardous(_row132())
    assert p["public_url"] is None


def test_b10_summary_is_hazard_class():
    p = _normalize_hazardous(_row132(hazard_class="4류 위험물"))
    assert p["summary"] == "4류 위험물"


def test_b11_visibility_scopes_public():
    p = _normalize_hazardous(_row132())
    assert p["visibility_scopes"] == ["PUBLIC"]


def test_b12_object_reindex_payload():
    rows = [_row132()]
    adapter = _adapter132(rows)
    p = adapter.object_reindex_payload("C001")
    assert p is not None
    assert p["canonical_id"] == "C001"


# ============================================================================
# C01-C12: ChemAccidentAdapter (EXT-165)
# ============================================================================

def test_c01_iter_documents_valid_row():
    docs = list(_adapter165([_row165()]).iter_documents())
    assert len(docs) == 1
    assert "암모니아" in docs[0]["title"]


def test_c02_no_datano_skipped():
    row = _row165(datano="")
    row["raw"]["dataNo"] = ""
    row["raw"]["datano"] = ""
    docs = list(_adapter165([row]).iter_documents())
    assert docs == []


def test_c03_missing_timestamp_skipped():
    docs = list(_adapter165([_row165(snapshot_completed_at=None)]).iter_documents())
    assert docs == []


def test_c04_title_from_chem_area_type():
    p = _normalize_chem_accident(_row165(chem="암모니아", area="경기도", cscTy="폭발"))
    assert p["title"] == "암모니아 경기도 폭발"


def test_c05_title_partial_fields():
    p = _normalize_chem_accident(_row165(chem="암모니아", area="", cscTy=""))
    assert p["title"] == "암모니아"


def test_c06_title_fallback_datano():
    p = _normalize_chem_accident(_row165(chem="", area="", cscTy=""))
    assert p["title"] == "사고 1001"


def test_c07_summary_from_raw():
    p = _normalize_chem_accident(_row165(summary="누출 사고"))
    assert p["summary"] == "누출 사고"


def test_c08_public_url_has_datano():
    p = _normalize_chem_accident(_row165(datano="1001"))
    assert p["public_url"] == "/accident/chemical/1001"


def test_c09_public_url_encodes_special_chars():
    p = _normalize_chem_accident(_row165(datano="1001/special"))
    assert "%2F" in p["public_url"]
    assert "1001" in p["public_url"]


def test_c10_visibility_scopes_public():
    p = _normalize_chem_accident(_row165())
    assert p["visibility_scopes"] == ["PUBLIC"]


def test_c11_object_reindex_payload():
    rows = [_row165()]
    adapter = _adapter165(rows)
    p = adapter.object_reindex_payload("1001")
    assert p is not None
    assert p["canonical_id"] == "1001"


def test_c12_object_reindex_payload_missing():
    adapter = _adapter165([])
    assert adapter.object_reindex_payload("9999") is None


# ============================================================================
# R01-R06: public_safety_search router — type keys registered
# ============================================================================

def _make_router_client():
    from routers.public_safety_search import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def _mock_opensearch_unavailable():
    from services.shared_search.opensearch_client import OpenSearchUnavailable
    raise OpenSearchUnavailable("test")


def test_r01_chem_safety_type_key_accepted():
    client = _make_router_client()
    with patch(
        "routers.public_safety_search.get_client",
        side_effect=_mock_opensearch_unavailable,
    ):
        resp = client.get("/public/safety-search?q=암모니아&type=chem_safety")
    assert resp.status_code == 503


def test_r02_hazardous_type_key_accepted():
    client = _make_router_client()
    with patch(
        "routers.public_safety_search.get_client",
        side_effect=_mock_opensearch_unavailable,
    ):
        resp = client.get("/public/safety-search?q=아세톤&type=hazardous")
    assert resp.status_code == 503


def test_r03_chem_accident_type_key_accepted():
    client = _make_router_client()
    with patch(
        "routers.public_safety_search.get_client",
        side_effect=_mock_opensearch_unavailable,
    ):
        resp = client.get("/public/safety-search?q=폭발&type=chem_accident")
    assert resp.status_code == 503


def test_r04_unknown_type_returns_422():
    client = _make_router_client()
    resp = client.get("/public/safety-search?q=test&type=ext_unknown")
    assert resp.status_code == 422


def test_r05_sections_includes_chem_safety_section():
    from routers.public_safety_search import _SECTION_TYPES
    types = [ot for _, ot in _SECTION_TYPES]
    assert "CHEM_SAFETY" in types
    assert "HAZARDOUS_MATERIAL" in types
    assert "CHEM_ACCIDENT" in types


def test_r06_public_object_types_includes_new():
    from routers.public_safety_search import _PUBLIC_OBJECT_TYPES
    assert "CHEM_SAFETY" in _PUBLIC_OBJECT_TYPES
    assert "HAZARDOUS_MATERIAL" in _PUBLIC_OBJECT_TYPES
    assert "CHEM_ACCIDENT" in _PUBLIC_OBJECT_TYPES
